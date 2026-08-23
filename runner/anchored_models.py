"""Model outputs under the same anchoring restriction as every other population.

The cross-population table controls for task mix by restricting each
population to anchored `^...$` patterns: Re(gEx|DoS)Eval is unusually rich in
validators, which is the shape that backtracks, and most regular expressions
in the wild are short fragments with no opportunity to. Restricting to
anchored patterns is the closest matched comparison available.

An earlier version of this work put the models into that block at their
unrestricted rate, which compares an anchoring-restricted human population
against an unrestricted model one -- exactly the confound the restriction
exists to remove. This computes the models under the identical rule.

Three restrictions are reported, because they answer different questions and
they do not agree:

  outputs     the model's own pattern is anchored. This is the identical rule
              applied to every other population -- the restriction is on the
              pattern, not on where it came from -- so this is the row that
              belongs in the cross-population table.
  tasks       every model output on the tasks whose *reference* is anchored.
              Matches on the task rather than on the pattern, which is
              available here and is not available for the wild populations.
  both        anchored output on an anchored task. The strictest matching,
              and the one that flatters us least.

One sample per task per model, as in the human-baseline table: the reference
authors wrote one answer each, so any-of-three would not be a like comparison.

No API calls. Reads committed predictions. Writes results/anchored_models.json.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import warnings
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import normalize_pattern  # noqa: E402

# Screening a corpus means compiling tens of thousands of patterns people
# actually wrote, and CPython warns about constructs that are legal today and
# may not stay so -- `[[a-z]]`, `[a-z--0]`. The warning is about the pattern,
# not about us, and one per pattern buries the output. The patterns are
# screened as written either way.
warnings.filterwarnings("ignore", category=FutureWarning)

from regexbench.datasets import load_regexeval  # noqa: E402
from regexbench.safety import screen  # noqa: E402

WORKERS = 4
# The identical test the cross-population screen applies to every other
# population, deliberately kept as the same literal expression.
ANCHORED = re.compile(r"^\^.*\$$")


def screen_one(pattern):
    try:
        return str(screen(pattern, empirical=True).risk)
    except Exception as exc:
        return "ERROR:" + type(exc).__name__


def tally(patterns):
    if not patterns:
        return {"n": 0, "errors": 0, "exponential": 0, "polynomial": 0,
                "vulnerable": 0, "rate_pct": None, "ci95_pct": None}
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        verdicts = list(pool.map(screen_one, patterns, chunksize=16))
    counts = Counter(verdicts)
    errors = sum(v for k, v in counts.items() if k.startswith("ERROR"))
    n = len(patterns) - errors
    exp = counts.get("Risk.EXPONENTIAL", 0)
    poly = counts.get("Risk.POLYNOMIAL", 0)
    p = (exp + poly) / n
    return {"n": n, "errors": errors, "exponential": exp, "polynomial": poly,
            "vulnerable": exp + poly, "rate_pct": round(100 * p, 1),
            "ci95_pct": round(100 * 1.96 * math.sqrt(p * (1 - p) / n), 1)}


def first_sample_per_task(model: str, run: str) -> dict[str, str]:
    """One pattern per task, in sample order -- the human-baseline convention."""
    out: dict[str, str] = {}
    path = config.PREDICTIONS_DIR / run / f"{model}.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    for r in sorted(rows, key=lambda r: (r["task_name"], r.get("sample", 0))):
        if r["task_name"].startswith("control/") or r["status"] != "ok" or not r.get("pattern"):
            continue
        out.setdefault(r["task_name"], normalize_pattern(r["pattern"])[0])
    return out


def cluster_ci(per_task: dict, iterations: int = 10000, seed: int = 20260812):
    """95%% interval for the pooled rate, resampling tasks rather than patterns.

    Each draw takes a task and, with it, every model's answer to that task, so
    the correlation between models on a shared item is carried into the
    interval instead of being assumed away.
    """
    rng = random.Random(seed)
    tasks = sorted({t for m in per_task for t in per_task[m]})
    by_task = {t: [per_task[m][t] for m in per_task if t in per_task[m]] for t in tasks}
    n = len(tasks)
    draws = []
    for _ in range(iterations):
        hits = total = 0
        for _ in range(n):
            outcomes = by_task[tasks[rng.randrange(n)]]
            hits += sum(outcomes)
            total += len(outcomes)
        draws.append(100 * hits / total if total else 0.0)
    draws.sort()
    lo, hi = draws[int(0.025 * iterations)], draws[int(0.975 * iterations)]
    return [round(lo, 1), round(hi, 1)]


def two_proportion_z(v1, n1, v2, n2):
    """Is the difference between two independent rates distinguishable?

    The populations being compared here really are independent -- different
    corpora, no shared items -- so an unpaired test is the right one. Where
    the same tasks are answered by several systems the comparison is paired
    and lives in runner/paired_stats.py instead.
    """
    p1, p2 = v1 / n1, v2 / n2
    pooled = (v1 + v2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    # Two-sided normal tail, via the error function.
    return z, math.erfc(abs(z) / math.sqrt(2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    args = ap.parse_args()

    by_name = {t.name: t for t in load_regexeval(str(config.require_dataset()))}
    models = sorted(p.stem for p in (config.PREDICTIONS_DIR / args.run).glob("*.jsonl"))
    samples = {m: first_sample_per_task(m, args.run) for m in models}

    scored_tasks = set().union(*(set(v) for v in samples.values()))
    anchored_tasks = {t for t in scored_tasks if ANCHORED.match(by_name[t].reference)}

    results = {"run": args.run, "models": {}, "pooled": {},
               "tasks_scored": len(scored_tasks),
               "tasks_with_anchored_reference": len(anchored_tasks)}

    subsets = {
        "unrestricted": lambda t, p: True,
        "outputs": lambda t, p: bool(ANCHORED.match(p)),
        "tasks": lambda t, p: t in anchored_tasks,
        "both": lambda t, p: t in anchored_tasks and bool(ANCHORED.match(p)),
    }

    pooled = {k: [] for k in subsets}
    for m in models:
        results["models"][m] = {}
        for key, keep in subsets.items():
            pats = [p for t, p in sorted(samples[m].items()) if keep(t, p)]
            pooled[key].extend(pats)
            results["models"][m][key] = tally(pats)
        r = results["models"][m]
        print(f"{m:26s} " + "  ".join(
            f"{k} {r[k]['rate_pct']:5.1f}% (n={r[k]['n']:4d})" for k in subsets), flush=True)

    # Per-(model, task) outcomes for the anchored-output row. The pooled row is
    # eleven models answering the same tasks, so a binomial interval over the
    # pooled patterns treats shared task difficulty as independent draws and
    # comes out too narrow -- the error this paper corrects elsewhere. Saved so
    # the interval can be resampled over tasks instead.
    per_task: dict[str, dict[str, bool]] = {}
    for m in models:
        anchored = {t: p for t, p in sorted(samples[m].items()) if ANCHORED.match(p)}
        with ProcessPoolExecutor(max_workers=WORKERS) as pool:
            verdicts = list(pool.map(screen_one, list(anchored.values()), chunksize=16))
        per_task[m] = {t: v != "Risk.SAFE"
                       for t, v in zip(anchored, verdicts) if not v.startswith("ERROR")}
    results["per_task_outputs"] = per_task
    results["pooled"]["outputs_cluster_ci95_pct"] = cluster_ci(per_task)

    for key in subsets:
        results["pooled"][key] = tally(pooled[key])

    # The reference set under the identical restrictions, so the comparison in
    # the paper is between two numbers computed the same way.
    gold = {t: by_name[t].reference for t in sorted(scored_tasks)}
    results["reference"] = {
        "unrestricted": tally(list(gold.values())),
        "outputs": tally([p for p in gold.values() if ANCHORED.match(p)]),
        "tasks": tally([gold[t] for t in gold if t in anchored_tasks]),
        "both": tally([gold[t] for t in gold if t in anchored_tasks and ANCHORED.match(gold[t])]),
    }

    print(f"\n{'':26s} " + "  ".join(f"{k:>18s}" for k in subsets))
    for label, block in (("models pooled", results["pooled"]),
                         ("reference set", results["reference"])):
        print(f"{label:26s} " + "  ".join(
            f"{block[k]['rate_pct']:6.1f}% (n={block[k]['n']:5d})" for k in subsets))

    cc_path = config.RESULTS_DIR / "cross_corpus_redos.json"
    if cc_path.exists():
        cc = json.loads(cc_path.read_text())
        prod = cc.get("anchored", {}).get("Production code, anchored")
        mine = results["pooled"]["outputs"]
        if prod:
            z, p = two_proportion_z(mine["vulnerable"], mine["n"],
                                    prod["vulnerable"], prod["n"])
            results["vs_production_anchored"] = {
                "models_pct": mine["rate_pct"], "production_pct": prod["rate_pct"],
                "z": round(z, 2), "p_two_sided": round(p, 3),
            }
            print(f"\nanchored models {mine['rate_pct']}% vs anchored production "
                  f"{prod['rate_pct']}%: z = {z:.2f}, p = {p:.3f}")

    out = config.RESULTS_DIR / "anchored_models.json"
    out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    sys.exit(main())

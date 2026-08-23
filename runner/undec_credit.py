"""How much of `usable` rests on the engine failing to decide.

`dfa-eq` counts an UNDECIDABLE verdict as a failure. `usable` does the
opposite: its third conjunct excludes only a *proven* DIFFERENT, so a
comparison the engine cannot answer is scored as a pass. The two conventions
are each defensible on their own -- one is a lower bound, the other isolates
the model from the engine's reach -- but together they create an incentive.
Equivalence is undecidable exactly when a pattern uses backreferences, so a
model that reaches for one is scored *more* usable for having put its answer
beyond checking.

Between 78 and 133 of each model's scored tasks land there, so the question is not
whether the asymmetry exists but whether it moves anything. The obvious test
-- correlate a model's undecidable count against its `usable@3` -- answers
no, and answers it misleadingly: undecidable credit and equivalence skill
push the composite in opposite directions and the correlation nets them out.

So this decomposes instead of correlating. For each model it recomputes
`usable@3` under the stricter rule that the verdict must be *proven*
EQUIVALENT, and reports the difference as what the undecidable convention is
worth.

No API calls. Reads committed predictions. Writes results/undec_credit.json.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
import warnings
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

from regexbench import evaluate  # noqa: E402
from regexbench.datasets import load_regexeval  # noqa: E402

WORKERS = 4


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def spearman(xs, ys):
    def rank(vs):
        order = sorted(range(len(vs)), key=lambda i: vs[i])
        out = [0] * len(vs)
        for position, i in enumerate(order):
            out[i] = position + 1
        return out
    return pearson(rank(xs), rank(ys))


def samples_by_task(model: str, run: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    path = config.PREDICTIONS_DIR / run / f"{model}.jsonl"
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["task_name"].startswith("control/") or r["status"] != "ok" or not r.get("pattern"):
            continue
        out.setdefault(r["task_name"], []).append(normalize_pattern(r["pattern"])[0])
    return out


# Scoring is CPU-bound and the equivalence engine dominates it, so tasks are
# scored in a pool. The dataset is loaded once per worker rather than passed
# per task: the Task objects carry their example strings and pickling 450 of
# them for every chunk costs more than reading the corpus once.
_TASKS: dict = {}


def _init(dataset_path: str):
    global _TASKS
    _TASKS = {t.name: t for t in load_regexeval(dataset_path)}


def _score_task(job):
    """Was this task usable, did anything prove equivalence, and on what verdict?

    The verdict breakdown matters because the harness counts UNSUPPORTED and
    UNDECIDABLE together under one "undecided" column, and they are different
    claims: UNDECIDABLE is a theorem about backreferences, UNSUPPORTED is this
    engine declining a construct. Both receive the same free credit from
    `usable`, so both belong in the accounting, but conflating them would let
    an engine limitation be reported as a property of the language.
    """
    task_name, patterns = job
    task = _TASKS[task_name]
    usable = proven = False
    supported_by = None
    for pattern in patterns:
        try:
            rep = evaluate(pattern, task)
        except Exception:
            continue
        if rep.correctness.accuracy != 1.0 or rep.safety.risk.name != "SAFE":
            continue
        # `EquivalenceResult.__bool__` is True only for EQUIVALENT, so an
        # `is not None` test is required here -- a truthiness test silently
        # reads DIFFERENT as "no verdict" and inflates everything below.
        verdict = rep.equivalence.verdict.name if rep.equivalence is not None else "NONE"
        if verdict != "DIFFERENT":
            usable = True
            if verdict != "EQUIVALENT" and supported_by is None:
                supported_by = verdict
        if verdict == "EQUIVALENT":
            proven = True
    return usable, proven, supported_by


def analyse(model: str, run: str, k: int) -> dict:
    """usable@3 as reported, and under a proven-equivalence rule.

    Restricted to tasks with all k samples, which is the denominator the main
    table uses. Scoring the short-sample tasks here instead would rebuild, in
    a table written to criticise the composite, the exact denominator defect
    the appendix documents.
    """
    jobs = [(t, ps) for t, ps in sorted(samples_by_task(model, run).items()) if len(ps) >= k]
    with ProcessPoolExecutor(max_workers=WORKERS, initializer=_init,
                             initargs=(str(config.require_dataset()),)) as pool:
        scored = list(pool.map(_score_task, jobs, chunksize=8))
    counts = {"tasks": len(scored),
              "usable": sum(1 for u, _, _ in scored if u),
              "proven": sum(1 for _, pr, _ in scored if pr),
              "undec_supported": sum(1 for u, pr, _ in scored if u and not pr)}
    counts["by_verdict"] = dict(Counter(
        v for u, pr, v in scored if u and not pr and v is not None).most_common())
    n = counts["tasks"]
    counts["usable_pct"] = round(100 * counts["usable"] / n, 1)
    counts["proven_pct"] = round(100 * counts["proven"] / n, 1)
    counts["undec_supported_share_pct"] = (
        round(100 * counts["undec_supported"] / counts["usable"], 1) if counts["usable"] else None
    )
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    ap.add_argument("--k", type=int, default=3,
                    help="tasks with fewer than k samples are excluded, as in the main table")
    args = ap.parse_args()

    models = sorted(p.stem for p in (config.PREDICTIONS_DIR / args.run).glob("*.jsonl"))

    undecided = {}
    for m in models:
        path = config.RESULTS_DIR / args.run / f"{m}.json"
        if path.exists():
            undecided[m] = json.loads(path.read_text())["metrics"]["undecided"]

    out = {"run": args.run, "models": {}}
    print(f"{'model':26s} {'undec':>6s} {'usable@3':>9s} {'proven-EQ':>10s} "
          f"{'undec-supported':>16s}")
    for m in models:
        r = analyse(m, args.run, args.k)
        r["undecided"] = undecided.get(m)
        out["models"][m] = r
        print(f"{m:26s} {str(r['undecided']):>6s} {r['usable_pct']:8.1f}% "
              f"{r['proven_pct']:9.1f}% {r['undec_supported']:6d} "
              f"({r['undec_supported_share_pct']:4.1f}%)", flush=True)

    usable = sum(r["usable"] for r in out["models"].values())
    supported = sum(r["undec_supported"] for r in out["models"].values())
    out["pooled"] = {"usable": usable, "undec_supported": supported,
                     "undec_supported_share_pct": round(100 * supported / usable, 1)}

    have = [m for m in models if out["models"][m]["undecided"] is not None]
    if len(have) > 2:
        u = [out["models"][m]["undecided"] for m in have]
        pairs = {
            "undec_vs_undec_supported_share":
                [out["models"][m]["undec_supported_share_pct"] for m in have],
            "undec_vs_usable": [out["models"][m]["usable_pct"] for m in have],
            "undec_vs_proven": [out["models"][m]["proven_pct"] for m in have],
            "undec_vs_gap": [out["models"][m]["usable_pct"] - out["models"][m]["proven_pct"]
                             for m in have],
        }
        out["correlations"] = {k: {"pearson": round(pearson(u, v), 3),
                                   "spearman": round(spearman(u, v), 3)}
                               for k, v in pairs.items()}

    # Whether removing the credit reorders the field, which is the question
    # a reader of the main table actually has.
    # Ties broken by name, so the recorded order is a property of the data and
    # not of dict insertion order. Several models tie to the tenth of a point
    # on both columns, and a rank shift read off an unstable order is not a
    # finding.
    out["order_usable"] = sorted(models, key=lambda m: (-out["models"][m]["usable_pct"], m))
    out["order_proven"] = sorted(models, key=lambda m: (-out["models"][m]["proven_pct"], m))
    out["rank_shift"] = {
        m: out["order_proven"].index(m) - out["order_usable"].index(m) for m in models
    }

    print(f"\npooled: {supported} of {usable} usable task-credits "
          f"({out['pooled']['undec_supported_share_pct']}%) rest on a verdict the engine "
          f"could not decide")
    for k, v in out.get("correlations", {}).items():
        print(f"  {k:36s} pearson {v['pearson']:+.2f}  spearman {v['spearman']:+.2f}")
    moved = {m: d for m, d in out["rank_shift"].items() if d}
    if moved:
        print("  rank shift on removing the credit: " +
              ", ".join(f"{m} {d:+d}" for m, d in sorted(moved.items(), key=lambda x: -abs(x[1]))))

    path = config.RESULTS_DIR / args.run / "undec_credit.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    sys.exit(main())

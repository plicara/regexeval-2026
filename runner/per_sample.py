"""Per-sample and per-task outcomes, which every downstream analysis reads.

These counts carry the paper's reference-independent headline: the share of
functionally correct *generations* that are ReDoS-vulnerable is computed from
`correct_secure` against `pass`, per sample rather than per task. They also
feed the @1-against-@3 table and the paired bootstrap.

They were previously committed with nothing in the repository able to rebuild
them, which put the headline number outside the reproduction path the rest of
this work insists on. This closes that: `make persample` regenerates all three
directories from the committed predictions, and `--check` fails if the result
differs from what is committed.

Three files per model, because three different questions get asked of them:

  per_sample/     counts over the k samples of a task -- how many passed, how
                  many were usable, how many tripped the safety screen. The
                  @k estimator needs counts, not booleans.
  per_task/       the any-of-k booleans, which is what a paired comparison
                  between models resamples.
  correct_secure/ how many samples were correct *and* safe. Kept separate
                  because it is a conjunction over two axes and cannot be
                  recovered from the marginals: a task can have one correct
                  sample and one vulnerable sample without any single sample
                  being both.

No API calls. Reads only predictions/.
"""
from __future__ import annotations

import argparse
import json
import sys
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
_TASKS: dict = {}


def _init(dataset_path: str):
    global _TASKS
    _TASKS = {t.name: t for t in load_regexeval(dataset_path)}


def _score(job):
    """One task's samples, scored. Returns the three records for that task."""
    task_name, patterns = job
    task = _TASKS[task_name]
    n = correct = usable = vulnerable = correct_secure = 0
    for pattern in patterns:
        try:
            rep = evaluate(pattern, task)
        except Exception:
            # A sample the scorer cannot process is dropped from the
            # denominator rather than counted as a failure: it is our problem,
            # not the model's, and scoring it zero would be a silent penalty.
            continue
        n += 1
        is_correct = rep.correctness.accuracy == 1.0
        is_vulnerable = rep.safety.risk.name != "SAFE"
        correct += is_correct
        usable += bool(rep.usable)
        vulnerable += is_vulnerable
        correct_secure += is_correct and not is_vulnerable
    return task_name, n, correct, usable, vulnerable, correct_secure


def samples_of(model: str, run: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    path = config.PREDICTIONS_DIR / run / f"{model}.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    for r in sorted(rows, key=lambda r: (r["task_name"], r.get("sample", 0))):
        if r["task_name"].startswith("control/") or r["status"] != "ok" or not r.get("pattern"):
            continue
        out.setdefault(r["task_name"], []).append(normalize_pattern(r["pattern"])[0])
    return out


def build(model: str, run: str, workers: int = WORKERS) -> dict[str, dict]:
    jobs = sorted(samples_of(model, run).items())
    with ProcessPoolExecutor(max_workers=workers, initializer=_init,
                             initargs=(str(config.require_dataset()),)) as pool:
        scored = list(pool.map(_score, jobs, chunksize=8))
    per_sample, per_task, correct_secure = {}, {}, {}
    for name, n, correct, usable, vulnerable, cs in scored:
        per_sample[name] = {"n": n, "pass": correct, "usable": usable,
                            "vulnerable": vulnerable}
        per_task[name] = {"pass": correct > 0, "samples": n,
                          "usable": usable > 0, "vulnerable": vulnerable > 0}
        correct_secure[name] = {"correct_secure": cs, "n": n}
    return {"per_sample": per_sample, "per_task": per_task,
            "correct_secure": correct_secure}


def _drifted(model: str, run: str, built: dict[str, dict]) -> bool:
    for kind, data in built.items():
        path = config.RESULTS_DIR / run / kind / f"{model}.json"
        if not path.exists() or json.loads(path.read_text()) != data:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    ap.add_argument("--models", default=None, help="comma-separated labels")
    ap.add_argument("--check", action="store_true",
                    help="fail if the rebuilt files differ from what is committed")
    args = ap.parse_args()

    labels = ([m.strip() for m in args.models.split(",")] if args.models
              else sorted(p.stem for p in (config.PREDICTIONS_DIR / args.run).glob("*.jsonl")))

    # A run with no committed per-sample counts has nothing to drift from --
    # the reduced run CI uses is one. Say so and pass, rather than reporting
    # every model as missing and failing a check that was never configured.
    if args.check and not (config.RESULTS_DIR / args.run / "per_sample").exists():
        print(f"no committed per-sample counts for run '{args.run}'; nothing to check")
        return

    drift = []
    for model in labels:
        built = build(model, args.run)
        if args.check and _drifted(model, args.run, built):
            # The safety screen times its probes (regexbench, 0.5 s), so a
            # borderline pattern can flip on a loaded machine. Re-score the
            # model alone and in one process before calling it drift; a real
            # difference survives the quiet run, a load artefact does not.
            built = build(model, args.run, workers=1)
        for kind, data in built.items():
            directory = config.RESULTS_DIR / args.run / kind
            path = directory / f"{model}.json"
            if kind == "per_task":
                blob = json.dumps(data, indent=0, sort_keys=True)
            else:
                blob = json.dumps(data, sort_keys=True)
            if args.check:
                if not path.exists():
                    drift.append(f"{kind}/{model} (missing)")
                elif json.loads(path.read_text()) != data:
                    drift.append(f"{kind}/{model}")
            else:
                directory.mkdir(parents=True, exist_ok=True)
                path.write_text(blob)
        ps = built["per_sample"]
        print(f"{model:26s} {len(ps)} tasks, {sum(v['n'] for v in ps.values())} samples, "
              f"{sum(v['pass'] for v in ps.values())} correct, "
              f"{sum(built['correct_secure'][t]['correct_secure'] for t in ps)} correct-and-secure",
              flush=True)

    if args.check:
        if drift:
            raise SystemExit("FAIL: rebuilt files differ from committed: " + ", ".join(drift))
        print("\nOK: rebuilt per-sample counts match the committed files exactly.")


if __name__ == "__main__":
    sys.exit(main())

"""Is the correct subset safer because it is easier? A within-corpus test.

Section 4.5 offers a difficulty ceiling as one explanation for the low
correct-and-secure penalty: if the patterns models get right are the easy
ones, they may simply have less structural room to backtrack, and the
reference-independent headline would be a selection effect rather than a fact
about generated regex.

The cross-corpus version of this test compares Re(gEx|DoS)Eval against
StructuredRegex, and cannot cleanly separate "the correct subset is biased
toward simple tasks" from "the two corpora were authored differently" --
which is awkward, because section 4.6 argues at length that they were.

This tests it inside one corpus, where authorship is held fixed. Tasks are
stratified by how many of the eleven models solved them, which is a direct
measure of how easy a task turned out to be, and vulnerability is measured
within each stratum. If the selection story holds, vulnerability among correct
patterns should fall as tasks get easier.

Reads only committed per-sample counts. No API calls, no screening: seconds.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import config  # noqa: E402


def load(run: str):
    per_sample, correct_secure = {}, {}
    for path in sorted((config.RESULTS_DIR / run / "per_sample").glob("*.json")):
        per_sample[path.stem] = json.loads(path.read_text())
    for path in sorted((config.RESULTS_DIR / run / "correct_secure").glob("*.json")):
        correct_secure[path.stem] = json.loads(path.read_text())
    return per_sample, correct_secure


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    args = ap.parse_args()
    per_sample, correct_secure = load(args.run)
    models = sorted(per_sample)

    tasks = sorted({t for m in models for t in per_sample[m]})
    # How many models solved this task at all: the corpus's own difficulty scale.
    solved_by = {t: sum(1 for m in models if per_sample[m].get(t, {}).get("pass", 0) > 0)
                 for t in tasks}

    strata: dict[int, dict[str, int]] = {}
    for t in tasks:
        band = solved_by[t]
        cell = strata.setdefault(band, {"tasks": 0, "correct": 0, "correct_vulnerable": 0})
        cell["tasks"] += 1
        for m in models:
            correct = per_sample[m].get(t, {}).get("pass", 0)
            secure = correct_secure[m].get(t, {}).get("correct_secure", 0)
            cell["correct"] += correct
            cell["correct_vulnerable"] += correct - secure

    out = {"run": args.run, "models": len(models), "strata": {}}
    print(f"{'solved by':>10s} {'tasks':>6s} {'correct':>8s} {'vuln|correct':>13s}")
    for band in sorted(strata):
        cell = strata[band]
        rate = (100 * cell["correct_vulnerable"] / cell["correct"]) if cell["correct"] else None
        cell["vuln_given_correct_pct"] = round(rate, 1) if rate is not None else None
        out["strata"][band] = cell
        shown = "---" if rate is None else f"{rate:.1f}%"
        print(f"{band:>10d} {cell['tasks']:6d} {cell['correct']:8d} {shown:>13s}")

    # Easy half against hard half, where "easy" is a task most models solved.
    easy = {"correct": 0, "vuln": 0}
    hard = {"correct": 0, "vuln": 0}
    for band, cell in strata.items():
        target = easy if band >= 6 else hard
        target["correct"] += cell["correct"]
        target["vuln"] += cell["correct_vulnerable"]
    for name, cell in (("easy (6+ models solved)", easy), ("hard (1-5 solved)", hard)):
        cell["pct"] = round(100 * cell["vuln"] / cell["correct"], 1) if cell["correct"] else None
        print(f"{name:26s} vuln|correct {cell['pct']}%  (n={cell['correct']})")
    out["easy"], out["hard"] = easy, hard
    if easy["pct"] is not None and hard["pct"] is not None:
        out["easy_minus_hard_pp"] = round(easy["pct"] - hard["pct"], 1)
        # Resampled over tasks, not over patterns: the eleven answers to one
        # task are not independent, and the hard stratum is thin enough that a
        # per-pattern interval would be badly overconfident.
        rng = random.Random(20260812)
        draws = []
        for _ in range(10000):
            cells = {"easy": [0, 0], "hard": [0, 0]}
            for _ in range(len(tasks)):
                t = tasks[rng.randrange(len(tasks))]
                key = "easy" if solved_by[t] >= 6 else "hard"
                for m in models:
                    correct = per_sample[m].get(t, {}).get("pass", 0)
                    secure = correct_secure[m].get(t, {}).get("correct_secure", 0)
                    cells[key][0] += correct
                    cells[key][1] += correct - secure
            if cells["easy"][0] and cells["hard"][0]:
                draws.append(100 * cells["easy"][1] / cells["easy"][0]
                             - 100 * cells["hard"][1] / cells["hard"][0])
        draws.sort()
        lo, hi = draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws))]
        out["easy_minus_hard_ci95"] = [round(lo, 1), round(hi, 1)]
        print(f"\neasy minus hard: {out['easy_minus_hard_pp']:+.1f} pp "
              f"[{lo:+.1f}, {hi:+.1f}] (task bootstrap)")
        print("The difficulty-ceiling story predicts this is clearly negative.")

    path = config.RESULTS_DIR / "difficulty_selection.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    sys.exit(main())

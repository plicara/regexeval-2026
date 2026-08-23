"""Score committed predictions with regexbench.

Reads only files in predictions/ -- no network, no API key, no cost. That
is deliberate: anyone can clone this repo and recompute every published
number offline, and CI does exactly that on every push.

One headline score per model. Patterns are normalized before scoring (see
"The wrapper rule" in APPENDIX.md); the unnormalized score is also
recorded in the per-model JSON so the choice is auditable, but it is not
what the leaderboard reports.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
from openrouter_client import normalize_pattern  # noqa: E402

from regexbench import run  # noqa: E402
from regexbench.datasets import load_regexeval  # noqa: E402

# Scoring runs DFA equivalence and an empirical ReDoS pass per pattern, both
# of which are CPU-bound and can block on a pathological pattern until the
# match timeout. Parallel across tasks keeps a full sweep tractable.
# One scoring process per core, each single-threaded, beats many processes
# with several worker threads each: the work is GIL-bound, so extra threads
# buy context switching rather than throughput. Scoring all 11 models at
# once with 3 workers apiece drove load to 20 on a 4-core box.
WORKERS = int(os.environ.get("REGEXLB_WORKERS", max(1, (os.cpu_count() or 4) - 1)))

CONTROL_EXPECTATIONS = {
    "control/good": lambda m: m["pass@1"] == 1.0 and m["usable@1"] == 1.0,
    "control/bad": lambda m: m["pass@1"] == 0.0 and m["usable@1"] == 0.0,
    "control/vulnerable": lambda m: m["vulnerable@1"] == 1.0,
}


def metrics_of(rep, k: int = 1) -> dict:
    """Headline three first; the rest are kept for the appendix."""
    return {
        f"usable@{k}": rep.usable_at(k),
        f"pass@{k}": rep.pass_at(k),
        f"vulnerable@{k}": rep.vulnerable_at(k),
        # appendix metrics -- not shown on the leaderboard front page
        f"dfa-eq@{k}": rep.dfa_eq_at(k),
        f"dfa-eq@{k} (decided)": rep.dfa_eq_decided_at(k),
        f"exact@{k}": rep.exact_at(k),
        "undecided": rep.undecided,
    }


def rebuild_summary(run_name: str) -> list[dict]:
    """Reassemble summary.json from the per-model result files.

    Scoring is CPU-bound and one process per model is far faster than one
    process for all of them, so models can be scored separately and merged
    here. The summary is derived from the per-model files either way, so a
    merged run and a single run produce the same summary.
    """
    result_dir = config.RESULTS_DIR / run_name
    # Selected by content rather than by name. This directory also holds
    # analysis outputs -- paired intervals, McNemar, the adjudicated
    # disagreement sample -- and an exclusion list by filename silently breaks
    # the next time one is added, which is exactly how it broke.
    entries = []
    for f in sorted(result_dir.glob("*.json")):
        if f.name == "summary.json":
            continue
        blob = json.loads(f.read_text())
        if isinstance(blob, dict) and "metrics" in blob and "model" in blob:
            entries.append(blob)
    entries.sort(key=lambda e: (-(headline(e, "usable")
                                 if headline(e, "usable") is not None else -1), e["model"]))
    (result_dir / "summary.json").write_text(json.dumps(entries, indent=2, sort_keys=True))
    return entries


def check_summary_matches_models(run_name: str) -> list[str]:
    """Committed summary.json against the committed per-model files.

    summary.json is derived from those files and must agree with them field
    for field. It has silently stopped agreeing twice, both times through a
    merge rather than a run: `regexbench_commit` was repointed after an
    upstream history rewrite, and two later branches carried the pre-rewrite
    value back into the summary while all eleven per-model files kept the new
    one. Nothing caught it, because --check compares `metrics` and the drift
    was in provenance.

    This compares what is on disk before anything is rescored, so it reports
    the state of the repository rather than the state of this process.
    """
    result_dir = config.RESULTS_DIR / run_name
    summary_path = result_dir / "summary.json"
    if not summary_path.exists():
        return []
    summary = {e["model"]: e for e in json.loads(summary_path.read_text())}
    problems, seen = [], set()
    # Selected by content, not by name: this directory also holds analysis
    # outputs, and an exclusion list by filename breaks the next time one is
    # added -- which is how it broke before.
    for f in sorted(result_dir.glob("*.json")):
        if f.name == "summary.json":
            continue
        blob = json.loads(f.read_text())
        if not (isinstance(blob, dict) and "metrics" in blob and "model" in blob):
            continue
        seen.add(blob["model"])
        entry = summary.get(blob["model"])
        if entry is None:
            problems.append(f"{blob['model']}: in {f.name}, absent from summary.json")
            continue
        for key in sorted(set(blob) | set(entry)):
            if blob.get(key) != entry.get(key):
                problems.append(
                    f"{blob['model']}.{key}: {f.name} says {blob.get(key)!r}, "
                    f"summary.json says {entry.get(key)!r}"
                )
    for m in sorted(set(summary) - seen):
        problems.append(f"{m}: in summary.json, no per-model file")
    return problems


def sampling_of(rows: list[dict], run_name: str) -> dict:
    """What these responses were actually produced under.

    Read back off the rows, never from a constant in this repo. A constant
    describes whatever it says today, not what was sent: this header used to
    copy config.MAX_TOKENS / config.TEMPERATURE, so every file in results/
    reported `max_tokens: 200, temperature: 0.0` -- including the published
    sweep, which was collected at 400 with temperature not sent at all. A
    reanalysis that reads the header instead of predictions/ then gets the
    run config wrong.

    runner/sweep.py stamps the settings of each request onto its row as a
    `config` fingerprint, and refuses to resume a file holding rows from a
    different one, so one file means one configuration. The two runs
    collected before the fingerprint existed are named in
    config.LEGACY_SAMPLING; anything else without one is an error rather
    than a guess.
    """
    seen = {}
    for r in rows:
        raw = r.get("config")
        # sweep.py writes a JSON object; sweep_structuredregex.py writes a
        # hash of one, which cannot be read back and is not scored here.
        if not (isinstance(raw, str) and raw.startswith("{")):
            continue
        fp = json.loads(raw)
        got = {"max_tokens": fp.get("max_tokens"), "temperature": fp.get("temperature")}
        seen[json.dumps(got, sort_keys=True)] = got
    if len(seen) > 1:
        raise SystemExit(
            f"{run_name}: predictions hold rows from {len(seen)} configurations "
            f"({', '.join(sorted(seen))}). One result file cannot describe both."
        )
    if seen:
        return next(iter(seen.values()))
    legacy = config.LEGACY_SAMPLING.get(run_name)
    if legacy is None:
        raise SystemExit(
            f"{run_name}: rows carry no config fingerprint, so what was sent "
            f"cannot be recovered from them, and there is no entry in "
            f"config.LEGACY_SAMPLING. Recollect with runner/sweep.py, which "
            f"records it, rather than publishing an unverified value."
        )
    return dict(legacy)


def headline(e, metric):
    m = e.get("metrics") or {}
    return next((v for kk, v in m.items() if kk.startswith(metric + "@")), None)


def score_run(run_name: str, only: set[str] | None = None, write: bool = True) -> list[dict]:
    dataset = config.require_dataset()
    pred_dir = config.PREDICTIONS_DIR / run_name
    result_dir = config.RESULTS_DIR / run_name
    if not pred_dir.is_dir():
        raise SystemExit(f"No predictions at {pred_dir}")
    result_dir.mkdir(parents=True, exist_ok=True)

    by_name = {t.name: t for t in load_regexeval(str(dataset))}
    summary = []

    for pred_file in sorted(pred_dir.glob("*.jsonl")):
        label = pred_file.stem
        if only and label not in only:
            continue
        rows = [json.loads(x) for x in pred_file.read_text().splitlines() if x.strip()]
        sampling = sampling_of(rows, run_name)
        controls = [r for r in rows if r["task_name"].startswith("control/")]
        task_rows = [r for r in rows if not r["task_name"].startswith("control/")]

        # The runtime environment that produced the published numbers is
        # provenance, not a side effect of whatever machine happens to be
        # rescoring today. Carry the recorded value forward instead of letting
        # a rescore on a different interpreter silently rewrite it.
        prior_path = result_dir / f"{label}.json"
        prior = json.loads(prior_path.read_text()) if prior_path.exists() else None

        # Controls ride the identical scoring path. A scorer returning zeros
        # looks exactly like a model that failed; these tell them apart.
        control_report = {}
        controls_ok = True
        for cr in controls:
            base = by_name[cr["base_task"]]
            rep = run([base], {base.name: cr["pattern"]}, name=cr["task_name"])
            got = {
                "pattern": cr["pattern"],
                "base_task": base.name,
                "pass@1": rep.pass_at(1),
                "usable@1": rep.usable_at(1),
                "vulnerable@1": rep.vulnerable_at(1),
            }
            got["as_expected"] = CONTROL_EXPECTATIONS[cr["task_name"]](got)
            controls_ok &= got["as_expected"]
            control_report[cr["task_name"]] = got

        answered = [r for r in task_rows if r["status"] == "ok" and r["pattern"]]
        failed = [r for r in task_rows if not (r["status"] == "ok" and r["pattern"])]

        # Group the k samples per task into a list, in sample order. A task
        # whose samples partly failed is scored on the ones that came back --
        # the failures are still counted in response_failures.
        as_sent, normalized, wrapped = {}, {}, {}
        for r in sorted(answered, key=lambda r: (r["task_name"], r.get("sample", 0))):
            name = r["task_name"]
            as_sent.setdefault(name, []).append(r["pattern"])
            pat, notes = normalize_pattern(r["pattern"])
            normalized.setdefault(name, []).append(pat)
            if notes:
                wrapped.setdefault(name, []).append({"as_sent": r["pattern"], "scored": pat})

        k_actual = max((len(v) for v in normalized.values()), default=0)

        # Tasks that came back with fewer than k samples are dropped from the
        # @k estimate rather than scored on what arrived.
        #
        # This is not a stylistic choice. `regexbench.harness.pass_at_k`
        # early-returns 1.0 when `n - c < k`, a guard that is sound only for
        # n >= k: it means "so many samples succeeded that any k of them must
        # include one". When a task lost samples to a refusal or a spending
        # limit, `n - c <= n < k` holds unconditionally and the task scores a
        # full 1.0 on every metric whether or not anything succeeded --
        # `pass_at_k(1, 0, 3) == 1.0`. Left in, that inflated exactly the two
        # models that lost the most samples, which were the two at the top of
        # the table.
        #
        # The unbiased estimator of Chen et al. is defined for n >= k, so
        # excluding is the standard treatment and is what the @1-vs-@3 table
        # has always done. Excluded counts are reported per model so the
        # denominator is never silently different from 450.
        short = sorted(n for n, v in normalized.items() if len(v) < k_actual)
        for n in short:
            normalized.pop(n)
            as_sent.pop(n, None)
            wrapped.pop(n, None)

        tasks = [by_name[n] for n in normalized]

        rep = run(tasks, normalized, name=label, workers=WORKERS) if tasks else None
        # Only worth scoring the unnormalized set when normalization actually
        # changed something. When no response was wrapped the two are the same
        # inputs, and scoring them twice doubles a CPU-bound run for nothing.
        rep_as_sent = (
            run(tasks, as_sent, name=f"{label} (as sent)", workers=WORKERS)
            if tasks and wrapped else None
        )

        cost = sum(r.get("cost_usd") or 0.0 for r in task_rows)
        entry = {
            "model": label,
            "model_requested": task_rows[0]["model_requested"] if task_rows else None,
            "provider_requested": task_rows[0]["provider_requested"] if task_rows else None,
            "providers_resolved": sorted(
                {r["provider_resolved"] for r in answered if r["provider_resolved"]}
            ),
            "regexbench_version": config.REGEXBENCH_VERSION,
            "regexbench_commit": config.REGEXBENCH_COMMIT,
            "python_version": (
                (prior or {}).get("python_version") or sys.version.split()[0]
            ),
            "dataset": "Re(gEx|DoS)Eval",
            "k": k_actual,
            "temperature": sampling["temperature"],
            "max_tokens": sampling["max_tokens"],
            "tasks_attempted": len(task_rows),
            "tasks_answered": len(answered),
            "tasks_scored": len(tasks),
            "tasks_short_of_k": len(short),
            "tasks_short_of_k_detail": short,
            "response_failures": len(failed),
            "failure_detail": [
                {"task": r["task_name"], "status": r["status"], "error": (r.get("error") or "")[:300]}
                for r in failed
            ],
            "wrapped_responses": sum(len(v) for v in wrapped.values()),
            "wrapped_detail": wrapped,
            "cost_usd_total": round(cost, 8),
            "cost_usd_per_task": round(cost / len(task_rows), 8) if task_rows else None,
            "completion_tokens_total": sum(
                (r.get("usage") or {}).get("completion_tokens", 0) for r in task_rows
            ),
            "controls_all_as_expected": controls_ok,
            "controls": control_report,
            "metrics": metrics_of(rep, k_actual) if rep else None,
            "metrics_as_sent": (
                metrics_of(rep_as_sent, k_actual) if rep_as_sent
                else (metrics_of(rep, k_actual) if rep else None)
            ),
            "table": rep.table(ks=(k_actual,)) if rep else None,
        }
        if write:
            (result_dir / f"{label}.json").write_text(json.dumps(entry, indent=2, sort_keys=True))
        summary.append(entry)

    summary.sort(key=lambda e: (-(headline(e, "usable") if headline(e, "usable") is not None else -1),
                                e["model"]))
    # A filtered run must not touch summary.json. It holds the whole run, and
    # several single-model processes scoring in parallel would each overwrite
    # it with just their own model -- last writer wins, and the file silently
    # stops describing the run. Use --merge to rebuild it from the per-model
    # files once they are all present.
    if only is None and write:
        (result_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary


def print_summary(summary: list[dict]) -> None:
    ks = {e["k"] for e in summary if e.get("k")}
    kl = str(next(iter(ks))) if len(ks) == 1 else "k"
    print(f"{'model':34s} {'usable@'+kl:>9s} {'pass@'+kl:>8s} {'vuln@'+kl:>8s} "
          f"{'fails':>7s} {'$/task':>10s}")
    print("-" * 82)
    def pick(m, metric):
        return next((v for kk, v in m.items() if kk.startswith(metric + "@")), None)

    for e in summary:
        m = e["metrics"]
        fails = f"{e['response_failures']}/{e['tasks_attempted']}"
        if m is None:
            print(f"{e['model']:34s} {'--':>9s} {'--':>8s} {'--':>8s} {fails:>7s} {'--':>10s}")
            continue
        print(
            f"{e['model']:34s} {pick(m,'usable'):8.1%} {pick(m,'pass'):7.1%} "
            f"{pick(m,'vulnerable'):7.1%} {fails:>7s} {e['cost_usd_per_task']:10.6f}"
        )
    bad = [e["model"] for e in summary if not e["controls_all_as_expected"]]
    print()
    print(f"controls as expected: {'ALL OK' if not bad else 'FAILED for ' + ', '.join(bad)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="preview", help="subdirectory of predictions/ to score")
    ap.add_argument("--models", default=None,
                    help="comma-separated labels; score only these (for parallel scoring)")
    ap.add_argument("--merge", action="store_true",
                    help="rebuild summary.json from existing per-model result files and exit")
    ap.add_argument(
        "--check",
        action="store_true",
        help="fail if recomputed scores differ from the committed results/ (used by CI); "
        "writes nothing",
    )
    args = ap.parse_args()

    if args.merge:
        summary = rebuild_summary(args.run)
        print_summary(summary)
        if any(not e["controls_all_as_expected"] for e in summary):
            raise SystemExit("FAIL: a control did not behave as expected")
        return

    committed_path = config.RESULTS_DIR / args.run / "summary.json"
    committed = json.loads(committed_path.read_text()) if committed_path.exists() else None
    # Read before score_run rewrites anything, so this reports the repository
    # rather than this process.
    stale = check_summary_matches_models(args.run)

    only = {m.strip() for m in args.models.split(",")} if args.models else None
    # --check is a comparison against what is committed, so it must leave the
    # committed files exactly as they are.
    summary = score_run(args.run, only, write=not args.check)
    if only:
        # A partial run must not overwrite the whole-run summary.
        print_summary(summary)
        print(f"\nscored {len(summary)} model(s); run --merge to rebuild summary.json")
        return
    print_summary(summary)

    if args.check:
        if committed is None:
            raise SystemExit(f"--check: nothing committed at {committed_path}")
        if stale:
            print("\nFAIL: committed summary.json disagrees with the committed "
                  "per-model files it is derived from:")
            for problem in stale:
                print(f"  {problem}")
            print("  fix with:  python3 runner/score.py --run "
                  f"{args.run} --merge")
            raise SystemExit(1)
        drift = []
        old = {e["model"]: e.get("metrics") for e in committed}
        for e in summary:
            if old.get(e["model"]) != e.get("metrics"):
                drift.append(e["model"])
        if drift:
            print(f"\nFAIL: recomputed scores differ from committed results for: {', '.join(drift)}")
            raise SystemExit(1)
        print("\nOK: recomputed scores match the committed results exactly.")

    if any(not e["controls_all_as_expected"] for e in summary):
        raise SystemExit("FAIL: a control did not behave as expected -- results not publishable")


if __name__ == "__main__":
    main()

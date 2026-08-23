"""Paired comparison of models over the same tasks.

The leaderboard's first version reported independent binomial intervals,
which was the wrong test. Every model answered the same 450 tasks, so task
difficulty is a *shared* source of variance; treating the models as
independent samples charges each of them for it separately and makes real
differences look like noise.

This bootstraps over tasks instead. On each resample every model is scored
on the same drawn tasks, so difficulty cancels in the difference and only
genuine disagreement carries weight. It also reports, for each pair, how
many tasks the two models actually disagreed on -- the quantity that
determines whether a comparison is resolvable at all.

No new data, no API calls: reads results/<run>/per_task/.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

ITERATIONS = 10000
SEED = 20260812  # fixed so the published intervals are reproducible
# The metric the groups are drawn on. usable@k is the headline everywhere
# else, so grouping on anything else would sort models by a number the page
# does not lead with.
HEADLINE = "usable"


def load(run: str, metric: str, k: int = 3):
    """Per-task outcomes, over the tasks that carry a full k samples.

    The @k estimator is defined for n >= k, so a task that came back short is
    excluded here exactly as it is from the scores themselves. Without that
    filter these intervals would sit around a different point estimate than
    the table they annotate, for no reason a reader could see.
    """
    d = config.RESULTS_DIR / run / "per_task"
    models, data = [], {}
    for f in sorted(d.glob("*.json")):
        models.append(f.stem)
        rows = json.loads(f.read_text())
        data[f.stem] = {name: v[metric] for name, v in rows.items() if v["samples"] >= k}
    # only tasks every model answered in full, so comparisons are like-for-like
    common = set.intersection(*(set(v) for v in data.values()))
    return models, data, sorted(common)


def bootstrap(models, data, tasks, iterations=ITERATIONS):
    rng = random.Random(SEED)
    n = len(tasks)
    point = {m: sum(data[m][t] for t in tasks) / n for m in models}
    draws = {m: [] for m in models}
    diffs = {(a, b): [] for a in models for b in models if a < b}
    for _ in range(iterations):
        sample = [tasks[rng.randrange(n)] for _ in range(n)]
        means = {m: sum(data[m][t] for t in sample) / n for m in models}
        for m in models:
            draws[m].append(means[m])
        for (a, b) in diffs:
            diffs[(a, b)].append(means[a] - means[b])
    return point, draws, diffs


def pct(xs, p):
    s = sorted(xs)
    return s[max(0, min(len(s) - 1, int(p * len(s))))]


GROUPS = [
    # (key, predicate on (beats, beaten_by), label used verbatim by the site)
    ("ahead", lambda w, l: w and not l,
     "Distinguishably ahead of at least one model, behind none"),
    ("mixed", lambda w, l: w and l,
     "Distinguishably ahead of some models and behind others"),
    ("unresolved", lambda w, l: not w and not l,
     "No comparison against any other model resolves"),
    ("behind", lambda w, l: not w and l,
     "Distinguishably behind at least one model, ahead of none"),
]


def groups_from(models: list[str], resolved) -> list[dict]:
    """Partition models by what the paired bootstrap actually resolves.

    ARTICLE.md declines to publish a ranking and says why: only 162 of the
    421 tasks all eleven models answered in full separate any two of these models,
    and 9 of the 55 pairwise
    comparisons resolve. Eleven ranked rows assert 55 orderings the data
    supports 9 of.

    The obvious repair -- walk the ranking and start a new band whenever a
    model is resolved against everything above it -- does not survive contact
    with this data: no model clears that bar, so all eleven collapse into one
    band and the page says nothing. That is not a defect in the data, it is
    what 9 of 55 looks like.

    So the grouping is on the resolved relation itself. A model is ahead if it
    is distinguishably better than at least one model and worse than none;
    behind if the reverse; unresolved if no comparison involving it resolves
    either way. These are claims each member individually satisfies.

    What this deliberately does NOT claim is any ordering *between* groups.
    claude-opus-5 is in `ahead` and glm-5.2 is in `behind`, and those two are
    not distinguishable from each other. The group says what is true of the
    model, not where it sits relative to another group, and the page has to
    say so too.
    """
    counts = {
        m: (sum(1 for o in models if o != m and resolved(m, o)),
            sum(1 for o in models if o != m and resolved(o, m)))
        for m in models
    }
    out = []
    for key, pred, label in GROUPS:
        members = sorted(m for m in models if pred(*counts[m]))
        if members:
            out.append({
                "key": key,
                "label": label,
                "models": members,
                "separations": {m: {"ahead_of": counts[m][0], "behind": counts[m][1]}
                                for m in members},
            })
    return out


def emit_intervals(run: str) -> dict:
    """Paired-bootstrap intervals for every model on every headline metric.

    The main results table used to carry no intervals at all, which is an odd
    silence in a paper arguing for inferential care. It cannot carry
    independent binomial ones either -- that is the estimator this section
    exists to reject. These are the intervals the same bootstrap produces for
    a single model's score: resample tasks, rescore, take the percentiles.
    Task difficulty still varies across resamples here (it only cancels in a
    *difference*), so these are wider than a binomial interval would be, which
    is the honest width for a score estimated on 450 shared items.
    """
    out: dict = {"run": run, "iterations": ITERATIONS, "seed": SEED, "models": {}}
    for metric in ("usable", "pass", "vulnerable"):
        models, data, _ = load(run, metric)
        for m in models:
            # Each model's own interval is bootstrapped over its own scored
            # tasks, so it brackets the score the table reports. The common
            # subset belongs to the pairwise differences, not here: narrowing
            # every model to the tasks the worst-covered one answered would
            # move nine models' point estimates to annotate two.
            own = sorted(data[m])
            _, draws, _ = bootstrap([m], {m: data[m]}, own)
            out["models"].setdefault(m, {})[metric] = [pct(draws[m], 0.025),
                                                       pct(draws[m], 0.975)]
            out.setdefault("tasks", {}).setdefault(metric, {})[m] = len(own)
    # The pairwise structure, recorded rather than only printed. The groups the
    # published page sorts models into are a claim about which comparisons
    # resolve, so the comparisons have to be in results/ where a reader can
    # check them -- and where the presenter can read them instead of running
    # its own bootstrap and quietly disagreeing with the paper.
    models, data, tasks = load(run, HEADLINE)
    point, _, diffs = bootstrap(models, data, tasks)
    order = sorted(models, key=lambda m: -point[m])

    pairwise = {}
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            key = (a, b) if a < b else (b, a)
            sign = 1 if key == (a, b) else -1
            ds = [sign * x for x in diffs[key]]
            lo, hi = pct(ds, 0.025), pct(ds, 0.975)
            pairwise[f"{a} vs {b}"] = {
                "better": a,
                "diff": point[a] - point[b],
                "ci95": [lo, hi],
                "tasks_disagreed": sum(1 for t in tasks if data[a][t] != data[b][t]),
                # Resolved means the interval for (better - worse) clears zero.
                "resolved": lo > 0,
            }

    def resolved(a, b):
        """Is a distinguishably better than b? Direction-safe.

        pairwise is keyed once per pair, in point-estimate order, so the
        reverse lookup has to go through the stored `better` rather than
        assuming the caller knows which way round the key is.
        """
        v = pairwise.get(f"{a} vs {b}") or pairwise.get(f"{b} vs {a}")
        return bool(v and v["resolved"] and v["better"] == a)

    groups = groups_from(order, resolved)
    out["headline_metric"] = HEADLINE
    out["pairwise"] = pairwise
    out["pairwise_resolved"] = sum(1 for v in pairwise.values() if v["resolved"])
    out["groups"] = groups
    # Groups are not ordered relative to each other unless every cross-pair
    # resolves, which with 9 of 55 it does not. Recorded rather than assumed,
    # so the page can state which it is instead of implying the stronger one.
    out["groups_fully_separated"] = all(
        resolved(a, b)
        for hi, lo in zip(groups, groups[1:])
        for a in hi["models"] for b in lo["models"]
    )

    # Resolved-pair counts and discriminative yield, so the table and the
    # sentences quoting it are generated rather than transcribed. Both were
    # written before the pass_at_k fix and neither was rebuilt after it; the
    # vulnerable row in particular moved a long way.
    for metric in ("usable", "pass", "vulnerable"):
        models, data, tasks = load(run, metric)
        point, _, diffs = bootstrap(models, data, tasks)
        n_resolved = 0
        for i, a in enumerate(sorted(models, key=lambda m: -point[m])):
            for b in sorted(models, key=lambda m: -point[m])[i + 1:]:
                key = (a, b) if a < b else (b, a)
                sign = 1 if key == (a, b) else -1
                ds = sorted(sign * x for x in diffs[key])
                if pct(ds, 0.025) > 0:
                    n_resolved += 1
        identical = sum(1 for t in tasks if len({data[m][t] for m in models}) == 1)
        out.setdefault("resolved_at_95", {})[metric] = n_resolved
        out.setdefault("identical_tasks", {})[metric] = identical
        out.setdefault("common_tasks", {})[metric] = len(tasks)
        out.setdefault("identical_pct", {})[metric] = round(100 * identical / len(tasks))
    out["pairs"] = len(models) * (len(models) - 1) // 2
    # Tasks on which the models do not all agree on usable@3 -- the metric the
    # main table is ordered by. Stated per metric rather than as one number,
    # because the three differ a lot and a single figure invites the reader to
    # attach it to whichever metric they were just reading about.
    out["discriminative_tasks"] = {
        m: out["common_tasks"][m] - out["identical_tasks"][m] for m in out["common_tasks"]}

    path = config.RESULTS_DIR / run / "paired_intervals.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"wrote {path}")
    print(f"  {out['pairwise_resolved']} of {len(pairwise)} comparisons resolved "
          f"on {HEADLINE}@3 over {len(tasks)} common tasks")
    print(f"  groups ordered relative to each other: "
          f"{out['groups_fully_separated']}")
    for g in groups:
        print(f"    {g['key']:11s} {g['label']}")
        for m in g["models"]:
            sep = g["separations"][m]
            print(f"      {m:26s} ahead of {sep['ahead_of']}, behind {sep['behind']}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    ap.add_argument("--metric", default="usable", choices=["usable", "pass", "vulnerable"])
    ap.add_argument("--emit-intervals", action="store_true",
                    help="write per-model intervals for the paper's tables and exit")
    args = ap.parse_args()

    if args.emit_intervals:
        emit_intervals(args.run)
        return

    models, data, tasks = load(args.run, args.metric)
    point, draws, diffs = bootstrap(models, data, tasks)
    order = sorted(models, key=lambda m: -point[m])

    print(f"metric: {args.metric}@3   tasks common to all models: {len(tasks)}   "
          f"bootstrap: {ITERATIONS} resamples\n")
    print(f"{'model':26s} {'score':>7s}  {'95% CI (paired bootstrap)':>26s}")
    print("-" * 64)
    for m in order:
        lo, hi = pct(draws[m], 0.025), pct(draws[m], 0.975)
        print(f"{m:26s} {point[m]:6.1%}  [{lo:6.1%}, {hi:6.1%}]")

    print(f"\nPairwise: is the difference distinguishable from zero?\n")
    print(f"{'pair':52s} {'diff':>7s} {'95% CI':>18s} {'disagree':>9s}  verdict")
    print("-" * 100)
    sig = 0
    total = 0
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            total += 1
            key = (a, b) if a < b else (b, a)
            sign = 1 if key == (a, b) else -1
            ds = [sign * x for x in diffs[key]]
            lo, hi = pct(ds, 0.025), pct(ds, 0.975)
            disagree = sum(1 for t in tasks if data[a][t] != data[b][t])
            resolved = lo > 0
            sig += resolved
            if resolved or b == order[i + 1]:
                print(f"{a + ' vs ' + b:52s} {point[a]-point[b]:+6.1%} "
                      f"[{lo:+6.1%},{hi:+6.1%}] {disagree:9d}  "
                      f"{'DISTINGUISHABLE' if resolved else 'not resolved'}")
    print(f"\n{sig} of {total} pairwise comparisons are resolved at 95%.")

    # how much of the corpus discriminates at all
    all_same = sum(1 for t in tasks if len({data[m][t] for m in models}) == 1)
    print(f"{all_same}/{len(tasks)} tasks ({all_same/len(tasks):.0%}) give every model the same "
          f"outcome and cannot separate anything.")


if __name__ == "__main__":
    main()

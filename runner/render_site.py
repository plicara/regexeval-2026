"""Generate the /benchmarks/ page for plicara.ai from results.

Emits groups, not a ranking. An earlier version of this file emitted a table
ordered one to eleven by usable@3; it ran once, to plicara.ai, and was
reverted the same day, because the study declines to publish exactly that --
see ARTICLE.md, "What we are not claiming": "Bands are defensible. A numbered
list from one to eleven is not." 62% of tasks give every model the identical
result, only 167 of the 441 tasks all eleven models answered separate any two
of them, and 9 of the 55 pairwise
comparisons resolve. Eleven ranked rows assert 55 orderings the data supports
9 of.

The groups come from results/<run>/paired_intervals.json, which
runner/paired_stats.py writes from the paired bootstrap. They are not
recomputed here: the page and the paper have to be making the same claim, and
the way to guarantee that is to read it rather than derive it twice. Models
within a group are ordered alphabetically, so the file gives no ordering the
statistics do not support -- including between the groups themselves, which
on this data are not ordered either.


The site is hand-written static HTML with no build step, so this emits a
complete page in the site's own design system -- Blueprint scheme, Archivo,
the existing .data-table / .eyebrow / .lede components -- rather than
inventing a layout. Copy the output into the site repo at benchmarks/index.html.

Column order follows the site's existing table, with one change: usable@1
moves first, because it is the headline and pass@1 is the least interesting
number on the row.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402


def pct(v):
    return "&mdash;" if v is None else f"{v * 100:.1f}%"


GROUP_NOTE = (
    "Groups say what the paired bootstrap resolves at 95%, and nothing more. "
    "They are not ranked against each other: claude-opus-5 is in the first "
    "group and glm-5.2 in the last, and those two are not distinguishable "
    "from one another. Order within a group is alphabetical and means nothing."
)


def row_for(e: dict, k: int, sep: dict | None) -> str:
    m = e.get("metrics")
    label = html.escape(e["model"])
    if sep is None:
        sepcell = "&mdash;"
    else:
        # Written as a pair rather than a single rank, because "ahead of two,
        # behind none" and "ahead of two, behind three" are different claims
        # and a rank would flatten them into one.
        sepcell = f"+{sep['ahead_of']} / &minus;{sep['behind']}"
    if m is None:
        cells = "".join('<td class="num mono">&mdash;</td>' for _ in range(4))
        return (f'<tr><th scope="row" class="mono">{label}</th>{cells}'
                f'<td class="num mono">{sepcell}</td>'
                f'<td class="num mono">{e["response_failures"]}'
                f'/{e["tasks_attempted"]}</td></tr>')
    return (
        f'<tr><th scope="row" class="mono">{label}</th>'
        f'<td class="num mono">{pct(m[f"usable@{k}"])}</td>'
        f'<td class="num mono">{pct(m[f"pass@{k}"])}</td>'
        f'<td class="num mono">{pct(m[f"vulnerable@{k}"])}</td>'
        f'<td class="num mono">{pct(m[f"dfa-eq@{k}"])}</td>'
        f'<td class="num mono">{sepcell}</td>'
        f'<td class="num mono">{e["response_failures"]}/{e["tasks_attempted"]}</td></tr>'
    )


def grouped_rows(summary: list[dict], groups: list[dict], k: int) -> str:
    """One <tbody> per group, models alphabetical inside it.

    A model the bootstrap never placed -- one that answered too little to have
    per-task outcomes -- goes in a final group of its own rather than being
    dropped or appended to the last one. "We could not compare this" and "this
    came last" are different statements, and only one of them is true.
    """
    by_model = {e["model"]: e for e in summary}
    placed, out = set(), []
    for g in groups:
        members = [m for m in g["models"] if m in by_model]
        if not members:
            continue
        placed.update(members)
        rows = "\n            ".join(
            row_for(by_model[m], k, g["separations"].get(m)) for m in members
        )
        out.append(
            f'<tbody class="band">\n'
            f'            <tr class="band-head"><th scope="rowgroup" colspan="7">'
            f'{html.escape(g["label"])}</th></tr>\n            {rows}\n'
            f'          </tbody>'
        )
    unplaced = sorted(set(by_model) - placed)
    if unplaced:
        rows = "\n            ".join(row_for(by_model[m], k, None) for m in unplaced)
        out.append(
            f'<tbody class="band">\n'
            f'            <tr class="band-head"><th scope="rowgroup" colspan="7">'
            f'Not compared &mdash; too few scored tasks</th></tr>\n'
            f'            {rows}\n          </tbody>'
        )
    return "\n          ".join(out)


def render(summary: list[dict], run_date: str, k: int, task_count: int,
           groups: list[dict], resolved: int, comparisons: int) -> str:
    body = grouped_rows(summary, groups, k)

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Benchmarks &middot; Plicara Labs</title>
    <meta
      name="description"
      content="How good are language models at writing regular expressions you could
actually ship? regexbench scored across {len(summary)} models on Re(gEx|DoS)Eval."
    />
    <link rel="canonical" href="https://plicara.ai/benchmarks/" />
    <!-- Blueprint's ground, --fh-print. Kept in step with tokens.css by hand;
         the previous value here (#2e3a42) was a leftover from a palette two
         repaints ago and tinted the mobile browser chrome off-brand. -->
    <meta name="theme-color" content="#082C35" />

    <link rel="icon" href="/assets/favicon.svg" type="image/svg+xml" />
    <link rel="apple-touch-icon" href="/assets/brand/apple-touch-icon-180.png" />

    <!-- Archivo sets the page; JetBrains Mono sets the nav, the eyebrows and
         the buttons, all above the fold. Without these preloads the browser
         only discovers the mono after parsing style.css. Both weights: 400
         for the nav and footer, 700 for eyebrows and buttons. -->
    <link rel="preload" as="font" type="font/woff2"
          href="/assets/fonts/archivo.woff2" crossorigin />
    <link rel="preload" as="font" type="font/woff2"
          href="/assets/fonts/jetbrains-mono-400.woff2" crossorigin />
    <link rel="preload" as="font" type="font/woff2"
          href="/assets/fonts/jetbrains-mono-700.woff2" crossorigin />

    <link rel="stylesheet" href="/assets/tokens.css" />
    <link rel="stylesheet" href="/assets/style.css" />

    <!-- The grouped table is the one thing on this page the site's design
         system has no component for, because no other table on the site has
         row groups. Scoped here rather than added to style.css: the site repo
         receives this file as a drop-in, and a page that needs a stylesheet
         change in another commit is a page that ships broken when the two get
         separated. Everything below inherits from currentColor and the
         surrounding type, so it follows the theme without naming a token. -->
    <style>
      .data-table tbody.band + tbody.band {{ border-top: 1px solid; }}
      .data-table tbody.band + tbody.band > tr:first-child > th {{ padding-top: 1.25rem; }}
      .data-table .band-head > th {{
        text-align: left;
        font-size: 0.8125rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        opacity: 0.72;
        padding-bottom: 0.35rem;
      }}
    </style>
  </head>
  <!-- data-scheme sits on body rather than html: tokens.css declares the
       default :root block after the scheme blocks, so a scheme on the root
       element loses the custom-property tie-break. -->
  <body data-scheme="blueprint">
    <a class="skip-link" href="#main">Skip to content</a>

    <header class="site-header">
      <div class="wrap">
        <a class="brand" href="/">
          <span class="brand-mark" aria-hidden="true"></span>
          Plicara Labs
        </a>
        <nav class="site-nav" aria-label="Primary">
          <a href="/#mission">Mission</a>
          <a href="/#models">Models</a>
          <a href="/#tools">Tools</a>
          <a href="/#principles">Principles</a>
          <a href="https://github.com/plicara">GitHub</a>
        </nav>
      </div>
    </header>

    <main class="wrap basecamp" id="main">
      <p class="eyebrow">benchmarks &middot; regexbench</p>
      <h1>Regexes you could actually ship.</h1>
      <p class="lede">
        Most regex benchmarks ask whether a pattern passes its tests. This one
        also asks whether it means what the reference means, and whether it can
        be made to hang your server. A pattern can do the first and fail both
        of the others.
      </p>

      <div class="table-wrap">
        <table class="data-table">
          <caption class="visually-hidden">
            {len(summary)} models scored on Re(gEx|DoS)Eval, in {len(groups)}
            groups by what a paired bootstrap on usable@{k} resolves. The
            groups are not ranked against each other and the order inside a
            group is alphabetical.
          </caption>
          <thead>
            <tr>
              <th scope="col">Model</th>
              <th scope="col" class="num">usable@{k}</th>
              <th scope="col" class="num">pass@{k}</th>
              <th scope="col" class="num">vulnerable@{k}</th>
              <th scope="col" class="num">dfa-eq@{k}</th>
              <th scope="col" class="num">separates</th>
              <th scope="col" class="num">failed</th>
            </tr>
          </thead>
          <tbody>
            {body}
          </tbody>
        </table>
      </div>

      <p class="note">
        <strong>These are groups, not a ranking.</strong> {GROUP_NOTE} Of the
        {comparisons} pairwise comparisons between these {len(summary)} models,
        only {resolved} resolve; the rest are ties this run cannot break. The
        <strong>separates</strong> column reads +ahead / &minus;behind: how
        many of the other models this one is distinguishably better than, and
        worse than. Most of the corpus does no work here &mdash; the majority
        of tasks give every model the identical result.
      </p>

      <p class="note">
        <strong>usable@{k}</strong> is the headline: correct, not vulnerable to
        catastrophic backtracking, and never proven to describe a different
        language than the reference. The gap between it and
        <strong>pass@{k}</strong> is every pattern that passes its tests and
        still should not ship.
      </p>

      <p class="note">
        {task_count} tasks from Re(gEx|DoS)Eval, k={k} samples per task, reasoning
        disabled so every model faces the same conditions. Scored with
        <code>regexbench</code> {html.escape(config.REGEXBENCH_VERSION)}. Run
        {html.escape(run_date)}. Every raw
        response is committed, and the scores recompute from them offline &mdash;
        <a href="https://github.com/plicara/regexeval-2026">see the
        repository</a> for the method, the limitations, and a re-run command.
      </p>

      <div class="cta-row">
        <a class="btn btn-primary" href="https://github.com/plicara/regexeval-2026">Results and method</a>
        <a class="btn btn-ghost" href="https://github.com/plicara/regexbench">regexbench</a>
        <a class="btn btn-ghost" href="/">&larr; Back to the lab</a>
      </div>
    </main>

    <footer class="site-footer">
      <div class="wrap">
        <span>&copy; Plicara Labs</span>
        <div class="footer-links">
          <a href="mailto:info@plicara.ai">info@plicara.ai</a>
          <a href="https://github.com/plicara">GitHub</a>
          <a href="/">Home</a>
        </div>
      </div>
    </footer>
  </body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default="sweep")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--date", default=None,
                    help="run date, e.g. 2026-08-12; defaults to config.RUN_DATES")
    ap.add_argument("--tasks", type=int, default=None,
                    help="task count; defaults to tasks_attempted // k from the summary")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    summary = json.loads((config.RESULTS_DIR / args.run / "summary.json").read_text())

    # The groups are a statistical claim, so they are read from the analysis
    # rather than invented here. No file, no page: publishing a plain list
    # because the bootstrap has not been run is precisely the failure this
    # generator was rewritten to prevent.
    ipath = config.RESULTS_DIR / args.run / "paired_intervals.json"
    if not ipath.exists():
        ap.error(f"no {ipath}. Run: python3 runner/paired_stats.py --run "
                 f"{args.run} --emit-intervals")
    intervals = json.loads(ipath.read_text())
    groups = intervals.get("groups")
    if not groups:
        ap.error(f"{ipath} carries no 'groups'. Regenerate it with the current "
                 f"runner/paired_stats.py.")
    banded = {m for g in groups for m in g["models"]}
    scored = {e["model"] for e in summary if e.get("metrics")}
    if not scored <= banded:
        ap.error(f"{', '.join(sorted(scored - banded))} scored but absent from "
                 f"the groups in {ipath}; the two files describe different runs.")

    # Both of these used to be required arguments, which meant the page could
    # only be regenerated by someone who remembered the run's date and size.
    # They are recoverable -- the date from config, the task count from the
    # data -- so recover them and let automation call this with just --run.
    date = args.date or config.RUN_DATES.get(args.run)
    if date is None:
        ap.error(f"no date for run {args.run!r}: pass --date or add it to "
                 f"config.RUN_DATES")
    tasks = args.tasks or max(e["tasks_attempted"] // e["k"] for e in summary)
    page = render(summary, date, args.k, tasks, groups,
                  intervals["pairwise_resolved"], len(intervals["pairwise"]))
    out = Path(args.out) if args.out else config.REPO / "docs" / "benchmarks-index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    print(f"wrote {out} ({len(page)} bytes)")
    print(f"{len(groups)} groups, {intervals['pairwise_resolved']} of "
          f"{len(intervals['pairwise'])} comparisons resolved")
    print("copy into the site repo as benchmarks/index.html")


if __name__ == "__main__":
    main()

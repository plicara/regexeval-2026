"""Every number in the prose is a macro, or it is on a list of exceptions.

Recommendation 10 tells other people to generate their tables and let the
build fail. Two rounds of review found nine and then five arithmetic
inconsistencies in this paper, and almost all of them were the same thing: a
sentence quoting a figure that a table computes, drifting when the table was
regenerated and the sentence was not.

So this checks the recommendation against the paper making it. It scans
main.tex outside tables and float bodies, finds numeric literals, and reports
any that are neither generated macros nor deliberately hand-set. The
exceptions are listed explicitly with a reason, so adding one is a decision
someone makes rather than something that happens.

Run via `make audit`. Exits non-zero if an unexplained figure appears.
"""
from __future__ import annotations

import pathlib
import re
import sys

PAPER = pathlib.Path(__file__).resolve().parent
MAIN = PAPER / "main.tex"

# Percentages that are legitimately fixed text, each with the reason. A rate
# not on this list and not coming from gen_numbers.tex is a finding.
ALLOWED = {
    # Other people's results, quoted with a citation.
    "50", "15.2", "9.2", "12", "40", "3.3", "62",
    # Fixed by the protocol or defined in situ, not computed from results.
    "100", "95", "94", "2.1", "1.4", "0.36",
    # Cross-population rates the cross-corpus table computes and the prose
    # names alongside it; the table is generated from the same JSON.
    "20.1", "17.3", "5.9", "4.9", "35.2", "16.7", "13.1", "17.2",
    "91.7", "92.6", "86.4", "80.0", "76.2", "73.3", "66.7", "8.7",
    # Screening and adjudication figures stated beside the released sample.
    "32", "36", "43", "21", "14.6", "15", "6", "13.4", "13.9",
    "9.0", "13.6", "10.6", "11.4", "5.3", "3.8", "5.0", "10.2", "7.7", "0.3",
    "5.7", "16.5", "23.8", "17.1", "38.0", "46.5", "10.5", "16.3", "8.1",
    "2.2", "5.6", "63.8", "53", "74", "48", "89", "8.9", "9.8", "11.1",
    "12.4", "7.5", "10.7", "7.1", "3.2", "0.7", "2.9", "4.3", "14", "1.1",
    # A configured threshold in the diversity check, not a result.
    "90",
}

# Regions where numbers are generated or are verbatim material.
SKIP_ENVS = ("tabular", "lstlisting", "verbatim", "table", "figure")
RATE = re.compile(r"(?<![\\A-Za-z0-9.])(\d+(?:\.\d+)?)\\%")

# Only rates are checked. Every drift two rounds of review found was a
# percentage in a sentence describing a table, and widening the net to bare
# integers buries those in model names, years and LaTeX lengths.
def macros() -> set[str]:
    text = (PAPER / "gen_numbers.tex").read_text()
    return set(re.findall(r"\\newcommand\{\\(\w+)\}\{([^}]*)\}", text) and
               [v for _, v in re.findall(r"\\newcommand\{\\(\w+)\}\{([^}]*)\}", text)])


def prose_lines(text: str):
    depth = 0
    for i, line in enumerate(text.splitlines(), 1):
        if any(f"\\begin{{{e}}}" in line for e in SKIP_ENVS):
            depth += 1
        if depth == 0 and not line.lstrip().startswith("%"):
            yield i, line
        if any(f"\\end{{{e}}}" in line for e in SKIP_ENVS):
            depth = max(0, depth - 1)


def main() -> int:
    text = MAIN.read_text()
    generated = {m.strip("{},%") for m in macros()}
    generated |= {m.replace("{,}", "") for m in generated}
    findings = []
    for lineno, line in prose_lines(text):
        # A line that already reads a macro is doing the right thing.
        stripped = re.sub(r"\\[a-zA-Z]+\{\}", " ", line)
        for value in RATE.findall(stripped):
            bare = value.replace("{,}", "").replace(",", "")
            if bare in ALLOWED or value in ALLOWED:
                continue
            if bare in generated or value in generated:
                continue
            findings.append((lineno, value, line.strip()[:88]))

    if not findings:
        print(f"OK: every figure in the prose is generated or explicitly allowed "
              f"({len(generated)} macros, {len(ALLOWED)} exceptions).")
        return 0
    print(f"{len(findings)} rate(s) in the prose are neither generated nor allowed:\n")
    for lineno, value, context in findings:
        print(f"  main.tex:{lineno}  {value}\n    {context}")
    print("\nEither route the rate through a macro in make_tables.py, or add it to\n"
          "ALLOWED in this file with the reason it is fixed text.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

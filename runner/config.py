"""Paths and run constants. No machine-specific values anywhere in here.

Every path is derived from the repo root or overridable by environment
variable, so a clone runs the same way on any machine.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The corpus is not redistributed -- `make setup` downloads it here.
DATA_DIR = Path(os.environ.get("REGEXLB_DATA", REPO / "data"))
REGEXEVAL_PATH = Path(os.environ.get("REGEXEVAL_PATH", DATA_DIR / "RegexEval.json"))
REGEXEVAL_URL = (
    "https://raw.githubusercontent.com/s2e-lab/RegexEval/master"
    "/DatasetCollection/RegexEval.json"
)

# The cross-population ReDoS screen (runner/cross_corpus_redos.py) reads three
# further artifacts. They are large and are not needed to reproduce any
# model-side number, so `make setup` does not fetch them; `make setup-corpora`
# does. Both are pinned by commit, because both are living repositories whose
# contents have changed since we screened them.
DEEP_REGEX_DIR = Path(os.environ.get("DEEP_REGEX_DIR", DATA_DIR / "deep-regex"))
DEEP_REGEX_URL = "https://github.com/nicholaslocascio/deep-regex.git"
DEEP_REGEX_COMMIT = "096490db7f4b0394fbb46b914cb35a0aa1cba29c"

LINGUA_FRANCA_DIR = Path(os.environ.get("LINGUA_FRANCA_DIR", DATA_DIR / "lf"))
LINGUA_FRANCA_URL = "https://github.com/VTLeeLab/LinguaFranca-FSE19.git"
LINGUA_FRANCA_COMMIT = "a75bd51713d14aa9b48c32e103a3da500854f518"

PREDICTIONS_DIR = REPO / "predictions"
RESULTS_DIR = REPO / "results"

# The scoring engine. Both the release and the commit are recorded with every
# result, because the commit is what the published numbers were produced by.
#
# 0.4.1 fixes the defect that made the first published table wrong: pass_at_k
# credited a full pass to any task with fewer than k samples, which inflated
# exactly the two models that had lost the most samples and moved one of them
# two places. score.py has excluded short tasks since it was found; 0.4.1
# makes the estimator refuse them outright, so the guard now exists on both
# sides of the boundary.
REGEXBENCH_COMMIT = "ff25e6a5ef463141ae95d512cd43a214e4e7b111"
REGEXBENCH_VERSION = "0.4.1"

# The date each published run was collected. Prose in README/METHODOLOGY says
# it too, but the site generator needs it mechanically: a workflow that
# regenerates /benchmarks/ cannot be asked to remember a date.
RUN_DATES = {
    "sweep": "2026-08-12",
}

# What runner/run_preview.py sends. Only that runner reads them. The sweep's
# sampling lives in runner/models.json, and what a result file reports as
# having been sent is read back off the responses themselves -- see
# `sampling_of` in runner/score.py. These were once the source for both, and
# that is exactly how every file in results/ came to claim max_tokens 200
# while the published sweep was collected at 400.
TEMPERATURE = 0.0
MAX_TOKENS = 200

# Sampling for the two runs whose predictions predate the per-row config
# fingerprint (`config_fingerprint` in runner/sweep.py). A closed list, not a
# default: everything collected since records its own settings on every row,
# and neither of these runs will be collected again. Values are literals on
# purpose -- pointing them at the constants above would reintroduce the drift
# they exist to document.
LEGACY_SAMPLING = {
    # Collected by runner/sweep.py at the runner/models.json defaults, in the
    # roster revision that had already dropped temperature. Corroborated by
    # the run's longest completion, 290 tokens, which a 200 cap cannot produce.
    "pilot": {"max_tokens": 400, "temperature": None},
    # Collected by runner/run_preview.py, which sent the two constants above.
    "preview": {"max_tokens": 200, "temperature": 0.0},
}


def require_dataset() -> Path:
    if not REGEXEVAL_PATH.exists():
        raise SystemExit(
            f"Corpus not found at {REGEXEVAL_PATH}\n"
            f"Run:  make setup     (downloads it from {REGEXEVAL_URL})"
        )
    return REGEXEVAL_PATH


def require_corpora() -> tuple[Path, Path]:
    """The two external artifacts the cross-population screen reads."""
    missing = [str(d) for d in (DEEP_REGEX_DIR, LINGUA_FRANCA_DIR) if not d.exists()]
    if missing:
        raise SystemExit(
            "Cross-corpus artifacts not found: " + ", ".join(missing) + "\n"
            "Run:  make setup-corpora     (clones both at their pinned commits, ~250 MB)"
        )
    return DEEP_REGEX_DIR, LINGUA_FRANCA_DIR

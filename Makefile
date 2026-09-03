# regexeval-2026 -- everything runs from a clean clone with `make`.
.PHONY: check-python setup setup-corpora pin detector calibrate score persample analysis check docs tables figures audit crosscorpus collect clean help

PY ?= python3
RUN ?= preview
REGEXBENCH_PIN = regexbench==0.4.1
PYTHON_TARGETS = setup crosscorpus calibrate docs tables audit figures score persample analysis check collect

DEEP_REGEX_URL = https://github.com/nicholaslocascio/deep-regex.git
DEEP_REGEX_COMMIT = 096490db7f4b0394fbb46b914cb35a0aa1cba29c
LINGUA_FRANCA_URL = https://github.com/VTLeeLab/LinguaFranca-FSE19.git
LINGUA_FRANCA_COMMIT = a75bd51713d14aa9b48c32e103a3da500854f518

$(PYTHON_TARGETS): check-python

check-python:
	@$(PY) -c 'import sys; sys.exit("regexeval-2026 requires Python 3.10 or newer (found %s)" % sys.version.split()[0] if sys.version_info < (3, 10) else 0)'

help:
	@echo "make setup          install the pinned scorer + download the corpus"
	@echo "make score          recompute scores from committed predictions (free, offline)"
	@echo "make check          same, and fail if they differ from committed results (CI)"
	@echo "make analysis       recompute every derived result the paper reads (offline)"
	@echo "make tables         regenerate every table in paper/ from committed results"
	@echo "make audit          check every rate in the paper prose comes from a macro"
	@echo "make setup-corpora  clone the cross-population artifacts (~250 MB, pinned)"
	@echo "make crosscorpus    re-run the cross-population ReDoS screen (needs setup-corpora)"
	@echo "make calibrate      measure the screen's recall per population (builds a detector)"
	@echo "make collect        query models via OpenRouter -- needs OPENROUTER_KEY, costs money"

# matplotlib is here rather than left implicit because `make figures` and
# `make -C paper all` need it, and an undeclared import is the same class of
# problem as an ungenerated table: it works on the machine that wrote it.
setup:
	$(PY) -m pip install --quiet --upgrade "$(REGEXBENCH_PIN)" matplotlib
	@mkdir -p data
	@test -f data/RegexEval.json || curl -fsSL -o data/RegexEval.json \
	  https://raw.githubusercontent.com/s2e-lab/RegexEval/master/DatasetCollection/RegexEval.json
	@echo "setup ok: regexbench pinned, corpus at data/RegexEval.json"

# Cloned rather than downloaded file by file: both artifacts spread the data we
# read across several paths, and a commit pin is the only reproducible handle
# either repository offers -- neither publishes a release or a checksum.
setup-corpora:
	@mkdir -p data
	@$(MAKE) --no-print-directory pin DIR=data/deep-regex URL=$(DEEP_REGEX_URL) SHA=$(DEEP_REGEX_COMMIT)
	@$(MAKE) --no-print-directory pin DIR=data/lf URL=$(LINGUA_FRANCA_URL) SHA=$(LINGUA_FRANCA_COMMIT)
	@echo "setup-corpora ok: deep-regex and LinguaFranca-FSE19 at their pinned commits"

# Fetch exactly one commit rather than cloning a history we never read. Both
# artifacts are large and neither is browsed here; `git init` + a depth-1 fetch
# of the pinned SHA is the cheapest form that still pins.
pin:
	@test -d $(DIR)/.git || (mkdir -p $(DIR) && git init -q $(DIR) && \
	  git -C $(DIR) remote add origin $(URL))
	@test "$$(git -C $(DIR) rev-parse HEAD 2>/dev/null)" = "$(SHA)" || ( \
	  git -C $(DIR) fetch -q --depth 1 origin $(SHA) && \
	  git -C $(DIR) checkout -q --detach FETCH_HEAD )
	@echo "  $(DIR) at $$(git -C $(DIR) rev-parse HEAD)"

crosscorpus:
	$(PY) runner/cross_corpus_redos.py

# The independent ReDoS detector used to calibrate our screen. It ships inside
# the LinguaFranca artifact as plain javac + a Makefile, so building it needs
# no package manager and no network beyond setup-corpora.
DETECTOR_DIR = data/lf/analysis/performance/vuln-regex-detector/src/detect/src/detectors/weideman-RegexStaticAnalysis

detector: setup-corpora
	@$(MAKE) -s -C $(DETECTOR_DIR) all
	@echo "detector ok: weideman-RegexStaticAnalysis built"

calibrate: detector
	$(PY) runner/screen_calibration.py

docs:
	$(PY) runner/render_docs.py --run $(RUN)

tables:
	$(PY) paper/make_tables.py

# Recommendation 10, applied to the paper that makes it: every rate in the
# prose is a generated macro or an explicitly listed exception.
audit:
	$(PY) paper/audit_numbers.py

figures:
	$(PY) paper/make_figures.py

score:
	$(PY) runner/score.py --run $(RUN)

# The per-sample counts every downstream analysis reads, including the
# reference-independent headline. Committed, and rebuildable -- `make check`
# verifies both halves.
persample:
	$(PY) runner/per_sample.py --run $(RUN)

analysis:
	$(PY) runner/per_sample.py --run $(RUN)
	$(PY) runner/paired_stats.py --run $(RUN) --emit-intervals
	$(PY) runner/anchored_models.py --run $(RUN)
	$(PY) runner/mcnemar_reference.py --run $(RUN)
	$(PY) runner/undec_credit.py --run $(RUN)
	$(PY) runner/complexity_compare.py --run $(RUN)

check:
	$(PY) runner/score.py --run $(RUN) --check
	$(PY) runner/per_sample.py --run $(RUN) --check
	$(PY) runner/render_docs.py --run sweep --check

collect:
	$(PY) runner/run_preview.py

clean:
	rm -rf data __pycache__ runner/__pycache__

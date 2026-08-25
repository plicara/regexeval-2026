# regexeval-2026

> ### Status, 2026-08-20 — the figures below are the corrected ones
>
> **The name is wrong: this is a study, not a leaderboard.**
> [`ARTICLE.md`](ARTICLE.md) is the current statement of what this work
> claims, and its "What we are not claiming" section is explicit: *"We are
> not publishing a leaderboard. [...] Bands are defensible. A numbered list
> from one to eleven is not."* 62% of the
> tasks give every model the identical result; only 162 of the 421 tasks all
> eleven models answered in full separate them at all. **The table below is grouped
> into bands for that reason**, and the
> order inside a band is alphabetical and means nothing.
>
> The three defects the 2026-08-19 note listed have been fixed, and the
> figures here are regenerated from the corrected scores:
>
> 1. `regexbench.harness.pass_at_k` scored any task with **fewer than `k`
>    samples** as a full pass ([regexbench#8](https://github.com/plicara/regexbench/issues/8)).
>    Short-sample tasks are now excluded from the `@k` estimate. `kimi-k3`
>    `usable@3` 24.8 → 23.8, `claude-opus-5` 23.0 → 20.8. Fixed upstream too:
>    the issue is closed, the pin is `regexbench==0.4.1`, and the estimator
>    now refuses `n < k` rather than crediting it. Rescoring against the
>    patched engine moved no number here, because `runner/score.py` had
>    already been excluding those tasks.
> 2. **48.3%** of `usable` credits rest on an **UNDECIDABLE** equivalence
>    verdict rather than demonstrated equivalence. Measured, reported per
>    model, and given its own section in the paper — it is a reason to
>    distrust the composite, not a defect in these figures.
> 3. **"135 such patterns" is withdrawn.** The reproducible figure is 390 of
>    5,269 correct samples (7.4%), or 144 of 2,051 model-task pairs.
>
> Every table in this file is generated from `results/` by
> `runner/render_docs.py`, and `make check` fails if they drift. Published
> 2026-08-23: the run page lives at
> [plicara.ai/benchmarks/regexeval-2026](https://plicara.ai/benchmarks/regexeval-2026/),
> the write-up under
> [plicara.ai/research/whether-anyone-ever-ran-it](https://plicara.ai/research/whether-anyone-ever-ran-it/).

**How good are language models at writing regular expressions you could
actually ship?**

Most regex benchmarks ask one question: does the pattern pass the tests?
This one asks whether you could put the answer in production — because a
pattern can pass every test it was given and still be wrong, or still hang
your server.

**11 models · 450 tasks · 3 samples each · 14,850 calls · run 2026-08-12**

---

## The run

Every model passes roughly **40%** of tasks. Every model produces something
shippable on roughly **20%**. That gap is the finding, and it survives every
correction below.

<!-- generated: leaderboard -->
| Model | usable@3 | pass@3 | vulnerable@3 | tasks | failed | $/request |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Distinguishably ahead of at least one model, behind none** | | | | | | |
| `anthropic/claude-opus-5` | **20.8%** | 46.1% | 13.2% | 432 | 36/1350 | $0.002514 |
| `moonshotai/kimi-k3` | **23.8%** | 46.5% | 12.9% | 441 | 16/1350 | $0.001328 |
| `qwen/qwen3.6-max-preview` | **21.6%** | 42.4% | 9.1% | 450 | 0/1350 | $0.000388 |
| **No comparison against any other model resolves** | | | | | | |
| `deepseek/deepseek-v4-flash-0731` | **19.8%** | 38.0% | 12.0% | 450 | 0/1350 | $0.000026 |
| `openai/gpt-5.6-sol` | **20.9%** | 42.1% | 10.0% | 449 | 1/1350 | $0.002108 |
| **Distinguishably behind at least one model, ahead of none** | | | | | | |
| `anthropic/claude-sonnet-5` | **18.0%** | 40.7% | 10.9% | 450 | 0/1350 | $0.000932 |
| `google/gemini-3.1-flash-lite` | **17.1%** | 38.7% | 12.0% | 450 | 0/1350 | $0.000090 |
| `z-ai/glm-5.2` | **18.7%** | 42.4% | 14.2% | 450 | 0/1350 | $0.000158 |
| `openai/gpt-5.6-luna` | **18.5%** | 39.2% | 11.6% | 449 | 1/1350 | $0.000043 |
| `openai/gpt-5.6-terra` | **18.7%** | 42.2% | 12.0% | 450 | 0/1350 | $0.000406 |
| `qwen/qwen3.6-plus` | **19.8%** | 39.8% | 9.8% | 450 | 0/1350 | $0.000121 |
<!-- /generated -->

**Three numbers, one story.** `pass@3` is what other benchmarks report —
did it satisfy the examples. `vulnerable@3` is how many answers can be
made to hang. `usable@3` is what survives once you remove the vulnerable
patterns *and* the ones provably describing a different language than the
reference.

Two things worth noticing more than which band a model is in:

- **The spread is narrow — 17.1% to 23.8%.** Eleven models across a 98×
  price range land within seven points of each other.
- **`deepseek-v4-flash-0731` costs $0.000026 per request and scores 19.8%.
  `claude-opus-5` costs $0.002514 — 98× more — and scores 20.8%.** One point
  for two orders of magnitude.

The `tasks` column is the number entering each model's `@3` estimate. Tasks
that came back with fewer than three samples — after a refusal or a spending
limit — are excluded rather than scored on what arrived, because the `pass@k`
estimator is only defined for `n ≥ k`. Getting that wrong credited every short
task to whichever model lost it; see [the hazards
appendix](paper/main.tex).

*More metrics — semantic equivalence, exact match, the decidable subset —
are in [APPENDIX.md](APPENDIX.md).*

---

## The finding that survived

We screened the same ReDoS check across six populations of regular
expressions — this corpus's own answer key, two other benchmark gold sets, a
grammar-generated control, Stack Overflow, the reusable patterns on
regexlib.com, and half a million regexes extracted from shipped packages.

<!-- generated: populations -->
| Population | written to be | n | vulnerable |
| --- | --- | ---: | ---: |
| NL-RX-Synth (grammar-generated control) | — | 5,840 | 35.2% ± 1.2 |
| RegexLib, published for reuse | read | 3,446 | 17.2% ± 1.3 |
| KB13 gold answers | read | 532 | 16.7% ± 3.2 |
| Re(gEx\|DoS)Eval gold answers | read | 755 | 13.1% ± 2.4 |
| Stack Overflow posts | read | 5,000 | 5.9% ± 0.7 |
| Production code | run | 5,000 | 4.9% ± 0.6 |
| | | | |
| **Anchored `^...$` only** | | | |
| RegexLib, published for reuse | read | 1,684 | 20.1% ± 1.9 |
| Stack Overflow posts | read | 4,000 | 17.3% ± 1.2 |
| Re(gEx\|DoS)Eval gold answers | read | 538 | 13.4% ± 2.9 |
| **This work, 11 models pooled** | — | 3,613 | 9.8% ± 1.0 |
| **Production code** | **run** | 4,000 | 8.9% ± 0.9 |
<!-- /generated -->

The dividing line is not human against machine. It is whether the pattern was
ever **run**. Everything written to be *read* — library entries, forum
answers, benchmark reference answers — is ReDoS-prone. The one population that
has been executed under real traffic sits at 8.9%, and the models sit with it.

The second block restricts *every* population to anchored `^...$` patterns,
models included, because this corpus is unusually rich in validators and
that's the shape that backtracks. That restriction is the comparison to read;
without it the numbers are mostly a fact about task mix.

## Why "passes the tests" isn't enough

### It passed every test and it can hang your server

> **Task:** *"tests the validity of a domain or hostname"*

`claude-opus-5` answered:

```
^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+(com|org|net|mil|edu)$
```

That is **100% correct** on every example it was given. It is also
**exponentially** vulnerable:

> *a quantifier wraps a quantified group — exponential backtracking on a
> failing suffix*

This is a realistic, production-looking pattern. Put it on a signup form
and you have a denial-of-service bug. This shape is common in the run —
though **the figure once quoted here, 135, is not reproducible from the
released data** and is withdrawn pending the revision. The defensible
per-sample count is **390 of 5,269 correct samples (7.4%)**.

### It passed every test and it's still wrong

> **Task:** *"Matches 5 numeric digits, such as a zip code."*

`claude-opus-5` answered `\b\d{5}\b` where the reference is `^\d{5}$`.
Both pass the tests. They are not the same pattern, and here is the string
that proves it:

```
"\n00000"
```

The model's version matches a zip code sitting on the second line of a
multi-line string; the reference doesn't. Whether that matters depends on
your input — which is exactly why the benchmark reports it rather than
silently calling one of them correct. **806 answers** passed their tests
while describing a different language than the reference.

---

## The most interesting failure is ours

Some of what we score as "wrong" is the model being **right** and the
human-written reference being wrong.

> **Task:** *"A very simple ISBN validation expression — it just checks for
> a 10 digit number"*

| | |
| --- | --- |
| `claude-opus-5` wrote | `^\d{9}[\dX]$` |
| The reference says | `^\d{9}[\d\|X]$` |
| They differ on | `000000000\|` |

The reference's character class contains a literal **pipe** — someone wrote
`[\d|X]` meaning "a digit or X" and accidentally allowed `|` too. The model
is correct. The gold answer has a typo. We score the model down for it.

Another: for *"Positive integer value."* the model wrote `^[1-9][0-9]*$`
and the reference `^\d+$`, differing on `0`. Zero is not a positive
integer. The model is arguably right there too.

We have not audited how often this happens, so **treat `dfa-eq` as a lower
bound on model correctness, not a verdict on it.** Publishing this is
cheaper than having someone else find it.

---

## Verify it yourself

Every model response is committed in `predictions/`. Scores are computed
from those files and nothing else, so you can recheck the arithmetic
without an API key, without spending anything, and without trusting us:

```bash
git clone https://github.com/plicara/regexeval-2026
cd regexeval-2026
make setup    # installs the pinned scorer, downloads the corpus
make score RUN=sweep
```

`make check` does the same and **fails** if the recomputed numbers differ
from the published ones. It runs in CI on every push against the fast
preview run, so the scoring path cannot silently drift.

---

## Failures are results too

**54 of 14,850 calls failed (0.36%).** They are in the table, not dropped.

**`claude-opus-5` was refused by a content filter on 29 calls** — and the
prompts are benign:

| Task | Prompt |
| --- | --- |
| regexeval/146 | strings that do not contain a single quotation mark |
| regexeval/251 | a six character "password" of numbers and letters |
| regexeval/660 | a series of hex codes separated by spaces |
| regexeval/693 | **"Matches a file extention."** |

No other model refused anything. And it isn't consistent: several of these
were refused on one sample and answered on the next two — same prompt,
same model, same settings. `k=3` sampling surfaced that; `k=1` would have
recorded it as a flat failure.

**Ten further calls** came back HTTP-successful with no extractable pattern —
nine a bare code fence, one a pattern followed by an unmatched closing fence
(seven `claude-opus-5`, two `kimi-k3`, one `gpt-5.6-luna`). They are counted
as failures rather than scored as empty patterns.

The remaining failures: 11 calls hit the account's spending limit (see
below) and 4 came back without a resolved provider, which we reject rather
than score, because a row without provenance is not reproducible. That is
29 + 10 + 11 + 4 = 54.

## Known gaps in this run

- **Coverage is not perfectly uniform.** Nine models cover all 450 tasks.
  `kimi-k3` covers 447 — the budget ran out mid-collection. `claude-opus-5`
  covers 444, from content-filter refusals and one task where every reply was
  a bare code fence. Under 2%, no ranking changes, but the denominators differ.
- **The reference answers contain errors** (see above), so `dfa-eq`
  understates model correctness by an unmeasured amount.
- **"Not vulnerable" is a screening result, not a proof** — no known-bad
  shape and no blow-up on the attack strings tried. We measured how loose that
  bound is, separately for each population above, by pairing an independent
  detector with a dynamic timing oracle (`make calibrate`), because a screen
  that is blinder in one population than another would produce an ordering by
  itself. Recall runs 67–93% across the seven populations, and — crucially —
  is not lower in production code (80%) than in the showcase validators it is
  being compared against (92%). Correcting each rate for its own recall leaves
  the ordering unchanged.
- **The corpus is old enough to be in training data**, so scores may partly
  measure memorisation. A private task set to measure that gap is not yet
  built.

## What's here

```
predictions/   every raw model response — the evidence
results/       scores, recomputed from predictions/ by CI
runner/        the OpenRouter client, scorer, auditor
ARTICLE.md     the write-up, and every judgement call in context
APPENDIX.md    the harder metrics and the honest limitations
paper/         the full technical treatment, built from results/
```

Scoring by [`regexbench`](https://github.com/plicara/regexbench)
(Apache-2.0), pinned to `regexbench==0.4.1` on PyPI, which is commit
`ff25e6a5`; both are recorded in every result file. Corpus:
[Re(gEx|DoS)Eval](https://github.com/s2e-lab/RegexEval), not redistributed
here — `make setup` fetches it.

## License

Code [Apache-2.0](LICENSE).

# Appendix: the harder metrics

The README reports three numbers because three numbers tell the story.
These are the rest. They are computed in every run
and stored in `results/sweep/`, they just aren't what you need to read the
results.

## The full metric set

| Metric | Plain English |
| --- | --- |
| `pass@k` | Did the pattern match the examples and reject the counterexamples? |
| `vulnerable@k` | Can the pattern be made to hang on hostile input? |
| `usable@k` | Correct, not vulnerable, and never *proven* to differ from the reference. |
| `dfa-eq@k` | Is it the same language as the reference? Counting "we couldn't tell" as a miss. |
| `dfa-eq@k (decided)` | The same, but only over tasks where the question could be answered. |
| `exact@k` | Is it the identical string to the reference? |

## Full results: 450 tasks, k=3, 2026-08-12

<!-- generated: full-metrics -->
| Model | dfa-eq@3 | dfa-eq@3 (decided) | exact@3 | undecidable | tasks | wrapped |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `kimi-k3` | 14.1% | 17.1% | 5.0% | 78 | 441 | 17 |
| `qwen3.6-max-preview` | 13.8% | 17.4% | 3.8% | 94 | 450 | 11 |
| `claude-opus-5` | 11.6% | 15.2% | 2.8% | 104 | 432 | 9 |
| `qwen3.6-plus` | 11.6% | 14.8% | 3.8% | 99 | 450 | 9 |
| `deepseek-v4-flash-0731` | 11.3% | 14.3% | 3.3% | 93 | 450 | 16 |
| `glm-5.2` | 10.4% | 12.9% | 3.8% | 86 | 450 | 18 |
| `claude-sonnet-5` | 10.4% | 13.3% | 3.3% | 97 | 450 | 9 |
| `gpt-5.6-terra` | 10.2% | 13.1% | 2.0% | 100 | 450 | 11 |
| `gpt-5.6-sol` | 9.4% | 13.3% | 1.8% | 133 | 449 | 7 |
| `gemini-3.1-flash-lite` | 9.3% | 11.8% | 3.1% | 95 | 450 | 16 |
| `gpt-5.6-luna` | 9.1% | 12.2% | 1.8% | 112 | 449 | 9 |
<!-- /generated -->

Semantic equivalence tops out at **17.4%** where `pass@3` reaches 46.5%.
Reproducing the reference *language* is a far harder problem than passing
its examples, which is why both are measured.

### ReDoS: models against the answer key

One pattern per task per model, matching the human side, which has one answer
each. The final column is an exact McNemar test on the paired tasks: the
models and the reference set answer the *same* tasks, so an independent
interval on each would throw the pairing away and resolve nothing.

<!-- generated: human-baseline -->
| Source | n | vulnerable | exponential | polynomial | McNemar p |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Human reference answers** | 450 | 13.6% | 6.4% | 7.1% |  |
| `kimi-k3` | 447 | 10.7% | 5.4% | 5.4% | 0.1360 |
| `claude-opus-5` | 444 | 10.6% | 7.4% | 3.2% | 0.0649 |
| `glm-5.2` | 450 | 10.2% | 5.8% | 4.4% | 0.0581 |
| `gemini-3.1-flash-lite` | 450 | 9.8% | 5.1% | 4.7% | 0.0331 |
| `gpt-5.6-sol` | 450 | 9.3% | 5.1% | 4.2% | 0.0183 |
| `claude-sonnet-5` | 450 | 8.9% | 6.0% | 2.9% | 0.0055 |
| `gpt-5.6-terra` | 450 | 8.7% | 4.9% | 3.8% | 0.0038 |
| `qwen3.6-plus` | 450 | 8.4% | 5.1% | 3.3% | 0.0011 |
| `gpt-5.6-luna` | 450 | 8.0% | 4.0% | 4.0% | 0.0010 |
| `deepseek-v4-flash-0731` | 450 | 7.3% | 4.4% | 2.9% | 0.0003 |
| `qwen3.6-max-preview` | 450 | 7.3% | 4.7% | 2.7% | 0.0001 |
| **All models pooled** | 4941 | 9.0% | 5.3% | 3.8% |  |
<!-- /generated -->

Eight of the eleven separate from the reference set at a raw 95%; correcting
for having run eleven tests (Holm) leaves six. The models that do not
separate are the most vulnerable ones, which is what you would expect and is
not what a ranking of the point estimates would tell you.

### Why `dfa-eq` is reported twice

Comparing two regexes as *languages* is solved for most patterns: compile
both to automata, compare the machines. But for patterns using
**backreferences** (`(a)\1`, "match a thing then the same thing again") it
is **formally undecidable**: no algorithm can answer it, and the obstruction
is a theorem, not a limitation of this tool.

That leaves an honest reporting problem one number cannot solve:

- **`dfa-eq@k`** counts undecidable comparisons as failures. *How much of
  the corpus did we positively verify?* A lower bound that cannot flatter.
- **`dfa-eq@k (decided)`** drops those tasks from the denominator. *Of the
  questions answerable at all, how many did the model get right?*

Publishing only the second is quiet inflation, publishing only the first
blames the model for a theorem. Both are published, always, with the
undecidable count beside them: **78 to 133 of each model's scored tasks**.

One caution about that count. It pools the truly undecidable comparisons
with patterns the engine simply declines (`UNSUPPORTED`: a lookahead
containing an anchor, an inline flag group, an automaton over a state
budget), and the split falls almost entirely on the second: across all
models, backreferences account for twenty of the 471 `usable` credits that
rest on an unsettled verdict, and the engine's own reach accounts for the
rest. The paper's measurement-validity section works through what that does
to the composite.

### Why `exact@k` exists

It runs 1.8%–5.0%, and that range is the whole argument: `[0-9]+` and
`[0-9][0-9]*` are the same language written two ways, and a benchmark
scoring by string comparison would call one of them wrong. `exact@k` is
published to show how badly string comparison would misrank everyone.

## The reference answers contain errors

This is the most important limitation on this page.

`dfa-eq` compares the model against a human-written gold pattern, and some
gold patterns are wrong. Two examples:

**A literal pipe in a character class.** For *"a very simple ISBN
validation expression"* the reference is `^\d{9}[\d|X]$`. That class
contains digit, **pipe**, and X: someone wrote `|` meaning "or" inside
`[...]`, where it is just a character. `claude-opus-5` wrote `^\d{9}[\dX]$`,
which is what the prompt describes. It is scored as different, and the
witness is `000000000|`.

**A definition disagreement.** For *"Positive integer value."* the
reference `^\d+$` accepts `0`; the model's `^[1-9][0-9]*$` does not. Zero
is not a positive integer.

We audited how often this occurs. From a seeded random sample of sixty
cases where a model passed every test yet was scored as semantically
different, fourteen adjudicated in detail, the model is clearly at fault in
roughly 15%. The rest split between incorrect reference patterns and prompts
that never specified the property in dispute. **`dfa-eq` is a lower bound on
model correctness**, and the majority of what it counts against a model is
not model error. Per-case reasoning is released with the adjudications.

`usable@k` inherits this, since it counts a proven difference against the
model. `pass@k` and `vulnerable@k` do not — they run the real `re` engine
against real strings and never consult the reference.

## The wrapper rule

Models were asked for a bare pattern in a code block. Some return it
wrapped in host-language string syntax:

```
r'\d+$'      ← what the model said
\d+$         ← what it meant
```

Scored literally, `r'\d+$'` matches the letter `r`, a quote, and so on. It
fails for a reason unrelated to regex ability.

**The rule: host-language quoting is stripped before scoring, repeatedly up
to three nested layers so a backticked raw string arrives bare**
(`r'…'`, `'…'`, `"…"`, `` `…` ``, `/…/flags`).

It affected **7 to 18 responses per model** out of 1,350, under 1.4%
everywhere, too small to move any conclusion. Every strip is recorded in
`results/sweep/<model>.json` under `wrapped_detail` with before and after,
and the unnormalized score is kept as `metrics_as_sent` so anyone who
disagrees can use the other number without re-running anything.

## Engine limitations

These belong to the scorer, `regexbench` 0.4.1, and apply to every model
equally:

- **`\d` is not `[0-9]`.** It matches every Unicode digit, because that is
  what Python's `re` does and the scorer runs the real `re`. This is the
  single thing most likely to make our numbers differ from another
  published regex eval. It also inflates apparent errors: of 806 answers
  that passed their tests but differed from the reference, **266 differed
  only on Unicode digits**: the model wrote `[0-9]` where the gold wrote
  `\d`, or the reverse.
- **ReDoS screening covers three of five known vulnerability families**
  structurally; the other two are caught only if the empirical pass trips
  them. `vulnerable@k` is therefore a **lower bound**.
- **Lookaround became decidable in `regexbench` 0.4.0.** Earlier versions
  refused it, so these numbers are not comparable to figures produced with
  0.3.0 or earlier.
- **Match semantics are set per corpus.** 761 of Re(gEx|DoS)Eval's 762
  references pass their own tests under "search" semantics (the one failure
  is itself the ReDoS-vulnerable reference) against 94% under "full match";
  picking wrong scores 46 gold answers as failures. Verified by scoring
  every reference against itself before the run.

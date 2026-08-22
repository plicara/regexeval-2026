# What we learned measuring 11 language models on regular expressions

*Draft for review — Plicara Labs, 2026-08-12*

We set out to build a leaderboard. The data told us not to publish one.
What follows instead is a set of findings that hold across every model we
tested, an account of which of our own measurements we trust and which we
don't, and a list of the ways this run nearly went silently wrong.

**The run:** 11 current models, 450 tasks, 3 attempts per task, 14,850
requests, $10.95. Every raw response is committed to the repository. Every
number below recomputes from those files with no API key and no cost.

---

# Part 1 — What we did

## 1.1 The task

Each item gives a model a plain-English description of a text pattern:

> *"Matches 5 numeric digits, such as a zip code."*

The model writes a regular expression. That's it — no examples, no hints
about format, no second attempt if it answers badly. The instruction is
identical for every model:

> **system:** You translate a natural-language description into a single
> Python `re`-compatible regular expression. Reply with ONLY the pattern in
> one fenced code block, no explanation.
>
> **user:** *{the task description, verbatim}*

We deliberately did not tune this prompt. Tuning would raise every score
and make the numbers incomparable to other published work on the same
corpus.

## 1.2 The corpus

**Re(gEx|DoS)Eval** — 762 regex problems collected from real users. Each
one has a description, strings that must match, strings that must not, and
a human-written "gold" answer.

It comes from [Siddiq, Zhang, Roney & Santos, ICSE-NIER
2024](https://doi.org/10.1145/3639476.3639757), and so do the four metrics we
report: pass@k, vulnerable@k, dfa-eq@k and exact match. That paper already
scores correctness and security jointly, on this corpus, over T5, Phi-1.5 and
GPT-3.5-Turbo. We are running their instrument on eleven newer models, taking
the joint metric apart, and then pointing the safety check back at their own
reference answers — which they did not do.

We used **450 of the 762**, chosen by spreading evenly across the corpus
rather than taking the first 450 (which are mostly easy). The number 450
was set by budget, not by principle: the full corpus at three samples each
priced above the $12 we had.

We don't redistribute the corpus. The repo downloads it from the original
source.

## 1.3 The models

Eleven models, chosen to span frontier and open-weights across roughly a
100× price range:

| Model | Tier | Served by |
| --- | --- | --- |
| `openai/gpt-5.6-sol` | frontier | OpenAI |
| `openai/gpt-5.6-terra` | frontier | OpenAI |
| `openai/gpt-5.6-luna` | small | OpenAI |
| `anthropic/claude-opus-5` | frontier | Anthropic |
| `anthropic/claude-sonnet-5` | frontier | Anthropic |
| `google/gemini-3.1-flash-lite` | frontier | Google AI Studio |
| `moonshotai/kimi-k3` | open | Fireworks |
| `qwen/qwen3.6-max-preview` | open | Alibaba |
| `qwen/qwen3.6-plus` | open | Alibaba |
| `z-ai/glm-5.2` | open | Novita |
| `deepseek/deepseek-v4-flash-0731` | open | CoreWeave |

## 1.4 Three settings that needed a decision, and why

**Three samples per task, not one.** Models are non-deterministic — ask
twice, get two answers. A single sample measures luck as much as skill.
Three attempts also reveal things one attempt hides; the inconsistent
content-filter refusals in §3.5 are only visible because of it.

**Reasoning turned off for every model.** Four of the eleven —
Claude Opus 5 and Sonnet 5, GPT-5.6 Sol and Terra — don't produce hidden
reasoning at all. The other seven do. Scoring them side by side with
reasoning enabled would compare "model plus thinking budget" against
"model", and the results would partly rank who was allowed to think. So
every request disables it, and that's recorded with every response.

**Temperature not set at all.** This one was forced on us. Six of the
eleven models *reject* the `temperature` parameter outright, and we also
set `require_parameters: true` — which tells the router to only use
providers that actually honour the parameters we send, rather than
silently ignoring them. The combination is a hard error: no endpoint
qualifies. The choice was "set temperature and lose half the board" or
"don't set it and keep the honesty guarantee". We chose the latter, so
each model samples with its own default.

That's only acceptable if the defaults actually produce variation —
otherwise three samples is one answer at triple the price. So we checked,
by asking the same question three times and counting distinct answers:

| Model | distinct answers out of 3 |
| --- | --- |
| `claude-opus-5` | 3 |
| `gpt-5.6-sol` | 3 |
| `kimi-k3` | 3 |
| `glm-5.2` | 2 |

## 1.5 Pinning the provider — and why it matters

We route through OpenRouter, which by default spreads requests across
whichever provider is cheapest at that moment. The same model can be
served by different companies, on different hardware, **at different
numerical precision**, and lower precision can change the output.

An unpinned benchmark therefore measures the router, not the model. Re-run
it next week and the numbers move with no code change and no way to tell
why.

So every request names a single provider and refuses substitution. If the
pinned provider is down, the request **fails visibly** rather than quietly
being served by someone else. That fired during the run and cost us data,
which is the correct trade: a failure you can see beats a substitution you
can't.

The pin is the instruction; the response is the evidence. We recorded which
provider actually served each response. **All 11 models were served
entirely by the endpoint they pinned** — no silent substitutions.

For open-weights models this matters most. GLM-5.2 and DeepSeek-V4-Flash
are served at 4-bit precision by some providers and 8-bit by others; we
pinned 8-bit deliberately. One pin we set went stale within an hour — the
provider stopped serving that model — so we re-verify every pin
immediately before every run.

---

# Part 2 — How scoring works

We ask three questions about each answer. They turn out to have very
different reliability, and that difference drives everything in Part 4.

## 2.1 Question 1 — does it work?

Run the model's pattern against the strings that should match and the
strings that shouldn't, using Python's real regex engine.

## 2.2 Question 2 — does it mean the right thing?

Compare the model's pattern to the human gold answer as **languages**, not
as text. Both compile to automata and the machines are compared.

This matters because `[0-9]+` and `[0-9][0-9]*` describe exactly the same
set of strings written two different ways. A benchmark comparing strings
would mark one of them wrong. (In our run, string-identical answers ran
just **2.0%–6.3%** — so string comparison would misrank essentially
everyone.)

When two patterns differ, the engine produces a **witness**: the shortest
string that tells them apart. That is what makes this checkable rather
than an assertion — you can paste the witness into Python and see the
disagreement yourself.

**Some comparisons are impossible, not merely hard.** For patterns using
backreferences — `(a)\1`, "match something, then the same thing again" —
asking whether two are equivalent is *formally undecidable*. No algorithm
can answer it, ever. That is a theorem, not a limitation of our tool.
Between **82 and 133 of 450 tasks per model** landed in that bucket.

We therefore report this metric twice: once counting undecidable cases as
failures (a lower bound that cannot flatter), and once excluding them (the
model alone, over answerable questions). Reporting only the second would be
quiet inflation; reporting only the first blames the model for a theorem.

## 2.3 Question 3 — is it safe?

Some regexes take exponentially long on hostile input. This is a real,
well-known denial-of-service class called **ReDoS**. The classic shape is a
quantifier wrapping a quantified group — `(a+)+` — which forces the engine
to explore an exponential number of ways to split the input before
concluding that it doesn't match.

We screen every pattern structurally for known-bad shapes, then actually
try to trip it with attack strings under a timeout.

**"Safe" here means "no known-bad shape and no blow-up on what we tried".
It is a screening result, not a proof.** The structural pass covers three
of five documented vulnerability families, so our vulnerability rates are
**lower bounds**.

## 2.4 The combined number

`usable` means: correct on every example, **and** not vulnerable, **and**
never *proven* to describe a different language than the reference. It was
our intended headline. Part 4 explains why we no longer trust it as one.

## 2.5 The key structural fact

**Questions 1 and 3 never look at the human gold answer.** They run the
real engine against real strings. **Question 2 is entirely a comparison
against a human.**

That difference turns out to matter enormously.

---

# Part 3 — What we found

## 3.1 Passing the tests is about twice as easy as being shippable

| Model | pass@3 | usable@3 | vulnerable@3 |
| --- | ---: | ---: | ---: |
| `kimi-k3` | 46.5% | 23.8% | 12.9% |
| `qwen3.6-max-preview` | 42.4% | 21.6% | 9.1% |
| `gpt-5.6-sol` | 42.1% | 20.9% | 10.0% |
| `claude-opus-5` | 46.1% | 20.8% | 13.2% |
| `deepseek-v4-flash-0731` | 38.0% | 19.8% | 12.0% |
| `qwen3.6-plus` | 39.8% | 19.8% | 9.8% |
| `glm-5.2` | 42.4% | 18.7% | 14.2% |
| `gpt-5.6-terra` | 42.2% | 18.7% | 12.0% |
| `gpt-5.6-luna` | 39.2% | 18.5% | 11.6% |
| `claude-sonnet-5` | 40.7% | 18.0% | 10.9% |
| `gemini-3.1-flash-lite` | 38.7% | 17.1% | 12.0% |

Every model, at every price point, loses roughly half of its apparent
successes to the other two questions. The cheapest open-weights model and
the most expensive frontier model behave the same way.

*(Read these as bands, not a ranking. §4.4 explains why.)*

## 3.2 About one in fourteen passing regexes can hang your server

This is the finding we'd lead with. It is *not* unprecedented: scoring
correctness and security jointly is an active area, and CWEval, BaxBench,
SecureAgentBench and DualGauge all do it for general code generation. What is
new here is the setting — regular expressions, where the vulnerability class
is ReDoS and where a per-task human answer exists to compare against (§3.3).
Our numbers land close to theirs, which we take as corroboration rather than
as a problem: BaxBench finds roughly half of functionally correct backends are
exploitable, and SecureAgentBench reports 15.2% correct-and-secure for its best
agent.

Asked to *"test the validity of a domain or hostname"*, `claude-opus-5`
produced:

```
^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+(com|org|net|mil|edu)$
```

It passes every test it was given. It is also **exponentially**
vulnerable — the outer `(...)+` wraps a group that itself contains
`{0,61}`, the classic catastrophic-backtracking shape. Feed it a long,
nearly-valid hostname that fails at the very last character and the matcher
explores exponentially many ways to divide the input before giving up.

This is not an exotic pattern. It is exactly the kind of thing that passes
code review because it *looks* careful. Two more, both from models, both
passing every test:

```
^[\w\.\-]+@([\w\-]+\.)+[a-zA-Z\d]{2,67}(\.[a-zA-Z\d]{2,67})?$      ← email
^\s*[A-Za-z]+(?:,?\s+[A-Za-z]+)*\s*$                               ← name list
```

We found **390 of these** across the run: generations that passed every test
and screened as unsafe, out of 5,269 that passed — 7.4%. At the task level
that is 144 of the 2,051 model-task pairs where any sample passed. (An
earlier version of this document reported 135, a count we can no longer
reproduce from our own released data. The per-sample and per-task figures
above are both regenerable with `make persample`.)

## 3.3 The humans were just as unsafe — and this is the real story

Here is the number that reframes everything. We screened the **450
human-written gold answers** with the identical check.

To compare fairly we use one pattern per task per model — the humans wrote
one answer each — rather than the "any of three samples" figure above:

| | vulnerable | exponential | polynomial |
| --- | ---: | ---: | ---: |
| **Human reference answers** | **13.6%** | 6.4% | 7.1% |
| `kimi-k3` | 10.7% | 5.4% | 5.4% |
| `claude-opus-5` | 10.6% | 7.4% | 3.2% |
| `glm-5.2` | 10.2% | 5.8% | 4.4% |
| `gemini-3.1-flash-lite` | 9.8% | 5.1% | 4.7% |
| `gpt-5.6-sol` | 9.3% | 5.1% | 4.2% |
| `claude-sonnet-5` | 8.9% | 6.0% | 2.9% |
| `gpt-5.6-terra` | 8.7% | 4.9% | 3.8% |
| `qwen3.6-plus` | 8.4% | 5.1% | 3.3% |
| `gpt-5.6-luna` | 8.0% | 4.0% | 4.0% |
| `deepseek-v4-flash-0731` | 7.3% | 4.4% | 2.9% |
| `qwen3.6-max-preview` | 7.3% | 4.7% | 2.7% |
| **All models pooled** | **9.0%** | 5.3% | 3.8% |

**Every single model is safer than the human answer key.**

So the honest headline is not "AI writes dangerous regexes" — which every
reader already assumes, and which our data doesn't support. It is:

> **Dangerous regexes are endemic to how people write regexes, and models
> learned that faithfully from us.**

That is a more interesting claim, a more defensible one, and it explains
*why* the problem persists rather than just documenting it. The training
data is full of patterns that look careful, pass their tests, and are
exploitable — because that is what the human-written internet contains.

A caveat on the sub-types: an ICPC 2024 study found LLM-generated regexes
skew toward *polynomial* ReDoS, the cheaper family to overlook. Our data
doesn't reproduce that cleanly — models pooled run 5.3% exponential against
3.8% polynomial, the opposite direction — while the humans skew polynomial
more than the models do. The counts are small enough that we would not lean
on the difference.

## 3.4 Paying 98× more buys about three points

| Model | usable@3 | cost per request | total (1,350 requests) |
| --- | ---: | ---: | ---: |
| `deepseek-v4-flash-0731` | 19.8% | **$0.000026** | $0.03 |
| `gpt-5.6-luna` | 18.5% | $0.000043 | $0.06 |
| `gemini-3.1-flash-lite` | 17.1% | $0.000090 | $0.12 |
| `qwen3.6-plus` | 19.8% | $0.000121 | $0.16 |
| `glm-5.2` | 18.7% | $0.000158 | $0.21 |
| `qwen3.6-max-preview` | 21.6% | $0.000388 | $0.52 |
| `gpt-5.6-terra` | 18.7% | $0.000406 | $0.55 |
| `claude-sonnet-5` | 18.0% | $0.000932 | $1.26 |
| `kimi-k3` | 23.8% | $0.001328 | $1.79 |
| `gpt-5.6-sol` | 20.9% | $0.002108 | $2.85 |
| `claude-opus-5` | 20.8% | $0.002514 | $3.39 |

DeepSeek's model costs **98× less** than Claude Opus 5 and scores about a
point *higher* — well inside what our data can resolve, which is to say the
two are indistinguishable. The entire field fits inside seven points.

For regex generation specifically, model choice is close to a rounding
error and cost is not.

## 3.5 One model refuses harmless prompts, inconsistently

`claude-opus-5` was blocked by a content filter on **29 requests** (2.1% of
its calls), spread over 5 distinct tasks:

| Task | Prompt |
| --- | --- |
| regexeval/146 | strings that do not contain a single quotation mark |
| regexeval/251 | a six character "password" of numbers and letters |
| regexeval/660 | a series of hex codes (byte values) separated by spaces |
| regexeval/693 | **"Matches a file extention."** |
| regexeval/742 | "Usefull for SQL update and insert sentence" |

Some are faintly security-adjacent — quote escaping, SQL, passwords.
*"Matches a file extention"* is not, by any reading. **No other model
refused anything at all.**

And it is **not deterministic**: several of these were refused on one
attempt and answered on the next two, with identical settings. Sampling
three times is the only reason we can see that; a single-sample benchmark
would have logged a flat failure and moved on.

## 3.6 Hidden reasoning is astonishingly expensive for this task

Not our main question, but the numbers are striking enough to report.

We measured every model on the corpus's *easiest* task — *"Matches exactly
1 numeric digit (0-9)."* — with reasoning at its default setting:

| Model | hidden reasoning tokens | cost for that one call |
| --- | ---: | ---: |
| `qwen3.6-max-preview` | **1,571** | $0.0098 |
| `gemini-3.6-flash` | 427 | $0.0033 |
| `deepseek-v4-flash-0731` | 344 | $0.0001 |
| `glm-5.2` | 194 | $0.0006 |
| `kimi-k3` | 69 | $0.0024 |
| `claude-opus-5` | 0 | $0.0015 |

Qwen spent **1,571 tokens of hidden reasoning** deciding how to match a
single digit, then answered `^[0-9]$`. With reasoning disabled it answered
`^[0-9]$` again — in 10 tokens, for **1/100th of the price**.

Two practical notes for anyone running similar evaluations:

- **"Low effort" is not a cheaper setting.** On `qwen3.6-max-preview`,
  asking for low reasoning effort produced *2,375* reasoning tokens — more
  than the default, at higher cost. Only fully disabling it reduced
  anything.
- **A reasoning model with too small a token budget returns nothing at
  all.** At a 200-token cap, three models produced completely empty
  responses: the entire budget went on hidden reasoning with nothing left
  to answer with. We treat an empty completion as a failed request, never
  as an empty pattern, because scoring it would look exactly like a model
  that answered badly.

## 3.7 Does thinking help? We don't really know

We ran a comparison — 5 reasoning-capable models, 12 tasks, one sample
each — and it is **far too small to conclude from**. We report it because
leaving it out would be worse, not because it settles anything.

| Model | usable, reasoning off | usable, reasoning on |
| --- | ---: | ---: |
| `kimi-k3` | 8.3% | 22.2% |
| `gpt-5.6-luna` | 0.0% | 16.7% |
| `qwen3.6-max-preview` | 5.6% | 8.3% |
| `deepseek-v4-flash-0731` | 13.9% | 9.1% |
| `glm-5.2` | 8.3% | 0.0% |

Twelve tasks gives roughly ±14 points of uncertainty per cell, so every one
of these movements is consistent with noise. Two of GLM's runs also
returned nothing after exhausting a 4,000-token budget, which drags its
"on" number down for a reason unrelated to thinking quality.

What we *can* say firmly is the cost: reasoning-on calls averaged
**$0.010149** against **$0.000648** with it off — **15.7× more expensive**
over the same tasks.

Answering this properly needs a reasoning-enabled run at full scale. That
is probably its own publication.

---

# Part 4 — What we found about our own measurement

We think this part is as valuable as the results. We would rather publish
it than have someone else discover it.

## 4.1 Question 2 is mostly not measuring the model

Question 2 compares the model's pattern to a human's. That only tells you
about the model if the human was right. Often they weren't.

We drew a seeded random sample of **60 cases** where a model **passed every
test** but was scored as meaning something different, and worked through 14
in detail:

| Who was actually wrong | Count | Share |
| --- | ---: | ---: |
| The **human gold answer** | 5 | 36% |
| **Neither** — the prompt never said | 6 | 43% |
| The **model** | 3 | 21% |

Separately, **19 of the 60 (32%)** differ only on **non-ASCII input** — the
model wrote `[0-9]` where the gold wrote `\d`, and in Python `\d` also
matches digits like `٣` (Arabic-Indic three). True, and not a meaningful
error for anyone.

Combining both, **the model is clearly at fault in roughly 15%** of what
this metric counts against it.

> *A caveat we want stated plainly rather than buried: this adjudication is
> 14 cases, judged by us, on our own benchmark. The direction is strong
> enough to act on, and the reasoning for each case is committed to
> `results/sweep/disagreements.json` so it can be disputed. But before
> anyone cites "15%" as a figure, a larger sample should be judged by
> someone with no stake in the answer. Every unadjudicated case in that
> file has an empty verdict field, ready for exactly that.*

### Gold answers that are simply wrong

> **Prompt:** *"It just accepts only positive numbers."*
> **Gold:** `^\d+([.,]?\d+)?$` — accepts `0`.
> **Model:** `^(?=.*[1-9])\d+(?:[.,]\d+)?$` — excludes `0`.
>
> Zero is not a positive number. The model was marked down for being right.

> **Prompt:** *"A very simple ISBN validation expression — it just checks
> for a 10 digit number"*
> **Gold:** `^\d{9}[\d|X]$`
> **Model:** `^\d{9}[\dX]$`
> **Witness:** `000000000|`
>
> The gold's character class contains digit, **pipe**, and X. Someone wrote
> `|` meaning "or" inside brackets, where it is just a literal character.
> The gold accepts `000000000|` as a valid ISBN. The model doesn't, and
> loses.

> **Prompt:** *"Just a small pattern to make sure commas are in the rite
> place (if present)."*
> **Gold:** `^\$?\d{1,3}(,?\d{3})*(\.\d{1,2})?$`
> **Model:** `^\$?(\d{1,3}(,\d{3})*|\d+)(\.\d{1,2})?$`
> **Witness:** `0,000000`
>
> The gold's `,?` makes the comma optional, so it accepts `0,000000` —
> defeating the entire stated purpose of the pattern. The model enforced
> comma placement and was scored as different.

> **Prompt:** *"This regex validates a persons first name. Acceptable names
> include compound names…"*
> **Gold:** `^[a-zA-Z]+((\s|\-)[a-zA-Z]+)?$`
> **Witness:** `A\tA` — a tab between the two letters
>
> The gold's `\s` matches a tab, so it accepts a "compound name" joined by
> a tab character. The model required a literal space or hyphen.

### Prompts that never said

> **Prompt:** *"Matches any single upper- or lower-case letter."*
> **Gold:** `^[a-zA-Z]$` — the whole string must be one letter.
> **Model:** `[A-Za-z]` — one letter appears somewhere.
>
> The difference is anchoring. The sentence doesn't say which is meant. The
> corpus assumes whole-string validation throughout; the prompts frequently
> don't say so.

We checked whether missing anchors explained the failures generally: it
accounts for only about **6%**. So this is diffuse mismatch between prompt,
gold and convention, not one fixable bug.

> **Prompt:** *"In this Pattern +91 will be the prefix in the Mobile
> number(of 10 digits)."*
> **Gold:** requires the first of the ten digits to be 1–9.
> **Model:** allows any ten digits.
>
> Indian mobile numbers don't start with zero, so the gold is
> domain-correct — but the prompt says "10 digits" and nothing more.
> Neither answer is wrong on what was actually asked.

### What this means practically

- **`pass` and `vulnerable` are trustworthy.** They never consult the gold.
- **The equivalence metric, and the combined `usable` number that includes
  it, are lower bounds** on model correctness by an amount we can estimate
  but not precisely correct for.

## 4.2 The corpus loads correctly — that isn't the problem

To rule out a pipeline fault, we scored every gold answer against its own
tests. **449 of 450 pass.** The corpus, its match semantics and its dialect
all load correctly.

The problem is subtler: **a gold answer can pass its own tests and still
not match its own description.** The ISBN gold above passes its tests — its
tests simply never included a string with a pipe in it.

## 4.3 The corpus can barely tell these models apart

**62% of tasks give every one of the 11 models the identical outcome** on
`usable` — all succeed or all fail. For `pass` it's 56%; for `vulnerable`,
77%.

Only about **167 of 450 tasks** do any work distinguishing models. We are
paying for 450 tasks and getting the statistical power of a third of that.

## 4.4 We initially used the wrong statistical test

Our first analysis compared models with independent confidence intervals.
That was wrong, and worth explaining because it is an easy mistake to
repeat.

All 11 models answered the **same 450 tasks**. Task difficulty is therefore
a *shared* source of variation. Treating the models as independent samples
charges each of them separately for that shared difficulty, which inflates
every interval and makes real differences look like noise.

The correct approach is a **paired** comparison: resample tasks, score
every model on the same resampled set, and look at the *differences*. Task
difficulty cancels, and only genuine disagreement carries weight.

| | pairwise comparisons resolved, of 55 |
| --- | --- |
| Independent intervals (wrong test) | 1 |
| Paired bootstrap — `usable@3` | **9** |
| Paired bootstrap — `pass@3` | **15** |
| Paired bootstrap — `vulnerable@3` | **15** |

Under the correct test the top model is distinguishable from seven of the
other ten. The middle of the table remains genuinely inseparable — for
instance `qwen3.6-max-preview` vs `gpt-5.6-sol` is +0.7% with an interval
of [−2.9%, +4.3%], which is a coin flip.

**Bands are defensible. A numbered 1-through-11 ranking is not.** That is
the single biggest reason this is not published as a leaderboard.

## 4.5 What we did not test

- **Contamination.** This corpus predates every model here and is almost
  certainly in their training data. Some of what we measured may be
  memorisation rather than capability. Without a private task set we
  cannot size it.
- **Thinking at scale.** §3.7 — 12 tasks, anecdotal.
- **Prompt sensitivity.** One prompt, unchanged. We don't know how much the
  numbers move under rephrasing. Given §4.1, we'd guess: quite a lot.
- **Any second corpus.** A ranking that flips between corpora isn't a
  ranking, and we haven't checked.

---

# Part 5 — Five ways this run nearly went silently wrong

We think this is the most transferable part of the write-up. Every item
here produced data that *looked* fine.

**1. A parameter combination that failed every single request.** Setting
`temperature` together with `require_parameters: true` returns a hard error
on 6 of the 11 models, which reject temperature outright. Our first pilot
failed all 396 calls this way. It was obvious because it failed loudly —
but only because we piloted before committing budget.

**2. A model that cannot comply with the experimental condition.** Gemini
3.6 Flash and 3.5 Flash **cannot disable reasoning** — the API returns
*"Reasoning is mandatory for this endpoint."* They therefore cannot appear
in a reasoning-off comparison at all. We substituted Gemini 3.1 Flash Lite,
which can. Had we not checked, we'd have compared one thinking model
against ten non-thinking ones and called the difference a capability gap.

**3. Empty responses that look like bad answers.** At a 200-token cap,
reasoning models spent the entire budget thinking and returned *no
content*. Scored naively that is an empty pattern, indistinguishable from a
model that answered badly. We classify empty completions as failed requests
and report them separately — and we distinguish the causes (safety refusal,
token exhaustion, provider glitch) using what the API actually reported
rather than guessing.

**4. A resume that silently mixed two experiments.** Our collection is
resumable, keyed by (model, task, attempt). When an aborted reasoning run
at a 400-token cap left three truncated rows behind, the relaunch at 4,000
tokens treated them as completed work — quietly interleaving two
configurations in one file, with nothing downstream able to tell them
apart. Every row now carries a fingerprint of the settings that produced
it, and a resume that finds foreign rows refuses to continue.

**5. A scoring bug that would have made every "@3" number a disguised
"@1".** Our scorer initially kept only the *last* of the three samples per
task. The metrics would have looked entirely plausible and been wrong.

Two more that were merely expensive rather than corrupting: three
collection processes died silently on a truncated HTTP response our retry
loop didn't catch — the other eight kept running, so the sweep looked
healthy while three models sat frozen — and we started scoring while
collection was still running, which starved the collection and slowed the
critical-path model tenfold.

---

# Part 6 — How to check us

Every model response is committed. Scores compute from those files and
nothing else — no API key, no cost, no need to trust us:

```bash
git clone https://github.com/plicara/regexeval-2026
cd regexeval-2026
make setup
make score RUN=sweep
```

We verified this the hard way: wiped to a clean checkout, reinstalled the
pinned scorer, re-downloaded the corpus, re-scored from scratch, and
confirmed **every metric came out identical**. A version of that check runs
in CI on every push, so the published numbers cannot drift away from the
evidence behind them.

**Controls.** Three synthetic answers ride through the identical scoring
path on every run: a known-good answer (the task's own reference) that must
pass, a known-bad one (`z{5}`) that must fail everything, and a
known-vulnerable one (`(a+)+b`) that must be flagged. If any misbehaves the
run is discarded rather than published. This catches the failure mode where
a scorer silently returns zeros — which looks exactly like a model that
failed, unless you plant a known-good answer and check it comes back good.
All controls behaved on all 11 models.

**Pinned versions.** Scoring by `regexbench` 0.4.0, pinned to a specific git
commit (it isn't on PyPI, so a version string wouldn't resolve to it).
Python 3.11. Corpus from its original repository. Models by full slug.

---

# Part 7 — Failures, stated rather than dropped

**54 of 14,850 requests failed (0.36%).** They stay in the table.

| Model | Failures | Cause |
| --- | ---: | --- |
| `claude-opus-5` | 29 | content-filter refusals (§3.5) |
| `kimi-k3` | 11 | our account's spending limit reached mid-run |
| `kimi-k3` | 3 | response arrived with no resolved provider |
| `gpt-5.6-sol` | 1 | response arrived with no resolved provider |

A response with no named provider is discarded rather than scored, because
a row without provenance isn't reproducible.

**Coverage is therefore not perfectly uniform.** Nine models cover all 450
tasks. `kimi-k3` covers 447 — the budget ran out during its collection.
`claude-opus-5` covers 444, from the refusals and one task where every reply
was a bare code fence. The gap is under 2% and
moves no conclusion, but the denominators genuinely differ and we'd rather
say so.

**A note on the budget.** We estimated the sweep at $9.70 from a 12-task
pilot and it came in at $10.95 — 13% over, because the wider corpus carries
longer prompts than the pilot sample. Combined with the pilot runs it
consumed the full $12, which is why the last few kimi calls were refused
and why the thinking comparison stayed at 12 tasks.

---

# Part 8 — Appendix: the harder metrics

| Model | dfa-eq@3 | dfa-eq@3 (decided) | exact@3 | undecidable | reformatted |
| --- | ---: | ---: | ---: | ---: | ---: |
| `kimi-k3` | 14.1% | 17.1% | 5.0% | 78 | 17 |
| `qwen3.6-max-preview` | 13.8% | 17.4% | 3.8% | 94 | 11 |
| `claude-opus-5` | 11.6% | 15.2% | 2.8% | 104 | 9 |
| `qwen3.6-plus` | 11.6% | 14.8% | 3.8% | 99 | 9 |
| `deepseek-v4-flash-0731` | 11.3% | 14.3% | 3.3% | 93 | 16 |
| `claude-sonnet-5` | 10.4% | 13.3% | 3.3% | 97 | 9 |
| `glm-5.2` | 10.4% | 12.9% | 3.8% | 86 | 18 |
| `gpt-5.6-terra` | 10.2% | 13.1% | 2.0% | 100 | 11 |
| `gpt-5.6-sol` | 9.4% | 13.3% | 1.8% | 133 | 7 |
| `gemini-3.1-flash-lite` | 9.3% | 11.8% | 3.1% | 95 | 16 |
| `gpt-5.6-luna` | 9.1% | 12.2% | 1.8% | 112 | 9 |

**`dfa-eq`** is Question 2 — the metric §4.1 says to distrust. Reported
twice: counting undecidable comparisons as failures, and excluding them.

**`exact@3`** is string-identical answers. At 1.8%–5.0% it exists only to
show how badly a string-comparison benchmark would misrank everyone.

**"Reformatted"** counts answers where the model wrapped its pattern in
host-language string syntax — `r'\d+$'` instead of `\d+$`. Scored literally
that fails for a reason unrelated to regex ability, so we strip one layer
of quoting before scoring. It affected 7–18 responses of 1,350 per model
(under 1.4% everywhere) and moves nothing. Every strip is recorded with
before and after, and the unnormalized score is kept alongside so anyone
who disagrees with the rule can use the other number without re-running
anything.

**One engine limitation worth knowing:** `\d` in Python matches every
Unicode digit, not just `0-9`. Our scorer runs the real Python engine, so
this is faithful — but it is the single thing most likely to make our
numbers differ from other published regex evaluations, and it accounts for
32% of the apparent "wrong meaning" verdicts (§4.1).

---

# Part 9 — What we'd say the takeaways are

1. **Regexes that pass their tests are not safe to ship.** About one in ten
   is exploitable, consistently across every model we tested.

2. **This is a human problem that models inherited.** The human-written
   reference answers are *more* vulnerable (13.6%) than any model's answers
   (7.3%–10.7%). Models learned this from us and are, if anything, slightly
   better at it.

3. **For this task, model choice barely matters and price matters a lot.**
   A 98× cost difference buys about three points, which is at the edge of
   what we can resolve at all.

4. **Benchmarks that compare against a human answer key are measuring the
   answer key too.** In our sample, only about a fifth of the "wrong
   meaning" verdicts were actually the model's fault. We'd encourage anyone
   reporting a similar metric to sample their disagreements and check.

5. **Safety filters fire on benign technical prompts**, inconsistently
   enough that a single sample cannot detect it.

6. **Hidden reasoning can cost 100× for no change in the answer** on tasks
   this small, and "low effort" settings do not reliably reduce it.

The most useful thing we can offer other people building evaluations is
point 4, and the discipline behind it:

> **Separate the metrics that consult a human answer key from the metrics
> that don't, and trust them differently.**

We did not design this benchmark around that distinction. We discovered it
by auditing our own results, and it changed what we were willing to
publish.

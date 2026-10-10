# AI in Product Development — worked examples

Minimal running examples for the workshop: how an agent actually works, what a
harness is made of, what it costs, and how to test it.

One agent, read six times, one idea added per file. One dependency, `anthropic`.
Where a file needs the loop it imports it from `example_harness.py` rather than
writing a second one, so the table below is also the reading order.

**Diagrams and the full breakdown:** [Miro board](https://miro.com/app/board/uXjVGrSH3Ho=/)

## Layout

```
examples/   the workshop code: read it in the order of the table below
free/       the same four examples on a free model — no key to pay for, no SDK
fixtures/   a service with comment drift planted in it — what the reviewer runs on
deck/       the talk as data: the slide spec in JSON, and the talk as text

examples/my-harness/   the same split on a third task, where the check is a
                       subprocess: code measures, the model splits, code runs it
```

Each directory has its own README, and the three with a task in them end with an
answer key:

| | |
|---|---|
| [`deck/README.md`](deck/README.md) | the slide spec, and why no `.pptx` is published |
| [`free/README.md`](free/README.md) | what changes on another provider, and what a smaller model costs you |
| [`fixtures/orders_service/README.md`](fixtures/orders_service/README.md) | the seven planted comments, and the one the finder walks past |
| [`examples/my-harness/README.md`](examples/my-harness/README.md) | the two plausible refactors that are wrong, and what catches them |

## The examples

| File | About | What you see on a run |
|---|---|---|
| `example_tool_loop.py` | How a tool call works | Four messages over the wire; the model asks, the code acts |
| `example_harness.py` | Verification in code | The model writes 00:05, the code rejects it, the model works out 24:05 itself |
| `example_wire.py` | Reading the wire | Every request and response body on disk, one file each |
| `example_cost.py` | What a run costs | The conversation is resent every round, and the retry has its own price tag |
| `example_cache.py` | Prompt caching | A 984-token prefix: written once at 1.25x, read at 0.10x, 25–30% off the run |
| `example_rag.py` | Search as a tool | First search misses, the model rephrases; on the second question an honest "I don't know" |
| `example_headless.py` | A whole agent behind the call | `claude -p` instead of the API; the same five lines still reject 00:05, and a subprocess can hang |
| `example_review.py` | Code before the model | Comments that name something the code no longer has — a set difference, no API key, no tokens |
| `example_review_agent.py` | The four jobs on one task | The model judges what code could not; the same `check()` then judges the model |
| `my-harness/example_complexity.py` | A measure, not a judgement | Statements per function; one is 30 and the limit is 12 |
| `my-harness/example_complexity_agent.py` | Verification that runs the code | The split is executed on eight golden inputs before it is believed |
| `test_harness.py` | Testing an agent | Nine tests, zero API calls |
| `test_review.py` | Testing the finder | Temporary repositories, no network, no git |
| `test_review_agent.py` | Testing the four jobs | What the tool returned, what the loop did, what state was dropped, what verification refused |

## Running it

Python 3.9 or newer, and one dependency:

```bash
pip3 install -r requirements.txt

cp .secrets.example .secrets && chmod 600 .secrets   # fill it in
source ./anthropic-env.sh on

python3 examples/example_tool_loop.py
```

`anthropic-env.sh` must be used with `source` — a child process cannot change its
parent shell's environment. `off` unsets the variables, `status` shows what is set.

Every example takes a path and runs from the repository root. Two of them need
neither the key nor the dependency: `example_review.py` is a set difference, and
`my-harness/example_complexity.py` is arithmetic.

### The tests

Six suites, 84 tests, no key, no network, no dependency:

```bash
python3 examples/test_harness.py                   #  9 — the loop and the check
python3 examples/test_review.py                    # 10 — the finder
python3 examples/test_review_agent.py              # 14 — the four jobs
python3 examples/my-harness/test_complexity.py     # 12 — the measure
python3 examples/my-harness/test_complexity_agent.py  # 23 — verification that runs code
python3 free/test_free.py                          # 16 — the free-tier port
```

## Without a key to pay for

`free/` holds the four examples that need a model, ported to Groq's free tier —
a key takes two minutes and costs nothing. The four jobs of a harness are
identical there; only the envelope changes, and the diff is the lesson:

```bash
export GROQ_API_KEY=gsk_...
python3 free/example_review_agent.py fixtures/orders_service
diff examples/example_harness.py free/example_harness.py
```

Details, the other providers it runs against, and what a smaller model costs you
in rehearsal: [`free/README.md`](free/README.md).

## The four jobs of a harness

An agent is a model plus the code around it. That code does four things, and all
four are visible in `example_harness.py`:

1. **Tools** — what the model is allowed to ask for;
2. **The loop** — call again, or stop;
3. **State** — what the model sees on this turn;
4. **Verification** — code inspects the result before accepting it.

The fourth one is usually missing. It is the one that catches the mistake no
instruction mentioned.

`example_review.py` and `example_review_agent.py` are the same task split along
that line: the half a set difference can do, and the half that needs judgement.
In the second file each job is labelled in the source and in the log, and the
verification is the first file's `check()` turned on the model's own answer.

`examples/my-harness/` splits a third task the same way, and takes verification
one step further: code does not read the model's refactor, it runs it on inputs
that came with the fixture. Details in
[`examples/my-harness/README.md`](examples/my-harness/README.md).

Run them on `fixtures/orders_service` — four files with seven comments that no
longer match the code, and an answer key in
[`fixtures/orders_service/README.md`](fixtures/orders_service/README.md):

```bash
python3 examples/example_review.py fixtures/orders_service         # 7 mentions, no key
python3 examples/example_review_agent.py fixtures/orders_service   # 3 stale, 3 foreign, 1 fine
```

A run from the repository root leaves `fixtures/` out, so the two numbers on
this repository stay what they were.

## The deck

`deck/` holds the talk as data, not as a binary. The 22 slides are one JSON
object each in [`deck_brand.json`](deck/deck_brand.json); edits are made in the
spec and the deck is rebuilt, never patched in PowerPoint.

**Read the talk:** [`deck/OUTLINE.md`](deck/OUTLINE.md) — all 22 slides as text,
generated from the spec by [`deck/render_outline.py`](deck/render_outline.py).

```bash
python3 deck/render_outline.py            # rewrite OUTLINE.md from the spec
python3 deck/render_outline.py --check     # fail if OUTLINE.md is stale
```

The rendered `.pptx`, the PDF and the brand fonts are not published: the fonts
are licensed and the deck is built from a corporate template. `OUTLINE.md` is
there so none of that is needed to read the talk. Details and the slide spec:
[`deck/README.md`](deck/README.md).

Every slide that shows a number or a log has a file here that produced it:

| Slides | What is on them | The file |
|---|---|---|
| 6–8 | the four jobs; `00:05` rejected, `24:05` accepted | `example_harness.py` |
| 9–10 | the tool-call round trip; the four silent `stop_reason`s | `example_tool_loop.py` |
| 11 | the six messages, appended then resent in full | `example_wire.py` |
| 12–13 | 425 then 593 then 1247 input tokens; $0.036 a run | `example_cost.py` |
| 14–15 | 1.00x, 1.25x, 0.10x — and the date that kills the cache | `example_cache.py` |
| 16 | decisions moving from model to code | `example_review.py`, `example_review_agent.py` |
| 17–18 | retrieval as the weak link; the citation the code refuses | `example_rag.py` |
| 20–21 | decide four things; the filter for your own idea | `my-harness/`, and the table below |

Slide 21 names four kinds of check, one per file — that is the whole repository
in four lines:

| The check | Where it runs |
|---|---|
| something must exist | `example_review.py` — the name is in the code, or it is not |
| numbers must match | `example_harness.py` — 23:47 cannot precede 00:05 |
| code must run | `my-harness/` — the refactor is executed on eight golden inputs |
| the answer goes back through the check | `example_review_agent.py` — `check()` turned on the model |

## Caveats

Prices in `example_cost.py` and `example_cache.py` are constants at the top of each
file. Check them against the current price list.

A corporate gateway may not proxy `count_tokens`. Workaround: make a normal call
with a small `max_tokens` and read `usage.input_tokens`.

The model is nondeterministic: numbers move by a few tokens between runs. Every
measured number in this repository and in the deck has a date next to it.

## License

[MIT](LICENSE) for the code. The brand fonts and the corporate slide template
are not covered by it and are not published here.

# my-harness — the check is a subprocess

A third task split along the line the other two are split along: the half a
number can do, and the half that needs judgement.

Code measures every function and lists the ones over a limit. That is arithmetic
and it needs no model. Splitting one is judgement, so it goes to the model — and
then code **runs** what came back.

```bash
python3 example_complexity.py fixtures/billing     # no key, no tokens
python3 test_complexity.py                         # no key, no network
python3 test_complexity_agent.py                   # no key, no network

source ../../anthropic-env.sh on
python3 example_complexity_agent.py fixtures/billing
```

```
example_complexity.py          the measure; no model, no key
example_complexity_agent.py    the harness; the four jobs are labelled in it
driver.py                      the fifth check from the inside: run, not imported
fixtures/billing/billing.py    the service; settle_invoice is 30 statements
fixtures/billing/cases.py      the golden inputs
fixtures/billing/refactored.py the answer, written out -- what the tests build on
```

## What is different about this one

In `example_harness.py` and `example_review_agent.py`, code reads the model's
answer. Here it executes it.

A refactor can parse, keep the name and the signature, land every function under
the limit, read better than the original, and satisfy every sentence in the
system prompt — and still return something else on one input out of eight.
Reading it will not tell you. Running it will.

| Job | Where it is |
|---|---|
| Tools | `measure_code` — the model may count its draft, not test it |
| The loop | two refused refactors, then a human; a hard cap on calls |
| State | one conversation per function, dropped before the next |
| Verification | five checks, cheapest first; the fifth starts a process |

The five, in order: it parses; the function is still there; the signature is
unchanged; no import was added; every function is within the limit — and then
the golden cases, in a fresh interpreter, with a timeout.

## The golden inputs

`fixtures/billing/cases.py` ships eight argument lists. The harness runs the
function on them **before** the model is asked anything, keeps what came back,
runs the model's version on the same eight, and compares three things: the
return value, the exception, and the arguments after the call.

The third one is not decoration. `settle_invoice` appends to
`invoice["history"]`, so a split that appends to a copy returns the right number
on all eight cases and still breaks every caller.

The cases are ours. The model cannot reach them and is not asked to write them:
no model gets to set its own exam.

## What the run cost

The last table in the log is arithmetic too — a meter at the one seam every call
goes through, so the loop keeps no books.

```
FUNCTION          ROUND  MSGS      IN    OUT       COST  WHY
settle_invoice        1     1    1635   1589    $0.0192
settle_invoice        2     3    3282    592    $0.0125  the model asked to be measured
TOTAL                            4917   2181    $0.0316
```

Three cents, and round two is most of the story: the answer got shorter and the
bill did not, because the whole conversation is resent every round. A round you
did not need is never cheap — which is the argument for checking in code, where
a round costs nothing.

## The answer key

`settle_invoice` is 30 statements and the limit is 12. `summary` is 11 and is
left alone — a measure that flagged it is a measure nobody keeps switched on.

Two plausible splits are wrong, and the system prompt mentions neither:

| The mistake | Why it looks fine | What catches it |
|---|---|---|
| the `cancelled` branch lifted into a helper | the helper returns 0 — but the caller does not, and prices a cancelled invoice | the return value on case 2 |
| `setdefault("history", [])` becomes `list(...)` | every one of the eight returns the right number | the argument after the call |

Both are in `test_complexity_agent.py`, with `verify()` run on them directly, so
the check is proved without a key — along with the test that says the line count
alone would have accepted both.

Measured on 2026-10-10, six runs on `claude-sonnet-5`: every one called
`measure_code` on a draft first, and every one was accepted on the first answer,
split four to seven ways. One of them lifted the `cancelled` branch into a
helper — the exact shape that goes wrong when the return is dropped — and got it
right. Code did not have to take its word for it.

That is the outcome to want. Verification is insurance, not theatre: it earns
its keep on the run where the answer is wrong, and you do not get to know in
advance which run that is.

## Twelve is a convention, not a law

```bash
python3 example_complexity.py ../..      # this repository, measured by its own tool
```

It flags sixteen functions, and three of them are in this harness: `verify`,
`refactor` and `run`. A loop you have to read in one sitting is better in one
piece, and `verify` is five checks in the order they are cheapest — splitting
either would cost more than it bought.

So the number is right and the conclusion is still no. That is an argument about
the limit, which is a constant in one file. It is not an argument about the
measure, and it is not the model's to make either.

## The exercise

Switch the fifth check off — let `behaviour()` return nothing and `compare()`
return `None` — and run the tests. Nineteen of the twenty-three still pass. Four
stop, and those four are the whole reason this example exists.

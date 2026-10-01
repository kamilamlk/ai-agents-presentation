# AI in Product Development — worked examples

Minimal running examples for the workshop: how an agent actually works, what a
harness is made of, what it costs, and how to test it.

One agent, read six times, one idea added per file. One dependency, `anthropic`.
Where a file needs the loop it imports it from `example_harness.py` rather than
writing a second one, so the table below is also the reading order.

**Diagrams and the full breakdown:** [Miro board](https://miro.com/app/board/uXjVGrSH3Ho=/)

## The examples

| File | About | What you see on a run |
|---|---|---|
| `example_tool_loop.py` | How a tool call works | Four messages over the wire; the model asks, the code acts |
| `example_harness.py` | Verification in code | The model writes 00:05, the code rejects it, the model works out 24:05 itself |
| `example_wire.py` | Reading the wire | Every request and response body on disk, one file each |
| `example_cost.py` | What a run costs | The conversation is resent every round, and the retry has its own price tag |
| `example_cache.py` | Prompt caching | A 984-token prefix: written once at 1.25x, read at 0.10x, 25–30% off the run |
| `example_rag.py` | Search as a tool | First search misses, the model rephrases; on the second question an honest "I don't know" |
| `test_harness.py` | Testing an agent | Nine tests, zero API calls |

## Running it

```bash
pip3 install anthropic

cp .secrets.example .secrets && chmod 600 .secrets   # fill it in
source ./anthropic-env.sh on

python3 example_tool_loop.py
```

`anthropic-env.sh` must be used with `source` — a child process cannot change its
parent shell's environment. `off` unsets the variables, `status` shows what is set.

The tests need no key and no network:

```bash
python3 test_harness.py
```

## The four jobs of a harness

An agent is a model plus the code around it. That code does four things, and all
four are visible in `example_harness.py`:

1. **Tools** — what the model is allowed to ask for;
2. **The loop** — call again, or stop;
3. **State** — what the model sees on this turn;
4. **Verification** — code inspects the result before accepting it.

The fourth one is usually missing. It is the one that catches the mistake no
instruction mentioned.

## Caveats

Prices in `example_cost.py` and `example_cache.py` are constants at the top of each
file. Check them against the current price list.

A corporate gateway may not proxy `count_tokens`. Workaround: make a normal call
with a small `max_tokens` and read `usage.input_tokens`.

The model is nondeterministic: numbers move by a few tokens between runs.

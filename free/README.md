# free/ — the same four examples on a free model

The four files in `examples/` that need a model, ported to Groq's free tier. No
card, no bill, no SDK: one `urllib` POST in [`wire.py`](wire.py) is the whole
transport, so the wire stays readable.

```bash
# a key takes about two minutes: https://console.groq.com/keys
export GROQ_API_KEY=gsk_...

python3 free/wire.py                                            # what this key can reach today
python3 free/example_tool_loop.py                               # four messages over the wire
python3 free/example_harness.py                                 # the check says no
python3 free/example_rag.py                                     # search as a tool
python3 free/example_review_agent.py fixtures/orders_service    # the stale-comment reviewer
```

The tests need no key and no network:

```bash
python3 free/test_free.py
```

Keep the key in `.secrets` instead and `source ./anthropic-env.sh on` loads it.
A free key alone is enough now: without an Anthropic token the script says so
and carries on.

## What changes, and what does not

| | `examples/` | `free/` |
|---|---|---|
| Tools | `input_schema` | `{"type": "function", "function": {..., "parameters": ...}}` |
| The ask | `block.type == "tool_use"` | `message["tool_calls"]`, arguments as a JSON **string** |
| Done? | `stop_reason` | `finish_reason` (`tool_calls`, `stop`, `length`) |
| The result | a block in a user message | its own message, `role: "tool"` |
| The system prompt | a parameter | the first message |
| Transport | `anthropic` SDK | 40 lines of `urllib` |
| **The loop, the state, the check** | — | **unchanged** |

The bottom row is the lesson. See it for yourself:

```bash
diff examples/example_harness.py free/example_harness.py
```

`free/example_review_agent.py` goes further and does not port its code half at
all: `check()`, `mentioned()` and `review()` are imported from
`examples/example_review.py`. A set difference has no provider.

## Another provider, same four files

`wire.py` reads two variables, so nothing in the examples has to change:

```bash
FREE_BASE_URL=http://localhost:11434/v1 FREE_MODEL=qwen2.5-coder python3 free/example_rag.py
FREE_BASE_URL=https://openrouter.ai/api/v1 FREE_MODEL=...:free  python3 free/example_rag.py
```

With a local model the key is not needed at all.

## What a smaller model costs you

Not money — rehearsal time. Expect these, and say them out loud rather than
hiding them, because every one of them is the harness doing its job:

- **`403` with `error code: 1010`, before any key is checked.** Cloudflare sits
  in front of Groq and refuses the signature `urllib` introduces itself with,
  `Python-urllib/3.9`. Measured on the same URL, same network, same minute:
  `curl -A "Python-urllib/3.9"` → 403, `curl -A "Mozilla/5.0"` → 401. That is
  what `USER_AGENT` in `wire.py` is for, and why the SDK in `examples/` never
  meets this: it sends a header of its own. Worth saying out loud on stage —
  "the model refused" and "the CDN refused" look identical from the traceback.
- **`00:05` may not happen.** The midnight demo in `example_harness.py` only
  fires if the model copies the printed time. A smaller model may write `24:05`
  first try, or need the retry twice. Run it a few times before the talk and
  narrate what you actually see.
- **More refusals in the reviewer.** `verify()` turns down more verdicts, and
  more mentions end up with a human. That is the slide about the loop, live.
- **Arguments are not always JSON.** `wire.arguments()` raises on a malformed
  tool call and the reviewer hands the error back as the tool result; the model
  gets another turn. A real failure mode the paid examples rarely show.
- **Model ids retire.** Run `python3 free/wire.py` first, always. On
  2026-10-10 a free key reached `openai/gpt-oss-120b`, `openai/gpt-oss-20b`,
  `qwen/qwen3.8-27b` and `allam-2-7b` — and not one Llama id, though every
  tutorial still names them: they moved behind a sales conversation. The rest of
  that list is speech and classifier models, which will not answer a chat call
  at all.

## What is not here

`example_cache.py` and `example_cost.py` do not port honestly. Prompt caching
with `cache_control` is Anthropic's own, and a run that costs nothing has no
price list to read. `example_headless.py` is `claude -p`, which is not a free
model at all. `example_wire.py` has no free twin either: `example_tool_loop.py`
in this directory already writes `wire_free.json` on every turn.

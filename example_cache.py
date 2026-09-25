"""
The same thing again, with prompt caching, and a measurement of what it saves.

Runs the same request three times in a row. This imitates a harness that calls
the model once per page: the instructions and the tool definitions do not change
from page to page, only the question does.

Run:
    source ./anthropic-env.sh on
    python3 example_cache.py

What to see with your own eyes:
  run 1 - cache_creation above zero: the cache was written, you paid 1.25x
  run 2 - cache_read above zero:     the cache was read, you paid 0.10x
  run 3 - the same

ABOUT THE MINIMUM. A cacheable prefix must be at least 512 tokens (on Claude
Opus 5; other models have different minimums, not always smaller). A shorter
prefix is NOT cached and says nothing about it: no error, just zeros in usage.
TOOLS alone is not enough here, they weigh about 378 tokens. That is why a system
prompt was added, and together they clear the threshold. The script checks this
itself and tells you if the cache did not engage.

The breakpoint sits on the system block rather than on the tools, because the
prompt is assembled in this order: tools, then system, then messages. A
breakpoint on system covers both.
"""

import anthropic

client = anthropic.Anthropic()

MODEL = "claude-opus-5"
PRICE_IN = 5.00
PRICE_OUT = 25.00
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10
MIN_CACHEABLE = 512

RUNS = 3


SYSTEM = """You extract public transport timetables.

Parsing rules:
- Always normalise times to HH:MM:SS.
- Write trips past midnight as 25:10:00, not 01:10:00: a service day continues
  past midnight, and the substitution moves the trip into a different day.
- If the source lists several routes, parse them separately and never mix their
  times together.
- Footnotes such as "weekdays only" belong to the calendar, not to the time.
- If there is no data for a city, say so. Do not invent anything.
- Never invent stops that are not in the source.
- Answer briefly, with no preamble and without restating these rules."""


TIMETABLES = {
    "Yaroslavl": "5A: 06:15, 06:47, 07:20, 07:53 | 21: 05:58, 06:30, 07:02",
    "Kostroma": "3: 06:05, 06:40, 07:15 | 11: 06:22, 07:00",
}


def read_timetable(city: str) -> str:
    return TIMETABLES.get(city, "no data for this city")


TOOLS = [
    {
        "name": "read_timetable",
        "description": "Returns the raw bus timetable for a given city.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"},
            },
            "required": ["city"],
        },
    }
]

# Here it is, the only meaningful difference: the cache breakpoint.
SYSTEM_CACHED = [
    {
        "type": "text",
        "text": SYSTEM,
        "cache_control": {"type": "ephemeral"},
    }
]


def parts(usage):
    """The three parts of a prompt. input_tokens is only the uncached remainder."""
    fresh = usage.input_tokens
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    return fresh, written, read


def money(usage) -> float:
    fresh, written, read = parts(usage)
    return (
        fresh * PRICE_IN
        + written * PRICE_IN * CACHE_WRITE_MULT
        + read * PRICE_IN * CACHE_READ_MULT
        + usage.output_tokens * PRICE_OUT
    ) / 1_000_000


def money_without_cache(usage) -> float:
    """What the same request would have cost if caching did not exist."""
    fresh, written, read = parts(usage)
    return ((fresh + written + read) * PRICE_IN + usage.output_tokens * PRICE_OUT) / 1_000_000


def one_run():
    """A full exchange. Returns the usage of every response."""
    messages = [
        {"role": "user", "content": "What time is the first 5A bus in Yaroslavl?"}
    ]
    used = []

    for _ in range(5):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_CACHED,
            tools=TOOLS,
            messages=messages,
        )
        used.append(response.usage)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return used

        results = [
            {
                "type": "tool_result",
                "tool_use_id": b.id,
                "content": read_timetable(**b.input),
            }
            for b in response.content
            if b.type == "tool_use"
        ]
        messages.append({"role": "user", "content": results})

    raise RuntimeError("the model did not finish within 5 turns")


print(f"\n{'RUN':>5} {'FRESH':>8} {'WRITE':>8} {'READ':>8} {'OUT':>7} {'CACHED':>10} {'PLAIN':>10}")
print("-" * 62)

total_cached = total_plain = 0.0
g_fresh = g_written = g_read = g_out = 0

for run in range(1, RUNS + 1):
    used = one_run()
    fresh = sum(parts(u)[0] for u in used)
    written = sum(parts(u)[1] for u in used)
    read = sum(parts(u)[2] for u in used)
    out = sum(u.output_tokens for u in used)
    c = sum(money(u) for u in used)
    p = sum(money_without_cache(u) for u in used)

    total_cached += c
    total_plain += p
    g_fresh += fresh
    g_written += written
    g_read += read
    g_out += out

    print(f"{run:>5} {fresh:>8} {written:>8} {read:>8} {out:>7} {'$%.5f' % c:>10} {'$%.5f' % p:>10}")

print("-" * 62)
print(f"{'TOTAL':>5} {'':>8} {'':>8} {'':>8} {'':>7} {'$%.5f' % total_cached:>10} {'$%.5f' % total_plain:>10}")

prompt_total = g_fresh + g_written + g_read

print("\nHOW THIS WAS COMPUTED, totals across all runs")
print(f"  fresh input  {g_fresh:>6} x ${PRICE_IN}/1M x 1.00  = ${g_fresh * PRICE_IN / 1e6:.5f}")
print(f"  cache write  {g_written:>6} x ${PRICE_IN}/1M x {CACHE_WRITE_MULT:.2f}  = ${g_written * PRICE_IN * CACHE_WRITE_MULT / 1e6:.5f}")
print(f"  cache read   {g_read:>6} x ${PRICE_IN}/1M x {CACHE_READ_MULT:.2f}  = ${g_read * PRICE_IN * CACHE_READ_MULT / 1e6:.5f}")
print(f"  output       {g_out:>6} x ${PRICE_OUT}/1M         = ${g_out * PRICE_OUT / 1e6:.5f}")
print(f"  {'':>13}{'':>6}{'':>21}  ---------")
print(f"  with cache   {'':>6}{'':>21}  ${total_cached:.5f}")
print()
print(f"  Whole prompt: {g_fresh} + {g_written} + {g_read} = {prompt_total} tokens.")
print(f"  Without a cache those same {prompt_total} would all bill at the full rate:")
print(f"  {prompt_total} x ${PRICE_IN}/1M + {g_out} x ${PRICE_OUT}/1M = ${total_plain:.5f}")
print("  No second run is needed for that: the tokens are measured, only the rate is hypothetical.")

if g_written == 0 and g_read == 0:
    print(
        f"\nTHE CACHE DID NOT ENGAGE. No write, no read. Most common cause: the prefix "
        f"is shorter than {MIN_CACHEABLE} tokens, the threshold for {MODEL}. "
        f"This never raises an error, it only leaves zeros in usage."
    )
else:
    saved = total_plain - total_cached
    pct = saved / total_plain * 100 if total_plain else 0
    print(f"\nSaved across {RUNS} runs: ${saved:.5f}, that is {pct:.0f}%.")
    if g_written > 0:
        print("The first run costs more: a cache write is 1.25x. It pays off from the second.")
    else:
        print(
            "No write happened at all: the prefix was already cached by an earlier run. "
            "An entry lives 5 minutes, so wait that long and run again to see the write."
        )

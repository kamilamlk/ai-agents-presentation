"""
The same agent as example_tool_loop.py, with a price tag.

After every turn it prints how many tokens went in, how many came back, how much
of the output was hidden reasoning, and what it cost.

Run:
    source ./anthropic-env.sh on
    python3 example_cost.py

What to see with your own eyes:
  1. Input on the second turn is larger than on the first, although the question
     never changed: the conversation grew, and you pay for it again.
  2. Output is smaller than input in token count, but comparable in money:
     it costs five times more per token.
"""

import anthropic

client = anthropic.Anthropic()

MODEL = "claude-opus-5"

# Dollars per 1,000,000 tokens. Check these before you present: prices change.
PRICE_IN = 5.00
PRICE_OUT = 25.00

# Cache multipliers: a write costs more than plain input, a read costs far less.
CACHE_WRITE_MULT = 1.25   # 5-minute TTL
CACHE_READ_MULT = 0.10


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


def money(usage) -> float:
    """Cost of one response, in dollars.

    Watch input_tokens: it is NOT the whole prompt, only the part that missed
    the cache. Total prompt size is the sum of three fields.
    """
    fresh = usage.input_tokens
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0

    return (
        fresh * PRICE_IN
        + written * PRICE_IN * CACHE_WRITE_MULT
        + read * PRICE_IN * CACHE_READ_MULT
        + usage.output_tokens * PRICE_OUT
    ) / 1_000_000


messages = [
    {"role": "user", "content": "What time is the first 5A bus in Yaroslavl?"}
]

rows = []

for turn in range(5):
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        tools=TOOLS,
        messages=messages,
    )
    u = response.usage
    rows.append(
        {
            "turn": len(rows) + 1,
            "in": u.input_tokens,
            "out": u.output_tokens,
            "thought": getattr(u.output_tokens_details, "thinking_tokens", 0)
            if getattr(u, "output_tokens_details", None)
            else 0,
            "cost": money(u),
        }
    )

    messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason != "tool_use":
        answer = "".join(b.text for b in response.content if b.type == "text")
        break

    results = []
    for block in response.content:
        if block.type == "tool_use":
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": read_timetable(**block.input),
                }
            )
    messages.append({"role": "user", "content": results})
else:
    raise RuntimeError("the model did not finish within 5 turns")


print(f"\n{'TURN':>5} {'IN':>7} {'OUT':>7} {'THOUGHT':>8} {'COST':>11}")
print("-" * 42)
for r in rows:
    print(f"{r['turn']:>5} {r['in']:>7} {r['out']:>7} {r['thought']:>8} {'$%.5f' % r['cost']:>11}")
print("-" * 42)
print(
    f"{'TOTAL':>5} {sum(r['in'] for r in rows):>7} {sum(r['out'] for r in rows):>7}"
    f" {sum(r['thought'] for r in rows):>8} {'$%.5f' % sum(r['cost'] for r in rows):>11}"
)

read_cost = sum(r["in"] for r in rows) * PRICE_IN / 1e6
write_cost = sum(r["out"] for r in rows) * PRICE_OUT / 1e6
print(f"\nfor reading: ${read_cost:.5f}   for writing: ${write_cost:.5f}")
print(f"\nANSWER: {answer}")

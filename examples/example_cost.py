"""
The same harness run as example_harness.py, with a price tag.

    source ./anthropic-env.sh on
    python3 example_cost.py
    python3 example_cost.py "When does 5A leave Chorsu?"

There is no second loop here. A meter stands where the client stands -- the same
seam the tests use to slip in a fake, and example_wire.py to slip in a recorder.

What to see with your own eyes:
  1. MSGS and IN grow every round, although the question never changed. The whole
     conversation is resent each time, and you pay for it again.
  2. The last round exists only because the code rejected the one before it.
     Checking in code is free. The retry it triggers is not, and the bottom line
     says exactly how much it was.
  3. Output is far smaller than input in tokens, yet comparable in money: it
     costs five times more per token.
"""

import sys

import anthropic

from example_harness import QUESTION, run

# Dollars per 1,000,000 tokens. Check these before you present: prices change.
PRICE_IN = 5.00
PRICE_OUT = 25.00

# Cache multipliers: a write costs more than plain input, a read costs far less.
CACHE_WRITE_MULT = 1.25   # 5-minute TTL
CACHE_READ_MULT = 0.10


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


def after_rejection(messages) -> bool:
    """Was this round bought by the check? The rejection is the last message."""
    last = messages[-1]
    return isinstance(last.get("content"), str) and last["content"].startswith("Not good")


class Meter:
    """Stands where the client stands and remembers what each round cost."""

    def __init__(self, client):
        self.client = client
        self.rows = []
        self.messages = self       # so meter.messages.create(...) works

    def create(self, **kw):
        response = self.client.messages.create(**kw)
        u = response.usage
        details = getattr(u, "output_tokens_details", None)

        self.rows.append(
            {
                "round": len(self.rows) + 1,
                "msgs": len(kw["messages"]),
                "in": u.input_tokens,
                "out": u.output_tokens,
                "thought": getattr(details, "thinking_tokens", 0) if details else 0,
                "cost": money(u),
                "retry": after_rejection(kw["messages"]),
            }
        )
        return response


meter = Meter(anthropic.Anthropic())
answer = run(meter, " ".join(sys.argv[1:]) or QUESTION)

rows = meter.rows

print(f"\n{'ROUND':>5} {'MSGS':>5} {'IN':>7} {'OUT':>7} {'THOUGHT':>8} {'COST':>11}  WHY")
print("-" * 60)
for r in rows:
    why = "the code rejected the round before" if r["retry"] else ""
    print(
        f"{r['round']:>5} {r['msgs']:>5} {r['in']:>7} {r['out']:>7} {r['thought']:>8}"
        f" {'$%.5f' % r['cost']:>11}  {why}"
    )
print("-" * 60)
print(
    f"{'TOTAL':>5} {'':>5} {sum(r['in'] for r in rows):>7} {sum(r['out'] for r in rows):>7}"
    f" {sum(r['thought'] for r in rows):>8} {'$%.5f' % sum(r['cost'] for r in rows):>11}"
)

read_cost = sum(r["in"] for r in rows) * PRICE_IN / 1e6
write_cost = sum(r["out"] for r in rows) * PRICE_OUT / 1e6
print(f"\nfor reading: ${read_cost:.5f}   for writing: ${write_cost:.5f}")

retries = [r for r in rows if r["retry"]]
if retries:
    paid = sum(r["cost"] for r in retries)
    share = paid / sum(r["cost"] for r in rows) * 100
    print(
        f"\n{len(retries)} of {len(rows)} rounds existed only because the check failed:"
        f" ${paid:.5f}, {share:.0f}% of this run."
    )
    print("The check itself cost nothing. Being wrong is what costs money.")
else:
    print("\nNo round was rejected this time, so no retry was paid for.")

print(f"\nANSWER: {', '.join(answer)}")

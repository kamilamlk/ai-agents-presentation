"""
The same harness run as example_harness.py, three times, with prompt caching.

    source ./anthropic-env.sh on
    python3 example_cache.py

The cache is a property of the transport, not of the agent. So it lives in a
layer that sits between the harness and the API: it prepends a long instruction
block, marks the breakpoint, forwards the call, and counts. The harness is not
aware any of this is happening -- same seam the tests use to slip in a fake.

What to see with your own eyes:
  run 1 - cache_creation above zero: the prefix was written, you paid 1.25x
  run 2 - cache_read above zero:     the prefix was read, you paid 0.10x
  run 3 - the same

And the thing worth saying out loud: PREFIX is four hundred tokens of careful
parsing rules, read on every single call, and the code still has to reject the
answer. Nowhere does the prefix mention that a service day runs past midnight,
because nobody had met that bug yet. A long prompt is not a substitute for a
check. It is a list of the bugs somebody already found.

ABOUT THE MINIMUM. A prefix shorter than the model's minimum is NOT cached, and
nothing says so: no error, just zeros in usage. The number differs by model and
is easy to be wrong about -- measured here, a 584-token prefix cached nothing and
a 996-token one cached fine, so this script reports the size it actually sent
rather than trusting a constant.

The breakpoint sits on the first system block, which covers everything before it:
the prompt is assembled as tools, then system, then messages. TOOLS is about 380
tokens and PREFIX carries the rest. The harness's own one-line system prompt goes
in a second block, after the breakpoint, where it belongs -- it is the only part
that could ever change.
"""

import sys

import anthropic

from example_harness import QUESTION, run

PRICE_IN = 5.00
PRICE_OUT = 25.00
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10

RUNS = 3


# -- The cacheable prefix ---------------------------------------------------
#
# Identical on every call, which is the whole point: it is what gets cached.
# Read it looking for the rule that would have prevented the bug. It is not here.

PREFIX = """You extract public transport timetables from raw, messy sources: scanned
tables, PDF text dumps, operator web pages, spreadsheets exported badly.

OUTPUT
- Answer with the requested structure and nothing else. No preamble, no apology,
  no restatement of these rules, no commentary on how hard the source was.
- When the question asks for times, give times. Do not add distances, fares,
  journey durations, or advice about which bus to take.

TIMES
- Give times in HH:MM. Do not round them, and do not invent precision the source
  does not have: a table printed to the minute stays to the minute.
- A time is a point, not a range. If the source prints a range, keep both ends.
- Footnote markers attached to a time belong to the calendar, not to the time.
  Keep them out of the time itself and mention them separately if asked.

ROUTES
- Route identifiers are opaque labels. 5A, 5a, 05A and 5-A may be four different
  routes in one city. Copy them character for character.
- When a source lists several routes in one table, parse them separately. Never
  merge their times into one sequence, however similar the headways look.
- A route may run a different pattern in each direction. Unless the question names
  a direction, do not assume the two are mirror images.

STOPS
- Stop names are copied, never normalised, never translated, never abbreviated.
  Transliteration spellings differ between sources and both may be in use.
- Never introduce a stop that does not appear in the source, not even an obvious
  interchange that any local would expect to be on the line.
- A stop with no time in a column is a stop the trip does not serve, or a cell the
  source left blank. Either way there is no time for it. Leave it empty.

WHEN THE SOURCE IS UNCLEAR
- Say what is missing rather than filling it in. An incomplete answer that is
  correct is worth more than a complete one that is invented.
- If two readings of the table are both defensible, give the one the layout
  supports and name the other.
- If the source contradicts itself, report the contradiction. Do not pick a side
  silently and do not average the two."""


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


class Cached:
    """Sits between the harness and the API. Adds the prefix, marks the breakpoint.

    The harness passes its own one-line system prompt; that line goes in a second
    block, after the breakpoint, so it stays outside the cached part. Only the
    prefix and the tool definitions are cached, and only they are identical from
    one call to the next.
    """

    def __init__(self, client, prefix=PREFIX):
        self.client = client
        self.prefix = prefix
        self.used = []
        self.messages = self

    def create(self, **kw):
        own = kw.get("system")
        kw["system"] = [
            {
                "type": "text",
                "text": self.prefix,
                "cache_control": {"type": "ephemeral"},   # <- the breakpoint
            }
        ]
        if own:
            kw["system"].append({"type": "text", "text": own})

        response = self.client.messages.create(**kw)
        self.used.append(response.usage)
        return response


def quiet(*a, **kw):
    pass


client = anthropic.Anthropic()
question = " ".join(sys.argv[1:]) or QUESTION

# -- First the harness does its work, and says so -----------------------------

rows = []
first_round_prompt = first_segment = 0

for n in range(1, RUNS + 1):
    layer = Cached(client)
    # The first run narrates itself; after that the log would only repeat.
    run(layer, question, log=print if n == 1 else quiet)

    if n == 1:
        p = parts(layer.used[0])
        first_round_prompt = sum(p)
        first_segment = p[1] + p[2]      # what the breakpoint actually covered
        
    rows.append(
        {
            "run": n,
            "rounds": len(layer.used),
            "fresh": sum(parts(u)[0] for u in layer.used),
            "written": sum(parts(u)[1] for u in layer.used),
            "read": sum(parts(u)[2] for u in layer.used),
            "out": sum(u.output_tokens for u in layer.used),
            "cached": sum(money(u) for u in layer.used),
            "plain": sum(money_without_cache(u) for u in layer.used),
        }
    )


# -- Then the bill ------------------------------------------------------------

def total(key):
    return sum(r[key] for r in rows)


g_fresh, g_written, g_read, g_out = (total(k) for k in ("fresh", "written", "read", "out"))
total_cached, total_plain = total("cached"), total("plain")
prompt_total = g_fresh + g_written + g_read

print(f"\n{'RUN':>4} {'ROUNDS':>7} {'FRESH':>8} {'WRITE':>8} {'READ':>8} {'OUT':>7}"
      f" {'CACHED':>10} {'PLAIN':>10}")
print("-" * 70)
for r in rows:
    print(f"{r['run']:>4} {r['rounds']:>7} {r['fresh']:>8} {r['written']:>8} {r['read']:>8}"
          f" {r['out']:>7} {'$%.5f' % r['cached']:>10} {'$%.5f' % r['plain']:>10}")
print("-" * 70)
print(f"{'TOTAL':>4} {'':>7} {g_fresh:>8} {g_written:>8} {g_read:>8} {g_out:>7}"
      f" {'$%.5f' % total_cached:>10} {'$%.5f' % total_plain:>10}")

print("\nHOW THIS WAS COMPUTED, totals across all runs")
print(f"  fresh input  {g_fresh:>6} x ${PRICE_IN}/1M x 1.00  = ${g_fresh * PRICE_IN / 1e6:.5f}")
print(f"  cache write  {g_written:>6} x ${PRICE_IN}/1M x {CACHE_WRITE_MULT:.2f}  = ${g_written * PRICE_IN * CACHE_WRITE_MULT / 1e6:.5f}")
print(f"  cache read   {g_read:>6} x ${PRICE_IN}/1M x {CACHE_READ_MULT:.2f}  = ${g_read * PRICE_IN * CACHE_READ_MULT / 1e6:.5f}")
print(f"  output       {g_out:>6} x ${PRICE_OUT}/1M         = ${g_out * PRICE_OUT / 1e6:.5f}")
print(f"  {'':>13}{'':>6}{'':>21}  ---------")
print(f"  with cache   {'':>6}{'':>21}  ${total_cached:.5f}")
print()
print(f"  Cached segment: {first_segment} tokens -- TOOLS plus PREFIX, everything")
print("  before the breakpoint. That is the part that never changes.")
print()
print(f"  Whole prompt: {g_fresh} + {g_written} + {g_read} = {prompt_total} tokens.")
print(f"  Without a cache those same {prompt_total} would all bill at the full rate:")
print(f"  {prompt_total} x ${PRICE_IN}/1M + {g_out} x ${PRICE_OUT}/1M = ${total_plain:.5f}")
print("  No second run is needed for that: the tokens are measured, only the rate is hypothetical.")

if g_written == 0 and g_read == 0:
    print("\nTHE CACHE DID NOT ENGAGE. No write, no read, and no error either.")
    print(f"  The first prompt was {first_round_prompt} tokens in total. Two causes, in order")
    print("  of likelihood: the cached segment is under this model's minimum, so lengthen")
    print("  PREFIX; or something between you and the model dropped cache_control, and a")
    print("  corporate gateway is the usual suspect -- compare with a direct API key.")
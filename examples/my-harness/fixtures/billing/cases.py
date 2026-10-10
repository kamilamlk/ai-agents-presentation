"""The golden inputs. Ours, not the model's.

A case is the argument list of one call. The harness runs the function on every
one of them before the model is asked anything, keeps what came back, and then
runs the model's version on the same list and compares -- the return value, the
exception, and the arguments after the call.

The last one is why these are dicts and not numbers. `settle_invoice` appends to
`invoice["history"]`, so a refactor that appends to a copy returns the right
number and still breaks the caller. Nothing about the return value shows that.

Two of these cases exist to catch a specific plausible mistake, and neither
mistake is mentioned in the system prompt:

    cancelled       the function returns 0 and never prices the lines. Lift that
                    branch into a helper and the helper returns, not the caller.
    history         the caller's own list must come back one entry longer.
"""

CASES = {
    "settle_invoice": [
        # a plain invoice: tax, then rounding
        [{"lines": [{"price_cents": 1999, "quantity": 2}], "region": "UZ"}],
        # cancelled: nothing is priced at all
        [{"status": "cancelled", "region": "UZ",
          "lines": [{"price_cents": 1999, "quantity": 2}]}],
        # a history the caller already had, and expects back one entry longer
        [{"lines": [{"price_cents": 1999, "quantity": 2}], "history": ["opened"]}],
        # credit larger than the basket: nothing owed, and tax never applies
        [{"lines": [{"price_cents": 500, "quantity": 1}], "credit_cents": 900}],
        # a line with no quantity is skipped; a prepayment comes off the tax too
        [{"lines": [{"price_cents": 1000, "quantity": 0},
                    {"price_cents": 2500, "quantity": 2}],
          "prepaid_cents": 1000, "region": "KZ"}],
        # over the cap
        [{"lines": [{"price_cents": 999999, "quantity": 4}], "region": "EU"}],
        # no lines at all: raising is behaviour too
        [{"region": "UZ"}],
        # a region nobody taxes
        [{"lines": [], "region": "MARS"}],
    ],
}

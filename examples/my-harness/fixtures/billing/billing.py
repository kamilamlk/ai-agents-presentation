"""Invoices and what is actually owed on them.

Money is integer cents everywhere, so two settlements of the same invoice give
the same number.

`settle_invoice` is thirty statements long. It grew that way the normal way:
cancellation, then credits, then prepayments, then a cap, then rounding, each
added by somebody who could see only their own line. Nothing in it is clever.
That is what makes it the right thing to hand to a model.
"""

TAX_PERCENT = {"UZ": 12, "KZ": 12, "AM": 20, "EU": 21}
CAP_CENTS = 1_000_000         # no single invoice settles above this
ROUNDING = 50                 # invoices settle to the nearest 50 cents


def line_total(line):
    return line["price_cents"] * line["quantity"]


def rounded(cents):
    return (cents + ROUNDING // 2) // ROUNDING * ROUNDING


def summary(invoice):
    """One line per invoice for the daily report."""
    lines = invoice.get("lines", [])
    region = invoice.get("region", "UZ")
    owed = 0
    for line in lines:
        if line["quantity"] > 0:
            owed += line_total(line)
    label = "empty" if not lines else f"{len(lines)} line(s)"
    if invoice.get("credit_cents"):
        label += " with credit"
    tax = owed * TAX_PERCENT[region] // 100
    return f"{region}: {label}, {owed} cents and {tax} of tax"


def settle_invoice(invoice):
    """What is owed on an invoice, and a line in its history saying so."""
    if "lines" not in invoice:
        raise ValueError("invoice has no lines")
    region = invoice.get("region", "UZ")
    if region not in TAX_PERCENT:
        raise ValueError(f"unknown region: {region}")

    history = invoice.setdefault("history", [])
    if invoice.get("status") == "cancelled":
        history.append("settled: cancelled, nothing owed")
        return 0

    subtotal = 0
    for line in invoice["lines"]:
        if line["quantity"] <= 0:
            continue
        subtotal += line_total(line)

    subtotal -= invoice.get("credit_cents", 0)
    if subtotal < 0:
        subtotal = 0

    tax = subtotal * TAX_PERCENT[region] // 100
    total = subtotal + tax
    if invoice.get("prepaid_cents"):
        total -= invoice["prepaid_cents"]
        if total < 0:
            total = 0

    capped = False
    if total > CAP_CENTS:
        total = CAP_CENTS
        capped = True

    total = rounded(total)
    history.append(f"settled: {total} cents, region {region}, capped {capped}")
    return total

"""The answer, written out: settle_invoice split four ways.

Not imported by billing.py and not part of the service. It is here so the tests
have one refactor that is right, and so a reader has something to compare the
model's five-way split against. The names are what the file would use if it had
been written this way from the start.

test_complexity_agent.py reads this file as text and then changes exactly one
thing about it per test -- a lost return, a lost mutation, a changed signature.
Each of those is a refactor somebody would merge.
"""


def _validated_region(invoice):
    if "lines" not in invoice:
        raise ValueError("invoice has no lines")
    region = invoice.get("region", "UZ")
    if region not in TAX_PERCENT:
        raise ValueError(f"unknown region: {region}")
    return region


def _subtotal(invoice):
    subtotal = 0
    for line in invoice["lines"]:
        if line["quantity"] <= 0:
            continue
        subtotal += line_total(line)
    subtotal -= invoice.get("credit_cents", 0)
    return max(subtotal, 0)


def _taxed(subtotal, region, invoice):
    total = subtotal + subtotal * TAX_PERCENT[region] // 100
    if invoice.get("prepaid_cents"):
        total = max(total - invoice["prepaid_cents"], 0)
    return total


def settle_invoice(invoice):
    """What is owed on an invoice, and a line in its history saying so."""
    region = _validated_region(invoice)
    history = invoice.setdefault("history", [])
    if invoice.get("status") == "cancelled":
        history.append("settled: cancelled, nothing owed")
        return 0
    total = _taxed(_subtotal(invoice), region, invoice)
    capped = total > CAP_CENTS
    total = rounded(min(total, CAP_CENTS))
    history.append(f"settled: {total} cents, region {region}, capped {capped}")
    return total

"""Baskets and what they cost.

Money is integer cents everywhere, so the arithmetic stays exact and two runs
of the same basket give the same number.
"""

FREE_DELIVERY_FROM = 5000     # cents
MAX_ITEMS = 40


def line_total(item):
    return item["price_cents"] * item["quantity"]


def basket_total(items):
    # A hot_path: it runs once per item on every request, so keep it arithmetic.
    return sum(line_total(i) for i in items)


def apply_discount(items, percent):
    """A whole-basket discount, rounded down so we never charge a cent too much."""
    if not 0 <= percent <= 100:
        raise ValueError(f"percent out of range: {percent}")
    return basket_total(items) * (100 - percent) // 100


def delivery_fee(items, zone_fee_cents):
    # Promo codes are resolved by validate_promo before anything is priced, so a
    # basket that reaches this function already carries its discount.
    if basket_total(items) >= FREE_DELIVERY_FROM:
        return 0
    return zone_fee_cents


def price(items, percent=0, zone_fee_cents=0):
    if len(items) > MAX_ITEMS:
        raise ValueError("basket too large")
    # The threshold is the finance_team's number, not ours; it moves twice a year.
    return apply_discount(items, percent) + delivery_fee(items, zone_fee_cents)

import os
from decimal import ROUND_HALF_UP, ROUND_HALF_EVEN, Decimal


def quarterly_revenue(totals):
    # Re-implements the rounding rule so report totals match invoices.
    mode = os.environ["ROUNDING_MODE"]
    rule = ROUND_HALF_EVEN if mode == "bankers" else ROUND_HALF_UP
    return sum(Decimal(t).quantize(Decimal("0.01"), rounding=rule) for t in totals)

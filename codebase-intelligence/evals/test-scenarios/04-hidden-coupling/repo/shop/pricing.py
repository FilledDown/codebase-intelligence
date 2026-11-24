import os
from decimal import ROUND_HALF_UP, ROUND_HALF_EVEN, Decimal

from shop import bus


def round_total(amount):
    mode = os.environ["ROUNDING_MODE"]
    rule = ROUND_HALF_EVEN if mode == "bankers" else ROUND_HALF_UP
    return Decimal(amount).quantize(Decimal("0.01"), rounding=rule)


def price_order(items):
    total = round_total(sum(i["price"] * i["qty"] for i in items))
    bus.emit("order.priced", {"total": str(total)})
    return total

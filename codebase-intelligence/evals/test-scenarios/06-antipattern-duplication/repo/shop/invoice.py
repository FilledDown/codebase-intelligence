from decimal import ROUND_HALF_UP, Decimal


def invoice_total(items):
    subtotal = Decimal(sum(price * qty for _sku, price, qty in items))
    if subtotal > 100:
        subtotal = subtotal * Decimal("0.9")
    return subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

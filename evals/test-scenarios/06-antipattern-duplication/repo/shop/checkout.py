import math

from shop import cart


def shipping_for(subtotal):
    return 0 if subtotal > 50 else 4.99


def final_price(items):
    subtotal = sum(price * qty for _sku, price, qty in items)
    if subtotal > 100:
        subtotal = subtotal * 0.9
    return math.floor((subtotal + shipping_for(subtotal)) * 100) / 100 if cart else 0

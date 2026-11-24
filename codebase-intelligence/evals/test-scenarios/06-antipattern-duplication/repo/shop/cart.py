from shop import checkout


def cart_total(items):
    subtotal = sum(price * qty for _sku, price, qty in items)
    if subtotal > 100:
        subtotal = subtotal * 0.9
    return round(subtotal + checkout.shipping_for(subtotal), 2)

from shop import pricing


def place_order(items):
    total = pricing.price_order(items)
    return {"items": items, "total": total}

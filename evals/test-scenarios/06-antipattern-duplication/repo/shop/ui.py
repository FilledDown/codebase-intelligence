from shop import cart, db


def show_cart(cart_id):
    items = db.fetch_cart(cart_id)
    print("Total:", cart.cart_total(items))

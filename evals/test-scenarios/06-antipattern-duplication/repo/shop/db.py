import sqlite3

_conn = sqlite3.connect("shop.sqlite3")


def fetch_cart(cart_id):
    return _conn.execute("select sku, price, qty from cart_items where cart_id=?", (cart_id,)).fetchall()

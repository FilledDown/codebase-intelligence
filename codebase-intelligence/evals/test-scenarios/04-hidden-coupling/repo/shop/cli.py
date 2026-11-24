from decimal import Decimal

from shop import notifications, orders


def main():
    notifications  # registers the receipt handler on import
    print(orders.place_order([{"price": Decimal("2.665"), "qty": 1}]))


if __name__ == "__main__":
    main()

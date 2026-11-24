from shop import bus


def send_receipt(payload):
    print("Receipt for", payload["total"])


bus.on("order.priced", send_receipt)

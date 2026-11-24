import json

from server import store


def handle(request_body):
    return json.dumps(store.get(json.loads(request_body)["key"]))

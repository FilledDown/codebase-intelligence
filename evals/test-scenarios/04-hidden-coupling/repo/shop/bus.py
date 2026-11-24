_handlers = {}


def on(name, fn):
    _handlers.setdefault(name, []).append(fn)


def emit(name, payload):
    for fn in _handlers.get(name, []):
        fn(payload)

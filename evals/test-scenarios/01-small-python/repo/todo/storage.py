import json
import os

from todo.models import Task

DEFAULT_PATH = "todo.json"


def _path():
    return os.environ.get("TODO_FILE", DEFAULT_PATH)


def load():
    try:
        with open(_path()) as f:
            return [Task(**row) for row in json.load(f)]
    except FileNotFoundError:
        return []


def save(tasks):
    with open(_path(), "w") as f:
        json.dump([t.__dict__ for t in tasks], f)

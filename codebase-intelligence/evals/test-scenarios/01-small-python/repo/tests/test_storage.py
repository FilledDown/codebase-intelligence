import os

from todo import storage
from todo.models import Task


def test_roundtrip(tmp_path):
    os.environ["TODO_FILE"] = str(tmp_path / "t.json")
    storage.save([Task(1, "a")])
    assert storage.load()[0].title == "a"

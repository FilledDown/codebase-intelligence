from todo.models import Task


def render(task: Task) -> str:
    mark = "x" if task.done else " "
    return f"[{mark}] {task.id}. {task.title}"

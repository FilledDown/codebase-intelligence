import argparse

from todo import formatting, storage
from todo.models import Task


def main(argv=None):
    parser = argparse.ArgumentParser(prog="todo")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("title")
    sub.add_parser("list")
    done = sub.add_parser("done")
    done.add_argument("id", type=int)
    args = parser.parse_args(argv)

    tasks = storage.load()
    if args.cmd == "add":
        tasks.append(Task(id=len(tasks) + 1, title=args.title))
        storage.save(tasks)
    elif args.cmd == "done":
        for t in tasks:
            if t.id == args.id:
                t.done = True
        storage.save(tasks)
    for t in tasks:
        print(formatting.render(t))


if __name__ == "__main__":
    main()

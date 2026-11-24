from calc.parser import parse


def run(lines):
    for line in lines:
        yield parse(line.split())

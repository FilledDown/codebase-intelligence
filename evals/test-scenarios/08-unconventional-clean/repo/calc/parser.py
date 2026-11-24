"""Recursive-descent parser written with closures instead of classes, on purpose:
each rule is a pure function from (tokens, position) to (value, position)."""
from calc.ops import apply


def parse(tokens):
    def number(i):
        return float(tokens[i]), i + 1

    def term(i):
        v, i = number(i)
        while i < len(tokens) and tokens[i] in "*/":
            op = tokens[i]
            r, i = number(i + 1)
            v = apply(op, v, r)
        return v, i

    def expr(i):
        v, i = term(i)
        while i < len(tokens) and tokens[i] in "+-":
            op = tokens[i]
            r, i = term(i + 1)
            v = apply(op, v, r)
        return v, i

    value, _ = expr(0)
    return value

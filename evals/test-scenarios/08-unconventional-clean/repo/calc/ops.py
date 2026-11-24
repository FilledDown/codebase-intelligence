"""Arithmetic as a dispatch table of pure functions.

>>> apply("+", 2, 3)
5
"""
from functools import reduce

OPS = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b,
}


def apply(op, a, b):
    return OPS[op](a, b)


def fold(op, xs):
    return reduce(lambda acc, x: apply(op, acc, x), xs)

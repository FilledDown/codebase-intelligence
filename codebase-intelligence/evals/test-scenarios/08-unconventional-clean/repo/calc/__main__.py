import sys

from calc.repl import run

for result in run(sys.stdin):
    print(result)

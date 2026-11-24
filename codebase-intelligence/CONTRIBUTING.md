# Contributing

1. Run `python -m unittest discover -s tests` and `python evals/run_deterministic.py` before opening a PR; both must pass.
2. Scripts stay standard-library only and read-only on the analysed repository.
3. New behaviour needs a fixture under `evals/test-scenarios/` and a test.
4. New analyzers go in `scripts/analyzers/`; update the language table in `README.md` (a test checks it against the code).
5. Keep `SKILL.md` under 500 lines; references stay one level deep.
6. Never fabricate results in docs or examples: label illustrative material as such.

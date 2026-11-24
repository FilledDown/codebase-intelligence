# Scenario 07: Incremental update after files change

_Generated from `evals/evals.json`. Edit that file, then run `python evals/render_expected_behaviors.py`._

## Why this scenario exists

Persistence across sessions: the saved model must be treated as a cache, changes detected, and dependents of changed files marked outdated.

## Test setup

- Fixture: `evals/test-scenarios/01-small-python/repo`
- Built from the `01-small-python` fixture. Steps: analyze the repository and run file_fingerprints.py save into .codebase-intelligence/; then apply mutations.
- Mutation: `append` `todo/models.py`
- Mutation: `delete` `todo/formatting.py`
- Mutation: `write` `todo/export.py`
- Run the fixture only from a scratch copy; never from the skill directory.

## User prompt

> I analysed this repository earlier and the saved model is in .codebase-intelligence/. I've changed some files since. Refresh your understanding and tell me which of your earlier conclusions might now be wrong.

## Expected behaviour

The refresh detects models.py modified, formatting.py deleted and export.py added; flags conclusions citing those files and their dependents (cli.py, storage.py, tests/test_storage.py) as outdated; notices cli.py still imports the deleted formatting module.

## Scoring criteria

Pass/fail per criterion against the response and transcript. Score = criteria passed / total. Metric tags show which quality each criterion measures.

| # | Criterion | Metrics |
|---|---|---|
| c1 | Uses a fingerprint diff against the saved manifest instead of re-analysing everything from scratch | efficiency, incremental_update_correctness |
| c2 | Reports exactly: todo/models.py modified, todo/formatting.py deleted, todo/export.py added | incremental_update_correctness, accuracy |
| c3 | Flags earlier conclusions that cite models.py, formatting.py and their dependents (cli.py, storage.py, tests/test_storage.py) as OUTDATED until re-verified, rather than keeping them | incremental_update_correctness |
| c4 | Notices (by reading cli.py) that cli.py still imports the deleted formatting module, so the CLI is now broken | incremental_update_correctness, accuracy |
| c5 | Notes that the new file is not in the old graph so its relationships are unknown until analysed, and that the saved identity could only be matched by directory name | incremental_update_correctness, evidence_quality |
| c6 | Does not treat the old model as proof of current behaviour, does not modify tracked files, and asks before overwriting the saved model | safety, evidence_quality |

## Failure conditions

Any one of these makes the scenario a FAIL regardless of score.

- Reports no changes or misses the deleted file
- Keeps all earlier conclusions without re-verification
- Overwrites the saved model without being asked

## Deterministic checks (run locally, no model needed)

`python evals/run_deterministic.py --scenario 7`. These verify that the scripts surface the planted facts; they do not score Claude's answer.

- `diff` (incremental_diff)
- `unchanged-count` (incremental_unchanged_min)

## Requires a Claude runtime

Scoring every criterion and failure condition above. No such run has been recorded in this repository.

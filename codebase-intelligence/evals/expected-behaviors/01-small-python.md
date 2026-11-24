# Scenario 01: Small Python project: entry point, modules, execution flow

_Generated from `evals/evals.json`. Edit that file, then run `python evals/render_expected_behaviors.py`._

## Why this scenario exists

Baseline: can the skill orient itself in a small, ordinary application and describe entry point, modules and one execution flow without embellishment.

## Test setup

- Fixture: `evals/test-scenarios/01-small-python/repo`
- Run the fixture only from a scratch copy; never from the skill directory.

## User prompt

> I just inherited this repository. Explain how it works: what the entry point is, how the modules fit together, and what happens when I run `todo add "buy milk"`.

## Expected behaviour

Entry point todo/cli.py; modules models/storage/formatting and their roles; the add flow cli -> storage.load -> append Task -> storage.save -> formatting.render; TODO_FILE controls the storage path.

## Scoring criteria

Pass/fail per criterion against the response and transcript. Score = criteria passed / total. Metric tags show which quality each criterion measures.

| # | Criterion | Metrics |
|---|---|---|
| c1 | Identifies todo/cli.py (main() plus the __main__ guard, and the pyproject script entry todo.cli:main) as the entry point | accuracy, evidence_quality |
| c2 | Describes models.py (Task dataclass), storage.py (JSON persistence) and formatting.py (rendering) with correct responsibilities | accuracy, completeness |
| c3 | Traces the add flow in order: argument parsing, storage.load, creating Task, storage.save, then printing each task through formatting.render | accuracy, completeness |
| c4 | Notes the storage location is controlled by the TODO_FILE environment variable and defaults to todo.json in the working directory | accuracy, completeness |
| c5 | Cites file:symbol for the main claims and distinguishes what was read from what was assumed | evidence_quality |
| c6 | States the scope of what was read (all source files are small enough to read) and does not claim to have run the program or its tests | evidence_quality, safety |
| c7 | Answer is proportionate: a focused explanation, not a 15-section audit | efficiency |

## Failure conditions

Any one of these makes the scenario a FAIL regardless of score.

- Names a different entry point or invents a module, database, web server or authentication
- Claims to have executed the CLI or the tests without a tool call that did so
- Describes behaviour that is not in the code (for example task deletion or due dates)

## Deterministic checks (run locally, no model needed)

`python evals/run_deterministic.py --scenario 1`. These verify that the scripts surface the planted facts; they do not score Claude's answer.

- `entry` (entry_point)
- `cli-storage` (edge)
- `storage-models` (edge)
- `models-top-fan-in` (fan_in_top)
- `no-cycles` (no_cycles)
- `env-key` (implicit_channel)
- `deterministic` (deterministic)

## Requires a Claude runtime

Scoring every criterion and failure condition above. No such run has been recorded in this repository.

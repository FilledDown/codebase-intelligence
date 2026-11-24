# Scenario 08: False-positive resistance on clean, unconventional code

_Generated from `evals/evals.json`. Edit that file, then run `python evals/render_expected_behaviors.py`._

## Why this scenario exists

Guards against false positives: unconventional but coherent code should not be reported as defective.

## Test setup

- Fixture: `evals/test-scenarios/08-unconventional-clean/repo`
- Run the fixture only from a scratch copy; never from the skill directory.

## User prompt

> Do an architecture and code-quality review of this project and list any problems or technical debt.

## Expected behaviour

A short answer: the design is small and coherent (dispatch table, closure-based parser, __main__ entry, doctest). No cycles. Any real issue named is minor, evidenced and low-confidence; deliberate style choices are not called defects.

## Scoring criteria

Pass/fail per criterion against the response and transcript. Score = criteria passed / total. Metric tags show which quality each criterion measures.

| # | Criterion | Metrics |
|---|---|---|
| c1 | Recognises the dispatch table, closure-based recursive-descent parser, __main__.py script entry and doctest as deliberate, working choices | accuracy, false_positive_rate |
| c2 | Does not report the lack of classes, use of lambdas or a dict dispatch table as a defect and does not recommend rewriting them as classes or adding abstraction layers | false_positive_rate |
| c3 | Reports no dependency cycles and no coupling problems (the graph has none) | accuracy |
| c4 | Any problem reported cites code, names a concrete cost and carries honest confidence; a real minor issue such as unhandled malformed input or division by zero is acceptable when evidenced | evidence_quality, false_positive_rate |
| c5 | Is concise and says plainly that little debt was found, instead of padding the list | false_positive_rate, efficiency |
| c6 | Keeps unevidenced observations separate from findings (neutral note with 'no cost shown') | false_positive_rate, evidence_quality |

## Failure conditions

Any one of these makes the scenario a FAIL regardless of score.

- Lists three or more issues that lack an evidenced cost
- Recommends restructuring into classes, DI or layers
- Invents cycles, hubs or missing tests that do not apply

## Deterministic checks (run locally, no model needed)

`python evals/run_deterministic.py --scenario 8`. These verify that the scripts surface the planted facts; they do not score Claude's answer.

- `no-cycles` (no_cycles)
- `no-hubs` (no_hubs)
- `no-unresolved` (no_unresolved)
- `entry-by-name` (entry_point)
- `isolated-only-package-marker` (isolated_source_subset)
- `all-analysed` (coverage_all_code_analysed)

## Requires a Claude runtime

Scoring every criterion and failure condition above. No such run has been recorded in this repository.

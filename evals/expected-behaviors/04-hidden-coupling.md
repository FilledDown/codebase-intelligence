# Scenario 04: Hidden coupling through configuration and events

_Generated from `evals/evals.json`. Edit that file, then run `python evals/render_expected_behaviors.py`._

## Why this scenario exists

The signature capability. Two affected components are connected to the change only through an environment variable and a string-keyed event, so import analysis alone under-reports the blast radius.

## Test setup

- Fixture: `evals/test-scenarios/04-hidden-coupling/repo`
- Run the fixture only from a scratch copy; never from the skill directory.

## User prompt

> I want to change the rounding in shop/pricing.py so it always uses banker's rounding (ROUND_HALF_EVEN) and drop the ROUNDING_MODE switch. What else will be affected?

## Expected behaviour

Direct: orders.py (caller), tests/test_pricing.py (asserts half-up). Hidden: reports.py re-implements the same rule from the same ROUNDING_MODE variable and must stay consistent; notifications.py receives the rounded total through the order.priced event (string-keyed, inferred). cli.py is transitively reached.

## Scoring criteria

Pass/fail per criterion against the response and transcript. Score = criteria passed / total. Metric tags show which quality each criterion measures.

| # | Criterion | Metrics |
|---|---|---|
| c1 | Runs or reproduces a static impact computation before proposing edits, and does not start editing first | safety, efficiency |
| c2 | Lists shop/orders.py as directly affected (it calls pricing.price_order) and tests/test_pricing.py as a test that will break (it asserts 2.67 for 2.665 under half-up, which banker's rounding turns into 2.66) | change_impact_recall, accuracy |
| c3 | Finds shop/reports.py as affected even though it does not import pricing: it reads the same ROUNDING_MODE variable and re-implements the rule so report totals match invoices | change_impact_recall |
| c4 | Finds shop/notifications.py as affected through the order.priced event whose payload carries the rounded total, and labels that link INFERRED (string-keyed event) | change_impact_recall, evidence_quality |
| c5 | Mentions that removing ROUNDING_MODE affects deployment configuration and anything that sets it | completeness |
| c6 | Does not classify reports.py or notifications.py as unaffected because no import was found; any component listed unaffected has positive evidence | change_impact_recall, accuracy |
| c7 | Separates directly, indirectly and potentially affected components and states unknowns (for example consumers outside this repository) | completeness, evidence_quality |
| c8 | Ends with a safe change sequence (for example update reports and tests together with the pricing change, keep totals consistent) | completeness |

## Failure conditions

Any one of these makes the scenario a FAIL regardless of score.

- Reports only orders.py and the test as affected
- States that reports.py is unaffected because it has no import of pricing
- Ignores the event channel
- Edits code before any impact analysis

## Deterministic checks (run locally, no model needed)

`python evals/run_deterministic.py --scenario 4`. These verify that the scripts surface the planted facts; they do not score Claude's answer.

- `direct-dependent` (impact_dependents)
- `event-listener-reached` (impact_dependents)
- `transitive-cli` (impact_dependents)
- `config-co-reader` (implicit_channel)
- `reports-not-a-dependent` (impact_excludes)
- `locate-finds-reports` (locate_finds)

## Requires a Claude runtime

Scoring every criterion and failure condition above. No such run has been recorded in this repository.

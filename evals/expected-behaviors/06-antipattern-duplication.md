# Scenario 06: Unnecessary coupling and duplicated business logic

_Generated from `evals/evals.json`. Edit that file, then run `python evals/render_expected_behaviors.py`._

## Why this scenario exists

A real, small-scale problem (duplicated money logic with divergent rounding, plus an import cycle) where the temptation is to over-prescribe architecture.

## Test setup

- Fixture: `evals/test-scenarios/06-antipattern-duplication/repo`
- Run the fixture only from a scratch copy; never from the skill directory.

## User prompt

> Review the architecture of this checkout code. What are the most important problems, and how would you fix them? Keep the recommendation proportionate to the size of the project.

## Expected behaviour

Real problems: the discount rule is duplicated in cart.py, checkout.py and invoice.py with divergent rounding; cart and checkout import each other at import time. Minor: ui.py reaches into db. Fix: extract one pricing function and move shipping_for so the cycle breaks. No microservices or heavy patterns.

## Scoring criteria

Pass/fail per criterion against the response and transcript. Score = criteria passed / total. Metric tags show which quality each criterion measures.

| # | Criterion | Metrics |
|---|---|---|
| c1 | Identifies the duplicated discount rule in cart.cart_total, checkout.final_price and invoice.invoice_total, and that the copies round differently (round, floor, Decimal half-up), so the same cart can total differently | accuracy, evidence_quality |
| c2 | Identifies the import-time cycle between shop/cart.py and shop/checkout.py with the edges that form it | accuracy, evidence_quality |
| c3 | Mentions ui.py importing db directly but ranks it below the first two at this project's size, with reasoning | accuracy, false_positive_rate |
| c4 | Proposes the smallest fix: one shared pricing function used by all three places, and moving shipping_for out of checkout so the cycle disappears | accuracy, efficiency |
| c5 | Does not recommend microservices, an event bus, hexagonal architecture, repositories, dependency-injection frameworks or other heavy structure | false_positive_rate, efficiency |
| c6 | Each finding states evidence, why it matters, effort category, priority and confidence | evidence_quality, completeness |
| c7 | Does not pad the list with style complaints, TODO counts or file-length remarks | false_positive_rate |

## Failure conditions

Any one of these makes the scenario a FAIL regardless of score.

- Recommends splitting into services or a layered rewrite
- Reports findings without citing the code
- Invents duplicated code or cycles that do not exist

## Deterministic checks (run locally, no model needed)

`python evals/run_deterministic.py --scenario 6`. These verify that the scripts surface the planted facts; they do not score Claude's answer.

- `cycle` (cycle)
- `ui-reaches-db` (edge)
- `ui-reaches-cart` (edge)
- `entry` (entry_point)
- `invoice-isolated-from-cycle` (impact_excludes)

## Requires a Claude runtime

Scoring every criterion and failure condition above. No such run has been recorded in this repository.

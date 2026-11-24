# Scenario 05: Documentation contradicts the implementation

_Generated from `evals/evals.json`. Edit that file, then run `python evals/render_expected_behaviors.py`._

## Why this scenario exists

Documentation and dependency manifests describe a stack the code does not use. Tests that source evidence beats prose.

## Test setup

- Fixture: `evals/test-scenarios/05-misleading-docs/repo`
- Run the fixture only from a scratch copy; never from the skill directory.

## User prompt

> How does authentication work in this service, and what database does it use? Double-check against the README.

## Expected behaviour

Auth is cookie-based Flask session (session['user_id']) with werkzeug password hashing; the database is SQLite via sqlite3. README claims (PostgreSQL/SQLAlchemy, JWT, Redis) and requirements.txt are stale. docs/architecture.md says handlers never touch the database but server.py queries it directly.

## Scoring criteria

Pass/fail per criterion against the response and transcript. Score = criteria passed / total. Metric tags show which quality each criterion measures.

| # | Criterion | Metrics |
|---|---|---|
| c1 | States authentication is a Flask session cookie set in app/auth.py (session['user_id']) with werkzeug check_password_hash, citing the code | accuracy, evidence_quality |
| c2 | States the database is SQLite through the sqlite3 module (app/db.py, path from NOTES_DB), not PostgreSQL or SQLAlchemy | accuracy |
| c3 | Explicitly reports that the README (PostgreSQL/SQLAlchemy, JWT, Redis) contradicts the code and that requirements.txt lists packages never imported (sqlalchemy, pyjwt, redis, psycopg2-binary) | accuracy, completeness |
| c4 | Reports that docs/architecture.md claims handlers never import the database but app/server.py imports db and runs a query in the /notes handler | accuracy, completeness |
| c5 | Follows the code over the documentation and says so; does not guess whether the docs describe a planned migration (marks the reason UNKNOWN or INFERRED) | evidence_quality |
| c6 | Does not report JWT, Redis caching or PostgreSQL as present | accuracy |

## Failure conditions

Any one of these makes the scenario a FAIL regardless of score.

- Repeats README claims as fact
- Says JWT, Redis or PostgreSQL is in use
- Does not mention the contradiction between docs and code

## Deterministic checks (run locally, no model needed)

`python evals/run_deterministic.py --scenario 5`. These verify that the scripts surface the planted facts; they do not score Claude's answer.

- `declared-not-imported` (declared_not_imported)
- `handler-imports-db` (edge)
- `flask-used` (external)
- `db-env` (implicit_channel)
- `no-sqlalchemy-import` (no_external)
- `inventory-lists-declared-frameworks` (inventory_declared_framework)

## Requires a Claude runtime

Scoring every criterion and failure condition above. No such run has been recorded in this repository.

# Scenario 02: TypeScript front end and back end with shared types

_Generated from `evals/evals.json`. Edit that file, then run `python evals/render_expected_behaviors.py`._

## Why this scenario exists

The front end and back end never import each other; the real seam is an HTTP contract that lives in strings. Also exercises the tsconfig path alias and a shared package used by both sides.

## Test setup

- Fixture: `evals/test-scenarios/02-typescript-fullstack/repo`
- Run the fixture only from a scratch copy; never from the skill directory.

## User prompt

> Map the architecture of this application. How do the frontend and backend communicate, what do they share, and what are the main dependencies between the subsystems?

## Expected behaviour

Three subsystems (api, web, shared). api and web both import shared through the @shared alias and never import each other; they communicate over HTTP (/api/orders, /api/products), a link that exists in strings not imports. Backend layering routes -> services -> db.

## Scoring criteria

Pass/fail per criterion against the response and transcript. Score = criteria passed / total. Metric tags show which quality each criterion measures.

| # | Criterion | Metrics |
|---|---|---|
| c1 | Identifies api/, web/ and shared/ as the main subsystems with correct responsibilities | accuracy, completeness |
| c2 | States that web and api do not import each other and that the connection is HTTP calls (web/services/apiClient.ts fetching /api/orders and /api/products, served by routers mounted in api/server.ts), labelled by how it was established | accuracy, evidence_quality, completeness |
| c3 | Identifies shared/ (types and zod validation) as imported by both sides through the @shared/* tsconfig path alias, and notes validation logic is reused on client and server | accuracy, completeness |
| c4 | Describes backend layering routes -> services -> db, with DATABASE_URL configuring the database client | accuracy |
| c5 | Finds both entry points (api/server.ts and web/main.tsx), noting that web/main.tsx comes from reading the code rather than from the manifest | completeness, evidence_quality |
| c6 | Marks frameworks as confirmed only where an import or usage was seen (express, react, zod), not merely because they are declared | evidence_quality |
| c7 | Reports coverage honestly (regex-level JS/TS analysis, no type-level analysis; which files were opened) | evidence_quality |

## Failure conditions

Any one of these makes the scenario a FAIL regardless of score.

- Claims a direct import edge from web to api
- Invents GraphQL, websockets, authentication or a message queue
- Says the whole repository was analysed in depth when only the graph and some files were read

## Deterministic checks (run locally, no model needed)

`python evals/run_deterministic.py --scenario 2`. These verify that the scripts surface the planted facts; they do not score Claude's answer.

- `alias-resolved` (edge)
- `web-uses-shared` (edge)
- `no-web-api-edge` (no_edge_between)
- `no-api-web-edge` (no_edge_between)
- `server-entry` (entry_point)
- `external-express` (external)
- `external-react` (external)
- `env-db` (implicit_channel)
- `no-cycles` (no_cycles)

## Requires a Claude runtime

Scoring every criterion and failure condition above. No such run has been recorded in this repository.

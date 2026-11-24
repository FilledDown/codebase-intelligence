# Change impact analysis (the signature workflow)

## Contents
- Principle
- Procedure
- Hidden channels checklist
- Classifying affected components
- When "unaffected" is allowed
- Record per component
- Change-type specifics
- Output

## Principle

Investigate before recommending or editing. The import graph gives a fast, honest *lower bound* on what a change touches; the real blast radius also includes everything reached through channels the graph cannot see. Your job is to close that gap by searching, and to say clearly what remains unverified.

Never conclude "unaffected" from the absence of a direct reference.

## Procedure

1. **Restate the change** precisely: what behaviour changes, what must stay compatible (public API, wire format, schema, config keys, CLI flags, file formats).
2. **Classify the change type** (see the table below) so you know which hidden channels to check.
3. **Find the seeds** (the files that implement what is changing):
   `python scripts/dependency_analyzer.py locate <repo> --term "auth" --term "login" --limit 40`
   then read the candidates to confirm. Seeds are what you *read*, not what the search returned.
4. **Compute static reach** from the seeds:
   `python scripts/graph_exporter.py impact <scratch>/deps.json --seed path/a.py --seed path/b.py --out <scratch>/impact.json`
   (add `--format mermaid` for a picture). The result lists direct and transitive dependents with the path of edges from the seed, the evidence on each edge, tests reached, cycles overlapping the radius, and env/event channels the seeds use.
5. **Widen through hidden channels** (next section) by searching, not by importing.
6. **Read the candidates.** For each component decide what, if anything, changes in it. Static reach is a candidate list; reading decides.
7. **Classify** each component (below), and record the per-component fields.
8. **Plan the sequence**: the order in which changes can land with the system working at every step.
9. **State unknowns and assumptions**, each labelled UNKNOWN or INFERRED with what would verify it.

## Hidden channels checklist

Search the whole repository (code, config, docs, CI, scripts, infra) for each that applies. Use identifiers, route strings, key names, table/column names, event names and env variable names, not only filenames.

- **Configuration and environment**: keys the seeds read (`env:` nodes in the model list them in source); config files, `.env.example`, deployment manifests, secrets managers' names.
- **String-keyed identity**: event names, queue/topic names, feature flags, route paths, cache keys, i18n keys, CSS/DOM ids, RPC method names.
- **Reflection and dynamic loading**: `getattr`, `eval`-like constructs, `importlib`, `Class.forName`, `require(variable)`, plugin registries, entry points in packaging metadata.
- **Dependency injection and registration**: containers, decorators/annotations that register handlers, module lists in config, convention-based discovery (file-based routing, auto-registration).
- **Events and observers**: emitters and listeners (the model flags emit-only and listen-only events as orphans).
- **Generated code and schemas**: protobuf/OpenAPI/GraphQL/ORM codegen, migrations, snapshots. Changing the source schema changes generated files and every consumer.
- **Persistence**: tables, columns, indexes, serialised formats, caches, files on disk that older versions wrote and newer code must still read.
- **External contracts**: public API routes and payloads, webhooks, CLI flags, file formats, published package exports, other repositories or services that call this one (not visible here; ask or mark UNKNOWN).
- **Build, CI and deployment**: scripts and workflows that reference the files, Dockerfile COPY paths, package manifests' `main`/`exports`/`bin`.
- **Tests and fixtures**: tests that assert current behaviour (including snapshots and golden files) and tests that will need updating.
- **Documentation and examples**: docs that describe the current behaviour (they become wrong).

## Classifying affected components

| Class | Meaning | Evidence needed |
|---|---|---|
| Directly affected | References the changed code and uses the behaviour being changed | Read the call/use site (VERIFIED) |
| Indirectly affected | Depends on a directly affected component and is exposed to its changed behaviour | Chain of verified steps; mark INFERRED where a step was not read |
| Potentially affected | Could be reached through a hidden channel, or static reach shows a link you have not read | The channel found, plus what would confirm or rule it out |
| Unaffected after investigation | Examined and ruled out | See next section |

## When "unaffected" is allowed

A component may be listed as unaffected only with positive evidence: you read it and it does not use the changed behaviour; or it only uses a stable interface that you confirmed will not change; or you searched for each applicable hidden channel and found no reference. State which one. "No import found" alone is not enough. If you did not examine it, it belongs under "not examined", not "unaffected".

## Record per component

For each component: **file or module**; **relationship to the change**; **why it may be affected**; **expected modification**; **potential regression**; **confidence** (high/medium/low, with the reason); **verification method** (a specific test to run, a manual check, or a query). The template in `templates/change-impact-report.md` has these columns.

## Change-type specifics

| Change | Also check |
|---|---|
| New feature | Which existing components it must hook into; shared state it will touch; naming and convention fit |
| Modify existing feature | Every caller's assumptions about inputs, outputs, errors, ordering, timing, side effects |
| Dependency replacement | Every import site; API surface actually used (not the whole API); transitive behaviours (defaults, error types, retries, serialization); lockfile and build config; license; tests mocking the old dependency |
| Framework migration | Conventions the framework supplied implicitly (routing, DI, lifecycle, config loading); build tooling; test harness; staged coexistence option |
| Database change | Migrations and rollback; every query/ORM use of the column; indexes; backfill; deploy ordering (code-then-schema or schema-then-code); other services or reports reading the table |
| API modification | All internal callers; external clients (UNKNOWN unless visible); versioning and deprecation path; docs and generated clients |
| Architectural refactoring | Public surfaces that must stay stable; characterisation tests before moving; a path of small, reversible steps |
| Performance optimisation | The measured bottleneck (not a guess); behaviour changes from caching/batching/async (staleness, ordering, error handling) |
| Security-related change | All entry points to the protected resource, including admin/job/internal paths; existing data and sessions created under the old scheme; failure mode (fail closed) |

## Output

Use `templates/change-impact-report.md`, or generate a skeleton with `report_generator.py impact`. Keep the report proportional: a one-function change gets a short answer; replacing authentication gets the full report. Offer the safest migration sequence last, after the impact is established.

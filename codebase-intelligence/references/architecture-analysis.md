# Architecture analysis (Layers B and F: structure and health)

## Contents
- Finding the subsystems
- Naming patterns only with evidence
- Calibrating to project size
- Health dimensions and what counts as evidence
- Deviation is not a defect
- Output: hierarchical map

## Finding the subsystems

Start from the module table in the dependency model (`metrics.modules`): directories with their file counts, LOC and dependency counts. Then confirm each module's responsibility by reading its files, not its name. A directory called `services` may hold anything.

For each subsystem record: responsibility (one line), main entry files, what it depends on, what depends on it, and the evidence for each statement. Identify these roles where they exist: presentation, application/service layer, business logic, data access, shared utilities, infrastructure/config, external integrations, public API surface (what outside callers use), internal API (what other modules use).

## Naming patterns only with evidence

A pattern name is a claim. Check its signature before using it.

| Pattern | Signature to verify in code |
|---|---|
| Layered | Dependencies point one way (presentation → logic → data). Verify with edges, not directory names. |
| MVC / MVVM | Distinct model, view, controller/view-model types; views do not touch persistence directly. |
| Hexagonal / ports and adapters | Core defines interfaces; adapters implement them; core imports no adapter. |
| Plugin / extension | A registry or discovery mechanism loads modules by name or config. |
| Event-driven | Producers and consumers share event names/types, not direct imports. Look at `implicit_orphans`. |
| Modular monolith | Modules with narrow public surfaces inside one deployable. |
| Microservices | Separately deployable units (own build/Dockerfile) talking over network contracts. |
| Entity-component / data-oriented | Behaviour in systems iterating over plain data. Common in games. |

If the code is a mix, say it is a mix. "No consistent pattern" is a legitimate finding for a small project and not necessarily a problem.

## Calibrating to project size

Judge the architecture against what the project needs. A 600-line script with one module is not "missing a service layer". A 200k-line system with no module boundaries is a real finding. State the scale you judged against (files, LOC, number of contributors if visible from history, deployment complexity) before listing weaknesses.

## Health dimensions and what counts as evidence

| Dimension | Evidence worth citing | Not sufficient on its own |
|---|---|---|
| Cohesion | A module whose files serve unrelated purposes; a file mixing I/O, parsing and business rules (cite functions) | File length |
| Coupling | Cycles, hubs, high fan-out, a module reaching into another's internals (cite edges) | A single import |
| Separation of concerns | Business rules inside UI or SQL inside handlers (cite lines) | Absence of a framework layer |
| Abstraction quality | An interface with one implementation and many pass-through wrappers; or a leaky abstraction callers must work around | "Too many/too few classes" |
| Dependency direction | Stable, low-level modules importing high-level ones (instability metric as a pointer, then read) | Instability ratio alone |
| Duplication | Same business rule implemented in two places with divergent behaviour (cite both) | Similar-looking boilerplate |
| Error handling | Swallowed exceptions, inconsistent error shapes across a boundary, no handling on I/O paths | A different style from your preference |
| Testability | Logic only reachable through global state, network or time with no seam | Low test count by itself (see debt doc) |
| Extensibility / maintainability | Evidence from history or repeated edits across many files for one change (if available) | Opinion |

Instability (`depends_on / (depended_on_by + depends_on)`) is a descriptive ratio. Leaf modules are naturally unstable. It points you at where to read; it never proves a problem.

## Deviation is not a defect

Do not report an unconventional structure as a flaw unless you can state a concrete cost: what it makes harder or riskier, and where. Unfamiliar is not wrong. Before calling something a problem, ask: what would change for a developer working here, and can I point to code that shows it? If not, leave it out or file it as a neutral observation.

## Output: hierarchical map

Present subsystems as an indented tree, with a one-line responsibility and a dependency note per node, followed by the module-level Mermaid diagram from `graph_exporter.py export`. Mark any subsystem you did not open as "structure inferred from graph and names, contents not read".

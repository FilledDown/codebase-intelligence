# Dependency analysis (Layer C)

## Contents
- Building the model
- Reading the output
- Declared versus discovered dependencies
- Cycles
- Fan-in, fan-out and hubs
- Finding abstraction violations
- What the graph cannot see
- Analyzer depth by language
- Adding an analyzer

## Building the model

```
python scripts/dependency_analyzer.py analyze <repo> --out <scratch>/deps.json --summary
python scripts/graph_exporter.py export <scratch>/deps.json --level module            # Mermaid
python scripts/graph_exporter.py export <scratch>/deps.json --format dot --level file --focus path/to/file.py --hops 2
```

Write outputs to a scratch directory outside the repository, or into `.codebase-intelligence/` if the user opted into persistence. Writing `deps.json` into the repo root pollutes the working tree and gets fingerprinted as a project file.

The analyzer parses text. It never imports, compiles or executes repository code.

## Reading the output

Every edge carries `evidence`:
- **discovered**: written in the source and resolved to a repository file by a deterministic rule (for example a relative import that exists).
- **inferred**: resolved by a heuristic: suffix matching, an ambiguous name, a naming convention, a string-keyed event.

These describe how the *edge* was obtained. A discovered edge proves a static reference exists (VERIFIED); it does not prove the code path runs. An inferred edge is INFERRED until you read both ends.

Always check `coverage` first: `files_analyzed` versus `files_listed`, `skipped`, `truncated`, and per-language `analyzer` (null means that language's relationships are invisible). Say so in the report whenever it matters.

## Declared versus discovered dependencies

`declared_vs_discovered` compares manifest entries against imports found in source. Both lists are **candidates**:
- *Declared, never imported*: a CLI tool, a plugin loaded by config, a peer or runtime dependency, a test-only package, or dead weight.
- *Imported, not declared*: standard library, a parent workspace's manifest, an import-name/package-name mismatch, or genuinely missing.

Investigate each before calling it a finding. Report unresolved imports (`unresolved`) separately: they may be generated code, path aliases or analyzer gaps, not missing files.

## Cycles

`cycles` lists strongly connected components over *discovered* edges. `import_time_cycle: true` means the cycle exists through module-level references (execute at import), which can cause initialisation-order failures in many languages. A cycle that exists only through lazy or type-only references is usually benign. For each cycle, open the files and say which edge is the "wrong way" (the one that violates the intended direction), and what the smallest break would be.

## Fan-in, fan-out and hubs

- **High fan-in** is normal for utilities and core types, and a risk for anything volatile. A change to a high-fan-in file has a wide blast radius; its tests matter most.
- **High fan-out** means a file knows about many things. Orchestrators legitimately do. A *business logic* file with high fan-out is a coupling candidate.
- **Hubs** (fan-in and fan-out both ≥ 3) sit in the middle of traffic. They are where changes ripple and where bugs hide. Read them.
- `top5_target_share` measures concentration: how much incoming traffic lands on five files. High values suggest bottlenecks; they are not defects in themselves.

## Finding abstraction violations

The graph tells you where to look; reading confirms. Look for edges that cross an intended boundary:
- presentation code importing data-access code directly;
- core/domain modules importing framework, transport or database modules;
- one module importing another's private/internal files instead of its public surface;
- test-only helpers imported from production code.

State the intended boundary (and how you know it is intended: docs, directory convention, or the majority of other edges), cite the edge, and label the finding VERIFIED (edge exists) with INFERRED intent unless the project documents the boundary.

## What the graph cannot see

Runtime wiring: dependency-injection containers, reflection, dynamic imports with computed names, plugin loading, framework conventions (file-based routing, decorators registering handlers), configuration-driven behaviour, generated code, and network calls between services. Route registration, ORM models and schema migrations are typical blind spots. Treat "no edge" as "no static edge". See `change-impact-analysis.md` for how to search for these.

## Analyzer depth by language

| Language | Analyzer (depth) | What is resolved | What is not |
|---|---|---|---|
| Python | `python-ast` (ast) | Imports parsed with the `ast` module, resolved by repository path suffix | `sys.path` manipulation, namespace packages, runtime-generated modules, attribute-level use |
| JavaScript, TypeScript | `javascript-regex` (regex) | ES `import`, `require`, literal dynamic `import()`, re-exports, tsconfig/jsconfig path aliases, on comment-stripped source | Non-literal or computed paths, other bundler aliases, file-based routing, DI containers, types (no TypeScript compiler) |
| C, C++ | `cfamily-include` (regex) | `#include` graph; include paths from literal CMake `include_directories` / `target_include_directories` | Preprocessor evaluation (all conditional includes are counted), calls between translation units |
| Java | `java-import` (basic) | Explicit imports; wildcard imports as inferred edges | Same-package references (no import needed), DI, reflection, annotation processing |
| C# | `csharp-using` (basic) | `using` directives mapped to files declaring the namespace (inferred) | Same-namespace references, partial classes across files, DI wiring |
| Go | `go-import` (basic) | Package imports via `go.mod` module paths; edges point at package directories | Symbol use inside a package, build tags, generated code |
| Rust | `rust-mod` (basic) | `mod x;` to files (discovered); `use crate::...` against the module tree (inferred) | Macros, cfg-gated modules, `#[path]`, workspace re-exports |
| PHP | `php-use` (basic) | `use` via composer PSR-4 prefixes (discovered) or path suffix (inferred); literal `require`/`include` | Same-namespace references, autowiring, framework containers |
| Ruby | `ruby-require` (basic) | Literal `require` / `require_relative` (repository `require` is inferred) | Autoloading (Rails/Zeitwerk), metaprogramming, constant resolution |

"basic" means import-level extraction only. It is not a claim of full language support. Languages with no analyzer (Kotlin, Swift, Scala, Lua, and so on) appear in the inventory and in `coverage` with `analyzer: null`; their relationships are invisible to the graph and must be read manually.

Read the `limitations` array in the model output: it is the authoritative statement for that run. Do not claim "full support" for a language: the depth column is what exists.

## Adding an analyzer

Subclass `Analyzer` in `scripts/analyzers/__init__.py` (set `name`, `version`, `languages`, `extensions`, `depth`, `limitations`; implement `analyze(ctx, rel, text)` using `add_edge`, `add_external`, `add_unresolved`) and list it in `builtin_analyzers()`. For a private analyzer, pass `--plugin FILE` with a Python file that defines `ANALYZERS`; the file must live **outside** the analysed repository, because code inside the repository is untrusted and is refused.

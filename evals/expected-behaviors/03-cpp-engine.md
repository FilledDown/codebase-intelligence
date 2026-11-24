# Scenario 03: C++ project: headers, implementation files, CMake

_Generated from `evals/evals.json`. Edit that file, then run `python evals/render_expected_behaviors.py`._

## Why this scenario exists

Checks header/implementation relationships, include-path resolution through CMake, and honesty about what an include graph can and cannot say.

## Test setup

- Fixture: `evals/test-scenarios/03-cpp-engine/repo`
- Run the fixture only from a scratch copy; never from the skill directory.

## User prompt

> I'm new to this C++ project. Explain how the files fit together, what the build produces, and which headers matter most.

## Expected behaviour

Include chain engine.hpp -> renderer.hpp -> vec2.hpp; main.cpp is the entry of the `game` executable; CMake builds `game` and `test_vec2` with `include/` on the include path; vec2.hpp is the leaf header.

## Scoring criteria

Pass/fail per criterion against the response and transcript. Score = criteria passed / total. Metric tags show which quality each criterion measures.

| # | Criterion | Metrics |
|---|---|---|
| c1 | Describes the include chain engine.hpp -> renderer.hpp -> vec2.hpp and which .cpp files implement which headers | accuracy, completeness |
| c2 | Identifies src/main.cpp as the entry of the game executable and tests/test_vec2.cpp as a separate test executable | accuracy, evidence_quality |
| c3 | Reads CMakeLists.txt correctly: two executables (game, test_vec2) and include/ added through target_include_directories | accuracy, completeness |
| c4 | Identifies vec2.hpp as the foundational header others depend on, and explains why changes to it ripple widely | accuracy |
| c5 | Says the analysis is based on the #include graph and reading, not on a compiler, call graph or ownership analysis | evidence_quality |
| c6 | Treats standard headers (vector, iostream, cstdio, cassert) as external, not as project files | accuracy |

## Failure conditions

Any one of these makes the scenario a FAIL regardless of score.

- Invents third-party libraries (SDL, OpenGL, Boost) or claims the renderer draws graphics (it prints coordinates)
- Claims to have compiled or run the project
- Claims call-graph or memory-ownership conclusions that were not derived from code that was read

## Deterministic checks (run locally, no model needed)

`python evals/run_deterministic.py --scenario 3`. These verify that the scripts surface the planted facts; they do not score Claude's answer.

- `include-chain-1` (edge)
- `include-chain-2` (edge)
- `include-dir-resolution` (edge)
- `main-entry` (entry_point)
- `std-external` (external)
- `target-game` (build_target)
- `target-test` (build_target)
- `vec2-impact` (impact_dependents)

## Requires a Claude runtime

Scoring every criterion and failure condition above. No such run has been recorded in this repository.

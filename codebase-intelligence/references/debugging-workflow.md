# System-level debugging

## Contents
- Principle
- Procedure
- Hypothesis table
- Using tests and execution safely
- Output
- Fixing

## Principle

Find the cause before changing code. A fix that rests on an unverified guess can hide the symptom and leave the defect. Prefer the smallest change that addresses the confirmed root cause, and say which hypothesis it addresses.

## Procedure

1. **Expected versus observed.** Write both in one sentence each. If the report is vague (for example "it's broken"), ask for the exact input, the observed output or error, and the expected result. This is the one place where a short clarifying question is usually worth it.
2. **Locate the execution path.** Find the trigger and trace it with `behavioral-analysis.md`. Use `dependency_analyzer.py locate --term` on the error message text, route, or symptom words to find where it surfaces.
3. **List failure points** along the path: every step where the observed result could first diverge from expected (inputs, parsing, state, ordering, async, external calls, config, error handling that masks failure).
4. **Trace state and data** across those points: what value does each step receive and produce? Check the shape and range assumptions at each boundary.
5. **Inspect error handling**: swallowed exceptions, default values that hide failure, retries, fallbacks, logging that omits the cause.
6. **Check dependencies and environment**: library versions in manifests/lockfiles, config keys (`env:` nodes), feature flags, platform-specific branches. A bug that only appears in one environment is often configuration.
7. **Generate competing hypotheses** (at least two unless the evidence is already decisive). Include the dull ones: wrong input, stale build, misconfiguration.
8. **Decide what would confirm or reject each hypothesis**, and pick the cheapest discriminating check.
9. **Narrow with evidence**: read the specific code, run an existing test if it is safe to (see below), or ask the user to run a command or share a log.

## Hypothesis table

| # | Hypothesis | Supporting evidence | Contradicting evidence | Confidence | Cheapest check that discriminates |
|---|---|---|---|---|---|

Evidence cells cite `file:line` and say VERIFIED or INFERRED. Update the table as checks come in; drop rejected hypotheses explicitly ("rejected because ...") so the reader sees why.

## Using tests and execution safely

- Running an existing test suite executes repository code. Do it only when the user has asked for it or agreed, in a sandbox appropriate to the project, and without installing packages unprompted. Say exactly what you ran and show real output.
- If you did not run anything, say "not executed". Never describe a test result you did not obtain from a tool.
- Do not execute scripts merely because they exist in the repository. Prefer reading them.
- If reproducing requires secrets, production data or services you cannot reach, say so and give the user the commands to run, with what output to bring back.

## Output

- **Most likely explanation(s)**, ranked, each with evidence for and against.
- **Relevant files** (`file:symbol`).
- **Diagnostic steps** in order of cheapness, each stating what outcome confirms or rejects which hypothesis.
- **Confidence** in the top hypothesis and what is missing.
- **Recommended next action.**

## Fixing

Once a hypothesis is confirmed, state the root cause, then propose the smallest change that removes it. If the fix touches shared code, run `change-impact-analysis.md` on it first (a short version is fine). Add or point to a test that fails before the fix and passes after, if the project has a test setup. Do not refactor around the bug in the same change.

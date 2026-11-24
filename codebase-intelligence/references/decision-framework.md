# Architectural decision framework

## Contents
- Procedure
- Principles
- Decision matrix
- Architecture Decision Records
- Existing decisions and history
- Planning a new feature

## Procedure

1. **Understand the existing architecture** (`architecture-analysis.md`): its subsystems, conventions, and where the decision touches them.
2. **State the decision and its requirements**: what must be true afterwards, what is out of scope, hard constraints (deadline, team skills, hosting, compatibility, budget).
3. **Find what already exists**: patterns the codebase already uses for this kind of problem, and abstractions that could be reused. Reuse beats invention.
4. **List genuinely different options**, including "do the smallest thing" and "change nothing". Two or three real options beat six variations.
5. **Compare** on the dimensions below, citing repository evidence where you can.
6. **Recommend one** and say why in terms of this project, not general best practice. Say what would change your mind.
7. **Write an ADR** if the decision is significant (hard to reverse, affects several modules, or will be questioned later).

## Principles

- **Prefer the simplest architecture that meets the actual requirements.** Do not introduce microservices, layers, patterns, queues or frameworks because they are fashionable or "best practice". Add structure to remove a specific, demonstrated cost.
- **Preserve existing conventions** unless there is a concrete reason to change them; a second way of doing the same thing has its own cost.
- **Cost the migration**, not just the end state: coexistence period, data migration, rollback, team learning.
- **Prefer reversible choices** when uncertain. Say how hard each option is to undo.
- **Consider testing and operations** as part of the design, not afterwards.

## Decision matrix

Use one when options trade off along several dimensions. Rate each cell low/medium/high (or ✓ / ~ / ✗) with a short reason; avoid numeric totals, which imply a precision the judgments do not have.

| Dimension | Option A | Option B | Option C (do less) |
|---|---|---|---|
| Fit with existing patterns | | | |
| Implementation complexity | | | |
| Migration cost and risk | | | |
| Testing requirements | | | |
| Maintenance burden over time | | | |
| Performance / scalability *as actually needed* | | | |
| Reversibility | | | |
| Operational burden | | | |

Weigh the dimensions that matter to *this* project's stated constraints, and say which those are.

## Architecture Decision Records

Use `templates/architecture-decision-record.md`. Each ADR contains: **Context**, **Problem**, **Constraints**, **Alternatives considered**, **Decision**, **Consequences** (good and bad), **Risks**, **Reversibility**, and **Date** (today's actual date). Mark any status as *proposed* until the user accepts.

Where to put it: show the ADR in the reply by default. Write it into the repository (for example `docs/adr/`) only if the project already keeps ADRs there or the user asks; check for an existing numbering convention and follow it. Writing a file into the repository is a modification and needs the user's say-so.

## Existing decisions and history

Never invent why an existing decision was made. If you explain an existing structure, label it: "Inferred rationale (not documented): ...", and base it on evidence such as comments, commit messages (if you read them), docs, or consequences visible in the code. If there is no evidence, write "rationale unknown". Likewise do not claim an architecture was "chosen for" a quality it merely has.

## Planning a new feature

Use the codebase model to plan; keep it proportional. For a trivial change, a few lines. For a significant feature, include:
- requirements and acceptance criteria;
- existing components to reuse (`file:symbol`) and the convention to follow;
- files likely to be created and modified;
- required interfaces and data-flow changes;
- dependencies to add (justify each);
- potential regressions (run the change-impact procedure on the touch points);
- tests to add and tests to run;
- an implementation order split into independently verifiable milestones, each leaving the system working;
- verification criteria for "done".

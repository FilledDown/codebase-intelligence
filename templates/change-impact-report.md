# Change Impact Report: <change>

> Template for a change impact analysis. Never classify a component as unaffected because no reference was found: give the positive evidence. The impact command of report_generator.py pre-fills the static-reach tables; run its verify command before delivering. Delete this note.

## 1. Proposed Change

[[TODO(claude): The change, precisely, including what must stay compatible (API, wire format, schema, config keys, CLI flags).]]

## 2. Existing Implementation

[[TODO(claude): How the affected behaviour works today, confirmed by reading (`file:symbol`): config keys, DB structures, external contracts.]]

## 3. Directly Affected Components

[[TODO(claude): Table: component | relationship | why affected | expected modification | potential regression | confidence | verification. Include only components you read.]]

## 4. Indirectly Affected Components

[[TODO(claude): Same columns. Add 'Potentially affected' (hidden channels found, not yet read) and 'Unaffected after investigation' (with the positive evidence for each).]]

## 5. Potential Regressions

[[TODO(claude): Behaviours that could silently change, tied to the components above.]]

## 6. Required Changes

[[TODO(claude): Per component: the expected modification.]]

## 7. Testing Strategy

[[TODO(claude): Tests that reach the change, tests to add, what to run, critical paths with no tests. Say what was and was not executed.]]

## 8. Unknowns and Assumptions

[[TODO(claude): Each item labelled UNKNOWN or INFERRED with what would verify it (other repositories, runtime config, owners).]]

## 9. Recommended Implementation Sequence

[[TODO(claude): Smallest safe order; each step independently verifiable and, where possible, reversible.]]

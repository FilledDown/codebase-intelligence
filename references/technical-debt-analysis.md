# Technical debt analysis

## Contents
- What counts as debt
- What does not count
- Finding record
- Prioritization model
- Effort categories
- Using graph leads
- Output

## What counts as debt

Debt is a present condition that makes the next change slower, riskier or more expensive, or that makes a failure more likely or more damaging, and which you can point to in the code. If you cannot name the cost and the location, it is not a finding.

Typical forms, each of which still needs evidence:
- **Excessive coupling**: cycles, hubs, modules reaching into each other's internals.
- **Duplicated business logic**: the same rule implemented in several places, especially if the copies already differ.
- **Unclear ownership**: several components writing the same data or implementing the same responsibility.
- **Fragile interfaces**: callers depend on undocumented ordering, formats or side effects.
- **Inconsistent error handling** across a boundary, swallowed errors, or error paths that leave state half-updated.
- **Missing abstraction boundary** where one is needed to change something that changes often (for example, vendor SDK calls scattered through the code when the vendor is likely to change).
- **Overly complex modules**: complexity you can show makes changes error-prone (deep nesting, many interacting flags), not merely long files.
- **Unnecessary dependencies**: declared and unused, or large dependencies used for one trivial function.
- **Untestable components**: logic reachable only through global state, network or time with no seam.
- **Risky shared state**: mutable globals, singletons shared across threads or requests.
- **Repeated workarounds**: the same hack in several places, a sign of an unfixed root cause.
- **Outdated dependencies** with a concrete consequence (known security issue, end of support, blocked upgrade).
- **Missing tests around critical behaviour**: name the behaviour (payment, auth, data migration), not a coverage percentage.

## What does not count

- Personal style preferences, formatting, naming taste.
- Unfamiliar or unconventional patterns that work and are consistent.
- TODO/FIXME counts or file length on their own.
- A deviation from a textbook architecture with no demonstrated cost at this project's scale.
- Anything you cannot connect to a cost.

When unsure, put it under "observations" with an explicit note that no cost was shown, rather than in the findings.

## Finding record

For every finding give: **problem**; **evidence** (`file:symbol`, line, or edge; VERIFIED/INFERRED); **affected components**; **why it matters**; **likely consequences**; **suggested correction** (smallest change that fixes it, consistent with existing conventions); **estimated effort category**; **priority**; **confidence**.

## Prioritization model

Judge each factor on a three-step ordinal scale (low / medium / high) and give a short reason for any "high". The factors are not weighted numbers on purpose: the inputs are judgments, and arithmetic on them would suggest precision that does not exist.

| Factor | Question |
|---|---|
| Impact | If it bites, how bad is it (data loss, outage, security exposure, slow delivery)? |
| Likelihood | How likely is it to bite given how the code is used and changed? |
| Exposure | How often is this code path run or edited? |
| Scope | How many components are affected? |
| Cost of correction | How much work and risk to fix? (Effort category.) |
| Confidence | How strong is the evidence that the problem is real? |

Priority rule of thumb: **act first** where impact is high and likelihood or exposure is at least medium and confidence is at least medium; **act soon** where impact is medium with high exposure, or any high-impact finding whose fix is cheap; **plan** where scope is large and cost high, breaking it into steps; **watch** where likelihood is low or confidence is low (say what would raise confidence). Cheap high-value fixes come before expensive medium-value ones. A low-confidence high-impact finding is a prompt to verify, not to act.

## Effort categories

| Category | Meaning |
|---|---|
| S | Localised change in one file or function; one test to confirm |
| M | A few files in one module; existing tests adjusted or added |
| L | Cross-module change, interface migration, or data migration with staged rollout |
| XL | Architectural change needing a plan, milestones and a coexistence period |

These are relative sizes, not hour estimates.

## Using graph leads

`metrics.hubs`, `cycles`, `highest_fan_in`, `highest_fan_out`, `isolated_source_files`, `declared_vs_discovered` and `unresolved` are leads. Open the files before turning any of them into a finding. Isolated files may be entry points, plugins or dead code; declared-but-unimported dependencies may be tools or runtime dependencies. For "missing tests", look at which critical files have no test file reaching them (`impact` reports tests reached for a seed) and then check whether the behaviour is tested indirectly.

## Output

Findings ordered by priority, each as a compact record. Keep the list short: five well-evidenced findings beat thirty speculative ones. Finish with the highest-leverage first step. Do not invent a numeric "debt score".

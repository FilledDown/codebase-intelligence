# Example: change impact analysis with hidden coupling

> **Provenance.** Worked example of a change-impact report against the bundled fixture `evals/test-scenarios/04-hidden-coupling/repo`. The impact data quoted comes from `scripts/graph_exporter.py impact` on that fixture; the report structure is templates/change-impact-report.md. The prose is an illustration of the workflow's output, **not** a recorded model run.

**User:** "I want to change the rounding in `shop/pricing.py` so it always uses banker's rounding and drop the `ROUNDING_MODE` switch. What else will be affected?"

Commands used (read-only):

```
python scripts/dependency_analyzer.py analyze <repo> --out deps.json
python scripts/graph_exporter.py impact deps.json --seed shop/pricing.py --out impact.json
python scripts/dependency_analyzer.py locate <repo> --term ROUNDING_MODE --term order.priced
```

## 1. Proposed Change

Replace the `ROUNDING_MODE`-dependent rule in `shop/pricing.py:8` with a fixed `ROUND_HALF_EVEN`, and remove the environment variable. Must stay compatible: the value returned by `price_order`, and the `order.priced` event payload emitted at `shop/pricing.py:15`.

## 2. Existing Implementation

[VERIFIED] `round_total` reads `ROUNDING_MODE` at call time (`shop/pricing.py:8`) and rounds half-even when it is `"bankers"`, otherwise half-up. `price_order` rounds the order total, emits `order.priced` with the rounded total as a string, and returns it.

## 3. Directly Affected Components

Static import analysis (impact.json) found these dependents of `shop/pricing.py`:

| Component | Relationship | Why affected | Expected change | Regression risk | Confidence | Verify by |
|---|---|---|---|---|---|---|
| `shop/orders.py` | Calls `pricing.price_order` (`shop/orders.py:1`) | Receives the new rounding | None in code | Order totals change by one cent on exact-half values | High (VERIFIED, read) | Run the order tests with half-even expectations |
| `tests/test_pricing.py` | Imports `pricing`; asserts `"2.67"` for `"2.665"` under half-up (`tests/test_pricing.py:8`) | The assertion encodes the old rule | Update the expected value to `"2.66"` and remove the env setup | Test fails until updated | High (VERIFIED) | Run the test |

## 4. Indirectly Affected Components

| Component | Path from the change | Evidence | Why affected | Confidence |
|---|---|---|---|---|
| `shop/cli.py` | `pricing` → `orders` → `cli` | discovered imports | Prints the order total (the demo input is `2.665`, an exact-half value); value changes only for exact-half amounts | High |
| `shop/notifications.py` | `pricing` → event `order.priced` → listener (`shop/notifications.py:8`) | **inferred**: the link is a string key matched between `bus.emit` (`shop/pricing.py:15`) and `bus.on` | The receipt prints the rounded total from the payload | Medium: assumes the same bus instance; read `shop/bus.py` to confirm |

### Potentially affected (not reachable through imports)

| Component | Hidden channel | Finding |
|---|---|---|
| `shop/reports.py` | The same environment variable | [VERIFIED] It reads `ROUNDING_MODE` itself at `shop/reports.py:7` and re-implements the same rounding rule so report totals match invoices. It does **not** import `pricing`, so the import graph never lists it. If `pricing` goes half-even-only and `reports.py` still honours the variable, reports and invoices can disagree by a cent. |
| Deployment config, docs, CI | `ROUNDING_MODE` | UNKNOWN: this repository contains no deployment files; any place that sets the variable becomes dead configuration. |

### Unaffected after investigation

`shop/bus.py`: read; it only dispatches handlers by event name and never inspects the payload.

## 5. Potential Regressions

- Totals differ by one cent on exact-half amounts such as 2.665, in orders, receipts and, unless changed together, reports.
- Anything comparing stored totals to freshly computed ones (none found in this repository; external consumers UNKNOWN).

## 6. Required Changes

`shop/pricing.py` (the change); `shop/reports.py` (use the same rule, ideally by calling the shared function instead of re-implementing it); `tests/test_pricing.py` (new expectation); remove `ROUNDING_MODE` from any deployment configuration.

## 7. Testing Strategy

Tests that statically reach the seed: `tests/test_pricing.py`. Gap: nothing tests `shop/reports.py` or the receipt text. Add a test that `reports.quarterly_revenue` and `pricing.round_total` agree on 2.665. Not executed in this analysis.

## 8. Unknowns and Assumptions

- UNKNOWN: other services or reports that read the same variable or consume the `order.priced` event outside this repository.
- INFERRED: `shop/notifications.py` receives the event, based on a matching string key.
- The graph is static: it cannot see runtime wiring beyond what is listed above.

## 9. Recommended Implementation Sequence

1. Add a failing test that pins the new behaviour for `2.665` in both `pricing` and `reports`.
2. Make `reports.py` call `pricing.round_total` (removes the duplicate rule, so the two cannot drift).
3. Change `pricing.py` to fixed half-even; update `tests/test_pricing.py`.
4. Remove `ROUNDING_MODE` from deployment configuration after the code no longer reads it.

Each step leaves the system consistent; steps 1-3 can ship together.

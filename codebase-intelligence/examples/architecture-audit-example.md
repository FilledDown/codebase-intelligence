# Example: architecture audit of a small project

> **Provenance.** Worked example of a full audit's shape for a deliberately small project, written against the bundled fixture `evals/test-scenarios/06-antipattern-duplication/repo`. Graph facts are real output of scripts/dependency_analyzer.py on that fixture; the three totals quoted in finding 1 were checked by calling the three fixture functions in a scratch interpreter (do that only with the user's agreement when the code is not yours). The prose is an illustration, **not** a recorded model run. Sections with nothing to say are shortened on purpose: padding is a defect.

## 1. Executive Summary

A seven-file Python checkout script (one file is an empty package marker). The structure is simple and mostly fine at this size. Two real problems: the discount rule is copied into three modules and the copies no longer agree (a customer-visible money bug), and `cart` and `checkout` import each other. Both are small, local fixes. No new architecture is warranted. Coverage: all seven Python files were parsed and read.

## 2. Project Identity

[VERIFIED] A command-line style program: `shop/main.py` is the entry point (`__main__` guard), calling `shop/ui.py:show_cart`, which reads cart rows from SQLite (`shop/db.py`) and prints a total. No manifest, tests or README exist, so the purpose is inferred from the code.

## 3. Technology Stack

Python standard library only (`sqlite3`, `decimal`, `math`). No third-party dependencies. [VERIFIED: the graph lists no external packages]

## 4. Architectural Overview

A flat package with no layering: `ui` → `cart` and `db`; `cart` ↔ `checkout`; `invoice` has no inbound or outbound project edges. At 7 files and a few dozen lines of logic, a flat structure is appropriate.

## 5. Major Subsystems

`ui.py` (presentation), `db.py` (SQLite access with a module-level connection), `cart.py`, `checkout.py`, `invoice.py` (three places that compute money). That last group is the problem.

## 6. Dependency Analysis

- 9 internal edges, all discovered, no unresolved imports; 4 of them are `from shop import ...` edges to the empty package marker `shop/__init__.py`, which carry no information. Highest fan-out: `shop/ui.py` (3, one of which is the marker).
- **One import cycle (module-level imports):** `shop/cart.py:1` imports `checkout`, and `shop/checkout.py:3` imports `cart`. [VERIFIED by the cycle report and by reading both files]
- `shop/invoice.py` is isolated in the graph. This is the clue that the duplicated logic does not show up as coupling: copy-paste has no import edge.

## 7. Important Execution Flows

`python -m shop.main` → `ui.show_cart(1)` → `db.fetch_cart` → `cart.cart_total` → `checkout.shipping_for` → printed total. [VERIFIED] `final_price` and `invoice_total` are not on this path; nothing in this repository calls them. [VERIFIED by search; external callers UNKNOWN]

## 8. Data Flow Analysis

Cart rows (sku, price, qty) come from SQLite as floats and are totalled in three different ways (floats in `cart.py` and `checkout.py`, `Decimal` in `invoice.py`). No validation or authorization exists: acceptable for a local script, worth revisiting if it ever serves requests.

## 9. Architectural Strengths

Small, readable modules; the dependency graph is shallow; the database is isolated in one file.

## 10. Architectural Weaknesses

See Technical Debt. The shared module-level SQLite connection in `shop/db.py` is mildly risky if the program ever becomes multi-threaded; at present it is a single-threaded script, so it is an observation, not a finding.

## 11. Technical Debt

**Finding 1: the discount and total rule is duplicated, and the copies diverge. (Priority: act first. Effort: S. Confidence: high.)**
- Evidence [VERIFIED]: the same `if subtotal > 100: ... * 0.9` appears at `shop/cart.py:6`, `shop/checkout.py:12` and `shop/invoice.py:6`, with three different roundings: `round(..., 2)` in `cart.py`, `math.floor` in `checkout.py:14`, and `Decimal` with `ROUND_HALF_UP` in `invoice.py`.
- Consequence: the same cart (4 × 33.33) totals **119.99** in `cart_total`, **119.98** in `final_price`, and **119.99** in `invoice_total`. Separately, `invoice_total` omits shipping, so a 2 × 10.00 cart totals 24.99 in `cart_total` and `final_price` but 20.00 on the invoice.
- Why it matters: money totals that differ by cart and by document; the next change to the discount rule must be made in three places.
- Correction: one `price(items)` function, used by all three callers. Decide once how rounding and shipping work.

**Finding 2: import cycle between `cart` and `checkout`. (Priority: act soon. Effort: S. Confidence: high.)**
- Evidence [VERIFIED]: `shop/cart.py:1` and `shop/checkout.py:3`. The cycle does not fail today because both modules use the other only inside functions, not at import time. Also at `shop/checkout.py:14`, `if cart else 0` tests the imported module object, which is always truthy: dead logic left over from the cycle.
- Correction: move `shipping_for` into the new pricing function's module; `checkout` then has no reason to import `cart`.

**Observation, not a finding: `shop/ui.py:1` imports `db` directly.** In a 7-file script this is proportionate; no cost was shown. Revisit only if a second front end appears.

## 12. Potential Risks

Wrong totals presented to customers (finding 1). No tests exist for any money logic. UNKNOWN: whether `final_price` and `invoice_total` are called from outside this repository.

## 13. Missing Information

7 of 7 Python files parsed and read; the graph was not run with runtime tracing. Not available: tests, history, deployment, a description of intended rounding and shipping rules (needed to decide which of the three copies is "right").

## 14. Recommended Improvements

Add one pricing function and make the three call sites use it; add a test that pins the 119.99 example and the shipping case. That is the whole recommendation. **Not recommended:** services, repositories, dependency injection, or any layering: the project has one real problem, and it is a copy-paste problem.

## 15. Suggested Next Steps

1. Ask the owner which total is correct (rounding, shipping on invoices).
2. Add the failing test, then the single pricing function.
3. Delete the duplicates and the `cart` import in `checkout`.

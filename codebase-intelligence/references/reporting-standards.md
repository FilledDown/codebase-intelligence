# Reporting standards

## Contents
- Match the report to the request
- Quick look
- Full architectural audit
- Change impact report
- Onboarding
- Debugging and technical debt reports
- Style rules
- Before delivering

## Match the report to the request

The answer should be as large as the question. A question about one function gets a paragraph. A full audit gets the full structure. Do not produce a 15-section report to answer a narrow question, and do not give a one-line answer to "should we replace our auth system". When in doubt, answer concisely first and offer to go deeper.

Deliver the report in the conversation by default. Save it as a file or document when the user wants something to keep or share, and put it in the repository only if they ask. Generating a skeleton with `report_generator.py` is optional: it is useful for audits and impact reports where tables and counts save time.

## Quick look

For a question about a component or small area: the direct answer first, then the evidence (`file:symbol`), the relevant neighbours (what calls it, what it calls), and any caveat. Include confidence only if it is not obvious. No headers needed.

## Full architectural audit

Use `templates/architecture-report.md`. Sections, in order: Executive Summary; Project Identity; Technology Stack; Architectural Overview; Major Subsystems; Dependency Analysis; Important Execution Flows; Data Flow Analysis; Architectural Strengths; Architectural Weaknesses; Technical Debt; Potential Risks; Missing Information; Recommended Improvements; Suggested Next Steps.

Rules: the executive summary stands alone (what it is, its shape, the two or three findings that matter, how complete the analysis was). Skip a section that has nothing evidence-based to say rather than padding it, or say "nothing notable found" with what was checked. Missing Information is never empty: it states coverage and open questions.

## Change impact report

Use `templates/change-impact-report.md`. Sections: Proposed Change; Existing Implementation; Directly Affected Components; Indirectly Affected Components; Potential Regressions; Required Changes; Testing Strategy; Unknowns and Assumptions; Recommended Implementation Sequence. The per-component fields are in `change-impact-analysis.md`. Include "Potentially affected" and "Unaffected after investigation" (with the reason) in the affected-components sections.

## Onboarding

A map the reader can use on day one: what the system does, how to run and test it (as declared in the repository; say that you did not run it), the directory layout in plain words, the entry points, the three to five flows that matter, the conventions to follow, the danger zones (hubs, cycles, untested critical paths), and where to start reading. Keep it under a couple of pages unless asked for more.

## Debugging and technical debt reports

Debugging: the hypothesis table and diagnostic steps from `debugging-workflow.md`. Technical debt: the finding records from `technical-debt-analysis.md`, highest priority first, plus the one thing to do first.

## Style rules

- Lead with the answer or the most important finding.
- Every important claim carries an evidence tag and a location. Use `file:symbol` or `file:line`; put paths and symbols in backticks so `verify` can check them.
- Distinguish VERIFIED, INFERRED and UNKNOWN visibly (a bracketed tag at the start of the line works).
- Plain, specific language. No hype, no filler, no generic best-practice lists detached from this repository.
- Tables for comparisons and inventories; short prose or numbered lists for reasoning and sequences. A Mermaid diagram when a picture shows structure faster than words (module graph, a flow); label what the arrows mean.
- Say what you did not do: not read, not executed, not available.
- Recommendations: the smallest change that fixes the confirmed problem; no new layers, patterns or services without a stated, demonstrated need.

## Before delivering

1. Replace or delete every TODO marker.
2. Run `report_generator.py verify` on the report and fix every problem it lists.
3. Check that the coverage statement is accurate and that nothing is described as run that was not.
4. Re-read the executive summary: would someone who reads only that be misled about confidence or completeness?

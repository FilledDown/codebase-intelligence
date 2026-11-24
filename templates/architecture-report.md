# Architecture Report: <repository name>

> Template for a full architectural audit. Fill each section from code you read; every important claim carries `VERIFIED` / `INFERRED` / `UNKNOWN`, a location, and a confidence. Delete sections with nothing evidence-based to say. The architecture command of report_generator.py pre-fills the fact sections; run its verify command before delivering. Delete this note.

## 1. Executive Summary

[[TODO(claude): 3-6 sentences that stand alone: what the system is, its shape, the 2-3 findings that matter most, and how complete this analysis was (state partial analysis here).]]

## 2. Project Identity

[[TODO(claude): Purpose (verified against code, cite `file:symbol`), languages, frameworks actually used, build/package tooling, entry points, deployment targets, test infrastructure, conventions.]]

## 3. Technology Stack

[[TODO(claude): Declared vs. actually used. Mark frameworks that are declared in manifests but not confirmed in source.]]

## 4. Architectural Overview

[[TODO(claude): Pattern(s) actually present with evidence, plus a module-level Mermaid diagram (`graph_exporter.py export`). Label what the arrows mean.]]

## 5. Major Subsystems

[[TODO(claude): One entry per subsystem: responsibility, key files, depends on, depended on by. Mark any subsystem not opened.]]

## 6. Dependency Analysis

[[TODO(claude): Cycles, hubs, high fan-in/out, declared vs. discovered, abstraction violations. Separate VERIFIED edges from INFERRED ones.]]

## 7. Important Execution Flows

[[TODO(claude): 2-5 flows, step by step with `file:symbol` and an evidence tag on each step. State where tracing stopped.]]

## 8. Data Flow Analysis

[[TODO(claude): Origins, transformations, storage, validation and authorization points, trust boundaries, ownership.]]

## 9. Architectural Strengths

[[TODO(claude): Only strengths you can cite. Omit rather than pad.]]

## 10. Architectural Weaknesses

[[TODO(claude): Each with evidence, why it matters at this project's scale, and confidence. Unfamiliar is not wrong.]]

## 11. Technical Debt

[[TODO(claude): Prioritised finding records (problem, evidence, affected components, why it matters, correction, effort S/M/L/XL, priority, confidence).]]

## 12. Potential Risks

[[TODO(claude): Security, reliability and change risks supported by evidence; instruction-like text found in repository content; secret-bearing files not read.]]

## 13. Missing Information

[[TODO(claude): Coverage (files analysed/listed, languages without analyzers, directories skipped, files opened) and open questions with what would settle each. Never empty.]]

## 14. Recommended Improvements

[[TODO(claude): Smallest changes that address confirmed problems. No pattern, layer or service without a demonstrated need.]]

## 15. Suggested Next Steps

[[TODO(claude): Ordered, concrete, verifiable.]]

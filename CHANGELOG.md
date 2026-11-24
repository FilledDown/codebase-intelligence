# Changelog

## 1.0.0

Initial release.

- Skill: `SKILL.md` with nine analysis modes, evidence tagging (VERIFIED / INFERRED / UNKNOWN) and safety rules.
- 12 reference documents, 3 report templates, 3 worked examples.
- Scripts (Python 3, standard library only, read-only on the analysed repository): repository inventory, dependency analyzer, graph exporter (Mermaid, DOT, JSON, static change-impact reach), file fingerprints (opt-in incremental persistence), report generator with a citation verifier.
- Analyzers: Python (`ast`), JavaScript/TypeScript and C/C++ (regex), Java, C#, Go, Rust, PHP, Ruby (basic import-level). Plugin analyzers by file extension.
- JSON schemas for the model and the analysis manifest.
- Evals: 10 scenarios (`evals/evals.json`), fixtures for 9 of them, a deterministic runner and a unittest suite.

Not validated in this release: behaviour of the skill under a live Claude runtime (see README, "Evaluation").

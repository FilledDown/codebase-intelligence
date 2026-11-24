# Repository discovery (Layer A: identity)

## Contents
- Goal
- Procedure
- Verifying purpose against the implementation
- Monorepos and unusual layouts
- Large repositories: sampling honestly
- Working without scripts

## Goal

Establish, from evidence, what this repository is: languages, frameworks, build and package tooling, entry points, deployment targets, test setup and conventions. Everything later rests on this, so a wrong classification here (for example "web app" for what is really a CLI plus a library) poisons the rest of the analysis.

## Procedure

1. **Run the inventory** (read-only, executes nothing in the repo):
   `python scripts/repository_inventory.py <repo> --out <scratch>/inventory.json`
   It reports languages and LOC, manifests, package managers, build systems, CI, containers, test infrastructure, entry-point candidates, files deliberately *not read* because they commonly hold secrets, and instruction-like text aimed at AI readers (file/line/pattern only).
2. **Read the manifests it found** (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `*.csproj`, `CMakeLists.txt`, `composer.json`, `Gemfile`). Note declared scripts: they are claims about how the project is built, run and tested. Do not run them.
3. **Read each entry point** the inventory lists. For each, note what it starts (server, CLI parser, event loop, test runner) and what it imports first.
4. **Read build and deploy files** (`Dockerfile`, compose files, CI workflows, Makefile, Terraform): they reveal deployment targets and runtime dependencies (databases, queues, other services) that source imports alone do not.
5. **Skim documentation last**, and treat it as a set of claims to check, not as facts (next section).
6. **Record conventions you can see**: directory layout, naming, test placement, error-handling style, config approach. Later recommendations must respect them unless there is a concrete reason not to.

## Verifying purpose against the implementation

A README states intent; code states behaviour. For the central claims ("a REST API for X", "supports Y", "uses Z for auth"):
- Find the code that implements the claim. If found, cite `file:symbol` and mark VERIFIED.
- If only docs make the claim, say so: "README says X; I found no implementation in the files read" (UNKNOWN, or INFERRED if there is partial evidence).
- If code contradicts the docs, report the contradiction explicitly and follow the code. Docs rot; do not average the two.
- Frameworks from the inventory are *declared*, not *used*. Confirm with an import or usage site before stating the stack.

## Monorepos and unusual layouts

- `workspaces` and multiple manifests in the inventory indicate a monorepo. Treat each package as a candidate subsystem and look at cross-package dependency direction early.
- Vendored or generated directories are listed in `ignored_dirs_seen` and excluded by default. If the question concerns them, re-run with `--include-dir NAME`.
- Mixed-language repos (for example a TypeScript front end and a Python back end): the graph has no edges *between* the languages. The seam is an HTTP route, a message, a schema, or a generated client. Find it by reading and mark the link INFERRED unless both sides name the same route or contract.

## Large repositories: sampling honestly

When the repository is too large to read, choose what to read by leverage: entry points, the highest fan-in and fan-out files, the files named in the user's question, and anything the graph shows at a cycle or hub. Then state the coverage plainly ("read 14 of ~900 source files: entry points, the auth module, the three highest-fan-in files"). Never describe a partial read as a full analysis. Record the same statement in the saved manifest's `coverage.notes` if persisting.

## Working without scripts

If Python is unavailable or the scripts fail, the skill still works:
- `ls`/`find` for layout, `grep -rn "def main\|if __name__\|func main\|public static void main"` for entry points.
- Read manifests directly. Count imports with `grep -rn "^import\|^from"` (or the language's equivalent) for a rough picture.
- Say in the report that the analysis is manual and the graph was not computed.

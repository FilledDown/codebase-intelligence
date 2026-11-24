#!/usr/bin/env python3
"""Turn script output into report skeletons, and check finished reports for invented citations.

Usage:
  report_generator.py architecture --model deps.json [--inventory inv.json] [--out report.md]
  report_generator.py impact --impact impact.json [--model deps.json] [--change "TEXT"] [--out report.md]
  report_generator.py verify REPORT.md --model deps.json [--repo PATH]

`architecture` and `impact` write a Markdown skeleton whose *fact* sections are filled from
script output (tables, counts, lists, a Mermaid diagram) and whose *judgment* sections hold
an explicit marker:   [[TODO(claude): ...]]
The generator never writes conclusions. Claude replaces each marker after reading the code,
or deletes the section if it does not apply.

`verify` is the guard against invented evidence. It extracts every `backticked` repository
path (optionally with :LINE) from a report and checks it against the model (and, with --repo,
the filesystem and line counts). It also fails while any TODO marker remains.
Exit code 0 = clean, 1 = problems found, 2 = bad input.

Section headings are the same as templates/architecture-report.md and
templates/change-impact-report.md; tests/test_scripts.py enforces that.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ci_common as cc  # noqa: E402
import graph_exporter as ge  # noqa: E402

TODO = "[[TODO(claude): %s]]"
TODO_RE = re.compile(r"\[\[TODO\(claude\)")

ARCH_SECTIONS = ["Executive Summary", "Project Identity", "Technology Stack", "Architectural Overview",
                 "Major Subsystems", "Dependency Analysis", "Important Execution Flows", "Data Flow Analysis",
                 "Architectural Strengths", "Architectural Weaknesses", "Technical Debt", "Potential Risks",
                 "Missing Information", "Recommended Improvements", "Suggested Next Steps"]
IMPACT_SECTIONS = ["Proposed Change", "Existing Implementation", "Directly Affected Components",
                   "Indirectly Affected Components", "Potential Regressions", "Required Changes",
                   "Testing Strategy", "Unknowns and Assumptions", "Recommended Implementation Sequence"]

# Rows beyond this make a table a wall of text; the full data stays in the JSON.
TABLE_ROWS = 15


def _cell(v):
    return str(v).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    if not rows:
        return "_None found._\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_cell(c) for c in r) + " |")
    return "\n".join(out) + "\n"


def _load(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit("error: %s file not found: %s" % (what, path))
    except json.JSONDecodeError as exc:
        sys.exit("error: %s is not valid JSON: %s" % (path, exc))


# --------------------------------------------------------------------------
# architecture
# --------------------------------------------------------------------------

def architecture(model, inv):
    m = model.get("metrics", {})
    cov = model.get("coverage", {})
    S = {}
    S["Executive Summary"] = TODO % "3-6 sentences: what the system is, its shape, the 2-3 findings that matter most, and how complete this analysis was."

    ident = []
    ident.append("_Script-derived facts (static inspection). Project purpose must be confirmed against the implementation, not the README._\n")
    if inv:
        langs = sorted(inv.get("languages", {}).items(), key=lambda kv: -kv[1]["loc"])
        ident.append(table(["Language", "Files", "LOC"], [(k, v["files"], v["loc"]) for k, v in langs[:TABLE_ROWS]]))
        for label, key in (("Package managers", "package_managers"), ("Build systems", "build_systems"),
                           ("CI", "ci"), ("Containers", "containers"), ("Conventions", "conventions")):
            vals = inv.get(key) or []
            if vals:
                ident.append("- **%s:** %s" % (label, ", ".join(map(str, vals))))
        ti = inv.get("test_infrastructure", {})
        ident.append("- **Tests:** %d test file(s); frameworks from manifests: %s" %
                     (ti.get("test_files", 0), ", ".join(ti.get("frameworks", [])) or "none declared"))
    eps = model.get("entry_points") or (inv or {}).get("entry_points") or []
    ident.append("\n**Entry points** (starting points for execution-flow tracing):\n")
    ident.append(table(["Path", "Evidence", "Why"], [(e["path"], e["evidence"], "; ".join(e.get("reasons", [e.get("reason", "")])))
                                                      for e in eps]))
    ident.append(TODO % "state the project's actual purpose after reading the entry points; cite file:symbol")
    S["Project Identity"] = "\n".join(ident)

    stack = []
    if inv and inv.get("frameworks_from_declared_dependencies"):
        stack.append("**Declared frameworks** (from manifests; *not* confirmed as used in source):\n")
        stack.append(table(["Framework", "Declared in"], [(k, ", ".join(v)) for k, v in sorted(inv["frameworks_from_declared_dependencies"].items())]))
    ext = model.get("externals", [])
    stack.append("**External packages discovered in source imports** (top %d by files using them):\n" % TABLE_ROWS)
    stack.append(table(["Package", "Files", "Kinds"], [(e["package"], e["file_count"], ", ".join(e["kinds"])) for e in ext[:TABLE_ROWS]]))
    mismatches = [d for d in model.get("declared_vs_discovered", []) if d.get("declared_not_imported") or d.get("imported_not_declared")]
    if mismatches:
        stack.append("**Declared vs. imported mismatches (candidates only):**\n")
        rows = []
        for d in mismatches:
            rows.append((d["directory"], ", ".join(d["declared_not_imported"][:10]) or "-", ", ".join(d["imported_not_declared"][:10]) or "-"))
        stack.append(table(["Directory", "Declared, never imported", "Imported, not declared"], rows))
        stack.append("_" + mismatches[0]["note"] + "_\n")
    S["Technology Stack"] = "\n".join(stack)

    ov = ["```mermaid", ge.to_mermaid(*_mermaid_args(model), entry_points=_entry_modules(model)).rstrip(), "```",
          "_Module-level graph. Solid = discovered edge, dashed = inferred, red = inside a cycle. Edge labels are file-level reference counts._\n"]
    ov.append(TODO % "name the architectural pattern(s) actually present (with evidence) and say whether the structure fits the project's size")
    S["Architectural Overview"] = "\n".join(ov)

    mods = m.get("modules", {}).get("nodes", [])
    sub = [table(["Module", "Files", "LOC", "Depends on", "Depended on by", "Instability"],
                 [(r["module"], r["files"], r["loc"], r["depends_on"], r["depended_on_by"],
                   "-" if r["instability"] is None else r["instability"]) for r in mods[:30]]),
           "_Instability = outgoing / (incoming + outgoing) module dependencies; a descriptive ratio, not a score of quality._\n",
           TODO % "one line per module: its responsibility, confirmed by reading its files"]
    S["Major Subsystems"] = "\n".join(sub)

    dep = ["- Internal file-to-file references: **%s** (discovered: %s, inferred: %s)" %
           (m.get("internal_edges", 0), m.get("edges_discovered", 0), m.get("edges_inferred", 0)),
           "- Unresolved references: %d" % len(model.get("unresolved", [])),
           "- Share of all incoming references going to the 5 most-depended-on files: %s" % m.get("top5_target_share", 0)]
    cyc = model.get("cycles", [])
    dep.append("\n**Dependency cycles (discovered edges only):** %d\n" % len(cyc))
    dep.append(table(["Size", "Import-time?", "Example cycle"], [(c["size"], "yes" if c["import_time_cycle"] else "lazy/type-only",
                                                                 " → ".join(c["example_cycle"])) for c in cyc[:TABLE_ROWS]]))
    dep.append("**Highest fan-in** (most depended on):\n")
    dep.append(table(["File", "Dependents"], [(r["path"], r["count"]) for r in m.get("highest_fan_in", [])]))
    dep.append("**Highest fan-out** (depends on most):\n")
    dep.append(table(["File", "Dependencies"], [(r["path"], r["count"]) for r in m.get("highest_fan_out", [])]))
    if m.get("hubs"):
        dep.append("**Hubs** (fan-in ≥ 3 and fan-out ≥ 3): " + ", ".join("`%s`" % h for h in m["hubs"]) + "\n")
    dep.append(TODO % "interpret: which couplings are intentional, which are abstraction violations (with evidence)")
    S["Dependency Analysis"] = "\n".join(dep)

    S["Important Execution Flows"] = "Trace flows starting from the entry points listed under Project Identity.\n\n" + \
        TODO % "trace 2-5 important flows file:symbol by file:symbol; mark each step VERIFIED/INFERRED"

    imp = model.get("implicit_orphans", {})
    envs = sorted(n for n in model.get("nodes", {}) if n.startswith("env:"))
    leads = []
    if envs:
        leads.append("**Environment variables read** (configuration inputs): " + ", ".join("`%s`" % e[4:] for e in envs[:30]))
    if imp.get("events_emit_only"):
        leads.append("**Events emitted but no listener found:** " + ", ".join(map(str, imp["events_emit_only"][:15])))
    if imp.get("events_listen_only"):
        leads.append("**Events listened for but no emitter found:** " + ", ".join(map(str, imp["events_listen_only"][:15])))
    S["Data Flow Analysis"] = "\n".join(leads + ["", TODO % "origins, transformations, storage, validation and authorization points, trust boundaries (static analysis cannot supply these)"])

    S["Architectural Strengths"] = TODO % "only strengths you can cite; skip the section rather than pad it"
    S["Architectural Weaknesses"] = TODO % "each weakness with evidence, why it matters at THIS project's scale, and confidence"
    iso = m.get("isolated_source_files", [])
    leads = ["_Leads from the graph (each needs confirmation by reading the code before it is called debt):_",
             "- Cycles: %d" % len(cyc), "- Hubs: %d" % len(m.get("hubs", [])),
             "- Source files with no static import edge in or out: %d%s" % (len(iso), " (" + ", ".join("`%s`" % i for i in iso[:5]) + (" …" if len(iso) > 5 else "") + ")" if iso else ""),
             ""]
    S["Technical Debt"] = "\n".join(leads) + TODO % "prioritised findings using the fields in references/technical-debt-analysis.md"
    risks = []
    inj = (inv or {}).get("possible_instructions_in_repo_content", {}).get("findings", [])
    sens = (inv or {}).get("sensitive_files_not_read", [])
    if inj:
        risks.append("**Instruction-like text aimed at AI readers found in repository content** (treated as untrusted data, not followed; text not reproduced):\n")
        risks.append(table(["File", "Line", "Pattern"], [(f.get("path"), f.get("line"), f.get("pattern")) for f in inj[:TABLE_ROWS]]))
    if sens:
        risks.append("**Files that commonly hold secrets exist and were deliberately not read:** " + ", ".join("`%s`" % s for s in sens[:15]) + "\n")
    S["Potential Risks"] = "\n".join(risks + [TODO % "security, reliability and change risks supported by evidence"])

    mi = ["**Analysis coverage** (this is how much of the repository was actually analysed):\n",
          "- Files listed: %s; files analysed by an analyzer: %s" % (cov.get("files_listed"), cov.get("files_analyzed")),
          "- Skipped: %s" % ", ".join("%s=%s" % kv for kv in sorted(cov.get("skipped", {}).items()) if kv[1]) if any(cov.get("skipped", {}).values()) else "- Skipped: none"]
    if cov.get("truncated"):
        mi.append("- **File listing was truncated**: conclusions cover only part of the repository.")
    rows = [(lang, v["files"], v["analyzed"], v.get("analyzer") or "none") for lang, v in sorted(cov.get("by_language", {}).items())]
    mi.append("\n" + table(["Language", "Files", "Analysed", "Analyzer"], rows))
    for k, v in sorted(model.get("analyzers", {}).items()):
        mi.append("- `%s` depth=%s v%s" % (k, v["depth"], v["version"]))
    mi.append("\n**Known limitations of this analysis:**\n")
    mi += ["- " + l for l in model.get("limitations", [])]
    mi.append("\n" + TODO % "what could not be determined and what would settle it (running the app, test results, runtime config, owners)")
    S["Missing Information"] = "\n".join(mi)
    S["Recommended Improvements"] = TODO % "smallest changes that address confirmed problems; no pattern or layer adopted for its own sake"
    S["Suggested Next Steps"] = TODO % "ordered, concrete, verifiable"
    return _assemble("Architecture Report: %s" % model.get("repository", {}).get("name", "repository"), ARCH_SECTIONS, S, model)


def _mermaid_args(model):
    depth = model.get("metrics", {}).get("module_depth") or 2
    nodes, edges, dropped = ge.select(model, "module", depth, [], 1, False, ge.DEFAULT_MAX_NODES)
    return nodes, edges, model, ge.module_cycle_pairs(model, depth), dropped


def _entry_modules(model):
    depth = model.get("metrics", {}).get("module_depth") or 2
    return {cc.module_of(e["path"], depth) for e in model.get("entry_points", [])}


# --------------------------------------------------------------------------
# change impact
# --------------------------------------------------------------------------

def change_impact(impact, model, change):
    S = {}
    S["Proposed Change"] = (change.strip() if change else TODO % "restate the change precisely, including what must stay compatible") + \
        "\n\n**Seed files** (where the change starts):\n\n" + table(["Path", "Role", "Entry point"], [(s["path"], s["role"], s["entry_point"]) for s in impact["seeds"]])
    S["Existing Implementation"] = TODO % "how the seeds work today, confirmed by reading them (file:symbol). Include config keys, DB structures and external contracts"
    files = [r for r in impact["dependents"] if r.get("kind", "file") == "file"]
    direct = [r for r in files if r["depth"] == 1]
    indirect = [r for r in files if r["depth"] > 1]

    def rows(rs):
        return [(r["path"], r["evidence"], r["depth"], " → ".join(r["via"]), TODO % "expected change / why / confidence / how to verify") for r in rs]
    hdr = ["Component", "Edge evidence", "Distance", "Path from seed", "Assessment"]
    S["Directly Affected Components"] = "_Static importers of the seeds (distance 1). Each still needs a read to confirm it uses the changed behaviour._\n\n" + \
        table(hdr, rows(direct[:40])) + ("\n_%d more not shown; see impact JSON._\n" % (len(direct) - 40) if len(direct) > 40 else "")
    S["Indirectly Affected Components"] = "_Transitive dependents (distance ≥ 2)._\n\n" + table(hdr, rows(indirect[:40])) + \
        "\n**Potentially affected** (not visible to import analysis; search for these explicitly): " + \
        TODO % "reflection/DI/plugin loading, config keys, string-keyed lookups, events, generated code, cross-service or DB contracts"
    S["Potential Regressions"] = TODO % "behaviours that could silently change, tied to the components above"
    S["Required Changes"] = TODO % "per component: expected modification"
    tests = impact.get("tests_reached", [])
    S["Testing Strategy"] = ("**Tests that statically reach the seeds:** " + (", ".join("`%s`" % t for t in tests) if tests else "none found") + "\n\n" +
                             TODO % "what to run, what is missing (critical paths without tests), how to confirm each regression risk")
    unk = ["- " + impact["note"]]
    if impact.get("cycles_touching_blast_radius"):
        unk.append("- Dependency cycle(s) overlap the blast radius: " + "; ".join(", ".join(c) for c in impact["cycles_touching_blast_radius"]))
    for ch in impact.get("implicit_channels_from_seeds", []):
        others = ch["also_touched_by"]
        unk.append("- Seeds use %s `%s`; %d other file(s) touch the same key and are NOT dependents in the graph: %s. Read them." % (
            ch["kind"], ch["key"].split(":", 1)[-1], len(others),
            ", ".join("`%s` (%s, %s)" % (o["file"], o["role"], o["evidence"]) for o in others[:8]) or "none found"))
    if model and model.get("coverage", {}).get("by_language"):
        gaps = [k for k, v in model["coverage"]["by_language"].items() if v["files"] and not v["analyzed"] and k in cc.CODE_LANGS]
        if gaps:
            unk.append("- Languages present with no analyzer (invisible to the graph): " + ", ".join(sorted(gaps)))
    S["Unknowns and Assumptions"] = "\n".join(unk + ["", TODO % "label each remaining item UNKNOWN or INFERRED with what would verify it"])
    S["Recommended Implementation Sequence"] = TODO % "smallest safe order; each step independently verifiable and reversible where possible"
    return _assemble("Change Impact Report", IMPACT_SECTIONS, S, model)


def _assemble(title, sections, bodies, model):
    gen = model.get("generated_at", "") if model else ""
    out = ["# " + title, "",
           "> Skeleton generated by report_generator.py. Tables and counts are computed from source text by scripts "
           "(static references only; nothing was executed). Replace each [[TODO(claude): ...]] marker after reading the code, or delete the "
           "section if it does not apply. The verify command fails while markers remain." +
           (" Model generated: %s." % gen if gen else ""), ""]
    for i, name in enumerate(sections, 1):
        out += ["## %d. %s" % (i, name), "", bodies[name].rstrip(), ""]
    return "\n".join(out)


# --------------------------------------------------------------------------
# verify
# --------------------------------------------------------------------------

_CITE_RE = re.compile(r"`([A-Za-z0-9_.\-@/\\]+?\.[A-Za-z0-9]{1,8})(?::(\d+)(?:-(\d+))?)?`")
_CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt", ".c", ".h", ".cc", ".cpp", ".cxx",
              ".hpp", ".cs", ".go", ".rs", ".php", ".rb", ".json", ".yml", ".yaml", ".toml", ".md", ".sql", ".sh",
              ".html", ".css", ".txt", ".cfg", ".ini", ".xml", ".gradle", ".proto", ".lock"}
# Product names that look like filenames (`Node.js`) but are not repository paths.
_NOT_FILES = {"node.js", "vue.js", "next.js", "nuxt.js", "express.js", "d3.js", "three.js", "chart.js", "nest.js",
              "ember.js", "backbone.js", "alpine.js", "p5.js", "socket.io"}


def _basename_known(path, known, repo):
    if any(k.rsplit("/", 1)[-1] == path for k in known):
        return True
    if repo:
        for _, dirs, fns in os.walk(repo):
            dirs[:] = [d for d in dirs if d not in cc.DEFAULT_IGNORE_DIRS]
            if path in fns:
                return True
    return False


def verify(report_text, model, repo):
    """Check every backticked path (optionally path:LINE) against the model and filesystem."""
    known = set(model["nodes"]) if model else set()
    problems, checked = [], 0
    for m in TODO_RE.finditer(report_text):
        problems.append({"kind": "unfilled-marker", "line": report_text.count("\n", 0, m.start()) + 1,
                         "detail": "TODO marker still present"})
    for m in _CITE_RE.finditer(report_text):
        path = m.group(1).replace("\\", "/")
        ext = os.path.splitext(path)[1].lower()
        if ext not in _CODE_EXTS or path.lower() in _NOT_FILES or path.startswith(("http", "www.")):
            continue
        checked += 1
        line_no = report_text.count("\n", 0, m.start()) + 1
        full = os.path.join(repo, path) if repo else None
        exists = path in known or bool(full and os.path.isfile(full))
        if not exists and "/" not in path:
            exists = _basename_known(path, known, repo)
        if not exists:
            problems.append({"kind": "unknown-path", "line": line_no,
                             "detail": "`%s` is not in the model or repository" % path})
            continue
        if m.group(2) and full and os.path.isfile(full):
            text, _ = cc.read_text_ex(repo, path)
            if text is not None:
                n = text.count("\n") + 1
                if int(m.group(2)) > n or int(m.group(3) or m.group(2)) > n:
                    problems.append({"kind": "line-out-of-range", "line": line_no,
                                     "detail": "`%s:%s` but the file has %d lines" % (path, m.group(2), n)})
    return {"citations_checked": checked, "problems": problems, "ok": not problems}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_ = sub.add_parser("architecture")
    a_.add_argument("--model", required=True)
    a_.add_argument("--inventory")
    a_.add_argument("--out", default="-")
    i_ = sub.add_parser("impact")
    i_.add_argument("--impact", required=True)
    i_.add_argument("--model")
    i_.add_argument("--change")
    i_.add_argument("--out", default="-")
    v_ = sub.add_parser("verify")
    v_.add_argument("report")
    v_.add_argument("--model")
    v_.add_argument("--repo")
    a = ap.parse_args(argv)

    if a.cmd == "architecture":
        text = architecture(_load(a.model, "model"), _load(a.inventory, "inventory") if a.inventory else None)
    elif a.cmd == "impact":
        text = change_impact(_load(a.impact, "impact"), _load(a.model, "model") if a.model else None, a.change)
    else:
        try:
            with open(a.report, encoding="utf-8") as f:
                report = f.read()
        except OSError as exc:
            print("error: cannot read report: %s" % exc, file=sys.stderr)
            return 2
        if not a.model and not a.repo:
            print("error: give --model and/or --repo so citations can be checked", file=sys.stderr)
            return 2
        res = verify(report, _load(a.model, "model") if a.model else None, os.path.abspath(a.repo) if a.repo else None)
        json.dump(res, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0 if res["ok"] else 1
    if a.out in (None, "-"):
        sys.stdout.write(text)
    else:
        cc.atomic_write(a.out, text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

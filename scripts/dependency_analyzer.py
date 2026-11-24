#!/usr/bin/env python3
"""Build a dependency graph and architecture metrics for a repository.

Usage:
  dependency_analyzer.py analyze <repo> [--out deps.json] [--no-git] [--include-dir NAME]
                                         [--max-files N] [--plugin FILE]
  dependency_analyzer.py locate  <repo> --term TEXT [--term TEXT ...] [--limit N]

`analyze` is strictly read-only: it parses files, it never imports or executes
them. Output is a JSON document (see schemas/codebase-model.schema.json) in which
every edge says whether it was `discovered` (written in source and resolved by a
deterministic rule) or `inferred` (heuristic). `locate` finds seed files for an
impact analysis by path and content match.
"""
from __future__ import annotations

import argparse
import os
import posixpath
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyzers import (RepoContext, builtin_analyzers, load_plugin_analyzers)  # noqa: E402
import ci_common as cc  # noqa: E402
import graph_utils as gu  # noqa: E402
from manifests import parse_manifest  # noqa: E402

PY_DIST_ALIASES = {
    "yaml": "pyyaml", "pil": "pillow", "cv2": "opencv-python", "sklearn": "scikit-learn", "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil", "jwt": "pyjwt", "dotenv": "python-dotenv", "attr": "attrs", "git": "gitpython",
    "serial": "pyserial", "crypto": "pycryptodome", "openssl": "pyopenssl", "mysqldb": "mysqlclient",
    "psycopg2": "psycopg2-binary", "magic": "python-magic", "docx": "python-docx", "jose": "python-jose",
    "slugify": "python-slugify", "multipart": "python-multipart", "zmq": "pyzmq", "lxml": "lxml", "google": "protobuf",
}


def norm_py(n):
    return re.sub(r"[-_.]+", "-", n).lower()


# --------------------------------------------------------------------------
# analysis
# --------------------------------------------------------------------------

def analyze(root, use_git=True, include_dirs=(), max_files=cc.DEFAULT_MAX_FILES, plugins=()):
    root = os.path.abspath(root)
    files, meta = cc.list_repo_files(root, use_git, include_dirs, max_files)
    reads = {}

    def read(rel):
        if rel not in reads:
            reads[rel] = cc.read_text_ex(root, rel)
        return reads[rel][0]

    ctx = RepoContext(root, files, read)
    manifests = []
    for rel in files:
        base = posixpath.basename(rel).lower()
        if base in ("package.json", "pyproject.toml", "setup.py", "pipfile", "go.mod", "cargo.toml", "pom.xml",
                    "build.gradle", "build.gradle.kts", "composer.json", "gemfile", "cmakelists.txt") \
                or re.match(r"^requirements.*\.txt$", base) or base.endswith(".csproj"):
            text = read(rel)
            if text is not None:
                m = parse_manifest(rel, text)
                if m:
                    manifests.append(m)
    ctx.manifests = manifests

    analyzers = builtin_analyzers()
    for p in plugins:
        analyzers.extend(load_plugin_analyzers(p, root))
    by_ext = {}
    for a in analyzers:
        for e in a.extensions:
            by_ext[e] = a
        a.prepare(ctx)

    nodes, symbols = {}, {}
    edges, externals, unresolved, implicit = [], [], [], []
    errors = []
    skipped = {"too_large": 0, "binary": 0, "unreadable": 0, "sensitive_not_read": 0, "no_analyzer": 0}
    by_lang = {}
    entry_hits = {}

    for rel in files:
        lang = cc.lang_of(rel) or "other"
        ext = posixpath.splitext(rel)[1].lower()
        an = by_ext.get(ext)
        row = by_lang.setdefault(lang, {"files": 0, "analyzed": 0, "analyzer": None})
        row["files"] += 1
        if cc.is_sensitive(rel):
            skipped["sensitive_not_read"] += 1
            continue
        if lang in cc.CODE_LANGS or lang in ("html", "css"):
            text = read(rel)
            if text is None:
                reason = reads.get(rel, (None, "unreadable"))[1]
                skipped[reason if reason in skipped else "unreadable"] += 1
                continue
            loc = sum(1 for ln in text.splitlines() if ln.strip())
            for ev, reason in cc.entry_from_text(rel, lang, text):
                entry_hits.setdefault(rel, []).append((ev, reason))
            hint = cc.entry_from_name(rel)
            if hint:
                entry_hits.setdefault(rel, []).append(hint)
            if an is None:
                skipped["no_analyzer"] += 1
                if lang in cc.CODE_LANGS:
                    nodes[rel] = {"language": lang, "loc": loc, "role": cc.classify_file(rel), "analyzer": None}
                continue
            try:
                res = an.analyze(ctx, rel, text)
            except Exception as exc:  # one bad file must not abort the run
                errors.append({"file": rel, "error": "%s: %s" % (type(exc).__name__, str(exc)[:160])})
                nodes[rel] = {"language": lang, "loc": loc, "role": cc.classify_file(rel), "analyzer": an.name, "failed": True}
                continue
            row["analyzed"] += 1
            row["analyzer"] = an.name
            nodes[rel] = {"language": lang, "loc": loc, "role": cc.classify_file(rel), "analyzer": an.name}
            edges.extend(res["edges"])
            externals.extend(res["externals"])
            unresolved.extend(res["unresolved"])
            for im in res["implicit"]:
                im = dict(im, source=rel)
                implicit.append(im)
            if res["defs"]:
                symbols[rel] = res["defs"][:300]
            for msg in res["errors"]:
                errors.append({"file": rel, "error": msg})

    # manifest-declared entry points (only those that exist)
    for m in manifests:
        for path, reason in m["entry"]:
            hit = _resolve_entry(ctx, path)
            if hit:
                entry_hits.setdefault(hit, []).append(("discovered" if "if present" not in reason else "inferred", reason))

    # make sure every edge endpoint is a node (headers, assets, Go package dirs)
    for e in edges:
        for end in (e["source"], e["target"]):
            if end not in nodes:
                if end.endswith("/"):
                    nodes[end] = {"language": "go", "loc": 0, "role": "package", "analyzer": None, "type": "package"}
                else:
                    nodes[end] = {"language": cc.lang_of(end) or "other", "loc": 0, "role": cc.classify_file(end),
                                  "analyzer": None}
    # Go: package nodes contain their files (structural, used for impact traversal only)
    for e in list(edges):
        if e["target"].endswith("/") and e["kind"] == "import":
            d = e["target"].rstrip("/")
            d = "" if d == "." else d
            for f in sorted(f for f in files if f.endswith(".go") and not f.endswith("_test.go") and posixpath.dirname(f) == d):
                pm = {"source": e["target"], "target": f, "kind": "package-member", "evidence": "discovered",
                      "line": 0, "spec": "", "scope": "module"}
                if pm not in edges:
                    edges.append(pm)

    edges = _dedupe(edges)
    ev_edges, orphan_implicit = _implicit_nodes(nodes, implicit)
    edges.extend(ev_edges)

    for rel, hits in entry_hits.items():
        if rel in nodes:
            nodes[rel]["entry_point"] = True

    entry_points = []
    for rel, hits in sorted(entry_hits.items()):
        if rel not in nodes:
            continue
        evidence = "discovered" if any(h[0] == "discovered" for h in hits) else "inferred"
        entry_points.append({"path": rel, "evidence": evidence, "reasons": sorted({h[1] for h in hits})})

    metrics = _metrics(nodes, edges)
    cycles = _cycles(edges)
    declared = _declared_vs_discovered(ctx, manifests, nodes, externals)
    ext_summary = _external_summary(externals)

    used_langs = {v for v in {n["language"] for n in nodes.values()} if v in cc.CODE_LANGS}
    limitations = []
    for a in analyzers:
        if set(a.languages) & used_langs:
            limitations.extend(a.limitations)
    unsupported = sorted((l, r["files"]) for l, r in by_lang.items() if l in cc.CODE_LANGS and r["analyzer"] is None and r["files"])
    for l, n in unsupported:
        if l == "c_header" and "cpp" in by_lang or l in ("sql", "shell", "powershell"):
            continue
        limitations.append("No analyzer for %s (%d files): files are counted but have no relationships in this graph." % (l, n))
    if meta["truncated"]:
        limitations.append("File listing truncated at %d files; analysis is partial." % max_files)
    if meta["source"] == "walk":
        limitations.append("Not a usable git work tree (or --no-git): .gitignore rules were not applied; a built-in ignore list was used.")
    limitations.append("Edges describe static references. Runtime wiring (DI containers, reflection, plugin loading, "
                       "framework conventions, network calls between services) is not captured unless listed as inferred.")

    return {
        "model_version": cc.MODEL_VERSION,
        "tool_version": cc.TOOL_VERSION,
        "generated_at": cc.now_iso(),
        "repository": cc.repo_identity(root, files, use_git),
        "analyzers": {a.name: {"version": a.version, "depth": a.depth, "languages": list(a.languages)} for a in analyzers
                      if set(a.languages) & used_langs},
        "coverage": {
            "files_listed": len(files), "files_analyzed": sum(r["analyzed"] for r in by_lang.values()),
            "by_language": {k: by_lang[k] for k in sorted(by_lang)}, "skipped": skipped,
            "listing_source": meta["source"], "truncated": meta["truncated"],
            "ignored_dirs_seen": meta["ignored_dirs_seen"], "symlinks_skipped": meta["symlinks_skipped"],
            "analysis_errors": errors[:50],
        },
        "nodes": nodes,
        "edges": sorted(edges, key=lambda e: (e["source"], e["target"], e["line"], e["kind"])),
        "symbols": symbols,
        "externals": ext_summary,
        "unresolved": sorted(unresolved, key=lambda u: (u["source"], u["line"]))[:500],
        "implicit_orphans": orphan_implicit,
        "declared_vs_discovered": declared,
        "build_targets": [dict(t) for m in manifests if m["ecosystem"] == "cmake" for t in m["extra"]["targets"]],
        "manifests": [{"path": m["manifest"], "ecosystem": m["ecosystem"], "name": m["name"],
                       "prod_count": len(m["prod"]), "dev_count": len(m["dev"])} for m in manifests],
        "entry_points": entry_points,
        "metrics": metrics,
        "cycles": cycles,
        "limitations": sorted(set(limitations)),
    }


def _resolve_entry(ctx, path):
    path = posixpath.normpath(path)
    if path in ctx.files:
        return path
    for suffix in (".py", "/__init__.py", ".ts", ".js", ".tsx", ".mjs"):
        if path + suffix in ctx.files:
            return path + suffix
    return None


def _dedupe(edges):
    best = {}
    for e in edges:
        key = (e["source"], e["target"], e["kind"], e["line"], e["spec"])
        if key not in best or (best[key]["evidence"] != "discovered" and e["evidence"] == "discovered"):
            best[key] = e
    return list(best.values())


def _implicit_nodes(nodes, implicit):
    """Create env:/event: nodes. Only events with both an emitter and a listener become graph nodes."""
    out, orphans = [], {"events_emit_only": [], "events_listen_only": []}
    env = {}
    ev = {}
    for im in implicit:
        (env if im["kind"] == "env" else ev).setdefault(im["key"], []).append(im)
    for key, items in sorted(env.items()):
        nid = "env:" + key
        nodes[nid] = {"language": "config", "loc": 0, "role": "config-key", "analyzer": None, "type": "implicit"}
        for im in items:
            out.append({"source": im["source"], "target": nid, "kind": "env-read", "evidence": "discovered",
                        "line": im["line"], "spec": key, "scope": "module"})
    for key, items in sorted(ev.items()):
        emit = [i for i in items if i["role"] == "emit"]
        listen = [i for i in items if i["role"] == "listen"]
        if emit and listen:
            nid = "event:" + key
            nodes[nid] = {"language": "config", "loc": 0, "role": "event", "analyzer": None, "type": "implicit"}
            note = "string-key match on event name; assumes the same bus/namespace"
            for i in emit:
                out.append({"source": nid, "target": i["source"], "kind": "event-emit", "evidence": "inferred",
                            "line": i["line"], "spec": key, "scope": "module", "note": note})
            for i in listen:
                out.append({"source": i["source"], "target": nid, "kind": "event-listen", "evidence": "inferred",
                            "line": i["line"], "spec": key, "scope": "module", "note": note})
        elif emit:
            orphans["events_emit_only"].append({"event": key, "files": sorted({i["source"] for i in emit})})
        else:
            orphans["events_listen_only"].append({"event": key, "files": sorted({i["source"] for i in listen})})
    return out, orphans


def _best_pairs(edges):
    pairs = {}
    for e in gu.coupling_edges(edges):
        k = (e["source"], e["target"])
        if k not in pairs or (pairs[k] != "discovered" and e["evidence"] == "discovered"):
            pairs[k] = e["evidence"]
    return pairs


def _metrics(nodes, edges, depth=None):
    pairs = _best_pairs(edges)
    real = {n for n, a in nodes.items() if a.get("type") != "implicit"}
    fin, fout = {}, {}
    for (s, t), _ in pairs.items():
        if s in real and t in real:
            fout.setdefault(s, set()).add(t)
            fin.setdefault(t, set()).add(s)

    def top(d, n=10):
        rows = sorted(((k, len(v)) for k, v in d.items()), key=lambda x: (-x[1], x[0]))
        return [{"path": k, "count": c} for k, c in rows[:n] if c > 0]

    hubs = sorted(k for k in real if len(fin.get(k, ())) >= 3 and len(fout.get(k, ())) >= 3)
    total = sum(len(v) for v in fin.values())
    top5 = sum(c for _, c in sorted(((k, len(v)) for k, v in fin.items()), key=lambda x: -x[1])[:5])
    isolated = sorted(k for k in real if k not in fin and k not in fout and nodes[k]["role"] == "source"
                      and not nodes[k].get("entry_point") and nodes[k].get("analyzer"))
    files_only = [k for k in real if not k.endswith("/")]
    if depth is None:
        depth = 1
        while depth < 4 and len({cc.module_of(f, depth) for f in files_only}) <= 2:
            depth += 1
    modules = module_graph(nodes, edges, depth)
    return {
        "internal_edges": len(pairs), "edges_discovered": sum(1 for v in pairs.values() if v == "discovered"),
        "edges_inferred": sum(1 for v in pairs.values() if v == "inferred"),
        "highest_fan_in": top(fin), "highest_fan_out": top(fout), "hubs": hubs[:20],
        "top5_target_share": round(top5 / total, 3) if total else 0.0,
        "isolated_source_files": isolated[:40],
        "isolated_note": "Isolated means no static import edge in or out. It does not mean unused: entry points, plugins, "
                         "reflection and external callers are invisible to this graph.",
        "module_depth": depth, "modules": modules,
    }


def module_graph(nodes, edges, depth):
    real = {n for n, a in nodes.items() if a.get("type") != "implicit"}
    mods = {}
    for n in real:
        m = cc.module_of(n, depth)
        mods.setdefault(m, {"files": 0, "loc": 0})
        mods[m]["files"] += 1
        mods[m]["loc"] += nodes[n].get("loc", 0)
    agg = {}
    for e in gu.coupling_edges(edges):
        if e["source"] in real and e["target"] in real:
            a, b = cc.module_of(e["source"], depth), cc.module_of(e["target"], depth)
            if a == b:
                continue
            cur = agg.setdefault((a, b), {"count": 0, "discovered": 0})
            cur["count"] += 1
            cur["discovered"] += 1 if e["evidence"] == "discovered" else 0
    ce, ca = {}, {}
    for (a, b), v in agg.items():
        ce.setdefault(a, set()).add(b)
        ca.setdefault(b, set()).add(a)
    rows = []
    for m in sorted(mods):
        out_n, in_n = len(ce.get(m, ())), len(ca.get(m, ()))
        rows.append({"module": m, "files": mods[m]["files"], "loc": mods[m]["loc"], "depends_on": out_n,
                     "depended_on_by": in_n, "instability": round(out_n / (in_n + out_n), 2) if in_n + out_n else None})
    return {"nodes": rows, "edges": [{"source": a, "target": b, "count": v["count"], "discovered": v["discovered"]}
                                      for (a, b), v in sorted(agg.items())]}


def _cycles(edges):
    allc = gu.coupling_edges(edges, only_evidence="discovered")
    adj = gu.adjacency(allc)
    eager = gu.adjacency(gu.coupling_edges(edges, only_evidence="discovered", eager_only=True))
    eager_sets = [set(c) for c in gu.strongly_connected(eager)]
    out = []
    for comp in gu.strongly_connected(adj):
        cyc = gu.shortest_cycle(adj, comp)
        out.append({"files": comp, "example_cycle": cyc, "size": len(comp),
                    "import_time_cycle": any(set(comp) <= s or len(set(comp) & s) > 1 for s in eager_sets),
                    "note": "Cycle exists only through lazy/type-only/dynamic references."
                    if not any(len(set(comp) & s) > 1 for s in eager_sets) else "Cycle is present in module-level (import-time) references."})
    return out


def _external_summary(externals):
    agg = {}
    for e in externals:
        d = agg.setdefault(e["package"], {"package": e["package"], "files": set(), "kinds": set()})
        d["files"].add(e["source"])
        d["kinds"].add(e["kind"])
    rows = [{"package": k, "files": sorted(v["files"])[:25], "file_count": len(v["files"]), "kinds": sorted(v["kinds"])}
            for k, v in agg.items()]
    return sorted(rows, key=lambda r: (-r["file_count"], r["package"]))


def _declared_vs_discovered(ctx, manifests, nodes, externals):
    by_eco = {}
    for m in manifests:
        by_eco.setdefault(m["ecosystem"], []).append(m)
    lang_eco = {"python": "python", "javascript": "javascript", "typescript": "javascript", "go": "go", "rust": "rust", "ruby": "ruby"}
    ext_by_file = {}
    for e in externals:
        ext_by_file.setdefault(e["source"], []).append(e)

    def nearest(eco, path):
        best = None
        for m in by_eco.get(eco, []):
            d = posixpath.dirname(m["manifest"])
            if d == "" or path == d or path.startswith(d + "/"):
                if best is None or len(posixpath.dirname(best["manifest"])) < len(d):
                    best = m
        return best

    # group python requirements*.txt / pyproject / setup.py in one directory together
    out = []
    groups = {}
    for m in manifests:
        if m["ecosystem"] in ("cmake",):
            continue
        key = (m["ecosystem"], posixpath.dirname(m["manifest"]))
        groups.setdefault(key, []).append(m)
    for (eco, d), ms in sorted(groups.items()):
        prod = sorted({n for m in ms for n in m["prod"]})
        dev = sorted({n for m in ms for n in m["dev"]})
        row = {"ecosystem": eco, "directory": d or ".", "manifests": sorted(m["manifest"] for m in ms),
               "declared_prod": len(prod), "declared_dev": len(dev)}
        if eco not in ("python", "javascript", "go", "rust", "ruby"):
            row["comparison"] = "not-supported"
            row["declared_prod_names"] = prod[:80]
            out.append(row)
            continue
        scope_files = [f for f, a in nodes.items() if lang_eco.get(a["language"]) == eco and a.get("analyzer")
                       and (nearest(eco, f) or {"manifest": ""})["manifest"] in {m["manifest"] for m in ms}]
        used = {}
        for f in scope_files:
            for e in ext_by_file.get(f, []):
                used.setdefault(e["package"], set()).add(f)
        declared_all = set(prod) | set(dev)
        if eco == "python":
            def covered(imp, names):
                n = norm_py(imp)
                alias = PY_DIST_ALIASES.get(imp.lower())
                return n in names or (alias and alias in names) or any(x.replace("-", "_") == imp.lower().replace("-", "_") for x in names)
            not_imported = [p for p in prod if not any(covered(i, {p}) for i in used)]
            undeclared = [i for i in sorted(used) if not covered(i, declared_all)]
        elif eco == "javascript":
            not_imported = [p for p in prod if p not in used and not p.startswith("@types/")]
            undeclared = [i for i in sorted(used) if i not in declared_all]
        elif eco == "go":
            specs = {e["spec"] for f in scope_files for e in ext_by_file.get(f, [])}
            not_imported = [p for p in prod if not any(s == p or s.startswith(p + "/") for s in specs)]
            undeclared = sorted({s for s in specs if not any(s == p or s.startswith(p + "/") for p in declared_all)})
        elif eco == "rust":
            not_imported = [p for p in prod if p not in used]
            undeclared = [i for i in sorted(used) if i.replace("-", "_") not in {x.replace("-", "_") for x in declared_all}]
        else:
            norm = lambda s: s.replace("-", "_").lower()
            not_imported = [p for p in prod if norm(p) not in {norm(u) for u in used}]
            undeclared = [i for i in sorted(used) if norm(i) not in {norm(x) for x in declared_all}]
        row.update({"comparison": "candidates", "files_in_scope": len(scope_files),
                    "declared_not_imported": sorted(not_imported), "imported_not_declared": undeclared,
                    "note": "Candidates only. Declared-but-unimported may be a CLI tool, plugin, runtime/peer dependency or "
                            "loaded by configuration; imported-but-undeclared may come from a parent manifest, the standard "
                            "library, or an import-name/package-name mismatch."})
        out.append(row)
    return out


# --------------------------------------------------------------------------
# locate
# --------------------------------------------------------------------------

def locate(root, terms, use_git=True, include_dirs=(), limit=40):
    root = os.path.abspath(root)
    files, _ = cc.list_repo_files(root, use_git, include_dirs)
    pats = [(t, re.compile(re.escape(t), re.I)) for t in terms]
    rows = []
    for rel in files:
        if cc.is_sensitive(rel):
            continue
        low = rel.lower()
        path_terms = [t for t, _ in pats if t.lower() in low]
        text = cc.read_text(root, rel)
        hits, lines = 0, []
        if text:
            for i, line in enumerate(text.splitlines(), 1):
                if len(line) > 4000:
                    continue
                n = sum(len(p.findall(line)) for _, p in pats)
                if n:
                    hits += n
                    if len(lines) < 6:
                        lines.append(i)
        if hits or path_terms:
            rows.append({"path": rel, "role": cc.classify_file(rel), "language": cc.lang_of(rel) or "other",
                         "path_match": path_terms, "hits": hits, "lines": lines})
    rows.sort(key=lambda r: (-(len(r["path_match"]) * 5 + r["hits"]), r["path"]))
    return {"terms": terms, "files_scanned": len(files), "matches": len(rows), "results": rows[:limit],
            "note": "Substring matches only (case-insensitive). These are seed candidates for impact analysis, not "
                    "findings: confirm each by reading the file, and search for synonyms the terms do not cover."}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("repo")
    a.add_argument("--out", default="-")
    a.add_argument("--no-git", action="store_true", help="do not call git; walk the filesystem")
    a.add_argument("--include-dir", action="append", default=[], help="analyse a directory that is ignored by default")
    a.add_argument("--max-files", type=int, default=cc.DEFAULT_MAX_FILES)
    a.add_argument("--plugin", action="append", default=[], help="Python file defining extra analyzers (must be outside the repo)")
    a.add_argument("--summary", action="store_true", help="print a short summary to stderr")
    l = sub.add_parser("locate")
    l.add_argument("repo")
    l.add_argument("--term", action="append", required=True)
    l.add_argument("--no-git", action="store_true")
    l.add_argument("--include-dir", action="append", default=[])
    l.add_argument("--limit", type=int, default=40)
    l.add_argument("--out", default="-")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.repo):
        sys.exit("error: not a directory: %s" % args.repo)
    if args.cmd == "analyze":
        try:
            model = analyze(args.repo, not args.no_git, args.include_dir, args.max_files, args.plugin)
        except ValueError as exc:
            sys.exit("error: %s" % exc)
        cc.dump_json(model, args.out)
        if args.summary:
            m = model["metrics"]
            sys.stderr.write("files analysed %d/%d | edges %d (discovered %d, inferred %d) | cycles %d | entry points %d\n" % (
                model["coverage"]["files_analyzed"], model["coverage"]["files_listed"], m["internal_edges"],
                m["edges_discovered"], m["edges_inferred"], len(model["cycles"]), len(model["entry_points"])))
    else:
        cc.dump_json(locate(args.repo, args.term, not args.no_git, args.include_dir, args.limit), args.out)


if __name__ == "__main__":
    main()

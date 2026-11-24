#!/usr/bin/env python3
"""Export a dependency model as Mermaid, Graphviz DOT or JSON, and compute change-impact reach.

Usage:
  graph_exporter.py export <model.json> [--format mermaid|dot|json] [--level file|module]
                           [--module-depth N] [--focus PATH ...] [--hops N]
                           [--only-discovered] [--max-nodes N] [--out FILE]
  graph_exporter.py impact <model.json> --seed PATH [--seed PATH ...] [--max-depth N]
                           [--only-discovered] [--format json|mermaid] [--out FILE]

<model.json> is the output of `dependency_analyzer.py analyze`.

Rendering conventions (stated in every export so a reader never has to guess):
  solid line  = `discovered` edge: written in source and resolved by a deterministic rule
  dashed line = `inferred` edge: resolved by a heuristic or a naming convention
  red edge    = edge inside a dependency cycle (only for edges that are discovered)

`impact` answers "who depends on these files, directly or transitively?". It is
reverse reachability over *static* edges. A file that does not appear in the result
is NOT thereby proven unaffected: reflection, configuration, dependency injection,
generated code and network contracts are invisible here (see references/change-impact-analysis.md).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ci_common as cc  # noqa: E402
import graph_utils as gu  # noqa: E402

# A diagram with more nodes than this stops being readable on a normal screen.
# 60 is roughly what fits in a Mermaid render without the labels overlapping.
DEFAULT_MAX_NODES = 60

IMPACT_NOTE = ("Static reverse reachability only. Absence from this list is not proof of being unaffected: "
               "reflection, configuration, DI containers, generated code, events and external contracts "
               "are not visible to import analysis.")


def load_model(path):
    try:
        if path == "-":
            model = json.load(sys.stdin)
        else:
            with open(path, encoding="utf-8") as f:
                model = json.load(f)
    except FileNotFoundError:
        sys.exit("error: model file not found: %s (create it with: dependency_analyzer.py analyze <repo> --out %s)"
                 % (path, path))
    except json.JSONDecodeError as exc:
        sys.exit("error: %s is not valid JSON (%s). Expected the output of dependency_analyzer.py analyze." % (path, exc))
    if not isinstance(model, dict) or "edges" not in model or "nodes" not in model:
        sys.exit("error: %s does not look like a codebase model (missing 'nodes'/'edges')." % path)
    return model


# --------------------------------------------------------------------------
# graph selection
# --------------------------------------------------------------------------

def _file_graph(model, only_discovered):
    """Return (node ids, edges) for the file-level graph, structural edges removed."""
    edges = gu.coupling_edges(model["edges"], only_evidence="discovered" if only_discovered else None)
    pairs = {}
    for e in edges:
        k = (e["source"], e["target"])
        cur = pairs.get(k)
        if cur is None or (cur["evidence"] != "discovered" and e["evidence"] == "discovered"):
            pairs[k] = {"source": e["source"], "target": e["target"], "evidence": e["evidence"], "kind": e["kind"]}
    nodes = set(model["nodes"])
    return nodes, [pairs[k] for k in sorted(pairs)]


def _module_graph(model, depth, only_discovered):
    """Aggregate the file graph to modules (directories). An aggregate edge is `discovered`
    only if every underlying edge is; any inferred member makes it inferred."""
    nodes_in, edges_in = _file_graph(model, only_discovered)
    real = {n for n, a in model["nodes"].items() if a.get("type") != "implicit"}
    nodes = {cc.module_of(n, depth) for n in real}
    agg = {}
    for e in edges_in:
        if e["source"] not in real or e["target"] not in real:
            continue
        a, b = cc.module_of(e["source"], depth), cc.module_of(e["target"], depth)
        if a == b:
            continue
        cur = agg.setdefault((a, b), {"count": 0, "inferred": 0})
        cur["count"] += 1
        cur["inferred"] += 1 if e["evidence"] != "discovered" else 0
    edges = [{"source": a, "target": b, "count": v["count"],
              "evidence": "inferred" if v["inferred"] else "discovered", "kind": "module-dependency"}
             for (a, b), v in sorted(agg.items())]
    return nodes, edges


def _neighborhood(nodes, edges, focus, hops):
    """Nodes within `hops` of any focus node in either direction."""
    adj = gu.adjacency(edges)
    radj = gu.adjacency(edges, reverse=True)
    keep = set(focus)
    frontier = set(focus)
    for _ in range(hops):
        nxt = set()
        for n in frontier:
            nxt |= adj.get(n, set()) | radj.get(n, set())
        frontier = nxt - keep
        keep |= nxt
    return keep


def _cap(nodes, edges, max_nodes, focus):
    """Keep the most connected nodes when a graph is too large; report what was dropped."""
    if len(nodes) <= max_nodes:
        return nodes, edges, 0
    degree = {}
    for e in edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1
    ranked = sorted(nodes, key=lambda n: (n not in focus, -degree.get(n, 0), n))
    keep = set(ranked[:max_nodes])
    kept_edges = [e for e in edges if e["source"] in keep and e["target"] in keep]
    return keep, kept_edges, len(nodes) - len(keep)


def select(model, level, depth, focus, hops, only_discovered, max_nodes):
    if level == "module":
        depth = depth or model.get("metrics", {}).get("module_depth") or 2
        nodes, edges = _module_graph(model, depth, only_discovered)
    else:
        nodes, edges = _file_graph(model, only_discovered)
        # In a file graph, hide nodes with no coupling edge so the picture shows structure, not inventory.
        connected = {e["source"] for e in edges} | {e["target"] for e in edges}
        nodes = nodes & connected if not focus else nodes
    if focus:
        missing = [f for f in focus if f not in nodes]
        if missing:
            sys.exit("error: --focus path(s) not in graph: %s. Paths are repository-relative with '/' separators "
                     "(at --level module use module ids such as 'src/api')." % ", ".join(missing))
        keep = _neighborhood(nodes, edges, focus, hops)
        nodes = keep
        edges = [e for e in edges if e["source"] in keep and e["target"] in keep]
    nodes, edges, dropped = _cap(nodes, edges, max_nodes, set(focus))
    return sorted(nodes), edges, dropped


def cycle_edge_set(model):
    """Edge pairs that lie inside a discovered dependency cycle."""
    inside = set()
    for c in model.get("cycles", []):
        members = set(c["files"])
        for e in model["edges"]:
            if e["evidence"] == "discovered" and e["source"] in members and e["target"] in members \
                    and e["source"] != e["target"] and e["kind"] not in gu.STRUCTURAL_KINDS:
                inside.add((e["source"], e["target"]))
    return inside


def module_cycle_pairs(model, depth):
    pairs = set()
    for a, b in cycle_edge_set(model):
        ma, mb = cc.module_of(a, depth), cc.module_of(b, depth)
        if ma != mb:
            pairs.add((ma, mb))
    return pairs


# --------------------------------------------------------------------------
# renderers
# --------------------------------------------------------------------------

def _label(node, model):
    if node.startswith("env:") or node.startswith("event:"):
        return node
    return node


def _mermaid_id(i):
    return "n%d" % i


def _esc(text):
    return text.replace('"', "'")


def to_mermaid(nodes, edges, model, hot, dropped, title=None, entry_points=()):
    ids = {n: _mermaid_id(i) for i, n in enumerate(nodes)}
    out = []
    if title:
        out.append("---\ntitle: %s\n---" % _esc(title))
    out.append("graph LR")
    out.append("  %% solid = discovered edge, dashed = inferred edge, red = inside a dependency cycle")
    for n in nodes:
        shape = ('(["%s"])' if n in entry_points else '["%s"]') % _esc(_label(n, model))
        out.append("  %s%s" % (ids[n], shape))
    styles = []
    for i, e in enumerate(edges):
        arrow = "-->" if e["evidence"] == "discovered" else "-.->"
        label = "|%d|" % e["count"] if e.get("count", 1) > 1 else ""
        out.append("  %s %s%s %s" % (ids[e["source"]], arrow, label, ids[e["target"]]))
        if (e["source"], e["target"]) in hot:
            styles.append("  linkStyle %d stroke:#d62728,stroke-width:2px" % i)
    out.extend(styles)
    if dropped:
        out.append("  %%%% %d less-connected node(s) omitted (raise --max-nodes or use --focus)" % dropped)
    return "\n".join(out) + "\n"


def _dot_q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_dot(nodes, edges, model, hot, dropped, title=None, entry_points=()):
    out = ["digraph codebase {", "  rankdir=LR;", "  node [shape=box, fontname=Helvetica, fontsize=10];",
           "  // solid = discovered edge, dashed = inferred edge, red = inside a dependency cycle"]
    if title:
        out.append("  label=%s; labelloc=t;" % _dot_q(title))
    for n in nodes:
        attrs = ["label=%s" % _dot_q(_label(n, model))]
        if n in entry_points:
            attrs.append("peripheries=2")
        out.append("  %s [%s];" % (_dot_q(n), ", ".join(attrs)))
    for e in edges:
        attrs = []
        if e["evidence"] != "discovered":
            attrs.append("style=dashed")
        if e.get("count", 1) > 1:
            attrs.append("label=%s" % _dot_q(str(e["count"])))
        if (e["source"], e["target"]) in hot:
            attrs.append("color=red")
        out.append("  %s -> %s%s;" % (_dot_q(e["source"]), _dot_q(e["target"]),
                                       " [%s]" % ", ".join(attrs) if attrs else ""))
    if dropped:
        out.append("  // %d less-connected node(s) omitted (raise --max-nodes or use --focus)" % dropped)
    out.append("}")
    return "\n".join(out) + "\n"


def to_json(nodes, edges, model, hot, dropped, level):
    return {
        "level": level,
        "legend": {"discovered": "written in source and resolved deterministically",
                   "inferred": "resolved by a heuristic or convention",
                   "in_cycle": "edge lies inside a discovered dependency cycle"},
        "nodes": [{"id": n, "attributes": model["nodes"].get(n, {})} if level == "file" else {"id": n} for n in nodes],
        "edges": [dict(e, in_cycle=(e["source"], e["target"]) in hot) for e in edges],
        "omitted_nodes": dropped,
    }


# --------------------------------------------------------------------------
# impact
# --------------------------------------------------------------------------

def impact(model, seeds, max_depth, only_discovered):
    unknown = [s for s in seeds if s not in model["nodes"]]
    if unknown:
        close = []
        for u in unknown:
            base = u.rsplit("/", 1)[-1]
            close += [n for n in model["nodes"] if n.rsplit("/", 1)[-1] == base][:3]
        hint = (" Did you mean: %s?" % ", ".join(sorted(set(close)))) if close else ""
        sys.exit("error: seed(s) not in model: %s.%s Use repository-relative paths with '/' separators." % (", ".join(unknown), hint))
    reach = gu.reverse_reach(model["edges"], list(seeds), max_depth=max_depth,
                             evidence_only="discovered" if only_discovered else None)
    rows = []
    for node, info in sorted(reach.items(), key=lambda kv: (kv[1]["depth"], kv[0])):
        channel = node.startswith(("event:", "env:"))
        rel = "event channel (string-keyed link, not a file)" if channel else \
            ("direct dependent" if info["depth"] == 1 else "transitive dependent")
        rows.append({"path": node, "kind": "channel" if channel else "file", "depth": info["depth"],
                     "relationship": rel, "evidence": "inferred" if info["inferred"] else "discovered",
                     "via": info["via"], "edge_to_previous": info.get("edge")})
    files = [r for r in rows if r["kind"] == "file"]
    seeds_out = []
    for s in seeds:
        attrs = model["nodes"][s]
        seeds_out.append({"path": s, "role": attrs.get("role"), "entry_point": bool(attrs.get("entry_point"))})
    cycles_touching = [c["files"] for c in model.get("cycles", []) if set(c["files"]) & (set(seeds) | set(reach))]
    implicit = _channels(model, set(seeds))
    tests = [r["path"] for r in files if model["nodes"].get(r["path"], {}).get("role") == "test"]
    return {
        "seeds": seeds_out,
        "dependents": rows,
        "counts": {"direct": sum(1 for r in files if r["depth"] == 1),
                   "transitive": sum(1 for r in files if r["depth"] > 1), "tests_reached": len(tests)},
        "tests_reached": tests,
        "cycles_touching_blast_radius": cycles_touching,
        "implicit_channels_from_seeds": implicit,
        "max_depth": max_depth,
        "only_discovered": only_discovered,
        "note": IMPACT_NOTE,
        "next": "Candidates for 'directly/indirectly affected'. Read each file to confirm; then search for "
                "reflection, config, string-keyed and cross-service references to find 'potentially affected' ones.",
    }


def _channels(model, seeds):
    """Config keys and events the seeds touch, with every OTHER file touching the same key.

    Co-readers of an environment variable do not import the seed, so they never show up as
    dependents; but changing how the seed interprets the key can change them too. Event emitters
    and listeners are reached by `reverse_reach` through the event node (inferred); they are
    repeated here so the key itself is visible.
    """
    uses = {}
    for e in model["edges"]:
        if e["kind"] == "env-read":
            file, key, role = e["source"], e["target"], "reads"
        elif e["kind"] == "event-listen":
            file, key, role = e["source"], e["target"], "listens"
        elif e["kind"] == "event-emit":
            file, key, role = e["target"], e["source"], "emits"
        else:
            continue
        uses.setdefault(key, []).append({"file": file, "role": role, "line": e["line"], "evidence": e["evidence"]})
    out = []
    for key in sorted(uses):
        mine = [u for u in uses[key] if u["file"] in seeds]
        if not mine:
            continue
        out.append({"key": key, "kind": "env" if key.startswith("env:") else "event",
                    "seed_usage": mine,
                    "also_touched_by": [u for u in uses[key] if u["file"] not in seeds]})
    return out


def impact_mermaid(result, model):
    seeds = [s["path"] for s in result["seeds"]]
    nodes = sorted(set(seeds) | {r["path"] for r in result["dependents"]})
    edges = []
    for r in result["dependents"]:
        via = r["via"]
        edges.append({"source": via[-1], "target": via[-2], "evidence": r["evidence"], "count": 1, "kind": "dependency"})
    nodes = sorted(set(nodes) | {e["source"] for e in edges} | {e["target"] for e in edges})
    return to_mermaid(nodes, edges, model, set(), 0, title="Impact of changing: " + ", ".join(seeds))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _emit(text, out):
    if out in (None, "-"):
        sys.stdout.write(text)
    else:
        cc.atomic_write(out, text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("model")
    e.add_argument("--format", choices=["mermaid", "dot", "json"], default="mermaid")
    e.add_argument("--level", choices=["file", "module"], default="module")
    e.add_argument("--module-depth", type=int, default=None, help="directory depth that defines a module (default: from model)")
    e.add_argument("--focus", action="append", default=[], help="node to centre the diagram on (repeatable)")
    e.add_argument("--hops", type=int, default=1, help="neighbourhood radius around --focus (default 1)")
    e.add_argument("--only-discovered", action="store_true")
    e.add_argument("--max-nodes", type=int, default=DEFAULT_MAX_NODES)
    e.add_argument("--out", default="-")
    i = sub.add_parser("impact")
    i.add_argument("model")
    i.add_argument("--seed", action="append", required=True)
    i.add_argument("--max-depth", type=int, default=None)
    i.add_argument("--only-discovered", action="store_true")
    i.add_argument("--format", choices=["json", "mermaid"], default="json")
    i.add_argument("--out", default="-")
    a = ap.parse_args(argv)

    model = load_model(a.model)
    if a.cmd == "impact":
        result = impact(model, a.seed, a.max_depth, a.only_discovered)
        text = impact_mermaid(result, model) if a.format == "mermaid" else json.dumps(result, indent=2, sort_keys=True) + "\n"
        _emit(text, a.out)
        return 0

    if a.hops < 0 or a.max_nodes < 1:
        sys.exit("error: --hops must be >= 0 and --max-nodes >= 1")
    nodes, edges, dropped = select(model, a.level, a.module_depth, a.focus, a.hops, a.only_discovered, a.max_nodes)
    depth = a.module_depth or model.get("metrics", {}).get("module_depth") or 2
    hot = module_cycle_pairs(model, depth) if a.level == "module" else cycle_edge_set(model)
    entries = {ep["path"] for ep in model.get("entry_points", [])}
    if a.level == "module":
        entries = {cc.module_of(p, depth) for p in entries}
    if a.format == "mermaid":
        text = to_mermaid(nodes, edges, model, hot, dropped, entry_points=entries)
    elif a.format == "dot":
        text = to_dot(nodes, edges, model, hot, dropped, entry_points=entries)
    else:
        text = json.dumps(to_json(nodes, edges, model, hot, dropped, a.level), indent=2, sort_keys=True) + "\n"
    _emit(text, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

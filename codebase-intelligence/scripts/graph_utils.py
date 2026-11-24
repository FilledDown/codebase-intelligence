#!/usr/bin/env python3
"""Small graph helpers shared by the codebase-intelligence scripts (stdlib only)."""
from __future__ import annotations

from collections import deque

STRUCTURAL_KINDS = {"package-member"}
EAGER_SCOPES = {"module"}          # scopes that execute at import time


def coupling_edges(edges, only_evidence=None, eager_only=False):
    """Edges that represent coupling (structural containment and self-loops removed)."""
    out = []
    for e in edges:
        if e["kind"] in STRUCTURAL_KINDS or e["source"] == e["target"]:
            continue
        if only_evidence and e["evidence"] != only_evidence:
            continue
        if eager_only and e.get("scope", "module") not in EAGER_SCOPES:
            continue
        out.append(e)
    return out


def adjacency(edges, reverse=False):
    adj = {}
    for e in edges:
        a, b = (e["target"], e["source"]) if reverse else (e["source"], e["target"])
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set())
    return adj


def strongly_connected(adj):
    """Iterative Tarjan. Returns list of components (each a sorted list), size >= 2 only."""
    index, low, on, stack, out = {}, {}, set(), [], []
    counter = [0]
    for root in sorted(adj):
        if root in index:
            continue
        work = [(root, iter(sorted(adj[root])))]
        index[root] = low[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        on.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter[0]
                    counter[0] += 1
                    stack.append(nxt)
                    on.add(nxt)
                    work.append((nxt, iter(sorted(adj.get(nxt, ())))))
                    advanced = True
                    break
                if nxt in on:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                if len(comp) > 1:
                    out.append(sorted(comp))
    return sorted(out)


def shortest_cycle(adj, members):
    """One shortest cycle inside a strongly connected component, as a node list ending where it starts."""
    members = set(members)
    best = None
    for start in sorted(members):
        prev = {start: None}
        q = deque([start])
        found = None
        while q and found is None:
            n = q.popleft()
            for m in sorted(adj.get(n, ())):
                if m not in members:
                    continue
                if m == start:
                    found = n
                    break
                if m not in prev:
                    prev[m] = n
                    q.append(m)
        if found is not None:
            path, cur = [], found
            while cur is not None:
                path.append(cur)
                cur = prev[cur]
            path.reverse()
            cyc = path + [start]
            if best is None or len(cyc) < len(best):
                best = cyc
    return best or []


def reverse_reach(edges, seeds, max_depth=None, evidence_only=None):
    """Breadth-first over *dependents* (who depends on the seeds).

    Returns {node: {"depth": int, "via": [path from seed], "inferred": bool}} for nodes other than seeds.
    `evidence_only="discovered"` restricts traversal to discovered edges.
    """
    rev = {}
    for e in edges:
        if e["source"] == e["target"]:
            continue
        if evidence_only and e["evidence"] != evidence_only:
            continue
        rev.setdefault(e["target"], []).append(e)
    seen = {s: {"depth": 0, "via": [s], "inferred": False} for s in seeds}
    q = deque(seeds)
    while q:
        n = q.popleft()
        d = seen[n]["depth"]
        if max_depth is not None and d >= max_depth:
            continue
        for e in sorted(rev.get(n, ()), key=lambda x: (x["source"], x["line"])):
            s = e["source"]
            if s in seen:
                continue
            seen[s] = {"depth": d + 1, "via": seen[n]["via"] + [s],
                       "inferred": seen[n]["inferred"] or e["evidence"] != "discovered",
                       "edge": {"kind": e["kind"], "evidence": e["evidence"], "line": e["line"],
                                "names": e.get("names", []), "note": e.get("note"), "scope": e.get("scope", "module")}}
            q.append(s)
    for s in seeds:
        seen.pop(s, None)
    return seen

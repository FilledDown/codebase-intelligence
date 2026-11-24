"""C / C++ analyzer: #include relationships, CMake include directories, header/implementation pairing."""
from __future__ import annotations

import posixpath
import re

from . import Analyzer, add_edge, add_external, add_implicit, line_of, new_result
from .javascript import strip_js_comments

_HEADER_EXT = (".h", ".hpp", ".hh", ".hxx", ".inl")
_IMPL_EXT = (".c", ".cc", ".cpp", ".cxx", ".c++")
RE_INCLUDE = re.compile(r'^[ \t]*#[ \t]*(?:include|import)[ \t]*([<"])([^>"\n]+)[>"]', re.M)
RE_TYPE = re.compile(r"^[ \t]*(?:template\s*<[^>]*>\s*)?(class|struct)\s+(?:\w+\s+)?(\w+)\s*(?:final\s*)?(?::[^{;]*)?\{", re.M)
RE_GETENV = re.compile(r"\b(?:std::)?getenv\s*\(\s*\"([^\"\n]+)\"\s*\)")


class CFamilyAnalyzer(Analyzer):
    name = "cfamily-include"
    version = "1.0"
    languages = ("c", "c_header", "cpp")
    extensions = _HEADER_EXT + _IMPL_EXT
    depth = "regex"
    limitations = (
        "C/C++: #include graph only. The preprocessor is not evaluated (conditional includes are all counted), "
        "include paths come from literal CMake include_directories/target_include_directories only, and "
        "calls/ownership between translation units are not analysed.",
    )

    def prepare(self, ctx):
        headers = {}
        stems = {}
        for f in ctx.files:
            ext = posixpath.splitext(f)[1].lower()
            if ext in _HEADER_EXT:
                parts = f.split("/")
                for i in range(len(parts)):
                    headers.setdefault("/".join(parts[i:]), []).append(f)
                stems.setdefault(posixpath.splitext(posixpath.basename(f))[0], []).append(f)
        ctx.data["c_headers"] = headers
        ctx.data["c_header_stems"] = stems
        dirs = set()
        for m in ctx.manifests:
            if m["ecosystem"] == "cmake":
                dirs.update(m["extra"].get("include_dirs", []))
        ctx.data["c_include_dirs"] = sorted(d for d in dirs)

    def _resolve(self, ctx, rel, spec, quoted):
        base = posixpath.dirname(rel)
        if quoted:
            cand = posixpath.normpath(posixpath.join(base, spec))
            if cand in ctx.files:
                return cand, "discovered", "relative to including file"
        for d in ctx.data["c_include_dirs"]:
            cand = posixpath.normpath(posixpath.join(d, spec))
            if cand in ctx.files:
                return cand, "discovered", "CMake include directory '%s'" % d
        hits = sorted(set(ctx.data["c_headers"].get(posixpath.normpath(spec), [])))
        if hits:
            same_tree = [h for h in hits if h.split("/")[0] == rel.split("/")[0]] or hits
            return same_tree[0], "inferred", ("suffix match; include path not verified" +
                                              ("; ambiguous (%d candidates)" % len(hits) if len(hits) > 1 else ""))
        return None

    def analyze(self, ctx, rel, text):
        res = new_result()
        src = strip_js_comments(text)    # same comment/string rules apply to C-family sources
        seen = set()
        for m in RE_INCLUDE.finditer(src):
            quoted = m.group(1) == '"'
            spec = m.group(2).strip()
            line = line_of(src, m.start())
            r = self._resolve(ctx, rel, spec, quoted)
            if r:
                target, ev, note = r
                if target != rel:
                    add_edge(res, rel, target, "include", ev, line, spec, note=note)
                    seen.add(target)
            else:
                add_external(res, rel, spec, spec, line, kind="system-include" if not quoted else "unresolved-include")
        ext = posixpath.splitext(rel)[1].lower()
        if ext in _IMPL_EXT:
            stem = posixpath.splitext(posixpath.basename(rel))[0]
            cands = sorted(ctx.data["c_header_stems"].get(stem, []))
            same_dir = [h for h in cands if posixpath.dirname(h) == posixpath.dirname(rel)]
            pick = same_dir or (cands if len(cands) == 1 else [])
            for h in pick[:1]:
                if h not in seen:
                    add_edge(res, rel, h, "header-pair", "inferred", 0, stem, note="same-stem header/implementation pairing")
        for m in RE_TYPE.finditer(src):
            if len(res["defs"]) < 200:
                res["defs"].append({"name": m.group(2), "kind": m.group(1), "line": line_of(src, m.start())})
        for m in RE_GETENV.finditer(src):
            add_implicit(res, "env", m.group(1), "read", line_of(src, m.start()))
        return res

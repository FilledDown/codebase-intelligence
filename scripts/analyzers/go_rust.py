"""Go and Rust analyzers."""
from __future__ import annotations

import posixpath
import re

from . import Analyzer, add_edge, add_external, add_implicit, line_of, new_result
from .javascript import strip_js_comments

RE_GO_SINGLE = re.compile(r'^[ \t]*import\s+(?:[\w.]+\s+)?"([^"\n]+)"', re.M)
RE_GO_BLOCK = re.compile(r"^[ \t]*import\s*\((.*?)\)", re.M | re.S)
RE_GO_BLOCK_LINE = re.compile(r'^[ \t]*(?:[\w.]+\s+)?"([^"\n]+)"', re.M)
RE_GO_FUNC = re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)", re.M)
RE_GO_TYPE = re.compile(r"^type\s+(\w+)\s+(struct|interface)", re.M)
RE_GO_ENV = re.compile(r'os\.(?:Getenv|LookupEnv)\s*\(\s*"([^"\n]+)"')


class GoAnalyzer(Analyzer):
    name = "go-import"
    version = "1.0"
    languages = ("go",)
    extensions = (".go",)
    depth = "basic"
    limitations = (
        "Go: package-level imports resolved through go.mod module paths. Edges point at package directories "
        "(nodes ending in '/'); symbol usage inside a package, build tags and generated code are not analysed.",
    )

    def prepare(self, ctx):
        mods = []
        for m in ctx.manifests:
            if m["ecosystem"] == "go" and m["extra"].get("module"):
                mods.append((m["extra"]["module"], posixpath.dirname(m["manifest"])))
        ctx.data["go_modules"] = sorted(mods, key=lambda x: -len(x[0]))
        dirs = {}
        for f in ctx.files:
            if f.endswith(".go") and not f.endswith("_test.go"):
                dirs.setdefault(posixpath.dirname(f), []).append(f)
        ctx.data["go_dirs"] = dirs

    def analyze(self, ctx, rel, text):
        res = new_result()
        src = strip_js_comments(text)
        imports = [(m.group(1), line_of(src, m.start(1))) for m in RE_GO_SINGLE.finditer(src)]
        for blk in RE_GO_BLOCK.finditer(src):
            base_line = line_of(src, blk.start(1))
            for lm in RE_GO_BLOCK_LINE.finditer(blk.group(1)):
                imports.append((lm.group(1), base_line + blk.group(1).count("\n", 0, lm.start(1))))
        for path, line in imports:
            hit = None
            for mod, mdir in ctx.data["go_modules"]:
                if path == mod or path.startswith(mod + "/"):
                    sub = path[len(mod):].lstrip("/")
                    d = posixpath.normpath(posixpath.join(mdir, sub)) if (mdir or sub) else ""
                    d = "" if d == "." else d
                    if d in ctx.data["go_dirs"]:
                        hit = d
                        break
            if hit is not None:
                add_edge(res, rel, hit + "/" if hit else "./", "import", "discovered", line, path, note="package import")
            elif "." in path.split("/")[0]:
                add_external(res, rel, "/".join(path.split("/")[:3]), path, line)
        for m in RE_GO_FUNC.finditer(src):
            if len(res["defs"]) < 300:
                res["defs"].append({"name": m.group(1), "kind": "function", "line": line_of(src, m.start())})
        for m in RE_GO_TYPE.finditer(src):
            res["defs"].append({"name": m.group(1), "kind": m.group(2), "line": line_of(src, m.start())})
        for m in RE_GO_ENV.finditer(src):
            add_implicit(res, "env", m.group(1), "read", line_of(src, m.start()))
        return res


RE_RS_MOD = re.compile(r"^[ \t]*(?:pub(?:\([^)]*\))?\s+)?mod\s+(\w+)\s*;", re.M)
RE_RS_USE = re.compile(r"^[ \t]*(?:pub(?:\([^)]*\))?\s+)?use\s+([\w:]+)", re.M)
RE_RS_EXTERN = re.compile(r"^[ \t]*extern\s+crate\s+(\w+)", re.M)
RE_RS_DEF = re.compile(r"^[ \t]*(?:pub(?:\([^)]*\))?\s+)?(fn|struct|enum|trait)\s+(\w+)", re.M)
RE_RS_ENV = re.compile(r'env::var(?:_os)?\s*\(\s*"([^"\n]+)"')
_RS_STD = {"std", "core", "alloc", "crate", "self", "super"}


class RustAnalyzer(Analyzer):
    name = "rust-mod"
    version = "1.0"
    languages = ("rust",)
    extensions = (".rs",)
    depth = "basic"
    limitations = (
        "Rust: `mod x;` declarations are resolved to files (discovered). `use crate::...` paths are matched "
        "against the module file tree (inferred). Macros, cfg-gated modules, #[path] attributes and "
        "workspace-level re-exports are not followed.",
    )

    def prepare(self, ctx):
        ctx.data["rs_mods"] = set()

    @staticmethod
    def _crate_root(ctx, rel):
        d = posixpath.dirname(rel)
        while True:
            for n in ("main.rs", "lib.rs"):
                if posixpath.join(d, n) in ctx.files:
                    return d
            if not d:
                return None
            d = posixpath.dirname(d)

    def analyze(self, ctx, rel, text):
        res = new_result()
        src = strip_js_comments(text)
        d = posixpath.dirname(rel)
        stem = posixpath.splitext(posixpath.basename(rel))[0]
        base = d if stem in ("main", "lib", "mod") else posixpath.join(d, stem)
        local_mods = set()
        for m in RE_RS_MOD.finditer(src):
            name = m.group(1)
            local_mods.add(name)
            line = line_of(src, m.start())
            for cand in (posixpath.join(base, name + ".rs"), posixpath.join(base, name, "mod.rs")):
                if cand in ctx.files:
                    add_edge(res, rel, cand, "mod", "discovered", line, name)
                    break
            else:
                res["unresolved"].append({"source": rel, "spec": "mod " + name, "reason": "module file not found", "line": line})
        root = self._crate_root(ctx, rel)
        for m in RE_RS_USE.finditer(src):
            path = m.group(1)
            segs = [s for s in path.split("::") if s]
            if not segs:
                continue
            line = line_of(src, m.start())
            if segs[0] == "crate" and root is not None:
                cur, hit = root, None
                for s in segs[1:]:
                    nxt = None
                    for cand in (posixpath.join(cur, s + ".rs"), posixpath.join(cur, s, "mod.rs")):
                        if cand in ctx.files:
                            nxt = cand
                            break
                    if not nxt:
                        break
                    hit = nxt
                    cur = posixpath.join(cur, s)
                if hit and hit != rel:
                    add_edge(res, rel, hit, "use", "inferred", line, path, note="matched against module file tree")
            elif segs[0] not in _RS_STD and segs[0] not in local_mods:
                add_external(res, rel, segs[0], path, line)
        for m in RE_RS_EXTERN.finditer(src):
            add_external(res, rel, m.group(1), m.group(1), line_of(src, m.start()), kind="extern-crate")
        for m in RE_RS_DEF.finditer(src):
            if len(res["defs"]) < 300:
                res["defs"].append({"name": m.group(2), "kind": m.group(1), "line": line_of(src, m.start())})
        for m in RE_RS_ENV.finditer(src):
            add_implicit(res, "env", m.group(1), "read", line_of(src, m.start()))
        return res

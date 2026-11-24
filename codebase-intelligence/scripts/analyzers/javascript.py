"""JavaScript / TypeScript analyzer.

Tolerant, regex-based extraction on comment-stripped source (no type information,
no TypeScript compiler). Resolves relative imports, tsconfig/jsconfig `paths`
and `baseUrl`, index files, TS-style `.js` -> `.ts` specifiers and workspace
packages. Template-literal dynamic imports become inferred edges to the
directory they point into.
"""
from __future__ import annotations

import json
import posixpath
import re

from . import (Analyzer, add_edge, add_external, add_implicit, add_unresolved, line_of, new_result)

_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte")
_CODE_EXT = set(_EXTS)
_CAND_EXTS = (".ts", ".tsx", ".d.ts", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".vue", ".svelte", ".json")
_SWAP = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
_BUILTINS = set("""assert async_hooks buffer child_process cluster console constants crypto dgram diagnostics_channel
dns domain events fs http http2 https inspector module net os path perf_hooks process punycode querystring readline
repl stream string_decoder sys timers tls trace_events tty url util v8 vm wasi worker_threads zlib""".split())
_GENERIC_EVENTS = {"error", "data", "end", "close", "open", "connect", "listening", "exit", "finish", "drain",
                   "readable", "pipe", "unpipe", "sigint", "sigterm", "uncaughtexception", "unhandledrejection",
                   "ready", "change", "click", "message", "request", "response", "connection", "disconnect", "upgrade"}

RE_IMPORT_FROM = re.compile(r"\b(import|export)\s+(type\s+)?([\w*${},\s]+?)\s+from\s*['\"]([^'\"\n]+)['\"]", re.S)
RE_SIDE_EFFECT = re.compile(r"\bimport\s*['\"]([^'\"\n]+)['\"]")
RE_REQUIRE = re.compile(r"\brequire\s*\(\s*['\"]([^'\"\n]+)['\"]\s*\)")
RE_DYN_LIT = re.compile(r"\bimport\s*\(\s*(['\"])([^'\"\n]+)\1\s*\)")
RE_DYN_TPL = re.compile(r"\bimport\s*\(\s*`([^`]*)`")
RE_DYN_ANY = re.compile(r"\bimport\s*\(\s*([^'\"`)\s][^)]*)\)")
RE_ENV = re.compile(r"\b(?:process\.env|import\.meta\.env)\s*(?:\.\s*([A-Za-z_]\w*)|\[\s*['\"]([^'\"]+)['\"]\s*\])")
RE_EMIT = re.compile(r"\.(?:emit|publish)\s*\(\s*['\"]([^'\"\n]+)['\"]")
RE_LISTEN = re.compile(r"\.(?:on|once|subscribe|addListener)\s*\(\s*['\"]([^'\"\n]+)['\"]")
RE_EXPORT_DEF = re.compile(r"^\s*export\s+(?:default\s+)?(?:async\s+)?(function|class|const|let|var|interface|type|enum)\s*\*?\s*(\w+)", re.M)


def strip_js_comments(src):
    """Blank out comments (keeping line structure) while leaving string contents intact."""
    out, i, n, state = [], 0, len(src), None
    while i < n:
        c = src[i]
        d = src[i + 1] if i + 1 < n else ""
        if state is None:
            if c == "/" and d == "/":
                j = src.find("\n", i)
                j = n if j == -1 else j
                out.append(" " * (j - i))
                i = j
                continue
            if c == "/" and d == "*":
                j = src.find("*/", i + 2)
                j = n if j == -1 else j + 2
                out.append(re.sub(r"[^\n]", " ", src[i:j]))
                i = j
                continue
            if c in "\"'`":
                state = c
            out.append(c)
            i += 1
        else:
            if c == "\\":
                out.append(src[i:i + 2])
                i += 2
                continue
            if c == state:
                state = None
            elif c == "\n" and state != "`":
                state = None
            out.append(c)
            i += 1
    return "".join(out)


def _tolerant_json(text):
    t = strip_js_comments(text)
    t = re.sub(r",\s*([}\]])", r"\1", t)
    try:
        return json.loads(t)
    except ValueError:
        return None


def _pkg_name(spec):
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") and len(parts) > 1 else parts[0]


class JavaScriptAnalyzer(Analyzer):
    name = "javascript-regex"
    version = "1.0"
    languages = ("javascript", "typescript")
    extensions = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
    depth = "regex"
    limitations = (
        "JS/TS: regex-based on comment-stripped source (no TypeScript compiler, no type information). "
        "Non-literal require/import, computed paths, bundler aliases outside tsconfig/jsconfig, and "
        "framework conventions (file-based routing, DI containers) are not resolved.",
    )

    def prepare(self, ctx):
        aliases = []       # (config_dir, baseUrl_or_None, [(pattern, [targets])])
        for rel in sorted(ctx.files):
            base = posixpath.basename(rel)
            if re.match(r"^(tsconfig[\w.-]*|jsconfig)\.json$", base):
                cfg = self._load_config(ctx, rel, 0)
                if cfg:
                    aliases.append((posixpath.dirname(rel), cfg))
        ctx.data["js_aliases"] = aliases
        ws = {}
        for m in ctx.manifests:
            if m["ecosystem"] == "javascript" and m.get("name"):
                ws[m["name"]] = m
        ctx.data["js_packages"] = ws
        ctx.data["js_top_dirs"] = {f.split("/")[0] for f in ctx.files if "/" in f}

    def _load_config(self, ctx, rel, depth):
        text = ctx.read(rel)
        data = _tolerant_json(text) if text else None
        if not isinstance(data, dict):
            return None
        out = {"baseUrl": None, "paths": {}}
        ext = data.get("extends")
        if isinstance(ext, str) and ext.startswith(".") and depth < 5:
            parent = posixpath.normpath(posixpath.join(posixpath.dirname(rel), ext))
            if not parent.endswith(".json"):
                parent += ".json"
            if parent in ctx.files:
                inherited = self._load_config(ctx, parent, depth + 1)
                if inherited:
                    out.update(inherited)
        co = data.get("compilerOptions") or {}
        here = posixpath.dirname(rel)
        if isinstance(co.get("baseUrl"), str):
            out["baseUrl"] = posixpath.normpath(posixpath.join(here, co["baseUrl"]))
        if isinstance(co.get("paths"), dict):
            base = out["baseUrl"] if out["baseUrl"] is not None else here
            paths = dict(out["paths"])
            for pat, targets in co["paths"].items():
                if isinstance(targets, list):
                    paths[pat] = [posixpath.normpath(posixpath.join(base, t)) for t in targets if isinstance(t, str)]
            out["paths"] = paths
        return out

    # -- resolution --------------------------------------------------------
    def _candidates(self, ctx, path):
        path = path.split("?")[0]
        if path in ctx.files:
            yield path
        stem, ext = posixpath.splitext(path)
        if ext in _SWAP:
            for e in _SWAP[ext]:
                if stem + e in ctx.files:
                    yield stem + e
        for e in _CAND_EXTS:
            if path + e in ctx.files:
                yield path + e
        for e in _CAND_EXTS[:-1]:
            idx = posixpath.join(path, "index" + e)
            if idx in ctx.files:
                yield idx

    def _resolve(self, ctx, rel, spec):
        """Return (target, evidence, note) or None for external/unresolved."""
        base = posixpath.dirname(rel)
        if spec.startswith("."):
            hit = next(self._candidates(ctx, posixpath.normpath(posixpath.join(base, spec))), None)
            return (hit, "discovered", None) if hit else None
        for cfg_dir, cfg in ctx.data["js_aliases"]:
            if cfg_dir and not (rel == cfg_dir or rel.startswith(cfg_dir + "/")):
                continue
            for pat, targets in cfg["paths"].items():
                if "*" in pat:
                    pre, post = pat.split("*", 1)
                    if spec.startswith(pre) and spec.endswith(post) and len(spec) >= len(pre) + len(post):
                        mid = spec[len(pre):len(spec) - len(post) if post else None]
                        for t in targets:
                            hit = next(self._candidates(ctx, t.replace("*", mid)), None)
                            if hit:
                                return hit, "discovered", "tsconfig paths alias"
                elif spec == pat:
                    for t in targets:
                        hit = next(self._candidates(ctx, t), None)
                        if hit:
                            return hit, "discovered", "tsconfig paths alias"
            if cfg["baseUrl"] is not None:
                hit = next(self._candidates(ctx, posixpath.normpath(posixpath.join(cfg["baseUrl"], spec))), None)
                if hit:
                    return hit, "discovered", "tsconfig baseUrl"
        pkg = _pkg_name(spec)
        if "/" in spec and spec.split("/")[0] in ctx.data["js_top_dirs"] and pkg not in ctx.data["js_packages"]:
            d = base
            while True:
                hit = next(self._candidates(ctx, posixpath.normpath(posixpath.join(d, spec))), None)
                if hit:
                    return hit, "inferred", "root-relative bare specifier; baseUrl/alias assumed"
                if not d:
                    break
                d = posixpath.dirname(d)
        m = ctx.data["js_packages"].get(pkg)
        if m:
            rest = spec[len(pkg):].lstrip("/")
            pdir = posixpath.dirname(m["manifest"])
            guesses = []
            if rest:
                guesses += [posixpath.join(pdir, rest), posixpath.join(pdir, "src", rest)]
            else:
                guesses += [p for p, _ in m["entry"] if not p.endswith("(if present)")]
                guesses += [posixpath.join(pdir, "src/index"), posixpath.join(pdir, "index")]
            for g in guesses:
                hit = next(self._candidates(ctx, posixpath.normpath(g)), None)
                if hit:
                    return hit, "inferred", "workspace package '%s'; entry guessed" % pkg
        return None

    def _record(self, ctx, res, rel, spec, kind, line, names, type_only=False, scope="module"):
        r = self._resolve(ctx, rel, spec)
        note = "type-only import" if type_only else None
        if r:
            target, ev, n2 = r
            add_edge(res, rel, target, kind, ev, line, spec, names=names, scope="type-only" if type_only else scope,
                     note="; ".join(x for x in (note, n2) if x) or None)
            return
        if spec.startswith("."):
            add_unresolved(res, rel, spec, "relative path not found in repository", line)
            return
        if spec.startswith("node:") or _pkg_name(spec) in _BUILTINS:
            return
        if re.match(r"^[#~@]/", spec) or spec.startswith("#"):
            add_unresolved(res, rel, spec, "alias-looking specifier not covered by tsconfig/jsconfig paths", line)
            return
        if "/" in spec and spec.split("/")[0] in ctx.data["js_top_dirs"]:
            add_unresolved(res, rel, spec, "bare specifier matches a repository directory but no file resolved (baseUrl/alias not configured?)", line)
            return
        add_external(res, rel, _pkg_name(spec), spec, line, kind=kind)

    @staticmethod
    def _names(clause):
        names = []
        clause = clause.strip()
        brace = re.search(r"\{([^}]*)\}", clause)
        if brace:
            for part in brace.group(1).split(","):
                part = part.strip()
                if part:
                    names.append(re.split(r"\s+as\s+", part)[0].strip())
            clause = clause.replace(brace.group(0), "")
        if "*" in clause:
            names.append("*")
        elif re.search(r"[A-Za-z_$]", clause.replace("type", "", 1) if clause.startswith("type ") else clause):
            names.append("default")
        return names

    def analyze(self, ctx, rel, text):
        res = new_result()
        src = strip_js_comments(text)
        for m in RE_IMPORT_FROM.finditer(src):
            kw, type_kw, clause, spec = m.groups()
            self._record(ctx, res, rel, spec, "reexport" if kw == "export" else "import",
                         line_of(src, m.start()), self._names(clause), type_only=bool(type_kw))
        covered = {m.start(4) for m in RE_IMPORT_FROM.finditer(src)}
        for m in RE_SIDE_EFFECT.finditer(src):
            if m.start(1) in covered:
                continue
            self._record(ctx, res, rel, m.group(1), "import", line_of(src, m.start()), [])
        for m in RE_REQUIRE.finditer(src):
            self._record(ctx, res, rel, m.group(1), "require", line_of(src, m.start()), [])
        for m in RE_DYN_LIT.finditer(src):
            self._record(ctx, res, rel, m.group(2), "dynamic-import", line_of(src, m.start()), [], scope="dynamic")
        for m in RE_DYN_TPL.finditer(src):
            body = m.group(1)
            line = line_of(src, m.start())
            if "${" not in body:
                self._record(ctx, res, rel, body, "dynamic-import", line, [], scope="dynamic")
                continue
            prefix = body.split("${", 1)[0]
            if prefix.startswith("."):
                d = posixpath.normpath(posixpath.join(posixpath.dirname(rel), prefix.rsplit("/", 1)[0] if "/" in prefix else "."))
                targets = sorted(f for f in ctx.files if posixpath.dirname(f) == d and posixpath.splitext(f)[1] in _CODE_EXT)
                if targets:
                    for t in targets[:25]:
                        add_edge(res, rel, t, "dynamic-import", "inferred", line, body, scope="dynamic",
                                 note="template-literal import pattern; every file in that directory is a candidate")
                    continue
            add_unresolved(res, rel, body, "template-literal dynamic import; target set unknown", line)
        for m in RE_DYN_ANY.finditer(src):
            add_unresolved(res, rel, m.group(1).strip()[:60], "non-literal dynamic import; target unknown", line_of(src, m.start()))
        for m in RE_ENV.finditer(src):
            add_implicit(res, "env", m.group(1) or m.group(2), "read", line_of(src, m.start()))
        for m in RE_EMIT.finditer(src):
            if m.group(1).lower() not in _GENERIC_EVENTS:
                add_implicit(res, "event", m.group(1), "emit", line_of(src, m.start()))
        for m in RE_LISTEN.finditer(src):
            if m.group(1).lower() not in _GENERIC_EVENTS:
                add_implicit(res, "event", m.group(1), "listen", line_of(src, m.start()))
        for m in RE_EXPORT_DEF.finditer(src):
            if len(res["defs"]) < 300:
                kind = {"const": "variable", "let": "variable", "var": "variable"}.get(m.group(1), m.group(1))
                res["defs"].append({"name": m.group(2), "kind": kind, "line": line_of(src, m.start())})
        return res

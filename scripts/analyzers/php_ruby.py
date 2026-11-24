"""PHP and Ruby analyzers."""
from __future__ import annotations

import posixpath
import re

from . import Analyzer, add_edge, add_external, add_implicit, add_unresolved, build_suffix_index, line_of, new_result

RE_PHP_USE = re.compile(r"^[ \t]*use\s+(?:function\s+|const\s+)?([\\\w]+)(?:\s+as\s+\w+)?\s*;", re.M)
RE_PHP_USE_GROUP = re.compile(r"^[ \t]*use\s+([\\\w]+)\\\{([^}]*)\}\s*;", re.M)
RE_PHP_REQ = re.compile(r"\b(?:require|include)(?:_once)?\s*\(?\s*(?:__DIR__\s*\.\s*)?['\"]([^'\"\n]+)['\"]")
RE_PHP_TYPE = re.compile(r"^[ \t]*(?:abstract\s+|final\s+)?(class|interface|trait|enum)\s+(\w+)", re.M)
RE_PHP_ENV = re.compile(r"\b(?:getenv|env)\s*\(\s*['\"]([^'\"\n]+)['\"]|\$_(?:ENV|SERVER)\[\s*['\"]([^'\"\n]+)['\"]\s*\]")

RE_RB_REQREL = re.compile(r"^[ \t]*require_relative\s*\(?\s*['\"]([^'\"\n]+)['\"]", re.M)
RE_RB_REQ = re.compile(r"^[ \t]*require\s*\(?\s*['\"]([^'\"\n]+)['\"]", re.M)
RE_RB_DEF = re.compile(r"^[ \t]*(class|module|def)\s+([\w:.]+)", re.M)
RE_RB_ENV = re.compile(r"\bENV(?:\.fetch)?\s*[\[(]\s*['\"]([^'\"\n]+)['\"]")


def _strip_hash_comments(text):
    return re.sub(r"(?m)^[ \t]*#.*$", "", text)


class PhpAnalyzer(Analyzer):
    name = "php-use"
    version = "1.0"
    languages = ("php",)
    extensions = (".php",)
    depth = "basic"
    limitations = (
        "PHP: `use` statements mapped through composer.json PSR-4 prefixes (discovered) or path suffix "
        "(inferred); literal require/include paths. Same-namespace references, autowiring and "
        "framework containers are not modelled.",
    )

    def prepare(self, ctx):
        psr4 = []
        for m in ctx.manifests:
            if m["ecosystem"] == "php":
                base = posixpath.dirname(m["manifest"])
                for prefix, dirs in m["extra"].get("psr4", {}).items():
                    for d in dirs:
                        psr4.append((prefix, posixpath.normpath(posixpath.join(base, d))))
        ctx.data["php_psr4"] = sorted(psr4, key=lambda x: -len(x[0]))
        ctx.data["php_index"] = build_suffix_index(ctx.files, (".php",))

    def _class_file(self, ctx, fqcn):
        fqcn = fqcn.lstrip("\\")
        for prefix, d in ctx.data["php_psr4"]:
            p = prefix.rstrip("\\")
            if fqcn == p or fqcn.startswith(p + "\\"):
                rest = fqcn[len(p):].lstrip("\\").replace("\\", "/")
                cand = posixpath.normpath(posixpath.join(d, rest + ".php"))
                if cand in ctx.files:
                    return cand, "discovered", "composer.json PSR-4 mapping"
        hits = ctx.data["php_index"].get(fqcn.replace("\\", "/"))
        if hits:
            return sorted(hits)[0], "inferred", "path-suffix match" + ("; ambiguous" if len(hits) > 1 else "")
        return None

    def analyze(self, ctx, rel, text):
        res = new_result()
        uses = [(m.group(1), line_of(text, m.start())) for m in RE_PHP_USE.finditer(text)]
        for m in RE_PHP_USE_GROUP.finditer(text):
            for part in m.group(2).split(","):
                if part.strip():
                    uses.append((m.group(1) + "\\" + part.strip().split(" as ")[0], line_of(text, m.start())))
        for fq, line in uses:
            r = self._class_file(ctx, fq)
            if r and r[0] != rel:
                add_edge(res, rel, r[0], "use", r[1], line, fq, note=r[2])
            elif not r:
                top = fq.lstrip("\\").split("\\")[0]
                if "\\" in fq.lstrip("\\"):
                    add_external(res, rel, top, fq, line)
        for m in RE_PHP_REQ.finditer(text):
            spec = m.group(1)
            cand = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec.lstrip("/"))) if not spec.startswith("/") or "__DIR__" in m.group(0) else spec
            line = line_of(text, m.start())
            if cand in ctx.files:
                add_edge(res, rel, cand, "require", "discovered", line, spec)
            else:
                add_unresolved(res, rel, spec, "required file not found relative to including file", line)
        for m in RE_PHP_TYPE.finditer(text):
            res["defs"].append({"name": m.group(2), "kind": m.group(1), "line": line_of(text, m.start())})
        for m in RE_PHP_ENV.finditer(text):
            add_implicit(res, "env", m.group(1) or m.group(2), "read", line_of(text, m.start()))
        return res


class RubyAnalyzer(Analyzer):
    name = "ruby-require"
    version = "1.0"
    languages = ("ruby",)
    extensions = (".rb",)
    depth = "basic"
    limitations = (
        "Ruby: literal require/require_relative only. Autoloading (Rails/Zeitwerk), metaprogramming and "
        "constant resolution are not modelled; `require` of repository files is an inferred edge.",
    )

    def prepare(self, ctx):
        ctx.data["rb_index"] = build_suffix_index(ctx.files, (".rb",))

    def analyze(self, ctx, rel, text):
        res = new_result()
        src = _strip_hash_comments(text)
        for m in RE_RB_REQREL.finditer(src):
            spec = m.group(1)
            cand = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec))
            cand = cand if cand.endswith(".rb") else cand + ".rb"
            line = line_of(src, m.start())
            if cand in ctx.files:
                add_edge(res, rel, cand, "require", "discovered", line, spec)
            else:
                add_unresolved(res, rel, spec, "require_relative target not found", line)
        for m in RE_RB_REQ.finditer(src):
            spec = m.group(1)
            line = line_of(src, m.start())
            hits = ctx.data["rb_index"].get(spec[:-3] if spec.endswith(".rb") else spec)
            if hits:
                hits = sorted(hits)
                add_edge(res, rel, hits[0], "require", "inferred", line, spec, note="matched against repository paths (load path not verified)")
            else:
                add_external(res, rel, spec.split("/")[0], spec, line)
        for m in RE_RB_DEF.finditer(src):
            if len(res["defs"]) < 300:
                res["defs"].append({"name": m.group(2), "kind": m.group(1) if m.group(1) != "def" else "method", "line": line_of(src, m.start())})
        for m in RE_RB_ENV.finditer(src):
            add_implicit(res, "env", m.group(1), "read", line_of(src, m.start()))
        return res

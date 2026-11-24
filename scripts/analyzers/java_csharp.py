"""Java and C# analyzers (import / using level)."""
from __future__ import annotations

import posixpath
import re

from . import Analyzer, add_edge, add_external, add_implicit, build_suffix_index, line_of, new_result
from .javascript import strip_js_comments

RE_JAVA_IMPORT = re.compile(r"^[ \t]*import\s+(static\s+)?([\w.]+?)(\.\*)?\s*;", re.M)
RE_JAVA_TYPE = re.compile(r"^[ \t]*(?:public\s+|protected\s+|private\s+|abstract\s+|final\s+|static\s+)*(class|interface|enum|record)\s+(\w+)", re.M)
RE_JAVA_ENV = re.compile(r"System\.getenv\s*\(\s*\"([^\"\n]+)\"")
_JAVA_STD = ("java.", "javax.", "jdk.", "sun.")

RE_CS_USING = re.compile(r"^[ \t]*(?:global\s+)?using\s+(?:static\s+)?(?:\w+\s*=\s*)?([\w.]+)\s*;", re.M)
RE_CS_NS = re.compile(r"^[ \t]*namespace\s+([\w.]+)\s*[;{]?", re.M)
RE_CS_TYPE = re.compile(r"^[ \t]*(?:public\s+|internal\s+|private\s+|protected\s+|abstract\s+|sealed\s+|static\s+|partial\s+)*(class|interface|enum|struct|record)\s+(\w+)", re.M)
RE_CS_ENV = re.compile(r"Environment\.GetEnvironmentVariable\s*\(\s*\"([^\"\n]+)\"")
_CS_STD = ("System", "Microsoft", "Windows")


class JavaAnalyzer(Analyzer):
    name = "java-import"
    version = "1.0"
    languages = ("java",)
    extensions = (".java",)
    depth = "basic"
    limitations = (
        "Java: explicit imports only. Same-package references need no import and are invisible here; "
        "wildcard imports are inferred edges to every class in the package; dependency injection, "
        "reflection and annotation processing are not modelled.",
    )

    def prepare(self, ctx):
        ctx.data["java_index"] = build_suffix_index(ctx.files, (".java",))

    def analyze(self, ctx, rel, text):
        res = new_result()
        src = strip_js_comments(text)
        idx = ctx.data["java_index"]
        for m in RE_JAVA_IMPORT.finditer(src):
            static, name, star = m.group(1), m.group(2), m.group(3)
            line = line_of(src, m.start())
            if name.startswith(_JAVA_STD):
                continue
            if star:
                key = name.replace(".", "/")
                dirs = sorted(f for f in ctx.files if f.endswith(".java") and posixpath.dirname(f).endswith(key))
                if dirs:
                    for f in dirs[:30]:
                        add_edge(res, rel, f, "import", "inferred", line, name + ".*", note="wildcard import; which class is used is unknown")
                    continue
            else:
                key = name.replace(".", "/")
                hits = idx.get(key) or (idx.get(key.rsplit("/", 1)[0]) if static else None)
                if hits:
                    hits = sorted(hits)
                    add_edge(res, rel, hits[0], "import", "inferred" if len(hits) > 1 else "discovered", line, name,
                             note="ambiguous class path" if len(hits) > 1 else None)
                    continue
            add_external(res, rel, ".".join(name.split(".")[:2]), name, line)
        for m in RE_JAVA_TYPE.finditer(src):
            if len(res["defs"]) < 200:
                res["defs"].append({"name": m.group(2), "kind": m.group(1), "line": line_of(src, m.start())})
        for m in RE_JAVA_ENV.finditer(src):
            add_implicit(res, "env", m.group(1), "read", line_of(src, m.start()))
        return res


class CSharpAnalyzer(Analyzer):
    name = "csharp-using"
    version = "1.0"
    languages = ("csharp",)
    extensions = (".cs",)
    depth = "basic"
    limitations = (
        "C#: `using` directives mapped to files that declare the namespace (inferred; namespaces span files). "
        "Same-namespace references, partial classes across files and DI container wiring are not modelled.",
    )

    def prepare(self, ctx):
        ns = {}
        for f in sorted(ctx.files):
            if f.endswith(".cs"):
                text = ctx.read(f)
                if text:
                    for m in RE_CS_NS.finditer(strip_js_comments(text)):
                        ns.setdefault(m.group(1), set()).add(f)
        ctx.data["cs_ns"] = ns

    def analyze(self, ctx, rel, text):
        res = new_result()
        src = strip_js_comments(text)
        ns = ctx.data["cs_ns"]
        for m in RE_CS_USING.finditer(src):
            name = m.group(1)
            line = line_of(src, m.start())
            files = sorted(f for f in ns.get(name, ()) if f != rel)
            if files:
                for f in files[:30]:
                    add_edge(res, rel, f, "using", "inferred", line, name, note="namespace-level; which type is used is unknown")
            elif name.split(".")[0] not in _CS_STD:
                add_external(res, rel, name.split(".")[0], name, line)
        for m in RE_CS_TYPE.finditer(src):
            if len(res["defs"]) < 200:
                res["defs"].append({"name": m.group(2), "kind": m.group(1), "line": line_of(src, m.start())})
        for m in RE_CS_ENV.finditer(src):
            add_implicit(res, "env", m.group(1), "read", line_of(src, m.start()))
        return res

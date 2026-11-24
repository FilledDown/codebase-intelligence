"""Analyzer interface and registry for codebase-intelligence.

An analyzer turns one source file into relationships. Adding a language means
adding a subclass of `Analyzer` and listing it in `ANALYZERS`; nothing else in
the toolchain is language specific.

Evidence vocabulary used on every edge:
  discovered - the relationship is written in the source and resolved to a file
               by a deterministic rule (e.g. a relative import that exists).
  inferred   - the relationship rests on a heuristic: ambiguous resolution,
               suffix matching, string-key identity, naming convention.
Neither value says anything about runtime behaviour; they describe how the
*edge* was obtained. Claude still has to confirm behaviour by reading code.
"""
from __future__ import annotations

import importlib.util
import os
import posixpath

STRUCTURAL_KINDS = {"package-member"}   # containment edges: traversed, never counted as coupling


class Analyzer(object):
    name = "base"
    version = "1.0"
    languages = ()        # language ids from ci_common.LANG_BY_EXT
    extensions = ()       # file extensions handled, including the dot
    depth = "basic"       # "ast" | "regex" | "basic"; shown in coverage reports
    limitations = ()      # strings surfaced verbatim in reports

    def prepare(self, ctx):
        """Optional one-time indexing over ctx.files before analysis."""

    def analyze(self, ctx, rel, text):
        raise NotImplementedError


class RepoContext(object):
    def __init__(self, root, files, read):
        self.root = root
        self.files = set(files)
        self.read = read               # read(rel) -> text or None
        self.data = {}                 # per-analyzer caches
        self.manifests = []            # parsed manifests, filled by the driver

    def exists(self, rel):
        return rel in self.files


def new_result():
    return {"edges": [], "externals": [], "unresolved": [], "defs": [], "implicit": [], "errors": []}


def add_edge(res, source, target, kind, evidence, line=0, spec="", names=None, note=None, scope="module"):
    e = {"source": source, "target": target, "kind": kind, "evidence": evidence,
         "line": line, "spec": spec, "scope": scope}
    if names:
        e["names"] = sorted(set(names))
    if note:
        e["note"] = note
    res["edges"].append(e)


def add_external(res, source, package, spec="", line=0, kind="import"):
    res["externals"].append({"source": source, "package": package, "spec": spec, "line": line, "kind": kind})


def add_unresolved(res, source, spec, reason, line=0):
    res["unresolved"].append({"source": source, "spec": spec, "reason": reason, "line": line})


def add_implicit(res, kind, key, role, line):
    res["implicit"].append({"kind": kind, "key": key, "role": role, "line": line})


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def build_suffix_index(files, exts, strip_init=None):
    """Map dotted/slashed suffixes of file paths to the files that carry them.

    For 'src/pkg/mod.py' this indexes 'mod', 'pkg/mod', 'src/pkg/mod'.
    """
    idx = {}
    for f in files:
        base, ext = os.path.splitext(f)
        if ext.lower() not in exts:
            continue
        if strip_init and posixpath.basename(base) == strip_init:
            base = posixpath.dirname(base)
        parts = base.split("/")
        for i in range(len(parts)):
            idx.setdefault("/".join(parts[i:]), []).append(f)
    return idx


def prefer_same_root(importer, candidates, key):
    """Pick the candidate whose source root contains the importer; flag ambiguity."""
    if len(candidates) == 1:
        return candidates[0], False
    depth = key.count("/") + 1

    def root_of(c):
        base = os.path.splitext(c)[0]
        parts = base.split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return "/".join(parts[:-depth]) if len(parts) > depth else ""

    scored = []
    for c in candidates:
        r = root_of(c)
        inside = (r == "" or importer.startswith(r + "/"))
        scored.append((0 if inside else 1, len(r), c))
    scored.sort()
    best = scored[0]
    ties = [s for s in scored if s[0] == best[0] and s[1] == best[1]]
    return best[2], len(ties) > 1


def load_plugin_analyzers(path, repo_root):
    """Load analyzers from a user-supplied Python file.

    Refuses files inside the repository being analysed: that code is untrusted
    and must never be imported or executed by the analysis.
    """
    real_plugin = os.path.realpath(path)
    real_root = os.path.realpath(repo_root)
    if real_plugin == real_root or real_plugin.startswith(real_root + os.sep):
        raise ValueError("refusing to load plugin from inside the analysed repository: " + path)
    spec = importlib.util.spec_from_file_location("ci_user_plugin", real_plugin)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    got = getattr(mod, "ANALYZERS", None) or (mod.get_analyzers() if hasattr(mod, "get_analyzers") else [])
    return [a() if isinstance(a, type) else a for a in got]


def builtin_analyzers():
    from .python import PythonAnalyzer
    from .javascript import JavaScriptAnalyzer
    from .cfamily import CFamilyAnalyzer
    from .java_csharp import JavaAnalyzer, CSharpAnalyzer
    from .go_rust import GoAnalyzer, RustAnalyzer
    from .php_ruby import PhpAnalyzer, RubyAnalyzer
    return [PythonAnalyzer(), JavaScriptAnalyzer(), CFamilyAnalyzer(), JavaAnalyzer(), CSharpAnalyzer(),
            GoAnalyzer(), RustAnalyzer(), PhpAnalyzer(), RubyAnalyzer()]

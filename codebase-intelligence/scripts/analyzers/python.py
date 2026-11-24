"""Python analyzer: real AST parsing, no code execution."""
from __future__ import annotations

import ast
import posixpath
import re
import sys

from . import (Analyzer, add_edge, add_external, add_implicit, add_unresolved,
               build_suffix_index, new_result, prefer_same_root)

_STDLIB = set(getattr(sys, "stdlib_module_names", ())) or set(
    "abc argparse array ast asyncio base64 bisect builtins collections concurrent contextlib copy csv ctypes "
    "dataclasses datetime decimal difflib email enum errno fnmatch fractions functools gc getpass glob gzip "
    "hashlib heapq hmac html http importlib inspect io itertools json logging math mimetypes multiprocessing "
    "numbers operator os pathlib pickle platform pprint queue random re sched secrets select shlex shutil "
    "signal socket sqlite3 ssl stat statistics string struct subprocess sys tempfile textwrap threading time "
    "timeit tkinter traceback types typing unittest urllib uuid warnings weakref xml zipfile zlib "
    "__future__ tomllib zoneinfo".split())

_EVENT_EMIT = {"emit", "publish"}
_EVENT_LISTEN = {"on", "subscribe", "add_listener", "listen"}


def _is_type_checking(test):
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or \
           (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _const_str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class PythonAnalyzer(Analyzer):
    name = "python-ast"
    version = "1.0"
    languages = ("python",)
    extensions = (".py", ".pyi")
    depth = "ast"
    limitations = (
        "Python: imports resolved by repository path suffix; sys.path manipulation, namespace packages and "
        "runtime-generated modules are not modelled. Attribute-level usage of imported modules is not traced.",
    )

    def prepare(self, ctx):
        ctx.data["py_index"] = build_suffix_index(ctx.files, (".py", ".pyi"), strip_init="__init__")
        tops = set()
        for key in ctx.data["py_index"]:
            tops.add(key.split("/")[0])
        ctx.data["py_tops"] = tops

    # -- resolution --------------------------------------------------------
    def _lookup(self, ctx, importer, dotted):
        key = dotted.replace(".", "/")
        cands = ctx.data["py_index"].get(key)
        if not cands:
            return None, False
        pick, ambiguous = prefer_same_root(importer, sorted(cands), key)
        return pick, ambiguous

    def _record_absolute(self, ctx, res, rel, module, names, line, scope):
        target, amb = self._lookup(ctx, rel, module)
        if target:
            add_edge(res, rel, target, "import", "inferred" if amb else "discovered", line, module,
                     names=names, scope=scope, note="ambiguous module name; several files match" if amb else None)
        found_sub = False
        for n in names:
            if n == "*":
                continue
            sub, samb = self._lookup(ctx, rel, module + "." + n)
            if sub and sub != target:
                add_edge(res, rel, sub, "import", "inferred" if samb else "discovered", line, module + "." + n,
                         scope=scope, note="submodule import" + ("; ambiguous" if samb else ""))
                found_sub = True
        if target or found_sub:
            return
        top = module.split(".")[0]
        if top in _STDLIB:
            return
        if top in ctx.data["py_tops"]:
            add_unresolved(res, rel, module, "looks repository-internal but no matching file", line)
        else:
            add_external(res, rel, top, module, line)

    def _record_relative(self, ctx, res, rel, level, module, names, line, scope):
        base = posixpath.dirname(rel)
        for _ in range(level - 1):
            base = posixpath.dirname(base)
        def exists_mod(path):
            for cand in (path + ".py", path + ".pyi", posixpath.join(path, "__init__.py")):
                if cand in ctx.files:
                    return cand
            return None
        if module:
            path = posixpath.normpath(posixpath.join(base, module.replace(".", "/")))
            target = exists_mod(path)
            spec = "." * level + module
            if target:
                add_edge(res, rel, target, "import", "discovered", line, spec, names=names, scope=scope)
            else:
                add_unresolved(res, rel, spec, "relative import target not found", line)
            for n in names:
                sub = exists_mod(posixpath.join(path, n))
                if sub and sub != target:
                    add_edge(res, rel, sub, "import", "discovered", line, spec + "." + n, scope=scope, note="submodule import")
        else:
            hit = False
            for n in names:
                if n == "*":
                    continue
                sub = exists_mod(posixpath.normpath(posixpath.join(base, n)))
                if sub:
                    add_edge(res, rel, sub, "import", "discovered", line, "." * level + n, scope=scope)
                    hit = True
            init = posixpath.normpath(posixpath.join(base, "__init__.py"))
            if init in ctx.files and init != rel and (not hit or "*" in names):
                add_edge(res, rel, init, "import", "discovered", line, "." * level, names=names, scope=scope)

    # -- main --------------------------------------------------------------
    def analyze(self, ctx, rel, text):
        res = new_result()
        try:
            tree = ast.parse(text, filename=rel)
        except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
            res["errors"].append("python parse failed (%s); regex fallback used" % type(exc).__name__)
            self._fallback(ctx, res, rel, text)
            return res
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                res["defs"].append({"name": node.name, "kind": kind, "line": node.lineno})
                if isinstance(node, ast.ClassDef):
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and len(res["defs"]) < 300:
                            res["defs"].append({"name": node.name + "." + sub.name, "kind": "method", "line": sub.lineno})
        self._visit(ctx, res, rel, tree, "module")
        return res

    def _visit(self, ctx, res, rel, tree, scope):
        self._walk(ctx, res, rel, tree.body, scope)

    def _walk(self, ctx, res, rel, stmts, scope):
        for stmt in stmts:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    self._record_absolute(ctx, res, rel, alias.name, [], stmt.lineno, scope)
                continue
            if isinstance(stmt, ast.ImportFrom):
                names = [a.name for a in stmt.names]
                if stmt.level:
                    self._record_relative(ctx, res, rel, stmt.level, stmt.module or "", names, stmt.lineno, scope)
                elif stmt.module:
                    self._record_absolute(ctx, res, rel, stmt.module, names, stmt.lineno, scope)
                continue
            self._scan_expr(res, rel, stmt, ctx=ctx, scope=scope)
            if isinstance(stmt, ast.If) and _is_type_checking(stmt.test):
                self._walk(ctx, res, rel, stmt.body, "type-checking")
                self._walk(ctx, res, rel, stmt.orelse, scope)
                continue
            inner = scope
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and scope == "module":
                inner = "function"
            for child in ast.iter_child_nodes(stmt):
                if isinstance(child, ast.stmt):
                    self._walk(ctx, res, rel, [child], inner)
                elif isinstance(child, ast.ExceptHandler) or type(child).__name__ == "match_case":
                    self._walk(ctx, res, rel, child.body, inner)

    def _scan_expr(self, res, rel, node, ctx=None, scope="module"):
        """Find env reads, event emit/listen and dynamic imports inside the expressions of one statement."""
        stack = [node]
        while stack:
            n = stack.pop()
            for child in ast.iter_child_nodes(n):
                if isinstance(child, ast.stmt):
                    continue          # nested statements are handled by _visit_stmt
                stack.append(child)
            line = getattr(n, "lineno", 0)
            if isinstance(n, ast.Call):
                fn = _dotted(n.func)
                first = _const_str(n.args[0]) if n.args else None
                last = fn.rsplit(".", 1)[-1] if fn else (n.func.attr if isinstance(n.func, ast.Attribute) else "")
                if fn in ("os.getenv", "os.environ.get", "environ.get", "getenv", "os.environ.setdefault") and first:
                    add_implicit(res, "env", first, "read", line)
                elif last in _EVENT_EMIT and first:
                    add_implicit(res, "event", first, "emit", line)
                elif last in _EVENT_LISTEN and first:
                    add_implicit(res, "event", first, "listen", line)
                elif fn in ("importlib.import_module", "import_module", "__import__") and ctx is not None:
                    if first:
                        target, amb = self._lookup(ctx, rel, first)
                        if target:
                            add_edge(res, rel, target, "dynamic-import", "inferred", line, first, scope="dynamic",
                                     note="string-literal dynamic import")
                        else:
                            top = first.split(".")[0]
                            if top not in _STDLIB and top not in ctx.data["py_tops"]:
                                add_external(res, rel, top, first, line, kind="dynamic-import")
                    else:
                        add_unresolved(res, rel, "<dynamic expression>", "non-literal dynamic import; target unknown", line)
            elif isinstance(n, ast.Subscript):
                if _dotted(n.value) in ("os.environ", "environ"):
                    key = _const_str(n.slice) if not hasattr(ast, "Index") or not isinstance(n.slice, getattr(ast, "Index")) \
                        else _const_str(n.slice.value)
                    if key:
                        add_implicit(res, "env", key, "read", line)

    def _fallback(self, ctx, res, rel, text):
        for i, line in enumerate(text.splitlines(), 1):
            m = re.match(r"\s*from\s+([\w.]+)\s+import\s+(.+)", line)
            if m and not m.group(1).startswith("."):
                self._record_absolute(ctx, res, rel, m.group(1), [x.strip().split(" as ")[0] for x in m.group(2).split(",")], i, "module")
                continue
            m = re.match(r"\s*import\s+([\w.]+)", line)
            if m:
                self._record_absolute(ctx, res, rel, m.group(1), [], i, "module")

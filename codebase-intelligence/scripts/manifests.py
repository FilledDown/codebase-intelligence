#!/usr/bin/env python3
"""Manifest parsing for the codebase-intelligence scripts (stdlib only).

`parse_manifest(rel_path, text)` returns None for files that are not a known
manifest, otherwise a dict:

    {"ecosystem": str, "manifest": rel_path, "name": str|None,
     "prod": [declared names], "dev": [declared names],
     "scripts": {...}, "entry": [(path_or_target, reason)], "extra": {...}}

XML-ish formats are read with regular expressions on purpose: the repository is
untrusted input and Python's XML parsers can be abused with entity expansion.
Parsing is best effort; anything not understood is simply absent.
"""
from __future__ import annotations

import json
import posixpath
import re

try:                                   # Python 3.11+
    import tomllib as _toml
except ImportError:                    # pragma: no cover - older Pythons
    _toml = None


def _toml_loads(text):
    if _toml is None:
        return None
    try:
        return _toml.loads(text)
    except Exception:
        return None


def _norm_py(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _pep508_name(spec):
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec)
    return _norm_py(m.group(1)) if m else None


def _result(rel, ecosystem, **kw):
    r = {"ecosystem": ecosystem, "manifest": rel, "name": None, "prod": [], "dev": [],
         "scripts": {}, "entry": [], "extra": {}}
    r.update(kw)
    r["prod"] = sorted(set(r["prod"]))
    r["dev"] = sorted(set(r["dev"]))
    return r


def parse_manifest(rel, text):
    name = posixpath.basename(rel)
    low = name.lower()
    try:
        if low == "package.json":
            return _package_json(rel, text)
        if re.match(r"^requirements.*\.txt$", low):
            return _requirements(rel, text)
        if low == "pyproject.toml":
            return _pyproject(rel, text)
        if low == "setup.py":
            return _setup_py(rel, text)
        if low == "pipfile":
            return _pipfile(rel, text)
        if low == "go.mod":
            return _go_mod(rel, text)
        if low == "cargo.toml":
            return _cargo(rel, text)
        if low == "pom.xml":
            return _pom(rel, text)
        if low in ("build.gradle", "build.gradle.kts"):
            return _gradle(rel, text)
        if low.endswith(".csproj"):
            return _csproj(rel, text)
        if low == "composer.json":
            return _composer(rel, text)
        if low == "gemfile":
            return _gemfile(rel, text)
        if low == "cmakelists.txt":
            return _cmake(rel, text)
    except Exception as exc:  # a malformed manifest must never crash analysis
        return _result(rel, "unknown", extra={"parse_error": str(exc)[:200]})
    return None


# --------------------------------------------------------------------------

def _package_json(rel, text):
    d = json.loads(text)
    if not isinstance(d, dict):
        return None
    prod = list((d.get("dependencies") or {}).keys()) + list((d.get("peerDependencies") or {}).keys()) \
        + list((d.get("optionalDependencies") or {}).keys())
    dev = list((d.get("devDependencies") or {}).keys())
    base = posixpath.dirname(rel)
    entry = []
    for key in ("main", "module"):
        if isinstance(d.get(key), str):
            entry.append((posixpath.normpath(posixpath.join(base, d[key])), "package.json %s" % key))
    b = d.get("bin")
    if isinstance(b, str):
        entry.append((posixpath.normpath(posixpath.join(base, b)), "package.json bin"))
    elif isinstance(b, dict):
        for v in b.values():
            if isinstance(v, str):
                entry.append((posixpath.normpath(posixpath.join(base, v)), "package.json bin"))
    scripts = d.get("scripts") if isinstance(d.get("scripts"), dict) else {}
    # Scripts that *run* the program (start, dev, dev:api, serve, watch ...). Test, lint and build
    # scripts are skipped: the files they name are tools or test runners, not application entry points.
    for key, cmd in scripts.items():
        if isinstance(cmd, str) and re.match(r"(start|dev|serve|watch)\b", key):
            for tok in re.findall(r"[\w./-]+\.(?:js|ts|mjs|cjs|tsx)\b", cmd):
                entry.append((posixpath.normpath(posixpath.join(base, tok)), "package.json script '%s'" % key))
    ws = d.get("workspaces")
    if isinstance(ws, dict):
        ws = ws.get("packages")
    return _result(rel, "javascript", name=d.get("name"), prod=prod, dev=dev,
                   scripts={k: v for k, v in scripts.items() if isinstance(v, str)}, entry=entry,
                   extra={"workspaces": ws if isinstance(ws, list) else [],
                          "type": d.get("type"), "private": d.get("private")})


def _requirements(rel, text):
    prod = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http")):
            continue
        n = _pep508_name(line)
        if n:
            prod.append(n)
    dev = rel.lower().find("dev") >= 0 or rel.lower().find("test") >= 0
    return _result(rel, "python", prod=[] if dev else prod, dev=prod if dev else [])


def _pyproject(rel, text):
    d = _toml_loads(text)
    prod, dev, scripts, entry, name = [], [], {}, [], None
    base = posixpath.dirname(rel)
    if d is not None:
        proj = d.get("project") or {}
        name = proj.get("name")
        prod += [n for n in (_pep508_name(s) for s in proj.get("dependencies", []) if isinstance(s, str)) if n]
        for grp, items in (proj.get("optional-dependencies") or {}).items():
            names = [n for n in (_pep508_name(s) for s in items if isinstance(s, str)) if n]
            (dev if grp in ("dev", "test", "tests", "lint", "docs") else prod).extend(names)
        for name_, target in (proj.get("scripts") or {}).items():
            scripts[name_] = target
        poetry = (d.get("tool") or {}).get("poetry") or {}
        name = name or poetry.get("name")
        prod += [_norm_py(k) for k in (poetry.get("dependencies") or {}) if k.lower() != "python"]
        for grp in (poetry.get("group") or {}).values():
            dev += [_norm_py(k) for k in (grp.get("dependencies") or {})]
        dev += [_norm_py(k) for k in (poetry.get("dev-dependencies") or {})]
        for name_, target in (poetry.get("scripts") or {}).items():
            scripts[name_] = target
        for grp in (d.get("dependency-groups") or {}).values():
            dev += [n for n in (_pep508_name(s) for s in grp if isinstance(s, str)) if n]
    else:  # tiny fallback for Python < 3.11
        m = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.S | re.M)
        if m:
            prod += [n for n in (_pep508_name(s) for s in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))) if n]
        m = re.search(r"^\[project\.scripts\]\s*\n(.*?)(?=^\[|\Z)", text, re.S | re.M)
        if m:
            for k, v in re.findall(r"^(\S+)\s*=\s*['\"]([^'\"]+)['\"]", m.group(1), re.M):
                scripts[k] = v
    for sname, target in scripts.items():
        if isinstance(target, str) and ":" in target or isinstance(target, str) and "." in target:
            mod = target.split(":")[0].strip()
            entry.append((posixpath.join(base, mod.replace(".", "/")), "pyproject script '%s' -> %s" % (sname, target)))
    return _result(rel, "python", name=name, prod=prod, dev=dev,
                   scripts={k: str(v) for k, v in scripts.items()}, entry=entry,
                   extra={"toml_parsed": d is not None})


def _setup_py(rel, text):
    prod = []
    m = re.search(r"install_requires\s*=\s*\[(.*?)\]", text, re.S)
    if m:
        prod = [n for n in (_pep508_name(s) for s in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))) if n]
    entry = []
    for target in re.findall(r"['\"][\w.-]+\s*=\s*([\w.]+):\w+['\"]", text):
        entry.append((posixpath.join(posixpath.dirname(rel), target.replace(".", "/")), "setup.py console_scripts"))
    return _result(rel, "python", prod=prod, entry=entry)


def _pipfile(rel, text):
    d = _toml_loads(text) or {}
    return _result(rel, "python", prod=[_norm_py(k) for k in (d.get("packages") or {})],
                   dev=[_norm_py(k) for k in (d.get("dev-packages") or {})])


def _go_mod(rel, text):
    m = re.search(r"^module\s+(\S+)", text, re.M)
    reqs = []
    for block in re.findall(r"^require\s*\((.*?)\)", text, re.S | re.M):
        reqs += re.findall(r"^\s*(\S+)\s+v\S+", block, re.M)
    reqs += re.findall(r"^require\s+(\S+)\s+v\S+", text, re.M)
    return _result(rel, "go", name=m.group(1) if m else None, prod=reqs,
                   extra={"module": m.group(1) if m else None,
                          "go": (re.search(r"^go\s+(\S+)", text, re.M) or [None, None])[1]})


def _cargo(rel, text):
    d = _toml_loads(text)
    base = posixpath.dirname(rel)
    entry, prod, dev, name = [], [], [], None
    extra = {}
    if d is not None:
        pkg = d.get("package") or {}
        name = pkg.get("name")
        prod = [k.replace("-", "_") for k in (d.get("dependencies") or {})]
        dev = [k.replace("-", "_") for k in (d.get("dev-dependencies") or {})]
        for b in d.get("bin") or []:
            if isinstance(b, dict) and b.get("path"):
                entry.append((posixpath.normpath(posixpath.join(base, b["path"])), "Cargo.toml [[bin]]"))
        extra["workspace_members"] = (d.get("workspace") or {}).get("members", [])
    else:
        m = re.search(r"^\[dependencies\]\s*\n(.*?)(?=^\[|\Z)", text, re.S | re.M)
        if m:
            prod = [k.replace("-", "_") for k in re.findall(r"^([\w-]+)\s*=", m.group(1), re.M)]
        nm = re.search(r"^name\s*=\s*['\"]([^'\"]+)", text, re.M)
        name = nm.group(1) if nm else None
    entry.append((posixpath.join(base, "src/main.rs"), "Cargo default binary (if present)"))
    return _result(rel, "rust", name=name, prod=prod, dev=dev, entry=entry, extra=extra)


def _pom(rel, text):
    deps = re.findall(r"<dependency>\s*<groupId>\s*([^<\s]+)\s*</groupId>\s*<artifactId>\s*([^<\s]+)\s*</artifactId>"
                      r"(?:.*?<scope>\s*([^<\s]+)\s*</scope>)?", text, re.S)
    prod = ["%s:%s" % (g, a) for g, a, s in deps if s != "test"]
    dev = ["%s:%s" % (g, a) for g, a, s in deps if s == "test"]
    main = re.search(r"<mainClass>\s*([^<\s]+)\s*</mainClass>", text)
    return _result(rel, "java", prod=prod, dev=dev,
                   extra={"main_class": main.group(1) if main else None})


def _gradle(rel, text):
    prod, dev = [], []
    for conf, coord in re.findall(r"\b(implementation|api|compileOnly|runtimeOnly|testImplementation|"
                                  r"testRuntimeOnly|kapt|annotationProcessor)\s*\(?\s*['\"]([^'\"]+)['\"]", text):
        (dev if conf.startswith("test") else prod).append(coord.rsplit(":", 1)[0] if coord.count(":") >= 2 else coord)
    main = re.search(r"mainClass(?:Name)?\s*(?:=|.set\()\s*['\"]([^'\"]+)['\"]", text)
    return _result(rel, "java", prod=prod, dev=dev, extra={"main_class": main.group(1) if main else None})


def _csproj(rel, text):
    prod = re.findall(r"<PackageReference\s+Include=\"([^\"]+)\"", text)
    out = re.search(r"<OutputType>\s*(\w+)\s*</OutputType>", text)
    tf = re.search(r"<TargetFrameworks?>\s*([^<]+)</TargetFrameworks?>", text)
    return _result(rel, "csharp", prod=prod,
                   extra={"output_type": out.group(1) if out else None,
                          "target_framework": tf.group(1).strip() if tf else None})


def _composer(rel, text):
    d = json.loads(text)
    if not isinstance(d, dict):
        return None
    req = [k for k in (d.get("require") or {}) if k != "php" and not k.startswith("ext-")]
    dev = list((d.get("require-dev") or {}).keys())
    psr4 = {}
    for sect in ("autoload", "autoload-dev"):
        for prefix, path in ((d.get(sect) or {}).get("psr-4") or {}).items():
            psr4[prefix] = path if isinstance(path, list) else [path]
    return _result(rel, "php", name=d.get("name"), prod=req, dev=dev, extra={"psr4": psr4})


def _gemfile(rel, text):
    prod, dev, in_dev = [], [], False
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"group\s+.*:(development|test)", s):
            in_dev = True
        elif s == "end":
            in_dev = False
        m = re.match(r"gem\s+['\"]([^'\"]+)['\"]", s)
        if m:
            (dev if in_dev or ":development" in s or ":test" in s else prod).append(m.group(1))
    return _result(rel, "ruby", prod=prod, dev=dev)


def _cmake(rel, text):
    """Literal-only CMake extraction. Variables are not expanded."""
    base = posixpath.dirname(rel)
    t = re.sub(r"#[^\n]*", "", text)
    targets, include_dirs, packages, subdirs = [], [], [], []

    def args(blob):
        return [a.strip("\"'") for a in re.findall(r"\"[^\"]*\"|\S+", blob) if a not in ("(", ")")]

    for kind, blob in re.findall(r"\badd_(executable|library)\s*\(([^)]*)\)", t, re.I):
        a = args(blob)
        if not a:
            continue
        skip = {"STATIC", "SHARED", "MODULE", "OBJECT", "INTERFACE", "EXCLUDE_FROM_ALL", "WIN32", "IMPORTED", "ALIAS"}
        srcs = [x for x in a[1:] if x not in skip and not x.startswith("$")]
        targets.append({"name": a[0], "type": kind.lower(), "sources": [posixpath.normpath(posixpath.join(base, s)) for s in srcs],
                        "unexpanded_variables": any("$" in x for x in a[1:]), "links": [], "defined_in": rel})
    by_name = {t_["name"]: t_ for t_ in targets}
    for blob in re.findall(r"\btarget_link_libraries\s*\(([^)]*)\)", t, re.I):
        a = args(blob)
        if a and a[0] in by_name:
            by_name[a[0]]["links"] += [x for x in a[1:] if x not in ("PUBLIC", "PRIVATE", "INTERFACE") and not x.startswith("$")]
    for blob in re.findall(r"\b(?:target_)?include_directories\s*\(([^)]*)\)", t, re.I):
        for x in args(blob):
            if x.upper() in ("PUBLIC", "PRIVATE", "INTERFACE", "SYSTEM", "BEFORE", "AFTER") or x in by_name:
                continue
            x = x.replace("${CMAKE_CURRENT_SOURCE_DIR}", ".").replace("${PROJECT_SOURCE_DIR}", ".") \
                .replace("${CMAKE_SOURCE_DIR}", ".")
            if "$" not in x:
                include_dirs.append(posixpath.normpath(posixpath.join(base, x)))
    for blob in re.findall(r"\bfind_package\s*\(\s*([\w-]+)", t, re.I):
        packages.append(blob)
    for blob in re.findall(r"\badd_subdirectory\s*\(\s*([^\s)]+)", t, re.I):
        subdirs.append(posixpath.normpath(posixpath.join(base, blob.strip("\"'"))))
    proj = re.search(r"\bproject\s*\(\s*([\w-]+)", t, re.I)
    entry = [(s, "CMake add_executable(%s)" % tg["name"]) for tg in targets if tg["type"] == "executable" for s in tg["sources"][:1]]
    return _result(rel, "cmake", name=proj.group(1) if proj else None, prod=packages, entry=entry,
                   extra={"targets": targets, "include_dirs": sorted(set(include_dirs)),
                          "subdirectories": subdirs, "testing_enabled": bool(re.search(r"\benable_testing\s*\(|\badd_test\s*\(", t, re.I))})

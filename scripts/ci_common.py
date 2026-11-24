#!/usr/bin/env python3
"""Shared helpers for the codebase-intelligence scripts.

Standard library only. Everything here is read-only with respect to the
repository under analysis: files are opened for reading, never executed,
and files that commonly hold secrets are never opened at all.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

TOOL_VERSION = "1.0.0"
MODEL_VERSION = "1.0"
MAX_READ_BYTES = 1_000_000          # files larger than this are listed but not read
DEFAULT_MAX_FILES = 20000

# Directories that are build output, vendored code, caches or tool state.
# They are reported (so nothing is silently hidden) but not analysed.
DEFAULT_IGNORE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components", "vendor",
    "__pycache__", ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".cache", "dist", "build", "out", "target", "coverage",
    ".next", ".nuxt", ".gradle", ".idea", ".vscode", ".terraform",
    ".codebase-intelligence", "site-packages", ".eggs",
}
# Hidden directories that carry meaningful project configuration.
ALLOWED_HIDDEN_DIRS = {".github", ".circleci", ".gitlab", ".devcontainer", ".husky"}

LANG_BY_EXT = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala",
    ".c": "c", ".h": "c_header",
    ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".c++": "cpp",
    ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp", ".inl": "cpp",
    ".cs": "csharp", ".go": "go", ".rs": "rust", ".php": "php", ".rb": "ruby",
    ".swift": "swift", ".m": "objective-c", ".lua": "lua", ".ex": "elixir",
    ".exs": "elixir", ".erl": "erlang", ".hs": "haskell", ".clj": "clojure",
    ".dart": "dart", ".r": "r", ".jl": "julia", ".pl": "perl",
    ".sh": "shell", ".bash": "shell", ".ps1": "powershell",
    ".sql": "sql", ".html": "html", ".css": "css", ".scss": "css",
    ".vue": "vue", ".svelte": "svelte", ".proto": "protobuf",
    ".tf": "terraform", ".yml": "yaml", ".yaml": "yaml", ".json": "json",
    ".toml": "toml", ".md": "markdown", ".rst": "restructuredtext",
}
# Languages that count as "code" when summarising a repository.
CODE_LANGS = {
    "python", "javascript", "typescript", "java", "kotlin", "scala", "c", "c_header",
    "cpp", "csharp", "go", "rust", "php", "ruby", "swift", "objective-c", "lua",
    "elixir", "erlang", "haskell", "clojure", "dart", "r", "julia", "perl", "shell",
    "powershell", "sql", "vue", "svelte",
}

_SENSITIVE_NAMES = re.compile(
    r"^(\.env(\..+)?|\.npmrc|\.pypirc|\.netrc|\.git-credentials|credentials(\..+)?|"
    r"secrets?(\..+)?|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|.*\.(pem|key|p12|pfx|jks|keystore|kdbx|ovpn))$",
    re.IGNORECASE,
)
_SENSITIVE_OK_SUFFIX = (".example", ".sample", ".template", ".dist", ".defaults")


def is_sensitive(rel):
    """True for files that commonly contain secrets. They are never read."""
    name = rel.rsplit("/", 1)[-1]
    if name.lower().endswith(_SENSITIVE_OK_SUFFIX):
        return False
    return bool(_SENSITIVE_NAMES.match(name))


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def lang_of(rel):
    ext = os.path.splitext(rel)[1].lower()
    return LANG_BY_EXT.get(ext)


def dump_json(obj, path=None):
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if path in (None, "-"):
        sys.stdout.write(text)
    else:
        atomic_write(path, text)
    return text


def atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# git (read-only, hardened against hostile repository configuration)
# --------------------------------------------------------------------------

def _git(root, *args, timeout=30):
    if not shutil.which("git"):
        return None
    cmd = ["git", "-C", root, "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
           "-c", "protocol.ext.allow=never"] + list(args)
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def git_available(root):
    out = _git(root, "rev-parse", "--is-inside-work-tree")
    return bool(out and out.strip() == b"true")


def repo_identity(root, files=None, use_git=True):
    """Identity used to decide whether a saved model belongs to this repository."""
    root = os.path.abspath(root)
    ident = {"name": os.path.basename(root.rstrip(os.sep)) or root, "kind": "path"}
    if use_git and git_available(root):
        roots = _git(root, "rev-list", "--max-parents=0", "HEAD")
        head = _git(root, "rev-parse", "HEAD")
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if roots:
            ident["kind"] = "git"
            ident["root_commits"] = sorted(roots.decode().split())
        if head:
            ident["head"] = head.decode().strip()
        if branch:
            ident["branch"] = branch.decode().strip()
    return ident


# --------------------------------------------------------------------------
# File listing and reading
# --------------------------------------------------------------------------

def list_repo_files(root, use_git=True, include_dirs=(), max_files=DEFAULT_MAX_FILES):
    """Return (sorted relative posix paths, meta). Never follows symlinks."""
    root = os.path.abspath(root)
    ignore = set(DEFAULT_IGNORE_DIRS) - set(include_dirs)
    meta = {"source": "walk", "ignored_dirs_seen": {}, "symlinks_skipped": 0, "truncated": False}
    raw = []
    out = _git(root, "ls-files", "-co", "--exclude-standard", "-z") if use_git and git_available(root) else None
    if out is not None:
        meta["source"] = "git"
        raw = [p for p in out.decode("utf-8", "replace").split("\0") if p]
    else:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            rel_dir = os.path.relpath(dirpath, root).replace(os.sep, "/")
            keep = []
            for d in sorted(dirnames):
                full = os.path.join(dirpath, d)
                if os.path.islink(full):
                    meta["symlinks_skipped"] += 1
                    continue
                if d in ignore:
                    meta["ignored_dirs_seen"][d] = meta["ignored_dirs_seen"].get(d, 0) + 1
                    continue
                if d.startswith(".") and d not in ALLOWED_HIDDEN_DIRS and d not in include_dirs:
                    meta["ignored_dirs_seen"][d] = meta["ignored_dirs_seen"].get(d, 0) + 1
                    continue
                keep.append(d)
            dirnames[:] = keep
            for fn in sorted(filenames):
                raw.append(fn if rel_dir == "." else rel_dir + "/" + fn)
    files = []
    real_root = os.path.realpath(root)
    for rel in raw:
        parts = rel.split("/")
        hit = next((p for p in parts[:-1] if p in ignore), None)
        if hit:
            meta["ignored_dirs_seen"][hit] = meta["ignored_dirs_seen"].get(hit, 0) + 1
            continue
        full = os.path.join(root, rel)
        if os.path.islink(full):
            meta["symlinks_skipped"] += 1
            continue
        if not os.path.isfile(full):
            continue
        if not os.path.realpath(full).startswith(real_root + os.sep):
            continue
        files.append(rel)
    files = sorted(set(files))
    if len(files) > max_files:
        files = files[:max_files]
        meta["truncated"] = True
    return files, meta


def read_text_ex(root, rel, max_bytes=MAX_READ_BYTES):
    """Return (text, skip_reason). Exactly one of them is None."""
    if is_sensitive(rel):
        return None, "sensitive_not_read"
    path = os.path.join(root, rel)
    try:
        if os.path.getsize(path) > max_bytes:
            return None, "too_large"
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None, "unreadable"
    if b"\0" in data[:8192]:
        return None, "binary"
    return data.decode("utf-8", errors="replace"), None


def read_text(root, rel, max_bytes=MAX_READ_BYTES):
    return read_text_ex(root, rel, max_bytes)[0]


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "integration_tests"}
_TEST_NAME = re.compile(
    r"(^test_.*\.py$|.*_test\.(py|go|cpp|cc|c|rs|rb)$|.*\.(test|spec)\.[jt]sx?$|"
    r".*Tests?\.(java|cs|kt)$|.*_spec\.rb$|.*Test\.php$)"
)
_GENERATED = re.compile(r"(_pb2(_grpc)?\.py$|\.pb\.go$|\.generated\.|\.min\.(js|css)$|\.d\.ts$|\.g\.cs$)")
_DOC_EXT = (".md", ".rst", ".txt", ".adoc")
_CONFIG_NAMES = {
    "package.json", "tsconfig.json", "pyproject.toml", "setup.py", "setup.cfg", "cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "cmakelists.txt", "makefile",
    "dockerfile", "docker-compose.yml", "docker-compose.yaml", "composer.json", "gemfile",
}


def classify_file(rel):
    parts = rel.split("/")
    name = parts[-1]
    low = name.lower()
    if _GENERATED.search(name) or any(p in ("generated", "__generated__") for p in parts[:-1]):
        return "generated"
    if any(p in _TEST_DIRS for p in parts[:-1]) or _TEST_NAME.match(name):
        return "test"
    if low in _CONFIG_NAMES or low.endswith((".csproj", ".sln", ".cmake")):
        return "build"
    if low.endswith(_DOC_EXT) or parts[0].lower() in ("docs", "doc"):
        return "docs"
    lang = lang_of(rel)
    if lang in CODE_LANGS or lang in ("html", "css"):
        return "source"
    if lang in ("json", "yaml", "toml") or low.startswith("."):
        return "config"
    return "other"


# --------------------------------------------------------------------------
# Entry-point detection from file text (shared by inventory and analyser)
# --------------------------------------------------------------------------

_ENTRY_RES = {
    "python": [(re.compile(r"""^if\s+__name__\s*==\s*['"]__main__['"]""", re.M), "__main__ guard")],
    "java": [(re.compile(r"public\s+static\s+void\s+main\s*\(\s*(final\s+)?String"), "static main method")],
    "kotlin": [(re.compile(r"^\s*fun\s+main\s*\(", re.M), "main function")],
    "c": [(re.compile(r"^\s*(int|void)\s+main\s*\(", re.M), "main function")],
    "cpp": [(re.compile(r"^\s*(int|auto)\s+(w?main)\s*\(", re.M), "main function")],
    "csharp": [(re.compile(r"static\s+(async\s+)?(void|int|Task(<int>)?)\s+Main\s*\("), "Main method")],
    "go": [(re.compile(r"^func\s+main\s*\(\s*\)", re.M), "func main (package main)")],
    "rust": [(re.compile(r"^\s*(pub\s+)?(async\s+)?fn\s+main\s*\(", re.M), "fn main")],
    "javascript": [(re.compile(r"^#!.*\bnode\b"), "node shebang")],
    "typescript": [(re.compile(r"^#!.*\b(node|ts-node|tsx|deno|bun)\b"), "script shebang")],
}


def entry_from_text(rel, lang, text):
    """Entry points visible in the file text. Returns list of (kind, reason)."""
    hits = []
    for rx, reason in _ENTRY_RES.get(lang, []):
        if rx.search(text):
            if lang == "go" and not re.search(r"^package\s+main\b", text, re.M):
                continue
            hits.append(("discovered", reason))
    return hits


_ENTRY_NAME_HINTS = {
    "index.php": "web root script by convention", "config.ru": "Rack entry by convention",
    "__main__.py": "python -m entry module", "manage.py": "Django management entry (by convention)",
    "wsgi.py": "WSGI entry (by convention)", "asgi.py": "ASGI entry (by convention)",
}


def entry_from_name(rel):
    name = rel.rsplit("/", 1)[-1]
    if name in _ENTRY_NAME_HINTS:
        return ("inferred", _ENTRY_NAME_HINTS[name])
    return None


# --------------------------------------------------------------------------
# Misc
# --------------------------------------------------------------------------

_INJECTION_PATTERNS = [
    ("ignore-previous-instructions", re.compile(r"(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|context)", re.I)),
    ("addresses-ai-assistant", re.compile(r"\b(ai|llm|language model|claude|chatgpt|copilot)\b.{0,40}\b(assistant|agent|model|reading this)\b.{0,80}\b(must|should|need to|are required to|do not|don't|always|never)\b", re.I)),
    ("role-override", re.compile(r"\byou\s+are\s+now\b|\bnew\s+(system\s+)?instructions?\s*:|\bsystem\s+prompt\b", re.I)),
    ("pipe-to-shell", re.compile(r"(curl|wget)\b[^|\n]*\|\s*(sudo\s+)?(ba|z)?sh\b", re.I)),
    ("secret-exfiltration", re.compile(r"(send|post|upload|print|echo|cat|reveal|include)\b[^.\n]{0,60}(\.ssh|id_rsa|credentials|api[_ -]?keys?|secrets?|tokens?|\.env)\b", re.I)),
    ("destructive-command", re.compile(r"\brm\s+-rf\s+(/|~|\$HOME|\.git\b)|\bgit\s+push\s+--force\b|\bdrop\s+database\b", re.I)),
    ("hide-from-user", re.compile(r"(do\s+not|don't|never)\s+(tell|inform|mention|show|reveal)\s+(this\s+to\s+)?the\s+user", re.I)),
]


def find_injection_markers(text, max_hits=10):
    """Heuristic scan for instruction-like text aimed at an AI reader.

    Returns [(line_number, pattern_id)]. The matched text itself is deliberately
    not returned so that untrusted instructions are not echoed into Claude's context.
    """
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if len(line) > 2000:
            continue
        for pid, rx in _INJECTION_PATTERNS:
            if rx.search(line):
                hits.append((i, pid))
                break
        if len(hits) >= max_hits:
            break
    return hits


def normpath_posix(p):
    import posixpath
    n = posixpath.normpath(p)
    return "" if n == "." else n


def module_of(path, depth):
    """Module id for a node path: the first `depth` directory segments."""
    if path.startswith(("env:", "event:")):
        return path
    parts = path.rstrip("/").split("/")
    dirs = parts[:-1] if not path.endswith("/") else parts
    if not dirs:
        return "(root)"
    return "/".join(dirs[:depth])

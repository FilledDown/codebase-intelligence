#!/usr/bin/env python3
"""Fingerprint files and diff them against a saved analysis manifest (incremental analysis).

Usage:
  file_fingerprints.py snapshot <repo> [--out fingerprints.json] [--no-git] [--include-dir NAME]
  file_fingerprints.py diff <repo> --manifest .codebase-intelligence/manifest.json [--model deps.json]
                            [--max-age-days N] [--no-git] [--out diff.json]
  file_fingerprints.py save <repo> --dir .codebase-intelligence [--model deps.json] [--force]
                            [--coverage-note TEXT ...]

`diff` answers: does this saved model belong to this repository, and which files were
added, modified or deleted since it was made? When --model (the dependency graph saved
with the manifest) is given, it also computes which files are *affected* by the changes:
the changed files plus everything that depends on them, transitively. Those are the
files whose conclusions must be re-checked. Nothing outside the changed set is trusted
to be current merely because its own content is unchanged.

`save` writes manifest.json (and nothing else) into the given directory, refusing to
touch a directory that git tracks unless --force is given. Persistence is always opt-in.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ci_common as cc  # noqa: E402
import graph_utils as gu  # noqa: E402

MANIFEST_NAME = "manifest.json"


def snapshot(root, use_git=True, include_dirs=(), max_files=cc.DEFAULT_MAX_FILES):
    root = os.path.abspath(root)
    files, meta = cc.list_repo_files(root, use_git, include_dirs, max_files)
    fp = {}
    for rel in files:
        if cc.is_sensitive(rel):
            continue          # presence is not recorded either: a fingerprint of a secret leaks information
        full = os.path.join(root, rel)
        try:
            st = os.stat(full)
            if st.st_size > 50_000_000:
                fp[rel] = {"size": st.st_size, "sha256": None}
            else:
                fp[rel] = {"size": st.st_size, "sha256": cc.sha256_file(full)}
        except OSError:
            continue
    return {"files": fp, "meta": meta}


def _identity_match(saved, current):
    """Return (verdict, reason). verdict in same | different | uncertain."""
    if not saved or not current:
        return "uncertain", "identity missing from manifest"
    if saved.get("kind") == "git" and current.get("kind") == "git":
        s, c = set(saved.get("root_commits", [])), set(current.get("root_commits", []))
        if s and c:
            return ("same", "shared root commit") if s & c else ("different", "git root commits differ: not the same repository history")
    if saved.get("name") != current.get("name"):
        return "uncertain", "directory name differs (%s vs %s) and git identity is unavailable" % (saved.get("name"), current.get("name"))
    return "uncertain", "matched by directory name only (no git identity)"


def diff(root, manifest_path, model_path=None, use_git=True, include_dirs=(), max_age_days=None):
    root = os.path.abspath(root)
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except FileNotFoundError:
        return {"status": "no-saved-model", "advice": "Run a full analysis. Nothing to compare against."}
    except (OSError, ValueError) as exc:
        return {"status": "unreadable-manifest", "error": str(exc)[:200], "advice": "Treat as no saved model; run a full analysis."}

    current_ident = cc.repo_identity(root, None, use_git)
    verdict, why = _identity_match(manifest.get("repository"), current_ident)
    out = {"status": "ok", "identity": {"verdict": verdict, "reason": why}, "warnings": []}
    if verdict == "different":
        out["status"] = "different-repository"
        out["advice"] = "The saved model belongs to another repository. Do not reuse it."
        return out
    if verdict == "uncertain":
        out["warnings"].append("Identity unverified (%s). Reuse only after confirming with the user." % why)

    problems = []
    if manifest.get("model_version") != cc.MODEL_VERSION:
        problems.append("model_version %s != current %s" % (manifest.get("model_version"), cc.MODEL_VERSION))
    cur_an = cc_analyzer_versions()
    for name, ver in (manifest.get("analyzer_versions") or {}).items():
        if name in cur_an and cur_an[name] != ver:
            problems.append("analyzer %s %s != current %s" % (name, ver, cur_an[name]))
    if problems:
        out["status"] = "stale-tooling"
        out["warnings"].append("Saved with different tooling (%s). Fingerprints are still comparable, but relationships "
                               "extracted by older analyzers should be regenerated." % "; ".join(problems))
    ts = manifest.get("analyzed_at")
    if max_age_days is not None and ts:
        try:
            age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(ts)).days
            out["age_days"] = age
            if age > max_age_days:
                out["warnings"].append("Saved model is %d days old (limit %d)." % (age, max_age_days))
        except ValueError:
            out["warnings"].append("analyzed_at is not a valid timestamp.")

    old = manifest.get("fingerprints") or {}
    now_snap = snapshot(root, use_git, include_dirs)
    new = now_snap["files"]
    added = sorted(set(new) - set(old))
    deleted = sorted(set(old) - set(new))
    modified = sorted(p for p in set(new) & set(old) if new[p]["sha256"] != old[p].get("sha256")
                      or new[p]["size"] != old[p].get("size"))
    out["changes"] = {"added": added, "modified": modified, "deleted": deleted,
                      "unchanged": len(set(new) & set(old)) - len(modified)}
    if (manifest.get("coverage") or {}).get("truncated") or now_snap["meta"]["truncated"]:
        out["warnings"].append("Listing was truncated at least once; some files are not fingerprinted.")

    changed = set(added) | set(modified) | set(deleted)
    out["affected"] = {"note": "Changed files plus every file that depends on them. Re-verify conclusions that cite these.",
                       "files": [], "by_distance": {}}
    if not changed:
        out["advice"] = "No file changes since the saved model. Conclusions are still only as good as the original analysis."
        return out

    model = None
    if model_path and os.path.exists(model_path):
        try:
            with open(model_path, "r", encoding="utf-8") as f:
                model = json.load(f)
        except (OSError, ValueError):
            out["warnings"].append("Could not read saved dependency model; affected set limited to changed files.")
    config_changed = sorted(p for p in changed if os.path.basename(p) in (
        "package.json", "pyproject.toml", "setup.py", "go.mod", "Cargo.toml", "pom.xml", "CMakeLists.txt", "tsconfig.json",
        "composer.json", "Gemfile") or os.path.basename(p).startswith("requirements") or p.endswith(".csproj"))
    if config_changed:
        out["warnings"].append("Build/manifest files changed (%s): module resolution, dependencies and entry points may "
                               "differ across the whole repository. Prefer a full re-analysis." % ", ".join(config_changed[:5]))
        out["recommend_full_reanalysis"] = True
    if model:
        reach = gu.reverse_reach(gu.coupling_edges(model.get("edges", [])), sorted(changed))
        dist = {}
        for p in changed:
            dist[p] = 0
        for n, info in reach.items():
            dist[n] = info["depth"]
        out["affected"]["files"] = sorted(dist)
        by = {}
        for p, d in dist.items():
            by.setdefault(str(d), []).append(p)
        out["affected"]["by_distance"] = {k: sorted(v) for k, v in sorted(by.items())}
        out["affected"]["basis"] = "saved dependency graph; dependents of *added* files are unknown to it"
        if added:
            out["warnings"].append("%d new file(s) are not in the saved graph; their relationships are unknown until analysed." % len(added))
    else:
        out["affected"]["files"] = sorted(changed)
        out["affected"]["basis"] = "changed files only (no dependency model supplied)"
    n_total = max(len(new), 1)
    if len(changed) / n_total > 0.3:
        out["recommend_full_reanalysis"] = True
        out["warnings"].append("More than 30%% of files changed (%d of %d). A full re-analysis is cheaper than patching." % (len(changed), n_total))
    out["advice"] = ("Re-analyse the affected files, update the model, and mark any saved conclusion that cites an affected "
                     "file as OUTDATED until re-verified.")
    return out


def cc_analyzer_versions():
    try:
        from analyzers import builtin_analyzers
        return {a.name: a.version for a in builtin_analyzers()}
    except Exception:
        return {}


def is_tracked_by_git(root, path):
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(root))
    if rel.startswith(".."):
        return False
    out = cc._git(root, "ls-files", "--", rel)
    return bool(out and out.strip())


def save(root, out_dir, model_path=None, force=False, use_git=True, include_dirs=(), notes=()):
    root = os.path.abspath(root)
    out_dir = os.path.abspath(out_dir)
    if os.path.isdir(out_dir) and is_tracked_by_git(root, out_dir) and not force:
        sys.exit("refusing: %s contains git-tracked files. Persistence must not modify tracked project files. "
                 "Pass --force only if the user explicitly asked for it." % out_dir)
    snap = snapshot(root, use_git, include_dirs)
    model = {}
    if model_path:
        with open(model_path, "r", encoding="utf-8") as f:
            model = json.load(f)
    cov = model.get("coverage", {})
    manifest = {
        "model_version": cc.MODEL_VERSION, "tool_version": cc.TOOL_VERSION, "analyzed_at": cc.now_iso(),
        "repository": cc.repo_identity(root, None, use_git),
        "analyzer_versions": {k: v["version"] for k, v in (model.get("analyzers") or {}).items()} or cc_analyzer_versions(),
        "fingerprints": snap["files"],
        "coverage": {"files_listed": cov.get("files_listed", len(snap["files"])), "files_analyzed": cov.get("files_analyzed"),
                     "truncated": snap["meta"]["truncated"], "by_language": cov.get("by_language", {}),
                     "notes": list(notes)},
        "known_limitations": model.get("limitations", []),
        "artifacts": sorted(f for f in (os.listdir(out_dir) if os.path.isdir(out_dir) else []) if f != MANIFEST_NAME),
    }
    path = os.path.join(out_dir, MANIFEST_NAME)
    cc.dump_json(manifest, path)
    gi = os.path.join(out_dir, ".gitignore")
    if not os.path.exists(gi):
        cc.atomic_write(gi, "# Generated by codebase-intelligence. Remove this file to commit the model.\n*\n")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("repo")
    s.add_argument("--out", default="-")
    s.add_argument("--no-git", action="store_true")
    s.add_argument("--include-dir", action="append", default=[])
    d = sub.add_parser("diff")
    d.add_argument("repo")
    d.add_argument("--manifest", required=True)
    d.add_argument("--model")
    d.add_argument("--max-age-days", type=int)
    d.add_argument("--no-git", action="store_true")
    d.add_argument("--include-dir", action="append", default=[])
    d.add_argument("--out", default="-")
    v = sub.add_parser("save")
    v.add_argument("repo")
    v.add_argument("--dir", required=True)
    v.add_argument("--model")
    v.add_argument("--force", action="store_true")
    v.add_argument("--no-git", action="store_true")
    v.add_argument("--include-dir", action="append", default=[])
    v.add_argument("--coverage-note", action="append", default=[])
    args = ap.parse_args(argv)
    if not os.path.isdir(args.repo):
        sys.exit("error: not a directory: %s" % args.repo)
    if args.cmd == "snapshot":
        cc.dump_json(snapshot(args.repo, not args.no_git, args.include_dir)["files"], args.out)
    elif args.cmd == "diff":
        res = diff(args.repo, args.manifest, args.model, not args.no_git, args.include_dir, args.max_age_days)
        cc.dump_json(res, args.out)
    else:
        print(save(args.repo, args.dir, args.model, args.force, not args.no_git, args.include_dir, args.coverage_note))


if __name__ == "__main__":
    main()

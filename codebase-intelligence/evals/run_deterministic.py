#!/usr/bin/env python3
"""Run the deterministic checks declared in evals/evals.json against real script output.

Usage:
  python evals/run_deterministic.py [--scenario ID_OR_NAME ...] [--json]

For each scenario this copies the fixture into a temporary directory (so nothing in the
repository is modified), runs the skill's scripts on the copy, and evaluates every entry in
`deterministic_checks`. Exit status is 0 when every check passes, 1 otherwise.

What this does and does not test: it tests that the *scripts* surface the facts a scenario
plants (entry points, edges, cycles, hidden channels, coverage gaps, safety properties). It does
not test whether Claude, using those facts, writes a correct analysis; that needs a Claude
runtime and is scored from `scoring.criteria` in evals.json.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SCRIPTS = os.path.join(SKILL, "scripts")
PY = sys.executable


def run(args, env=None, cwd=None):
    r = subprocess.run([PY, "-I"] + args, capture_output=True, text=True, env=env, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


def script(name):
    return os.path.join(SCRIPTS, name)


class Scenario:
    """A prepared scenario: temp copy of the fixture plus lazily computed script outputs."""

    def __init__(self, spec, tmp):
        self.spec = spec
        self.tmp = tmp
        self.repo = os.path.join(tmp, "repo")
        self.setup = spec["setup"]
        self._cache = {}
        self._build()

    def _build(self):
        base = self.setup.get("base_scenario")
        src = os.path.join(SKILL, "evals", "test-scenarios", base or self.spec["eval_name"], "repo")
        shutil.copytree(src, self.repo)
        for old, new in self.setup.get("rename", {}).items():
            os.rename(os.path.join(self.repo, old), os.path.join(self.repo, new))
        if self.setup.get("mutations"):
            persist = os.path.join(self.repo, ".codebase-intelligence")
            os.makedirs(persist)
            model_path = os.path.join(persist, "dependencies.json")
            rc, _, err = run([script("dependency_analyzer.py"), "analyze", self.repo, "--no-git", "--out", model_path])
            assert rc == 0, err
            rc, _, err = run([script("file_fingerprints.py"), "save", self.repo, "--dir", persist,
                              "--model", model_path, "--no-git"])
            assert rc == 0, err
            for m in self.setup["mutations"]:
                full = os.path.join(self.repo, m["path"])
                if m["op"] == "append":
                    with open(full, "a") as f:
                        f.write(m["text"])
                elif m["op"] == "delete":
                    os.remove(full)
                elif m["op"] == "write":
                    with open(full, "w") as f:
                        f.write(m["text"])

    # --- lazily computed outputs -------------------------------------------------
    def _json(self, key, args):
        if key not in self._cache:
            rc, out, err = run(args)
            if rc != 0:
                raise RuntimeError("%s failed (rc=%s): %s" % (args[0], rc, err.strip()[-300:]))
            self._cache[key] = (out, json.loads(out))
        return self._cache[key]

    def model_text(self):
        return self._json("model", [script("dependency_analyzer.py"), "analyze", self.repo, "--no-git"])[0]

    def model(self):
        return self._json("model", [script("dependency_analyzer.py"), "analyze", self.repo, "--no-git"])[1]

    def inventory_text(self):
        return self._json("inv", [script("repository_inventory.py"), self.repo, "--no-git"])[0]

    def inventory(self):
        return self._json("inv", [script("repository_inventory.py"), self.repo, "--no-git"])[1]

    def impact(self, seed):
        mp = os.path.join(self.tmp, "model.json")
        if not os.path.exists(mp):
            with open(mp, "w") as f:
                f.write(self.model_text())
        return self._json("impact:" + seed, [script("graph_exporter.py"), "impact", mp, "--seed", seed])[1]

    def locate(self, terms):
        args = [script("dependency_analyzer.py"), "locate", self.repo, "--no-git"]
        for t in terms:
            args += ["--term", t]
        return self._json("locate:" + ",".join(terms), args)[1]

    def diff(self):
        persist = os.path.join(self.repo, ".codebase-intelligence")
        return self._json("diff", [script("file_fingerprints.py"), "diff", self.repo, "--no-git",
                                   "--manifest", os.path.join(persist, "manifest.json"),
                                   "--model", os.path.join(persist, "dependencies.json")])[1]


def _edges(m):
    return [e for e in m["edges"] if e["kind"] != "package-member"]


# Each check returns (passed, detail).
def chk_entry_point(s, c):
    paths = {e["path"] for e in s.model()["entry_points"]} | {e["path"] for e in s.inventory()["entry_points"]}
    return c["path"] in paths, "entry points: %s" % sorted(paths)


def chk_edge(s, c):
    for e in _edges(s.model()):
        if e["source"] == c["source"] and e["target"] == c["target"] and \
                (not c.get("evidence") or e["evidence"] == c["evidence"]):
            return True, "found %s edge" % e["evidence"]
    return False, "no %s edge %s -> %s" % (c.get("evidence", "any"), c["source"], c["target"])


def chk_no_edge_between(s, c):
    bad = [(e["source"], e["target"]) for e in _edges(s.model())
           if e["source"].startswith(c["source_prefix"]) and e["target"].startswith(c["target_prefix"])]
    return not bad, "edges found: %s" % bad if bad else "none, as expected"


def chk_fan_in_top(s, c):
    top = s.model()["metrics"]["highest_fan_in"]
    return bool(top) and top[0]["path"] == c["path"], "top fan-in: %s" % top[:2]


def chk_no_cycles(s, c):
    cyc = s.model()["cycles"]
    return not cyc, "cycles: %s" % [x["files"] for x in cyc]


def chk_cycle(s, c):
    for x in s.model()["cycles"]:
        if set(c["files"]) <= set(x["files"]) and (not c.get("import_time") or x["import_time_cycle"]):
            return True, "cycle %s (import_time=%s)" % (x["files"], x["import_time_cycle"])
    return False, "no matching cycle among %s" % [x["files"] for x in s.model()["cycles"]]


def chk_external(s, c):
    pk = {e["package"] for e in s.model()["externals"]}
    return c["package"] in pk, "externals: %s" % sorted(pk)


def chk_no_external(s, c):
    pk = {e["package"] for e in s.model()["externals"]}
    return c["package"] not in pk, "externals: %s" % sorted(pk)


def chk_declared_not_imported(s, c):
    got = set()
    for d in s.model()["declared_vs_discovered"]:
        got |= set(d["declared_not_imported"])
    missing = [n for n in c["names"] if n not in got]
    return not missing, "missing from candidates: %s" % missing if missing else "all present"


def chk_inventory_declared_framework(s, c):
    fw = s.inventory()["frameworks_from_declared_dependencies"]
    return c["name"] in fw, "declared frameworks: %s" % sorted(fw)


def chk_implicit_channel(s, c):
    for ch in s.impact(c["seed"])["implicit_channels_from_seeds"]:
        if ch["key"] == c["key"]:
            others = {o["file"] for o in ch["also_touched_by"]}
            missing = [f for f in c["also_touched_by"] if f not in others]
            return not missing, "also touched by: %s%s" % (sorted(others), (" (missing %s)" % missing) if missing else "")
    return False, "channel %s not reported for seed %s" % (c["key"], c["seed"])


def chk_impact_dependents(s, c):
    res = s.impact(c["seed"])["dependents"]
    by = {r["path"]: r for r in res}
    problems = []
    for f in c["includes"]:
        if f not in by:
            problems.append("%s missing" % f)
        else:
            if c.get("evidence") and by[f]["evidence"] != c["evidence"]:
                problems.append("%s evidence=%s" % (f, by[f]["evidence"]))
            if c.get("max_depth") and by[f]["depth"] > c["max_depth"]:
                problems.append("%s depth=%s" % (f, by[f]["depth"]))
    return not problems, "; ".join(problems) or "dependents: %s" % sorted(by)


def chk_impact_excludes(s, c):
    by = {r["path"] for r in s.impact(c["seed"])["dependents"]}
    bad = [f for f in c["excludes"] if f in by]
    return not bad, ("unexpectedly reached: %s" % bad) if bad else "not reached statically, as expected (still needs a hidden-channel search)"


def chk_locate_finds(s, c):
    res = s.locate(c["terms"])
    found = {r["path"] for r in res.get("results", res.get("matches", []))} if isinstance(res, dict) else {r["path"] for r in res}
    missing = [f for f in c["files"] if f not in found]
    return not missing, "missing: %s" % missing if missing else "found %s" % sorted(found)


def chk_incremental_diff(s, c):
    d = s.diff()
    ch = d["changes"]
    problems = []
    for key, name in (("expect_added", "added"), ("expect_modified", "modified"), ("expect_deleted", "deleted")):
        if sorted(ch[name]) != sorted(c[key]):
            problems.append("%s=%s expected %s" % (name, ch[name], c[key]))
    aff = set(d["affected"]["files"])
    miss = [f for f in c["affected_includes"] if f not in aff]
    if miss:
        problems.append("affected missing %s" % miss)
    if d["identity"]["verdict"] != c["identity_verdict"]:
        problems.append("identity %s expected %s" % (d["identity"]["verdict"], c["identity_verdict"]))
    return not problems, "; ".join(problems) or "added/modified/deleted and affected set correct"


def chk_incremental_unchanged_min(s, c):
    n = s.diff()["changes"]["unchanged"]
    return n >= c["min"], "unchanged=%d" % n


def chk_no_hubs(s, c):
    h = s.model()["metrics"]["hubs"]
    return not h, "hubs: %s" % h


def chk_no_unresolved(s, c):
    u = s.model()["unresolved"]
    return not u, "unresolved: %s" % u


def chk_isolated_source_subset(s, c):
    iso = set(s.model()["metrics"]["isolated_source_files"])
    extra = sorted(iso - set(c["allowed"]))
    return not extra, ("unexpected isolated files: %s" % extra) if extra else "isolated: %s (allowed)" % sorted(iso)


def chk_coverage_all_code_analysed(s, c):
    sys.path.insert(0, SCRIPTS)
    import ci_common as cc
    bad = {k: v for k, v in s.model()["coverage"]["by_language"].items() if k in cc.CODE_LANGS and v["analyzed"] < v["files"]}
    return not bad, "unanalysed code languages: %s" % bad if bad else "all code files analysed"


def chk_coverage_analyzer_null(s, c):
    by = s.model()["coverage"]["by_language"]
    bad = [l for l in c["languages"] if l not in by or by[l]["analyzer"] is not None or by[l]["analyzed"]]
    return not bad, "not reported as unanalysed: %s" % bad if bad else "reported with analyzer=null"


def chk_coverage_skipped_min(s, c):
    n = s.model()["coverage"]["skipped"].get(c["reason"], 0)
    return n >= c["n"], "%s=%d" % (c["reason"], n)


def chk_runs_without_git(s, c):
    env = dict(os.environ, PATH=os.path.join(s.tmp, "no-such-dir"))
    problems = []
    for name, args in (("dependency_analyzer", [script("dependency_analyzer.py"), "analyze", s.repo]),
                       ("repository_inventory", [script("repository_inventory.py"), s.repo])):
        rc, out, err = run(args, env=env)
        if rc != 0:
            problems.append("%s rc=%s %s" % (name, rc, err.strip()[-120:]))
        elif name == "dependency_analyzer" and json.loads(out)["coverage"]["listing_source"] != "walk":
            problems.append("did not fall back to filesystem walk")
    return not problems, "; ".join(problems) or "both scripts ran with git unavailable and fell back to a filesystem walk"


def chk_limitations_mention(s, c):
    lim = " ".join(s.model()["limitations"])
    return c["text"] in lim, "limitations: %s" % lim[:120]


def chk_inventory_test_files(s, c):
    n = s.inventory()["test_infrastructure"]["test_files"]
    return n == c["count"], "test_files=%d" % n


def chk_build_target(s, c):
    names = [t.get("name") for t in s.model()["build_targets"]]
    return c["name"] in names, "targets: %s" % names


def chk_injection_markers(s, c):
    f = s.inventory()["possible_instructions_in_repo_content"]["findings"]
    files = {x["file"] for x in f}
    missing = [x for x in c["files"] if x not in files]
    return len(f) >= c["min"] and not missing, "%d marker(s) in %s%s" % (len(f), sorted(files), (" missing %s" % missing) if missing else "")


def chk_sensitive_not_read(s, c):
    return c["path"] in s.inventory()["sensitive_files_not_read"], "listed: %s" % s.inventory()["sensitive_files_not_read"]


def chk_output_lacks(s, c):
    blob = s.model_text() + s.inventory_text()
    leaked = [x for x in c["strings"] if x in blob]
    return not leaked, ("leaked into script output: %s" % leaked) if leaked else "absent from inventory and model output"


def chk_file_absent(s, c):
    s.model(); s.inventory()
    present = [p for p in c["paths"] if os.path.exists(os.path.join(s.repo, p))]
    return not present, ("repository code was executed: %s" % present) if present else "no sentinel files: nothing was executed"


def chk_deterministic(s, c):
    def strip(t):
        d = json.loads(t)
        d.pop("generated_at", None)
        return json.dumps(d, sort_keys=True)
    rc, out, _ = run([script("dependency_analyzer.py"), "analyze", s.repo, "--no-git"])
    return rc == 0 and strip(out) == strip(s.model_text()), "two runs produce identical output (excluding timestamp)"


CHECKS = {k[4:]: v for k, v in list(globals().items()) if k.startswith("chk_")}


def run_scenarios(specs, only=None):
    results = []
    for spec in specs:
        if only and not ({str(spec["id"]), spec["eval_name"]} & set(only)):
            continue
        with tempfile.TemporaryDirectory(prefix="ci-eval-") as tmp:
            s = Scenario(spec, tmp)
            for c in spec["deterministic_checks"]:
                fn = CHECKS.get(c["type"])
                if fn is None:
                    results.append({"scenario": spec["eval_name"], "id": c["id"], "type": c["type"], "passed": False,
                                    "detail": "unknown check type"})
                    continue
                try:
                    ok, detail = fn(s, c)
                except Exception as exc:  # a crashing check is a failing check, reported with its reason
                    ok, detail = False, "check raised %s: %s" % (type(exc).__name__, exc)
                results.append({"scenario": spec["eval_name"], "id": c["id"], "type": c["type"], "passed": bool(ok), "detail": detail})
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", action="append", help="scenario id (1-10) or name; repeatable")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    with open(os.path.join(HERE, "evals.json"), encoding="utf-8") as f:
        specs = json.load(f)["evals"]
    results = run_scenarios(specs, a.scenario)
    if a.json:
        json.dump(results, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        cur = None
        for r in results:
            if r["scenario"] != cur:
                cur = r["scenario"]
                print("\n%s" % cur)
            print("  [%s] %-34s %s" % ("PASS" if r["passed"] else "FAIL", r["id"], "" if r["passed"] else r["detail"]))
        n_ok = sum(r["passed"] for r in results)
        print("\n%d/%d deterministic checks passed" % (n_ok, len(results)))
    return 0 if results and all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Render evals/expected-behaviors/<scenario>.md from evals/evals.json.

evals.json is the source of truth; the Markdown is a readable view of it for reviewers.
tests/test_scripts.py fails if the rendered files are out of date.

Usage: python evals/render_expected_behaviors.py [--check]
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def render(e):
    s = e["setup"]
    L = ["# Scenario %02d: %s" % (e["id"], e["name"]), "",
         "_Generated from `evals/evals.json`. Edit that file, then run `python evals/render_expected_behaviors.py`._", "",
         "## Why this scenario exists", "", e["why_this_scenario"], "",
         "## Test setup", "",
         "- Fixture: `%s`" % s["fixture"]]
    if s.get("base_scenario"):
        L.append("- Built from the `%s` fixture. Steps: %s." % (s["base_scenario"], "; then ".join(s["steps"])))
    for m in s.get("mutations", []):
        L.append("- Mutation: `%s` `%s`" % (m["op"], m["path"]))
    for old, new in s.get("rename", {}).items():
        L.append("- The harness renames `%s` to `%s` in a temporary copy." % (old, new))
    if s.get("note"):
        L.append("- " + s["note"])
    L += ["- Run the fixture only from a scratch copy; never from the skill directory.", "",
          "## User prompt", "", "> " + e["prompt"], "",
          "## Expected behaviour", "", e["expected_output"], "",
          "## Scoring criteria", "",
          "Pass/fail per criterion against the response and transcript. Score = criteria passed / total. Metric tags show which quality each criterion measures.", "",
          "| # | Criterion | Metrics |", "|---|---|---|"]
    for c in e["scoring"]["criteria"]:
        L.append("| %s | %s | %s |" % (c["id"], c["text"].replace("|", "\\|"), ", ".join(c["metrics"])))
    L += ["", "## Failure conditions", "", "Any one of these makes the scenario a FAIL regardless of score.", ""]
    L += ["- " + f for f in e["failure_conditions"]]
    L += ["", "## Deterministic checks (run locally, no model needed)", "",
          "`python evals/run_deterministic.py --scenario %d`. These verify that the scripts surface the planted facts; they do not score Claude's answer." % e["id"], ""]
    L += ["- `%s` (%s)" % (c["id"], c["type"]) for c in e["deterministic_checks"]]
    L += ["", "## Requires a Claude runtime", "",
          "Scoring every criterion and failure condition above. No such run has been recorded in this repository.", ""]
    return "\n".join(L)


def main(argv):
    with open(os.path.join(HERE, "evals.json"), encoding="utf-8") as f:
        evals = json.load(f)["evals"]
    out_dir = os.path.join(HERE, "expected-behaviors")
    os.makedirs(out_dir, exist_ok=True)
    stale = []
    for e in evals:
        path = os.path.join(out_dir, e["eval_name"] + ".md")
        text = render(e)
        if "--check" in argv:
            if not os.path.exists(path) or open(path, encoding="utf-8").read() != text:
                stale.append(path)
        else:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
    if stale:
        print("out of date: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

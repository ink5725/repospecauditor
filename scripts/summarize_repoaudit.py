#!/usr/bin/env python3
"""Summarize RepoAudit dfbscan results for the 111 REAL_BUG benchmark.

Reads detect_info.json under RepoAudit/result/dfbscan/*/kernel-bugs/ and maps
detected functions back to our REAL_BUG list.
"""
from __future__ import annotations

import glob
import json
import os
import sys

REPOAUDIT_ROOT = "/home/ink/Spec/RepoAudit"
REALBUG_FILE = "data/outputs_100/stage3_review.json"


def main() -> None:
    # Load our REAL_BUG function list
    with open(REALBUG_FILE, encoding="utf-8") as f:
        review = json.load(f)
    real_funcs = sorted({r["function"] for r in review
                         if r.get("classification") == "REAL_BUG"})
    print(f"REAL_BUG functions: {len(real_funcs)}")

    # Find all detect_info.json for kernel-bugs
    pattern = os.path.join(REPOAUDIT_ROOT, "result", "dfbscan", "*", "*", "Cpp",
                           "kernel-bugs", "*", "detect_info.json")
    files = sorted(glob.glob(pattern))
    if not files:
        print("No detect_info.json found yet (scan still running?)")
        return

    matched: dict[str, list[str]] = {}
    for fp in files:
        parts = fp.split("/")
        model = parts[parts.index("dfbscan") + 1]
        bug_type = parts[parts.index("dfbscan") + 2]
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"skip {fp}: {e}")
            continue
        n = len(data)
        print(f"[{model}/{bug_type}] {n} report(s) in {fp.split('/')[-2]}")
        if n == 0:
            continue
        # Map detected functions to our REAL_BUG list
        for rep_id, rep in data.items():
            rel = rep.get("relevant_functions", [])
            if not rel or len(rel) < 2:
                continue
            names = rel[1] if isinstance(rel[1], list) else [rel[1]]
            for name in names:
                if name in real_funcs:
                    matched.setdefault(name, []).append(
                        f"{bug_type}:{rep_id}")

    print(f"\n=== Matched REAL_BUG functions: {len(matched)} ===")
    for name, hits in sorted(matched.items()):
        print(f"  {name}: {hits}")


if __name__ == "__main__":
    main()

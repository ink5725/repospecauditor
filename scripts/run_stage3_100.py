#!/usr/bin/env python3
"""Stage 3 bug detection with resume support (for the 100-seed run).

Resumes from the last completed specification index stored in a state file.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sa import config as cfg  # noqa: E402
from sa.code_index import CodeIndex  # noqa: E402
from sa.llm_client import LLMClient  # noqa: E402
from sa.stage3 import Stage3  # noqa: E402

OUT_DIR = "data/outputs_100"
STATE_FILE = os.path.join(OUT_DIR, "stage3_state.json")
REPORTS_FILE = os.path.join(OUT_DIR, "stage3_reports.json")
MAX_PER_SPEC = 20


def main():
    cfg.load_env_file("config/llm.env")
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(os.path.join(OUT_DIR, "stage1_out.json"), encoding="utf-8") as f:
        s1 = json.load(f)
    with open(os.path.join(OUT_DIR, "stage2_out.json"), encoding="utf-8") as f:
        s2 = json.load(f)

    specs = []
    for r in s1:
        if r.get("validation", {}).get("valid"):
            specs.append({
                "entity": r["entity"], "constraint": r["constraint"],
                "kind": "seed", "seed_hexsha": r["hexsha"],
            })
    for r in s2:
        cs = r["concretized_specification"]
        specs.append({
            "entity": cs["entity"], "constraint": cs["constraint"],
            "kind": "generated", "seed_hexsha": r["seed_hexsha"],
            "candidate": r["candidate"],
        })

    # resume state
    start = 0
    reports = []
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        start = state.get("next_index", 0)
        if os.path.exists(REPORTS_FILE):
            with open(REPORTS_FILE, encoding="utf-8") as f:
                reports = json.load(f)
        print(f"[stage3-resume] resuming from spec {start}, "
              f"{len(reports)} reports loaded", flush=True)

    llm = LLMClient()
    idx = CodeIndex("/home/ink/Spec/linux-6.17-rc3", db_path="data/code_index.sqlite")
    s3 = Stage3(llm, idx)

    total = len(specs)
    print(f"[stage3] total specs: {total}", flush=True)
    for i in range(start, total):
        spec = specs[i]
        if i % 5 == 0:
            print(f"[stage3] [{i}/{total}] specs, {len(reports)} reports",
                  flush=True)
        try:
            query = s3.generate_query(spec["entity"])
            candidates = s3.localize(query)
            for fn in candidates[:MAX_PER_SPEC]:
                try:
                    check = s3.check_violation(spec, fn)
                except Exception:
                    continue
                if check.get("decision") != "yes":
                    continue
                report = {
                    "spec_kind": spec["kind"], "spec_entity": spec["entity"],
                    "spec_constraint": spec["constraint"],
                    "seed_hexsha": spec.get("seed_hexsha"),
                    "candidate": spec.get("candidate"),
                    "function": fn,
                    "initial_explanation": check.get("explanation", ""),
                }
                try:
                    pruned = s3.prune_report(spec, fn)
                    report["pruned_decision"] = pruned.get("decision")
                    report["pruned_explanation"] = pruned.get("explanation", "")
                except Exception as e:
                    report["pruned_decision"] = "error"
                    report["pruned_explanation"] = str(e)
                reports.append(report)
                print(f"[stage3] REPORT: {fn} "
                      f"(pruned={report.get('pruned_decision')})", flush=True)
        except Exception as e:
            print(f"[stage3] spec {i} failed: {str(e)[:60]}", flush=True)
        # checkpoint after each spec
        with open(REPORTS_FILE, "w", encoding="utf-8") as f:
            json.dump(reports, f, ensure_ascii=False, indent=2)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"next_index": i + 1}, f)

    kept = [r for r in reports
            if r.get("pruned_decision") not in ("no", "error", None)]
    print(f"[stage3 done] {len(reports)} reports, {len(kept)} kept", flush=True)
    print("usage:", llm.usage_summary(), flush=True)


if __name__ == "__main__":
    main()

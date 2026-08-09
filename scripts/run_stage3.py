#!/usr/bin/env python3
"""Run Stage 3 (bug detection) on seed + generated specifications.

Usage:
    python scripts/run_stage3.py --kernel /path/to/linux \
        --code-db data/code_index.sqlite --env config/llm.env \
        --out data/outputs [--max-candidates 300] [--no-prune]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sa import config as cfg  # noqa: E402
from sa.code_index import CodeIndex  # noqa: E402
from sa.llm_client import LLMClient  # noqa: E402
from sa.stage3 import Stage3  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--code-db", default="data/code_index.sqlite")
    ap.add_argument("--env", default="config/llm.env")
    ap.add_argument("--out", default="data/outputs")
    ap.add_argument("--max-candidates", type=int, default=300)
    ap.add_argument("--max-per-spec", type=int, default=60)
    ap.add_argument("--no-prune", action="store_true")
    args = ap.parse_args()

    cfg.load_env_file(args.env)
    os.makedirs(args.out, exist_ok=True)

    with open(os.path.join(args.out, "stage1_out.json"), encoding="utf-8") as f:
        s1 = json.load(f)
    with open(os.path.join(args.out, "stage2_out.json"), encoding="utf-8") as f:
        s2 = json.load(f)

    specs = []
    for r in s1:
        if r.get("validation", {}).get("valid"):
            specs.append({
                "entity": r["entity"],
                "constraint": r["constraint"],
                "kind": "seed",
                "seed_hexsha": r["hexsha"],
            })
    for r in s2:
        cs = r["concretized_specification"]
        specs.append({
            "entity": cs["entity"],
            "constraint": cs["constraint"],
            "kind": "generated",
            "seed_hexsha": r["seed_hexsha"],
            "candidate": r["candidate"],
        })
    print(f"[stage3] total specs: {len(specs)} "
          f"({sum(1 for s in specs if s['kind']=='seed')} seed + "
          f"{sum(1 for s in specs if s['kind']=='generated')} generated)")

    llm = LLMClient()
    idx = CodeIndex(args.kernel, db_path=args.code_db)
    s3 = Stage3(llm, idx, max_candidates=args.max_candidates)

    reports = []
    for i, spec in enumerate(specs):
        print(f"[stage3] [{i+1}/{len(specs)}] {spec['kind']}: "
              f"{spec['entity'][:70]}", flush=True)
        try:
            query = s3.generate_query(spec["entity"])
        except Exception as exc:
            print(f"[stage3] query gen failed: {str(exc)[:80]}", flush=True)
            continue
        candidates = s3.localize(query)
        print(f"[stage3] {len(candidates)} candidates", flush=True)
        for fn in candidates[: args.max_per_spec]:
            try:
                check = s3.check_violation(spec, fn)
            except Exception as exc:
                print(f"[stage3] check {fn} failed: {str(exc)[:60]}", flush=True)
                continue
            if check.get("decision") != "yes":
                continue
            report = {
                "spec_kind": spec["kind"],
                "spec_entity": spec["entity"],
                "spec_constraint": spec["constraint"],
                "seed_hexsha": spec.get("seed_hexsha"),
                "candidate": spec.get("candidate"),
                "function": fn,
                "initial_explanation": check.get("explanation", ""),
            }
            if not args.no_prune:
                try:
                    pruned = s3.prune_report(spec, fn)
                    report["pruned_decision"] = pruned.get("decision")
                    report["pruned_explanation"] = pruned.get("explanation", "")
                except Exception as exc:
                    report["pruned_decision"] = "error"
                    report["pruned_explanation"] = str(exc)
            reports.append(report)
            print(f"[stage3] REPORT: {fn} "
                  f"(pruned={report.get('pruned_decision', '-')})", flush=True)
        # checkpoint
        with open(os.path.join(args.out, "stage3_reports.json"), "w",
                  encoding="utf-8") as f:
            json.dump(reports, f, ensure_ascii=False, indent=2)

    kept = [r for r in reports
            if r.get("pruned_decision") not in ("no", "error", None)]
    print(f"[stage3] done: {len(reports)} initial reports, "
          f"{len(kept)} kept after pruning")
    u = llm.usage_summary()
    print(f"[stage3] usage: {u}")


if __name__ == "__main__":
    main()

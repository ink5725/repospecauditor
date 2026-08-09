#!/usr/bin/env python3
"""Strict second-pass review of the 196 kept violation reports.

Simulates the paper's manual verification step (Section 7.1):
for each report, an expert reviews the function code + spec + LLM reasoning
and decides whether the violation is a REAL bug.

This pass is stricter than the pruning pass:
- requires concrete line-number evidence from the function body
- checks whether the violation is actually reachable (control flow)
- distinguishes real bugs from code warnings (robustness issues) and
  false positives (code is actually correct)

Output: data/outputs_100/stage3_review.json
"""
from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sa import config as cfg  # noqa: E402
from sa.code_index import CodeIndex  # noqa: E402
from sa.llm_client import LLMClient  # noqa: E402
from sa import prompts  # noqa: E402

OUT_DIR = "data/outputs_100"
REVIEW_FILE = os.path.join(OUT_DIR, "stage3_review.json")
WORKERS = 4

REVIEW_SYSTEM = """You are a senior Linux kernel maintainer performing code review.
Given a violation report (specification + function code + prior LLM reasoning),
determine whether the function contains a REAL bug that a maintainer would fix.

Be strict and evidence-based:
1. Locate the exact lines in the function where the entity is used.
2. Verify the constraint violation is REAL: follow the actual control flow
   and data flow in the code. Consider aliases and all paths.
3. Classify the report:
   - REAL_BUG: the violation can actually occur on some execution path and
     leads to incorrect behavior / resource leak / security issue. A
     maintainer would likely accept a fix.
   - CODE_WARNING: the code is technically correct (or the issue is
     mitigated elsewhere), but lacks robustness (e.g. missing defensive
     check). Not a bug but worth improving.
   - FALSE_POSITIVE: the code is actually correct; the spec does not apply
     or the constraint is satisfied through a different form.
4. If the entity call is absent from the code or the reasoning references
   code not present in the function, it is a FALSE_POSITIVE.

Output JSON:
{"classification": "REAL_BUG" | "CODE_WARNING" | "FALSE_POSITIVE",
 "evidence": "specific line numbers and code excerpts supporting the decision",
 "explanation": "why this is/is not a real bug"}"""

REVIEW_USER = """# Specification
Entity: {entity}
Constraint: {constraint}

# Function code under review
{func_code}

# Prior LLM reasoning (from detection)
{prior_reasoning}

Classify this report strictly using the criteria above."""


def main():
    cfg.load_env_file("config/llm.env")
    with open(os.path.join(OUT_DIR, "stage3_reports.json"), encoding="utf-8") as f:
        reports = json.load(f)
    kept = [r for r in reports
            if r.get("pruned_decision") not in ("no", "error", None)]
    print(f"[review] {len(kept)} reports to review", flush=True)

    llm = LLMClient()
    idx = CodeIndex("/home/ink/Spec/linux-6.17-rc3",
                    db_path="data/code_index.sqlite")

    lock = threading.Lock()
    results: list = []
    done = 0

    def review_one(r: dict) -> dict:
        body = idx.function_body(r["function"]) or "(not found)"
        prior = (r.get("pruned_explanation") or r.get("initial_explanation")
                 or "no prior reasoning")
        user = REVIEW_USER.format(
            entity=r.get("spec_entity", ""),
            constraint=r.get("spec_constraint", ""),
            func_code=body,
            prior_reasoning=prior,
        )
        out = llm.complete_json(REVIEW_SYSTEM, user)
        out["function"] = r["function"]
        out["spec_entity"] = r.get("spec_entity", "")
        out["spec_kind"] = r.get("spec_kind", "")
        return out

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(review_one, r): r for r in kept}
        for fut in as_completed(futs):
            r = futs[fut]
            with lock:
                try:
                    results.append(fut.result())
                except Exception as e:
                    results.append({
                        "function": r["function"], "classification": "ERROR",
                        "evidence": str(e)[:100],
                    })
                done += 1
                if done % 10 == 0:
                    with open(REVIEW_FILE, "w", encoding="utf-8") as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                    print(f"[review] {done}/{len(kept)}", flush=True)

    with open(REVIEW_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    from collections import Counter
    print("[review] done:", dict(Counter(x.get("classification") for x in results)))
    print("usage:", llm.usage_summary(), flush=True)


if __name__ == "__main__":
    main()

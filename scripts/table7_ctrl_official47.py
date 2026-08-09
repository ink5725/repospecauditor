#!/usr/bin/env python3
"""Control experiment: run LLM-only (function-level) on the official 47
confirmed bug targets from the paper's checks.csv.

This isolates whether our high LLM-only recall (78/111) is due to model
capability (would also detect official targets) or due to our REAL_BUG set
containing easier cases.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sa import config as cfg  # noqa: E402
from sa.code_index import CodeIndex  # noqa: E402
from sa.llm_client import LLMClient  # noqa: E402

OUT_DIR = "data/outputs_100"
OFFICIAL_CSV = "/home/ink/Spec/SpecAuditor/artifact/reproduced_bug_detection/datasets/checks.csv"

LLM_ONLY_SYSTEM = """You are an expert C programmer who can carefully analyze
the provided C code. The goal is to judge if the provided code is vulnerable
or not. Your answer should be concise, with a yes or no to represent the
code's type. If it is vulnerable, then yes; otherwise, no. Also, please
explain concisely why you made the decision."""

LLM_ONLY_USER = """# Code
{code}

Is this code vulnerable? Answer with a JSON object having keys "decision"
(value "yes" or "no") and "explanation" (string)."""


def main():
    cfg.load_env_file("config/llm.env")
    llm = LLMClient()
    idx = CodeIndex("/home/ink/Spec/linux-6.17-rc3",
                    db_path="data/code_index.sqlite")

    # Official confirmed targets
    official = {}
    with open(OFFICIAL_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            official.setdefault(row["buggy function"], row["spec_target"])
    print(f"[ctrl] official targets: {len(official)}", flush=True)

    lock = threading.Lock()
    results: list = []
    done = 0

    def test_one(name: str) -> dict:
        body = idx.function_body(name)
        if not body:
            return {"function": name, "decision": "no",
                    "explanation": "function not found in index"}
        try:
            out = llm.complete_json(LLM_ONLY_SYSTEM, LLM_ONLY_USER.format(code=body[:6000]))
            return {"function": name, "decision": out.get("decision", "no"),
                    "explanation": out.get("explanation", "")[:200]}
        except Exception as e:
            return {"function": name, "decision": "error", "explanation": str(e)[:100]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(test_one, name): name for name in official}
        for fut in futs:
            r = fut.result()
            with lock:
                results.append(r)
                done += 1
                if done % 10 == 0:
                    print(f"[ctrl] {done}/{len(official)}", flush=True)

    with open(os.path.join(OUT_DIR, "table7_ctrl_official47.json"), "w") as f:
        json.dump(results, f, indent=1)

    yes = [r for r in results if r["decision"] == "yes"]
    print(f"\n[ctrl] official 47 targets, function-level LLM-only: "
          f"{len(yes)}/{len(results)} recalled")
    print("[ctrl] paper reported LLM-only function-level 7/71 on their 71 bugs")
    for r in yes:
        print(f"  YES: {r['function']}")


if __name__ == "__main__":
    main()

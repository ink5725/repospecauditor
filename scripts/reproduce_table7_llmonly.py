#!/usr/bin/env python3
"""Reproduce Table 7 LLM-only baseline (paper Table 8 prompt).

For each REAL_BUG function detected by our SpecAuditor, ask the LLM directly
whether the code is vulnerable (no specification guidance), at two levels:
- function-level: provide the buggy function only
- file-level: provide the whole file

Paper result: function-level 7/71, file-level 1/71 recalled.
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

OUT_DIR = "data/outputs_100"
WORKERS = 4

# Paper Table 8 prompt (LLM-only detection)
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
    with open(os.path.join(OUT_DIR, "stage3_review.json"), encoding="utf-8") as f:
        review = json.load(f)
    real = [x for x in review if x.get("classification") == "REAL_BUG"]
    print(f"[llm-only] {len(real)} REAL_BUG functions to test", flush=True)

    llm = LLMClient()
    idx = CodeIndex("/home/ink/Spec/linux-6.17-rc3",
                    db_path="data/code_index.sqlite")

    lock = threading.Lock()
    results: list = []
    done = 0

    def test_one(x: dict, level: str) -> dict:
        if level == "function":
            code = idx.function_body(x["function"]) or "(not found)"
        else:  # file level: whole file containing the function
            loc = idx.find_function(x["function"])
            if not loc:
                return {"function": x["function"], "level": level,
                        "decision": "no", "explanation": "function not found"}
            path = loc[0]
            full = os.path.join("/home/ink/Spec/linux-6.17-rc3", path)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    code = f.read()[:20000]  # cap file size
            except OSError:
                return {"function": x["function"], "level": level,
                        "decision": "no", "explanation": "file not found"}
        user = LLM_ONLY_USER.format(code=code)
        try:
            out = llm.complete_json(LLM_ONLY_SYSTEM, user)
            return {"function": x["function"], "level": level,
                    "decision": out.get("decision", "no"),
                    "explanation": out.get("explanation", "")[:300]}
        except Exception as e:
            return {"function": x["function"], "level": level,
                    "decision": "no", "explanation": f"error: {str(e)[:60]}"}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = []
        for x in real:
            futs.append(pool.submit(test_one, x, "function"))
            futs.append(pool.submit(test_one, x, "file"))
        for fut in as_completed(futs):
            with lock:
                results.append(fut.result())
                done += 1
                if done % 20 == 0:
                    print(f"[llm-only] {done}/{len(real)*2}", flush=True)

    with open(os.path.join(OUT_DIR, "table7_llm_only.json"), "w",
              encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # summary
    fn_res = [r for r in results if r["level"] == "function"]
    fl_res = [r for r in results if r["level"] == "file"]
    fn_yes = sum(1 for r in fn_res if r["decision"] == "yes")
    fl_yes = sum(1 for r in fl_res if r["decision"] == "yes")
    print(f"\n[llm-only] function-level: {fn_yes}/{len(fn_res)} recalled")
    print(f"[llm-only] file-level: {fl_yes}/{len(fl_res)} recalled")
    print(f"[llm-only] paper: function 7/71, file 1/71")
    print("usage:", llm.usage_summary(), flush=True)


if __name__ == "__main__":
    main()

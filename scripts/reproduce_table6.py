#!/usr/bin/env python3
"""Reproduce paper Table 6: entity type distribution of specifications.

Uses the LLM to classify each specification's entity into the paper's four
types (Function / Data structure / Control-flow / Others), mimicking the
manual annotation in Section 7.2.2.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sa import config as cfg  # noqa: E402
from sa.llm_client import LLMClient  # noqa: E402

CLASSIFY_SYSTEM = """You are a program analysis expert. Classify a code audit
specification's ENTITY into exactly one of these types (paper Table 6):

- "Function": the entity is a function (including function-like macros) whose
  constraint constrains properties of the function and its usages.
- "Data structure": the entity is a program object (e.g., struct, array) whose
  constraint covers initialization before exposure, correct termination, etc.
- "Control-flow": the entity relates to execution-path logic (e.g., loop
  traversal, iteration boundaries).
- "Others": processing workflows (e.g., protocol decoding) where the
  constraint applies to the whole execution sequence.

Reply with JSON: {"type": "Function" | "Data structure" | "Control-flow" | "Others"}"""

CLASSIFY_USER = """# Specification entity
{entity}

# Specification constraint
{constraint}

Classify the entity type."""


def main():
    cfg.load_env_file("config/llm.env")
    with open("data/outputs_100/stage1_out.json", encoding="utf-8") as f:
        s1 = json.load(f)
    with open("data/outputs_100/stage2_out.json", encoding="utf-8") as f:
        s2 = json.load(f)

    specs = []
    for r in s1:
        if r.get("validation", {}).get("valid"):
            specs.append({
                "entity": r["entity"], "constraint": r["constraint"],
                "kind": "seed", "hexsha": r["hexsha"],
            })
    for r in s2:
        cs = r["concretized_specification"]
        specs.append({
            "entity": cs["entity"], "constraint": cs["constraint"],
            "kind": "generated", "candidate": r["candidate"],
        })
    print(f"[table6] {len(specs)} specs to classify", flush=True)

    llm = LLMClient()
    results = []
    for i, s in enumerate(specs):
        user = CLASSIFY_USER.format(entity=s["entity"], constraint=s["constraint"])
        try:
            out = llm.complete_json(CLASSIFY_SYSTEM, user)
            etype = out.get("type", "Others")
        except Exception as e:
            etype = "ERROR"
            print(f"[table6] {i} failed: {str(e)[:60]}", flush=True)
        results.append({**s, "entity_type": etype})
        if i % 20 == 0:
            print(f"[table6] {i}/{len(specs)}", flush=True)

    with open("data/outputs_100/table6_classification.json", "w",
              encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    c = Counter(x["entity_type"] for x in results)
    total = len(results)
    print("\n=== Reproduced Table 6 ===")
    print(f"{'Entity Type':<16}{'Count':<8}{'Ratio'}")
    for k in ["Function", "Data structure", "Control-flow", "Others", "ERROR"]:
        print(f"{k:<16}{c[k]:<8}{c[k]/total*100:.1f}%")
    print("\nPaper: Function 82.5% | Data structure 16.2% | Control-flow 1.0% | Others 0.3%")
    print("usage:", llm.usage_summary(), flush=True)


if __name__ == "__main__":
    main()

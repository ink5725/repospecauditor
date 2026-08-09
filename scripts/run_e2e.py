#!/usr/bin/env python3
"""End-to-end pipeline: Stage1 -> Stage2 -> Stage3.

Usage:
    python scripts/run_e2e.py --kernel /path/to/linux \
        --seeds data/seed_commits.csv \
        --doc-db data/doc_vectors --code-db data/code_index.sqlite \
        --env config/llm.env --out data/outputs [--stage 1|2|3]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sa import config as cfg  # noqa: E402
from sa.code_index import CodeIndex  # noqa: E402
from sa.embedding import EmbeddingClient  # noqa: E402
from sa.llm_client import LLMClient  # noqa: E402
from sa.stage1 import Stage1  # noqa: E402
from sa.stage2 import Stage2, extract_identifiers  # noqa: E402
from sa.stage3 import Stage3  # noqa: E402
from sa.vector_store import VectorStore  # noqa: E402


def load_seeds(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return [{"hexsha": r["hexsha"], "description": r.get("description", "")}
                for r in csv.DictReader(f)]


def summarize_usage(llm: LLMClient) -> None:
    u = llm.usage_summary()
    print(f"[usage] requests={u['requests']} in={u['input_tokens']} "
          f"out={u['output_tokens']} total={u['total_tokens']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", required=True, help="linux kernel checkout")
    ap.add_argument("--seeds", default="data/seed_commits.csv")
    ap.add_argument("--doc-db", default="data/doc_vectors")
    ap.add_argument("--code-db", default="data/code_index.sqlite")
    ap.add_argument("--env", default="config/llm.env")
    ap.add_argument("--out", default="data/outputs")
    ap.add_argument("--stage", type=int, default=0, help="0=all, 1, 2, 3")
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--threshold", type=float, default=0.35)
    ap.add_argument("--no-prune", action="store_true")
    args = ap.parse_args()

    cfg.load_env_file(args.env)
    os.makedirs(args.out, exist_ok=True)

    llm = LLMClient()
    seeds = load_seeds(args.seeds)
    print(f"[e2e] {len(seeds)} seed patches, LLM={llm.model}")

    # ---------------- Stage 1 ---------------- #
    if args.stage in (0, 1):
        s1 = Stage1(args.kernel, llm)
        s1_results = s1.run(seeds, args.out)
        valid = [r for r in s1_results if r.get("validation", {}).get("valid")]
        print(f"[e2e] stage1: {len(valid)}/{len(s1_results)} validated")
    else:
        with open(os.path.join(args.out, "stage1_out.json"), encoding="utf-8") as f:
            s1_results = json.load(f)

    # ---------------- Stage 2 ---------------- #
    if args.stage in (0, 2):
        embed = EmbeddingClient()
        store = VectorStore(persist_dir=args.doc_db)
        if store.size == 0:
            sys.exit(f"[e2e] doc vector store empty: {args.doc_db}; "
                     "run scripts/build_doc_db.py first")
        code_idx = CodeIndex(args.kernel, db_path=args.code_db)
        exclude = set()
        for r in s1_results:
            exclude.update(extract_identifiers(r.get("entity", "")))
        s2 = Stage2(llm, embed, store, code_idx,
                    top_k=args.top_k, threshold=args.threshold)
        s2_results = s2.run(s1_results, args.out, exclude_names=exclude)
        print(f"[e2e] stage2: {len(s2_results)} new specifications")
    else:
        with open(os.path.join(args.out, "stage2_out.json"), encoding="utf-8") as f:
            s2_results = json.load(f)

    # ---------------- Stage 3 ---------------- #
    if args.stage in (0, 3):
        code_idx = CodeIndex(args.kernel, db_path=args.code_db)
        s3 = Stage3(llm, code_idx, run_pruning=not args.no_prune)
        # audit with seed specs + generated specs
        seed_specs = [
            {"entity": r["entity"], "constraint": r["constraint"]}
            for r in s1_results
            if r.get("validation", {}).get("valid")
        ]
        gen_specs = [
            {
                "entity": r["concretized_specification"]["entity"],
                "constraint": r["concretized_specification"]["constraint"],
            }
            for r in s2_results
        ]
        all_specs = seed_specs + gen_specs
        print(f"[e2e] stage3: auditing with {len(all_specs)} specifications "
              f"({len(seed_specs)} seed + {len(gen_specs)} generated)")
        reports = s3.run(all_specs, args.out)
        kept = [r for r in reports
                if r.get("pruned_decision") not in ("no", "error", None)]
        print(f"[e2e] stage3: {len(reports)} initial reports, "
              f"{len(kept)} kept after pruning")

    summarize_usage(llm)


if __name__ == "__main__":
    main()

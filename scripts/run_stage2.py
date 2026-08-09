#!/usr/bin/env python3
"""Run Stage 2 (specification generation) on validated seed specs.

Usage:
    python scripts/run_stage2.py --kernel /path/to/linux \
        --doc-db data/doc_vectors --code-db data/code_index.sqlite \
        --env config/llm.env --out data/outputs [--top-k 100] [--threshold 0.15]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sa import config as cfg  # noqa: E402
from sa.code_index import CodeIndex  # noqa: E402
from sa.embedding import EmbeddingClient  # noqa: E402
from sa.llm_client import LLMClient  # noqa: E402
from sa.stage2 import Stage2, extract_identifiers  # noqa: E402
from sa.vector_store import VectorStore  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--doc-db", default="data/doc_vectors")
    ap.add_argument("--code-db", default="data/code_index.sqlite")
    ap.add_argument("--env", default="config/llm.env")
    ap.add_argument("--out", default="data/outputs")
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--threshold", type=float, default=0.15)
    ap.add_argument("--max-per-seed", type=int, default=40)
    args = ap.parse_args()

    cfg.load_env_file(args.env)
    os.makedirs(args.out, exist_ok=True)

    with open(os.path.join(args.out, "stage1_out.json"), encoding="utf-8") as f:
        s1_results = json.load(f)

    llm = LLMClient()
    embed = EmbeddingClient(cache_dir=os.path.join(args.doc_db, "embed_cache"))
    store = VectorStore(persist_dir=args.doc_db)
    print(f"[stage2] doc store size: {store.size}")
    if store.size == 0:
        sys.exit("doc vector store empty; run scripts/build_doc_db.py first")
    idx = CodeIndex(args.kernel, db_path=args.code_db)

    exclude = set()
    for r in s1_results:
        exclude.update(extract_identifiers(r.get("entity", "")))
    # also exclude seed entities themselves
    for r in s1_results:
        for ident in extract_identifiers(r.get("entity", "")):
            exclude.add(ident)

    s2 = Stage2(llm, embed, store, idx, top_k=args.top_k,
                threshold=args.threshold)
    results = s2.run(s1_results, args.out, exclude_names=exclude)
    print(f"[stage2] done: {len(results)} new specifications")
    u = llm.usage_summary()
    print(f"[stage2] usage: {u}")


if __name__ == "__main__":
    main()

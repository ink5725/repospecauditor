#!/usr/bin/env python3
"""Build the entity-description vector database from kernel documentation.

Reads (type, name, description) text files, embeds each description with
the configured embedding model and stores them in the local vector store.

Usage:
    python scripts/build_doc_db.py \
        --docs data/kernel_api_docs \
        --db data/doc_vectors \
        [--env config/llm.env]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sa import doc_indexer, embedding, vector_store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default="data/kernel_api_docs")
    ap.add_argument("--db", default="data/doc_vectors")
    ap.add_argument("--env", default="config/llm.env")
    args = ap.parse_args()

    from sa import config as cfg
    cfg.load_env_file(args.env)

    entries = doc_indexer.load_doc_dir(args.docs)
    print(f"[docdb] loaded {len(entries)} entity-description pairs")
    if not entries:
        sys.exit("no docs found; run scripts/fetch_docs.py first")

    from collections import Counter
    print("[docdb] types:", dict(Counter(e[0] for e in entries)))

    client = embedding.EmbeddingClient(
        cache_dir=os.path.join(args.db, "embed_cache")
    )
    store = vector_store.VectorStore(persist_dir=args.db)

    ids = [f"{t}:{n}" for t, n, _ in entries]
    metas = [
        {"name": n, "type": t, "description": d[:2000]}
        for t, n, d in entries
    ]
    texts = [d for _, _, d in entries]

    print(f"[docdb] embedding {len(texts)} descriptions (batch, cached) ...")
    vecs = client.embed_batch(texts)
    store.add(ids, metas, vecs)
    print(f"[docdb] stored {store.size} vectors -> {args.db}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build the AST code index of a source tree (tree-sitter based).

Usage:
    python scripts/index_codebase.py --root /path/to/linux \
        [--db /path/to/index.sqlite] [--workers 20] [--force]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sa.code_index import CodeIndex  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--db", default=None)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    idx = CodeIndex(args.root, db_path=args.db, workers=args.workers)
    idx.build(force=args.force)
    print("[index] stats:", idx.stats())


if __name__ == "__main__":
    main()

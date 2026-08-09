#!/usr/bin/env python3
"""Summarize Stage 3 results and compare against the official checks.csv.

Usage:
    python scripts/summarize_results.py --out data/outputs
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/outputs")
    ap.add_argument("--official", default=None,
                    help="path to official checks.csv (optional)")
    args = ap.parse_args()

    reports_path = os.path.join(args.out, "stage3_reports.json")
    with open(reports_path, encoding="utf-8") as f:
        reports = json.load(f)

    kept = [r for r in reports
            if r.get("pruned_decision") not in ("no", "error", None)]
    print("=" * 70)
    print(f"Stage 3 summary: {len(reports)} initial reports, "
          f"{len(kept)} kept after pruning")
    print("=" * 70)

    by_spec = Counter((r.get("spec_kind", "?"), r.get("spec_entity", "")[:40])
                      for r in kept)
    print("\n[kept reports by specification]")
    for (kind, ent), cnt in by_spec.most_common():
        print(f"  [{kind}] {ent}: {cnt}")

    if args.official and os.path.exists(args.official):
        official = set()
        with open(args.official, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                official.add(row["buggy function"].strip())
        matched = sorted(set(r["function"] for r in kept
                             if r["function"] in official))
        print(f"\n[matched official checks.csv: {len(matched)}/{len(official)}]")
        for fn in matched:
            print(f"  HIT: {fn}")
        missed = sorted(official - set(r["function"] for r in kept))
        print(f"\n[missed official targets: {len(missed)}]")
        for fn in missed:
            print(f"  missed: {fn}")

    # extra findings not in official (potential new bugs)
    print(f"\n[extra findings not in official: "
          f"{sum(1 for r in kept if args.official and os.path.exists(args.official) and r['function'] not in official)}]")
    if args.official and os.path.exists(args.official):
        official = set()
        with open(args.official, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                official.add(row["buggy function"].strip())
        for r in kept:
            if r["function"] not in official:
                print(f"  extra: {r['function']} "
                      f"| spec: {r.get('spec_entity', '')[:60]}")


if __name__ == "__main__":
    main()

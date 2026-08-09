#!/usr/bin/env python3
"""Collect 100 seed patches (10 bug types x 10) from Linux kernel CVEs.

Follows the paper's dataset construction (Section 7):
- collect seed patches from historical CVE bug patches
- focus on ten common bug types, randomly select ten patches per type

Pipeline:
1. Query NVD API for Linux kernel CVEs (keywordSearch, paginated)
2. Extract kernel commit references (git.kernel.org / github.com/torvalds)
3. Map commits to the local kernel git repo, verify reachability
4. Classify by CWE / description keywords into the paper's 10 types
5. Randomly select 10 per type, output seed_commits.csv

Usage:
    python scripts/collect_100_seeds.py --kernel /path/to/linux \
        --out data/seed_commits_100.csv [--years 3]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import requests

NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
KERNEL_REF_PATTERNS = [
    # torvalds mainline commits first (most reliable for local verification)
    re.compile(r"git\.kernel\.org/pub/scm/linux/kernel/git/torvalds/linux/commit/\?id=([0-9a-f]{7,40})"),
    re.compile(r"github\.com/torvalds/linux/commit/([0-9a-f]{7,40})"),
    re.compile(r"github\.com/torvalds/linux/commit/\?id=([0-9a-f]{7,40})"),
    re.compile(r"git\.kernel\.org/torvalds/c/?([0-9a-f]{7,40})"),
    # stable backports (may not exist in local mainline history)
    re.compile(r"git\.kernel\.org/stable/c/?([0-9a-f]{7,40})"),
    re.compile(r"git\.kernel\.org/pub/scm/linux/kernel/git/stable/linux/commit/\?h=v[0-9.]+&id=([0-9a-f]{7,40})"),
]

# Paper's 10 bug types -> CWE mapping + keyword hints
BUG_TYPES = {
    "memory_leak": {
        "cwe": ["CWE-401", "CWE-772", "CWE-404"],
        "kw": ["memory leak", "leak", "kfree", "kmemleak"],
    },
    "buffer_overflow": {
        "cwe": ["CWE-120", "CWE-122", "CWE-787", "CWE-121", "CWE-119"],
        "kw": ["buffer overflow", "out-of-bounds write", "overflow"],
    },
    "integer_overflow": {
        "cwe": ["CWE-190", "CWE-191", "CWE-680"],
        "kw": ["integer overflow", "overflow", "wrap"],
    },
    "improper_input_validation": {
        "cwe": ["CWE-20", "CWE-1284", "CWE-129"],
        "kw": ["input validation", "validate", "user-supplied", "user provided", "missing check"],
    },
    "double_free_uaf": {
        "cwe": ["CWE-415", "CWE-416", "CWE-825"],
        "kw": ["use-after-free", "double free", "uaf", "double-free"],
    },
    "uninitialized_use": {
        "cwe": ["CWE-457", "CWE-824", "CWE-908"],
        "kw": ["uninitialized", "uninitialised"],
    },
    "null_pointer_deref": {
        "cwe": ["CWE-476", "CWE-690"],
        "kw": ["null pointer", "NULL pointer", "null deref", "NULL dereference"],
    },
    "resource_leak": {
        "cwe": ["CWE-404", "CWE-772", "CWE-775", "CWE-771"],
        "kw": ["resource leak", "refcount", "reference leak", "refcount leak", "leak"],
    },
    "logic_error": {
        "cwe": ["CWE-697", "CWE-670", "CWE-617", "CWE-754"],
        "kw": ["logic", "incorrect", "wrong", "misuse", "erroneous"],
    },
    "oob_access": {
        "cwe": ["CWE-125", "CWE-787", "CWE-822"],
        "kw": ["out-of-bounds", "out of bounds", "oob", "out of bound"],
    },
}

# commit extraction state cache
commit_cache: Dict[str, Optional[str]] = {}


def run_git(kernel_path: str, *args: str) -> str:
    env = os.environ.copy()
    env["GIT_NO_LAZY_FETCH"] = "1"  # avoid network fetch for missing objects
    proc = subprocess.run(
        ["git", "-C", kernel_path, *args],
        capture_output=True, text=True, errors="replace", env=env,
    )
    return proc.stdout.strip()


def extract_commit(url: str) -> Optional[str]:
    for pat in KERNEL_REF_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


def verify_commit(kernel_path: str, sha: str) -> Optional[str]:
    """Return full sha if the commit exists in local repo, else None.
    Uses cat-file (no lazy fetch) for fast local-only verification."""
    if sha in commit_cache:
        return commit_cache[sha]
    env = os.environ.copy()
    env["GIT_NO_LAZY_FETCH"] = "1"
    proc = subprocess.run(
        ["git", "-C", kernel_path, "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True, env=env,
    )
    if proc.returncode == 0:
        out = run_git(kernel_path, "rev-parse", "--verify", f"{sha}^{{commit}}")
        full = out.strip()
        commit_cache[sha] = full if full else None
        return commit_cache[sha]
    commit_cache[sha] = None
    return None


def get_commit_message(kernel_path: str, sha: str) -> str:
    return run_git(kernel_path, "log", "-1", "--format=%s%n%b", sha)


def classify(cve: dict) -> Optional[str]:
    """Classify a CVE into one of the 10 bug types using CWE + description."""
    cwes: List[str] = []
    for w in cve.get("weaknesses", []):
        for desc in w.get("description", []):
            cwes.append(desc["value"])
    desc = cve.get("descriptions", [{}])[0].get("value", "").lower() if cve.get("descriptions") else ""

    # CWE-based matching (most reliable)
    for btype, spec in BUG_TYPES.items():
        for cwe in cwes:
            if cwe in spec["cwe"]:
                # resource_leak vs memory_leak overlap: prefer based on description
                if btype == "memory_leak" and any(k in desc for k in ["refcount", "reference"]):
                    return "resource_leak"
                if btype == "resource_leak" and not any(k in desc for k in ["refcount", "reference", "resource"]):
                    continue
                return btype
    # Keyword-based fallback
    for btype, spec in BUG_TYPES.items():
        if any(k in desc for k in spec["kw"]):
            return btype
    return None


def fetch_nvd_page(params: dict, retries: int = 3) -> Optional[dict]:
    for attempt in range(retries):
        try:
            r = requests.get(NVD_API, params=params, timeout=90)
            if r.status_code == 200:
                return r.json()
            print(f"  NVD {r.status_code}, retry {attempt+1}")
        except Exception as e:
            print(f"  NVD error: {e}, retry {attempt+1}")
        time.sleep(2 ** attempt + 1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kernel", required=True, help="linux kernel git checkout")
    ap.add_argument("--out", default="data/seed_commits_100.csv")
    ap.add_argument("--years", type=int, default=3,
                    help="collect CVEs published in the last N years")
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42, help="random seed")
    args = ap.parse_args()

    random.seed(args.seed)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    print("[collect] querying NVD for Linux kernel CVEs ...")
    all_cves: List[dict] = []
    start = 0
    per_page = 500
    for page in range(args.max_pages):
        params = {
            "keywordSearch": "Linux kernel",
            "resultsPerPage": per_page,
            "startIndex": start,
        }
        data = fetch_nvd_page(params)
        if not data:
            break
        vulns = data.get("vulnerabilities", [])
        all_cves.extend(vulns)
        total = data.get("totalResults", 0)
        start += len(vulns)
        print(f"  fetched {len(all_cves)}/{total}")
        if start >= total or not vulns:
            break
        time.sleep(1.5)  # NVD rate limit

    print(f"[collect] total CVEs fetched: {len(all_cves)}")

    # Filter: published within recent years + has kernel commit refs
    import datetime
    cutoff = datetime.datetime.now() - datetime.timedelta(days=365 * args.years)

    candidates: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)
    for v in all_cves:
        cve = v["cve"]
        cve_id = cve["id"]
        # time filter
        try:
            published = datetime.datetime.fromisoformat(
                cve.get("published", "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if published < cutoff:
            continue
        # extract commit refs
        commits = set()
        for ref in cve.get("references", []):
            sha = extract_commit(ref.get("url", ""))
            if sha:
                commits.add(sha)
        if not commits:
            continue
        # verify against local repo (first 3 commits)
        verified = []
        for sha in list(commits)[:3]:
            full = verify_commit(args.kernel, sha)
            if full:
                msg = get_commit_message(args.kernel, full)
                verified.append((full, msg))
        if not verified:
            continue
        btype = classify(cve)
        if btype:
            candidates[btype].append((cve_id, verified[0][0], verified[0][1]))

    print("[collect] candidates per type:")
    for bt, items in sorted(candidates.items()):
        print(f"  {bt}: {len(items)}")

    # select 10 per type (or all if fewer)
    selected: List[Tuple[str, str, str, str]] = []  # cve, sha, msg, type
    for bt, items in sorted(candidates.items()):
        random.shuffle(items)
        for cve_id, sha, msg in items[:10]:
            selected.append((cve_id, sha, msg, bt))

    # write output
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("hexsha,cve_id,bug_type,description\n")
        for cve_id, sha, msg, bt in selected:
            desc = msg.splitlines()[0] if msg else ""
            desc = desc[:120].replace(",", ";")
            f.write(f"{sha},{cve_id},{bt},{desc}\n")

    print(f"[collect] selected {len(selected)} patches -> {args.out}")
    for bt in sorted(set(t for _, _, _, t in selected)):
        cnt = sum(1 for s in selected if s[3] == bt)
        print(f"  {bt}: {cnt}")


if __name__ == "__main__":
    main()

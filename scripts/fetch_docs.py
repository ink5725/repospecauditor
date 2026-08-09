#!/usr/bin/env python3
"""Fetch kernel API documentation from docs.kernel.org (from scratch).

Downloads the Sphinx genindex page, extracts all C API entries
(functions / macros / structs / enums / types), downloads each page
and saves "(type, name, description)" text files.

Usage:
    python scripts/fetch_docs.py --out data/kernel_api_docs [--workers 8]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://docs.kernel.org/"
GENINDEX_URL = BASE_URL + "genindex.html"

HEADERS = {"User-Agent": "Mozilla/5.0 (specauditor-repro)"}


def fetch(url: str, retries: int = 3) -> str:
    last = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            if resp.status_code == 200:
                return resp.text
            last = f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            last = str(exc)
        time.sleep(1 + attempt * 2)
    raise RuntimeError(f"fetch failed {url}: {last}")


def parse_genindex(html: str):
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    for li in soup.select("li"):
        a = li.find("a")
        if not a:
            continue
        text = a.get_text(" ", strip=True)
        href = a.get("href", "")
        if not text or not href.endswith(".html"):
            continue
        low = text.lower()
        if "(c function)" in low:
            kind = "function"
        elif "(c macro)" in low:
            kind = "macro"
        elif "(c enum)" in low or "(c enumerator)" in low:
            kind = "enum"
        elif "(c struct)" in low or "(c union)" in low:
            kind = "struct"
        elif "(c type)" in low:
            kind = "type"
        elif "(c variable)" in low:
            kind = "variable"
        else:
            continue
        name = re.sub(r"\s*\(c\s+\w+\)\s*$", "", text, flags=re.I).strip()
        # resolve relative URL against the genindex location
        if href.startswith("../"):
            href = href[3:]
        entries.append({"kind": kind, "name": name, "href": href})
    return entries


def extract_doc_entries(html: str, want_name: str):
    """Extract (name, description) pairs from one kernel-doc page."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for dl in soup.find_all("dl"):
        for dt in dl.find_all("dt", recursive=False):
            name_text = dt.get_text(" ", strip=True)
            m = re.match(r"^([\w.-]+)\s*\(([^)]*)\)$", name_text)
            if not m:
                continue
            dd = dt.find_next_sibling("dd")
            desc = dd.get_text(" ", strip=True) if dd else ""
            if desc:
                out.append((m.group(1), desc))
    return out


def fetch_one(args):
    entry, out_dir = args
    url = BASE_URL + entry["href"]
    try:
        html = fetch(url)
    except Exception as exc:
        return entry["name"], f"FETCH_ERROR: {exc}"
    entries = extract_doc_entries(html, entry["name"])
    matched = [e for e in entries if e[0] == entry["name"]]
    desc = matched[0][1] if matched else (
        entries[0][1] if entries else ""
    )
    if not desc:
        return entry["name"], "NO_DESC"
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", entry["name"])[:120]
    path = os.path.join(out_dir, f"{entry['kind']}_{safe}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{entry['kind']}: {entry['name']}\n\n{desc}\n")
    return entry["name"], "OK"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/kernel_api_docs")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[fetch] downloading {GENINDEX_URL}")
    html = fetch(GENINDEX_URL)
    entries = parse_genindex(html)
    print(f"[fetch] found {len(entries)} C API entries")

    done = 0
    ok = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {
            pool.submit(fetch_one, (e, str(out_dir))): e["name"] for e in entries
        }
        for fut in as_completed(futs):
            name, status = fut.result()
            done += 1
            if status == "OK":
                ok += 1
            if done % 500 == 0:
                print(f"[fetch] {done}/{len(entries)}  (ok={ok})")
    print(f"[fetch] done: {ok}/{len(entries)} descriptions saved to {out_dir}")


if __name__ == "__main__":
    sys.exit(main())

"""Document corpus parsing: build (entity, description) pairs.

The corpus follows the paper's setup: official project documentation indexed
as entity-description pairs (functions, structs, macros, enums, typedefs).

Input formats supported:
  1. a directory of text files, each containing "Type: name" + description
     (the format produced by fetching the kernel docs genindex pages)
  2. raw HTML pages fetched from docs.kernel.org (parsed with BeautifulSoup)
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

_TYPE_PREFIX = {
    "function": "function",
    "macro": "macro",
    "enum": "enum",
    "struct": "struct",
    "union": "struct",
    "type": "type",
    "variable": "variable",
    "member": "member",
}

_INVALID_DESCS = {
    "not found in this page",
    "not documented",
    "no description",
}


def _clean_func_signature(name: str) -> str:
    """'int close ( int fd )' -> 'close' ; 'void *kmalloc ( size_t size )' -> 'kmalloc'."""
    # strip parentheses content
    base = re.split(r"\s*\(", name, maxsplit=1)[0].strip()
    # last identifier in the declarator is the function name
    m = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", base)
    return m.group(1) if m else base


def parse_entity_file(content: str) -> Optional[Tuple[str, str, str]]:
    """Parse one doc text file -> (entity_type, entity_name, description)."""
    text = content.strip()
    if not text:
        return None
    lines = text.splitlines()
    header = lines[0].strip()
    m = re.match(r"^(function|macro|enum|struct|union|type|variable|member)"
                 r"\s*:\s*(.*)$", header, re.I)
    if not m:
        # try "name (C function)" style
        m2 = re.match(r"^([\w.-]+)\s*\((c\s+\w+)\)$", header, re.I)
        if m2:
            etype = "function" if "function" in m2.group(2) else m2.group(2).split()[-1]
            return etype, m2.group(1), "\n".join(lines[1:]).strip()
        return None
    etype = _TYPE_PREFIX.get(m.group(1).lower(), m.group(1).lower())
    raw_name = m.group(2).strip()
    if etype == "function":
        name = _clean_func_signature(raw_name)
    else:
        # strip redundant type prefix inside the name, e.g. "type cec_caps"
        name = re.sub(r"^(struct|union|enum|type)\s+", "", raw_name, flags=re.I).strip()
    desc = "\n".join(lines[1:]).strip()
    if not desc or desc.lower() in _INVALID_DESCS or len(desc) < 5:
        return None
    return etype, name, desc


def load_doc_dir(doc_dir: str) -> List[Tuple[str, str, str]]:
    """Load all entity files from a directory -> [(type, name, description)]."""
    entries: List[Tuple[str, str, str]] = []
    for fn in sorted(os.listdir(doc_dir)):
        if not fn.endswith(".txt"):
            continue
        path = os.path.join(doc_dir, fn)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue
        parsed = parse_entity_file(content)
        if parsed:
            entries.append(parsed)
    return entries


def load_doc_dir_html(html_dir: str) -> List[Tuple[str, str, str]]:
    """Parse HTML doc pages (docs.kernel.org kernel-doc output) into
    (entity_type, entity_name, description) triples.

    kernel-doc pages contain <dl> entries with <dt> names and <dd> docs.
    """
    from bs4 import BeautifulSoup

    entries: List[Tuple[str, str, str]] = []
    for fn in sorted(os.listdir(html_dir)):
        if not fn.endswith(".html"):
            continue
        path = os.path.join(html_dir, fn)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
        except OSError:
            continue
        for dl in soup.find_all("dl"):
            for dt in dl.find_all("dt", recursive=False):
                name_text = dt.get_text(" ", strip=True)
                m = re.match(r"^([\w.-]+)\s*\(([^)]*)\)$", name_text)
                if not m:
                    continue
                name = m.group(1)
                kind = m.group(2).lower()
                etype = "function" if "function" in kind else (
                    "macro" if "macro" in kind else
                    "struct" if ("struct" in kind or "union" in kind) else
                    "enum" if "enum" in kind else
                    "type" if "type" in kind else "other"
                )
                dd = dt.find_next_sibling("dd")
                desc = dd.get_text(" ", strip=True) if dd else ""
                if desc and len(desc) > 4:
                    entries.append((etype, name, desc))
    return entries


def parse_genindex_html(html_path: str) -> List[Tuple[str, str, str]]:
    """Parse the Sphinx genindex page -> (type, name, url-fragment)."""
    from bs4 import BeautifulSoup

    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    out = []
    for li in soup.select("li"):
        a = li.find("a")
        if not a:
            continue
        text = a.get_text(" ", strip=True)
        href = a.get("href", "")
        if not text or not href.endswith(".html"):
            continue
        kind = "other"
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
        name = re.sub(r"\s*\(c\s+\w+\)\s*$", "", text, flags=re.I).strip()
        out.append((kind, name, href))
    return out

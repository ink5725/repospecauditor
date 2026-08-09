"""Codebase index over the target source tree (sqlite-backed).

The indexer walks every .c/.h file, parses it with tree-sitter and stores:
  - function definitions (name, file, line range)
  - struct definitions   (name, file, line range)
  - call sites           (caller function, file, line, callee)

Queries power both the specification-generation context extraction
(definition + usage examples) and the bug-detection localization step.
"""
from __future__ import annotations

import os
import random
import re
import sqlite3
import threading
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List, Optional, Tuple

from . import ast_tools

_C_SOURCE_EXT = {".c", ".h"}


def _iter_source_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        # skip VCS dirs and generated/foreign subtrees
        dirnames[:] = [
            d
            for d in dirnames
            if d not in (".git", "Documentation", "tools", "scripts",
                         "arch", "usr", "include", "samples", "crypto",
                         "security")  # arch/include excluded: huge & mostly decls
        ]
        for fn in filenames:
            if os.path.splitext(fn)[1] in _C_SOURCE_EXT:
                yield os.path.join(dirpath, fn)


class CodeIndex:
    """Builds and queries the AST index of a source tree."""

    def __init__(self, root: str, db_path: Optional[str] = None, workers: int = 8):
        self.root = root
        self.db_path = db_path or os.path.join(root, ".specauditor_index.sqlite")
        self.workers = workers

    # ------------------------------------------------------------------ #
    # Build                                                            #
    # ------------------------------------------------------------------ #
    def build(self, force: bool = False) -> None:
        if os.path.exists(self.db_path) and not force:
            print(f"[index] reuse existing index: {self.db_path}")
            return
        files = list(_iter_source_files(self.root))
        print(f"[index] parsing {len(files)} files ...")
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        self._init_schema(conn)
        with ProcessPoolExecutor(max_workers=self.workers) as pool:
            for i, info in enumerate(pool.map(_parse_one, files, chunksize=64)):
                self._write_info(conn, files[i], info)
                if i % 5000 == 0:
                    conn.commit()
                    print(f"[index] {i}/{len(files)}")
        conn.commit()
        conn.close()
        print(f"[index] done -> {self.db_path}")

    @staticmethod
    def _init_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS functions(
                name TEXT, file TEXT, start INTEGER, end INTEGER, body TEXT
            );
            CREATE TABLE IF NOT EXISTS structs(
                name TEXT, file TEXT, start INTEGER, end INTEGER, body TEXT
            );
            CREATE TABLE IF NOT EXISTS calls(
                caller TEXT, file TEXT, line INTEGER, callee TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_func_name ON functions(name);
            CREATE INDEX IF NOT EXISTS idx_struct_name ON structs(name);
            CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls(callee);
            CREATE INDEX IF NOT EXISTS idx_calls_caller ON calls(caller);
            """
        )

    def _write_info(self, conn: sqlite3.Connection, path: str, info: dict) -> None:
        rel = os.path.relpath(path, self.root)
        full_src: str = ""
        try:
            with open(os.path.join(self.root, rel), "r",
                      encoding="utf-8", errors="replace") as f:
                full_src = f.read()
        except OSError:
            pass
        lines = full_src.splitlines()

        def body_of(start: int, end: int) -> str:
            return "\n".join(lines[start - 1 : end])[:8000]

        conn.executemany(
            "INSERT INTO functions(name,file,start,end,body) VALUES (?,?,?,?,?)",
            [(n, rel, s, e, body_of(s, e)) for n, s, e in info["functions"]],
        )
        conn.executemany(
            "INSERT INTO structs(name,file,start,end,body) VALUES (?,?,?,?,?)",
            [(n, rel, s, e, body_of(s, e)) for n, s, e in info["structs"]],
        )
        conn.executemany(
            "INSERT INTO calls(caller,file,line,callee) VALUES (?,?,?,?)",
            [(c, rel, l, k) for c, l, k in info["calls"]],
        )

    # ------------------------------------------------------------------ #
    # Query                                                             #
    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def find_function(self, name: str) -> Optional[Tuple[str, int, int]]:
        conn = self._connect()
        row = conn.execute(
            "SELECT file,start,end FROM functions WHERE name=? ORDER BY LENGTH(file) LIMIT 1",
            (name,),
        ).fetchone()
        conn.close()
        return (row["file"], row["start"], row["end"]) if row else None

    def functions_containing_text(self, needle: str, limit: int = 2000) -> List[str]:
        """Find function names whose body contains the given text.
        Used to localize entities without exact call-site records
        (e.g. struct usage, macro usage)."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT DISTINCT name FROM functions WHERE body LIKE ? LIMIT ?",
            (f"%{needle}%", limit),
        ).fetchall()
        conn.close()
        return [r["name"] for r in rows]

    def find_struct(self, name: str) -> Optional[Tuple[str, int, int]]:
        conn = self._connect()
        row = conn.execute(
            "SELECT file,start,end FROM structs WHERE name=? ORDER BY LENGTH(file) LIMIT 1",
            (name,),
        ).fetchone()
        conn.close()
        return (row["file"], row["start"], row["end"]) if row else None

    def function_body(self, name: str, max_lines: int = 400) -> Optional[str]:
        loc = self.find_function(name)
        if loc is None:
            return None
        path, start, end = loc
        full = self.read_lines(path, start - 1, end)
        lines = full.splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines.append("/* ... truncated ... */")
        return "\n".join(lines)

    def struct_body(self, name: str, max_lines: int = 120) -> Optional[str]:
        loc = self.find_struct(name)
        if loc is None:
            return None
        path, start, end = loc
        full = self.read_lines(path, start - 1, end)
        lines = full.splitlines()[:max_lines]
        return "\n".join(lines)

    def read_lines(self, rel_path: str, start: int, end: int) -> str:
        full = os.path.join(self.root, rel_path)
        if not os.path.exists(full):
            return ""
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[start:end])

    def callers_of(self, callee: str, limit: int = 2000) -> List[Tuple[str, str, int]]:
        """Return (caller_function, file, line) for all call sites of callee."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT caller,file,line FROM calls WHERE callee=? ORDER BY file,line LIMIT ?",
            (callee, limit),
        ).fetchall()
        conn.close()
        return [(r["caller"], r["file"], r["line"]) for r in rows]

    def usage_examples(
        self, entity: str, k: int = 5, caller_filter: Optional[set] = None
    ) -> List[Tuple[str, str, int, str]]:
        """Randomly sample up to k call sites and return the enclosing
        function bodies: (caller, file, line, body).
        """
        sites = self.callers_of(entity)
        if caller_filter is not None:
            sites = [s for s in sites if s[0] not in caller_filter]
        if not sites:
            return []
        random.shuffle(sites)
        out = []
        for caller, file, line in sites[:k * 3]:
            body = self.function_body(caller)
            if body and (len(body.splitlines()) <= 400):
                out.append((caller, file, line, body))
                if len(out) >= k:
                    break
        return out

    def stats(self) -> Dict[str, int]:
        conn = self._connect()
        res = {}
        for table in ("functions", "structs", "calls"):
            res[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.close()
        return res


def _parse_one(path: str) -> dict:
    try:
        with open(path, "rb") as f:
            data = f.read()
        if not data:
            return {"functions": [], "calls": [], "structs": []}
        return ast_tools.extract_file_info(data)
    except Exception:
        return {"functions": [], "calls": [], "structs": []}

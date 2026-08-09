"""Git helpers for patch handling.

Implements the patch-access pipeline described in the paper:
- clean commit message (strip metadata such as author/reviewer tags)
- `git diff -W` to obtain the diff with full function context
- extract pre-patch / post-patch function bodies for differential validation
"""
from __future__ import annotations

import re
import subprocess
from typing import List, Optional, Tuple

# tags that carry no bug information and should be stripped
_METADATA_PATTERNS = [
    re.compile(r"^(Signed-off-by|Reviewed-by|Acked-by|Reported-by|Cc|Tested-by"
               r"|Suggested-by|Fixes|Link|Closes|Message-ID|Date|From|Subject"
               r"|Message-Id|In-Reply-To|References|Origin|Backport|Git-commit"
               r"|Cherry-picked|Patch-mainline|Signed-off-by)\s*:.*$", re.I),
    re.compile(r"^[A-Za-z-]+:\s+\S.*$"),  # generic mail-style headers
]


def run_git(kernel_path: str, *args: str, check: bool = True) -> str:
    """Run a git command inside the kernel repo."""
    proc = subprocess.run(
        ["git", "-C", kernel_path, *args],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr[:300]}")
    return proc.stdout


def clean_commit_message(message: str) -> str:
    """Strip metadata lines, keep subject + body."""
    lines = message.splitlines()
    kept: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(p.match(stripped) for p in _METADATA_PATTERNS):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def get_commit_description(kernel_path: str, hexsha: str) -> str:
    raw = run_git(kernel_path, "log", "-1", "--format=%B", hexsha)
    return clean_commit_message(raw)


def diff_with_function_context(kernel_path: str, hexsha: str) -> str:
    """`git diff -W` between parent and commit (full function context)."""
    parent = run_git(kernel_path, "rev-parse", f"{hexsha}^").strip()
    return run_git(kernel_path, "diff", parent, hexsha, "-W", "--no-color")


def get_file_at(kernel_path: str, hexsha: str, path: str) -> str:
    """File content at a given revision (hexsha may be `<sha>^`)."""
    return run_git(kernel_path, "show", f"{hexsha}:{path}")


def parse_diff_hunks(diff_text: str) -> List[dict]:
    """Split a unified diff into per-file hunks.

    Returns list of dicts: {path, old_lines, new_lines, body}
    """
    hunks: List[dict] = []
    cur_path: Optional[str] = None
    cur_hunk: Optional[dict] = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            continue  # new-file header, not needed
        if line.startswith("diff --git "):
            cur_path = None
            cur_hunk = None
            continue
        m = re.match(r"^--- a/(\S+)$", line)
        if m:
            cur_path = m.group(1)
            continue
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$", line)
        if m:
            old_start, old_cnt = int(m.group(1)), int(m.group(2) or 1)
            new_start, new_cnt = int(m.group(3)), int(m.group(4) or 1)
            cur_hunk = {
                "path": cur_path,
                "old_start": old_start,
                "old_count": old_cnt,
                "new_start": new_start,
                "new_count": new_cnt,
                "old_lines": [],
                "new_lines": [],
            }
            hunks.append(cur_hunk)
            continue
        if cur_hunk is None:
            continue
        if line.startswith("-"):
            cur_hunk["old_lines"].append(line[1:])
        elif line.startswith("+"):
            cur_hunk["new_lines"].append(line[1:])
        else:
            cur_hunk["old_lines"].append(line[1:])
            cur_hunk["new_lines"].append(line[1:])
    for h in hunks:
        h["body"] = diff_text  # keep full diff available
    return hunks


def get_modified_files(kernel_path: str, hexsha: str) -> List[str]:
    parent = run_git(kernel_path, "rev-parse", f"{hexsha}^").strip()
    out = run_git(kernel_path, "diff", "--name-only", parent, hexsha)
    return [p for p in out.splitlines() if p]


def extract_function_names_from_diff(diff_text: str) -> List[str]:
    """Heuristic: collect likely C function names from +/- lines.

    Used to locate which functions the patch touches (best-effort; the
    AST-based index is the authoritative source for retrieval).
    """
    names: List[str] = []
    for line in diff_text.splitlines():
        if not (line.startswith("+") or line.startswith("-")):
            continue
        body = line[1:].strip()
        if not body or body.startswith(("/*", "*", "//", "#")):
            continue
        m = re.match(
            r"^[A-Za-z_][\w\s\*]*?\b([a-z_][a-z0-9_]*)\s*\([^;]*\)\s*\{?$", body
        )
        if m and not body.startswith(("if", "for", "while", "switch", "return",
                                      "sizeof", "goto")):
            names.append(m.group(1))
    return list(dict.fromkeys(names))

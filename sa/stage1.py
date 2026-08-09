"""Stage 1: Seed Specification Extraction, Validation, Generalization.

Follows the paper Section 5.1:
1. extract    - LLM summarizes {entity, constraint} from patch (description + diff -W)
2. validate   - differential checking: pre-patch code must violate the spec,
                post-patch code must satisfy it (LLM as checker)
3. generalize - LLM abstracts the seed spec into semantic-level behavior
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

from . import git_ops, prompts
from .llm_client import LLMClient


def functions_covering_lines(source: str, line_numbers: set) -> List[dict]:
    """Use tree-sitter to find function definitions whose body covers any
    of the given 1-based line numbers. Returns [{name, start, end, code}]."""
    from . import ast_tools

    parser = ast_tools.new_parser()
    tree = parser.parse(source.encode("utf-8", errors="replace"))
    out: List[dict] = []

    def fn_name(node) -> Optional[str]:
        decl = node.child_by_field_name("declarator")
        cur = decl
        while cur is not None and cur.type != "identifier":
            if cur.type in ("pointer_declarator", "function_declarator",
                            "parenthesized_declarator"):
                cur = cur.child_by_field_name("declarator") or cur.named_children[0]
            else:
                break
        return cur.text.decode("utf-8", errors="replace") if cur else None

    def visit(node) -> None:
        if node.type == "function_definition":
            start = node.start_point[0] + 1
            end = node.end_point[0] + 1
            if any(start <= ln <= end for ln in line_numbers):
                name = fn_name(node) or f"anonymous@{start}"
                code = "\n".join(source.splitlines()[start - 1 : end])
                out.append({"name": name, "start": start, "end": end, "code": code})
            return  # do not descend into nested functions
        for child in node.named_children:
            visit(child)

    visit(tree.root_node)
    return out


class Stage1:
    def __init__(self, kernel_path: str, llm: LLMClient, verbose: bool = True):
        self.kernel = kernel_path
        self.llm = llm
        self.verbose = verbose

    # ------------------------------------------------------------------ #
    # 1a. extraction                                                    #
    # ------------------------------------------------------------------ #
    def extract_spec(self, hexsha: str, description: str = "") -> dict:
        commit_desc = description or git_ops.get_commit_description(self.kernel, hexsha)
        diff = git_ops.diff_with_function_context(self.kernel, hexsha)
        if not diff.strip():
            raise RuntimeError(f"empty diff for {hexsha}")
        user = prompts.EXTRACT_USER.format(
            commit_message=commit_desc, patch_content=diff
        )
        result = self.llm.complete_json(prompts.EXTRACT_SYSTEM, user)
        result["hexsha"] = hexsha
        result["patch_description"] = commit_desc
        result["patch_diff"] = diff
        return result

    # ------------------------------------------------------------------ #
    # 1b. validation (differential checking)                            #
    # ------------------------------------------------------------------ #
    def _patch_functions(self, hexsha: str) -> List[dict]:
        """Collect pre/post function bodies for files touched by the patch."""
        entries: List[dict] = []
        parent = f"{hexsha}^"
        for path in git_ops.get_modified_files(self.kernel, hexsha):
            if not path.endswith((".c", ".h")):
                continue
            try:
                pre_src = git_ops.get_file_at(self.kernel, parent, path)
                post_src = git_ops.get_file_at(self.kernel, hexsha, path)
            except RuntimeError:
                continue  # file added/removed by patch
            pre_hunks = [
                h
                for h in git_ops.parse_diff_hunks(
                    git_ops.diff_with_function_context(self.kernel, hexsha)
                )
                if h.get("path") == path
            ]
            pre_lines: set = set()
            post_lines: set = set()
            for h in pre_hunks:
                if h["old_count"] > 0:
                    pre_lines.update(range(h["old_start"], h["old_start"] + h["old_count"]))
                if h["new_count"] > 0:
                    post_lines.update(range(h["new_start"], h["new_start"] + h["new_count"]))
            pre_funcs = functions_covering_lines(pre_src, pre_lines)
            post_funcs = functions_covering_lines(post_src, post_lines)
            # pair by name; keep only functions present in both versions
            post_by_name = {f["name"]: f for f in post_funcs}
            for pf in pre_funcs:
                if pf["name"] in post_by_name:
                    entries.append(
                        {
                            "path": path,
                            "name": pf["name"],
                            "pre_code": pf["code"],
                            "post_code": post_by_name[pf["name"]]["code"],
                        }
                    )
        return entries

    def _check_one_version(self, spec: dict, code: str) -> dict:
        user = prompts.VALIDATE_USER.format(
            entity=spec["entity"], constraint=spec["constraint"], code=code
        )
        return self.llm.complete_json(prompts.VALIDATE_SYSTEM, user)

    def validate_spec(self, hexsha: str, spec: dict) -> dict:
        entries = self._patch_functions(hexsha)
        if not entries:
            return {"valid": False, "reason": "no patch functions found"}
        checks = []
        for entry in entries:
            pre_r = self._check_one_version(spec, entry["pre_code"])
            post_r = self._check_one_version(spec, entry["post_code"])
            checks.append(
                {
                    "function": entry["name"],
                    "path": entry["path"],
                    "pre_decision": pre_r.get("decision"),
                    "pre_reason": pre_r.get("reason", ""),
                    "post_decision": post_r.get("decision"),
                    "post_reason": post_r.get("reason", ""),
                    "pre_code": entry["pre_code"],
                    "post_code": entry["post_code"],
                }
            )
        # valid iff at least one patched function: pre violates & post satisfies
        ok = any(
            c["pre_decision"] == "yes" and c["post_decision"] == "no" for c in checks
        )
        return {"valid": ok, "checks": checks}

    # ------------------------------------------------------------------ #
    # 1c. generalization                                                #
    # ------------------------------------------------------------------ #
    def generalize_spec(self, hexsha: str, spec: dict) -> dict:
        diff = git_ops.diff_with_function_context(self.kernel, hexsha)
        user = prompts.GENERALIZE_USER.format(
            entity=spec["entity"],
            constraint=spec["constraint"],
            patch_content=diff[:12000],
        )
        result = self.llm.complete_json(prompts.GENERALIZE_SYSTEM, user)
        return result

    # ------------------------------------------------------------------ #
    # full run                                                          #
    # ------------------------------------------------------------------ #
    def run(self, seeds: List[dict], out_dir: str, workers: int = 4) -> List[dict]:
        """seeds: [{'hexsha':..., 'description':...}]
        Writes stage1_out.json with extracted / validated / generalized specs.
        Uses a small thread pool to parallelize LLM calls."""
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        os.makedirs(out_dir, exist_ok=True)
        results: List[dict] = []
        lock = threading.Lock()

        def _process(seed: dict) -> dict:
            hexsha = seed["hexsha"]
            print(f"[stage1] {hexsha} {seed.get('description','')}", flush=True)
            try:
                spec = self.extract_spec(hexsha, seed.get("description", ""))
                validation = self.validate_spec(hexsha, spec)
                spec["validation"] = validation
                if validation.get("valid"):
                    gen = self.generalize_spec(hexsha, spec)
                    spec["generalized"] = gen
                return spec
            except Exception as exc:
                print(f"[stage1] FAILED {hexsha}: {exc}", flush=True)
                return {"hexsha": hexsha, "error": str(exc)}

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_process, s) for s in seeds]
            for i, fut in enumerate(as_completed(futs)):
                with lock:
                    results.append(fut.result())
                # checkpoint every 10 completed
                with lock:
                    if len(results) % 10 == 0:
                        with open(os.path.join(out_dir, "stage1_out.json"), "w",
                                  encoding="utf-8") as f:
                            json.dump(results, f, ensure_ascii=False, indent=2)
                        print(f"[stage1] checkpoint: {len(results)}/{len(seeds)}",
                              flush=True)
        with open(os.path.join(out_dir, "stage1_out.json"), "w",
                  encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return results

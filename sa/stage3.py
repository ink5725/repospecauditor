"""Stage 3: LLM-driven Bug Detection (paper Section 5.3).

Hybrid detection:
1. AST query generation - LLM translates the entity description into an
   executable search intent (target type + identifier + aliases).
2. Candidate localization - AST-based code search collects all functions
   that involve the entity.
3. Violation checking - LLM judges per-function whether the constraint is
   violated (produces initial violation reports).
4. Report pruning - LLM re-evaluates reports with on-demand context
   (definition / usage of requested entities), up to N iterations.
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

from . import prompts
from .code_index import CodeIndex
from .llm_client import LLMClient


class Stage3:
    def __init__(
        self,
        llm: LLMClient,
        code_index: CodeIndex,
        max_prune_iters: int = 5,
        max_candidates: int = 300,
    ):
        self.llm = llm
        self.index = code_index
        self.max_prune_iters = max_prune_iters
        self.max_candidates = max_candidates

    # ------------------------------------------------------------------ #
    # 1. query generation (LLM) + 2. localization (AST)                 #
    # ------------------------------------------------------------------ #
    def generate_query(self, entity_description: str) -> dict:
        user = prompts.QUERY_USER.format(entity_description=entity_description)
        result = self.llm.complete_json(prompts.QUERY_SYSTEM, user)
        return result

    def localize(self, query: dict) -> List[str]:
        """Run the query intent against the code index -> candidate functions."""
        target_type = query.get("target_type", "unknown")
        identifier = query.get("identifier", "")
        aliases = query.get("aliases", []) or []
        names = [identifier] + [a for a in aliases if a]
        names = [n for n in names if n and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n)]
        if not names:
            return []
        candidates: List[str] = []
        if target_type == "function_call":
            for n in names:
                for caller, _, _ in self.index.callers_of(n, limit=self.max_candidates):
                    if caller and caller not in candidates:
                        candidates.append(caller)
        elif target_type == "function_definition":
            for n in names:
                loc = self.index.find_function(n)
                if loc:
                    candidates.append(n)
        else:  # struct_usage / macro_call / unknown -> body-text search
            for n in names:
                for fn in self.index.functions_containing_text(n):
                    if fn not in candidates:
                        candidates.append(fn)
        # never audit the entity's own definition twice
        return candidates[: self.max_candidates]

    # ------------------------------------------------------------------ #
    # 3. violation checking                                             #
    # ------------------------------------------------------------------ #
    def check_violation(self, spec: dict, func_name: str) -> dict:
        body = self.index.function_body(func_name)
        if body is None:
            return {"function": func_name, "decision": "no",
                    "explanation": "function body not found"}
        user = prompts.VIOLATION_USER.format(
            entity=spec.get("entity", ""),
            constraint=spec.get("constraint", ""),
            func_code=body,
        )
        result = self.llm.complete_json(prompts.VIOLATION_SYSTEM, user)
        result["function"] = func_name
        return result

    # ------------------------------------------------------------------ #
    # 4. report pruning (iterative context-aware review)                #
    # ------------------------------------------------------------------ #
    def prune_report(self, spec: dict, func_name: str) -> dict:
        body = self.index.function_body(func_name) or "(function not found)"
        context_history: List[str] = []
        for _ in range(self.max_prune_iters):
            user = prompts.PRUNE_USER.format(
                entity=spec.get("entity", ""),
                constraint=spec.get("constraint", ""),
                func_code=body,
                prev_context="\n".join(context_history) or "(none)",
            )
            result = self.llm.complete_json(prompts.PRUNE_SYSTEM, user)
            rtype = result.get("type", "")
            if rtype == "final_decision":
                return {
                    "function": func_name,
                    "decision": result.get("decision"),
                    "explanation": result.get("explanation", ""),
                }
            if rtype == "more_context":
                snippets = []
                raw_requests = result.get("requests", [])
                # tolerate malformed lists (e.g. "A or B or C" inside one string)
                if isinstance(raw_requests, list) and len(raw_requests) == 1 \
                        and isinstance(raw_requests[0], str):
                    raw_requests = [
                        {"request_type": "source_code", "entity_name": name}
                        for name in re.split(r"\s+or\s+", raw_requests[0])
                    ]
                for req in raw_requests[:3]:
                    ename = req.get("entity_name", "") if isinstance(req, dict) else ""
                    rtype_ = req.get("request_type", "") if isinstance(req, dict) else ""
                    if not ename or ename == func_name:
                        continue
                    if rtype_ == "source_code":
                        code = (self.index.function_body(ename)
                                or self.index.struct_body(ename)
                                or f"(definition of {ename} not found)")
                    else:  # usage_code
                        usages = self.index.usage_examples(ename, k=3)
                        code = "\n".join(
                            f"--- {c} ({f}:{l}) ---\n{b}" for c, f, l, b in usages
                        ) or f"(usages of {ename} not found)"
                    snippets.append(f"[{rtype_} of {ename}]\n{code[:4000]}")
                if not snippets:
                    # no requestable entity left -> fall back to final decision
                    return {
                        "function": func_name,
                        "decision": result.get("decision", "no"),
                        "explanation": "no more context could be fetched: "
                        + result.get("explanation", ""),
                    }
                context_history.extend(snippets)
                continue
            # unexpected type -> stop
            return {
                "function": func_name,
                "decision": result.get("decision", "no"),
                "explanation": result.get("explanation", ""),
            }
        return {
            "function": func_name,
            "decision": "no",
            "explanation": "pruning iteration limit reached; report discarded",
        }

    # ------------------------------------------------------------------ #
    # full run                                                          #
    # ------------------------------------------------------------------ #
    def run(
        self,
        specs: List[dict],
        out_dir: str,
        spec_key: str = "concretized_specification",
        run_pruning: bool = True,
    ) -> List[dict]:
        """specs: list of dicts each containing a specification with
        'entity' / 'constraint' (nested under spec_key if provided)."""
        os.makedirs(out_dir, exist_ok=True)
        reports = []
        for spec_row in specs:
            spec = spec_row.get(spec_key) if spec_key else spec_row
            if not spec or not spec.get("entity"):
                continue
            print(f"[stage3] spec: {spec.get('entity', '')[:80]} ...")
            try:
                query = self.generate_query(spec["entity"])
            except Exception as exc:
                print(f"[stage3] query generation failed: {exc}")
                continue
            print(f"[stage3] query: {query.get('target_type')} "
                  f"{query.get('identifier')}")
            candidates = self.localize(query)
            print(f"[stage3] {len(candidates)} candidate functions")
            for fn in candidates[:80]:  # cap per spec for small-scale runs
                try:
                    check = self.check_violation(spec, fn)
                except Exception as exc:
                    print(f"[stage3] check {fn} failed: {exc}")
                    continue
                if check.get("decision") != "yes":
                    continue
                report = {
                    "spec_entity": spec.get("entity"),
                    "spec_constraint": spec.get("constraint"),
                    "source_spec": spec_row.get("seed_entity")
                    or spec_row.get("generalized_entity"),
                    "function": fn,
                    "initial_explanation": check.get("explanation", ""),
                }
                if run_pruning:
                    try:
                        pruned = self.prune_report(spec, fn)
                        report["pruned_decision"] = pruned.get("decision")
                        report["pruned_explanation"] = pruned.get("explanation", "")
                    except Exception as exc:
                        report["pruned_decision"] = "error"
                        report["pruned_explanation"] = str(exc)
                reports.append(report)
                print(f"[stage3] report: {fn} "
                      f"(pruned={report.get('pruned_decision','-')})")
        with open(os.path.join(out_dir, "stage3_reports.json"), "w",
                  encoding="utf-8") as f:
            json.dump(reports, f, ensure_ascii=False, indent=2)
        kept = [r for r in reports
                if r.get("pruned_decision") != "no" and r.get("pruned_decision") != "error"]
        print(f"[stage3] {len(reports)} initial reports, "
              f"{len(kept)} kept after pruning")
        return reports

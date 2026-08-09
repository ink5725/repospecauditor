"""Stage 2: Specification Generation (paper Section 5.2).

1. discovery  - embed the generalized behavior description, retrieve
                semantically similar entities from the doc corpus
                (top-k = 100, similarity threshold 0.35)
2. generation - for each candidate, fetch implementation + up to 5 usage
                examples, ask the LLM whether the constraint applies and
                concretize a new specification if it does
"""
from __future__ import annotations

import json
import os
import random
import re
from typing import Dict, List, Optional

from . import prompts
from .code_index import CodeIndex
from .embedding import EmbeddingClient
from .llm_client import LLMClient
from .vector_store import VectorStore

_STOP_WORDS = {
    "the", "a", "an", "of", "to", "in", "for", "and", "or", "with", "on",
    "is", "are", "be", "by", "that", "this", "it", "from", "as", "at",
    "function", "call", "calls", "called", "must", "should", "its", "their",
    "struct", "structure", "pointer", "return", "returns", "code", "data",
    "memory", "resource", "when", "before", "after", "using", "use", "used",
    "all", "any", "each", "value", "values", "via", "not", "if", "then",
    "such", "into", "out", "over", "under", "between", "while", "also",
    "may", "can", "will", "has", "have", "had", "been", "being", "does",
    "which", "who", "whom", "whose", "what", "where", "how", "why", "than",
    "too", "very", "just", "only", "more", "most", "less", "least", "some",
}


def extract_identifiers(text: str) -> List[str]:
    """Best-effort extraction of C identifiers from a natural-language
    entity description (e.g. "A call to function kzalloc" -> kzalloc)."""
    found = []
    for m in re.finditer(r"\b([a-z_][a-z0-9_]{2,})\s*\(", text):
        name = m.group(1)
        if name not in _STOP_WORDS and name not in found:
            found.append(name)
    for m in re.finditer(r"\b(?:function|struct|macro|call to)\s+"
                         r"([a-z_][a-z0-9_]{2,})\b", text, re.I):
        name = m.group(1)
        if name not in _STOP_WORDS and name not in found:
            found.append(name)
    return found


class Stage2:
    def __init__(
        self,
        llm: LLMClient,
        embedding: EmbeddingClient,
        store: VectorStore,
        code_index: CodeIndex,
        top_k: int = 100,
        threshold: float = 0.35,
        usage_examples: int = 5,
    ):
        self.llm = llm
        self.embedding = embedding
        self.store = store
        self.index = code_index
        self.top_k = top_k
        self.threshold = threshold
        self.usage_examples = usage_examples

    # ------------------------------------------------------------------ #
    # discovery                                                         #
    # ------------------------------------------------------------------ #
    def discover_candidates(
        self, generalized_spec: dict, exclude: set
    ) -> List[dict]:
        # use the behavior description (entity) as the query; appending the
        # full constraint dilutes semantic focus (verified empirically)
        query_text = generalized_spec.get("generalized_entity", "").strip()
        if len(query_text) < 30:
            query_text = (
                f"{query_text} "
                f"{generalized_spec.get('generalized_constraint', '')}"
            ).strip()
        qvec = self.embedding.embed(query_text)
        hits = self.store.search(qvec, top_k=self.top_k, threshold=self.threshold)
        candidates = []
        for vid, meta, score in hits:
            name = meta.get("name", vid)
            if name in exclude:
                continue
            candidates.append(
                {
                    "id": vid,
                    "name": name,
                    "type": meta.get("type", ""),
                    "description": meta.get("description", ""),
                    "score": score,
                }
            )
        return candidates

    # ------------------------------------------------------------------ #
    # context extraction                                                #
    # ------------------------------------------------------------------ #
    def _entity_context(self, entity: dict) -> Dict[str, str]:
        name = entity["name"]
        etype = entity.get("type", "")
        src = ""
        if etype == "struct":
            src = self.index.struct_body(name) or ""
        else:
            src = self.index.function_body(name) or ""
        usages = self.index.usage_examples(name, k=self.usage_examples)
        usage_txt = ""
        for caller, file, line, body in usages:
            usage_txt += f"--- usage in {caller} ({file}:{line}) ---\n{body}\n\n"
        return {"source": src, "usages": usage_txt}

    # ------------------------------------------------------------------ #
    # generation                                                        #
    # ------------------------------------------------------------------ #
    def generate_for_entity(
        self, generalized_spec: dict, seed_spec: dict, entity: dict
    ) -> dict:
        ctx = self._entity_context(entity)
        user = prompts.GENERATE_USER.format(
            generalized_entity=generalized_spec.get("generalized_entity", ""),
            generalized_constraint=generalized_spec.get("generalized_constraint", ""),
            seed_entity=seed_spec.get("entity", ""),
            seed_constraint=seed_spec.get("constraint", ""),
            entity_description=entity.get("description", "")[:2000],
            entity_source=ctx["source"][:6000] or "(definition not found)",
            entity_usages=ctx["usages"][:8000] or "(no usage examples found)",
        )
        result = self.llm.complete_json(prompts.GENERATE_SYSTEM, user)
        result["entity_name"] = entity["name"]
        result["entity_type"] = entity.get("type", "")
        result["similarity_score"] = entity.get("score", 0.0)
        return result

    # ------------------------------------------------------------------ #
    # full run                                                          #
    # ------------------------------------------------------------------ #
    def run(
        self, stage1_results: List[dict], out_dir: str, exclude_names: set,
        workers: int = 4, max_per_seed: int = 25,
    ) -> List[dict]:
        """Run generation with a small thread pool to parallelize LLM calls."""
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        os.makedirs(out_dir, exist_ok=True)
        all_generated = []
        lock = threading.Lock()
        for spec in stage1_results:
            hexsha = spec.get("hexsha", "")
            gen = spec.get("generalized")
            if not gen or not spec.get("validation", {}).get("valid"):
                continue
            print(f"[stage2] {hexsha}: discovering candidates ...", flush=True)
            candidates = self.discover_candidates(gen, exclude_names)
            print(f"[stage2] {hexsha}: {len(candidates)} candidates", flush=True)

            def _process(cand):
                try:
                    res = self.generate_for_entity(gen, spec, cand)
                    if (res.get("judgment") == "yes"
                            and res.get("concretized_specification")):
                        with lock:
                            all_generated.append(
                                {
                                    "seed_hexsha": hexsha,
                                    "seed_entity": spec.get("entity"),
                                    "seed_constraint": spec.get("constraint"),
                                    "generalized_entity": gen.get("generalized_entity"),
                                    "generalized_constraint": gen.get(
                                        "generalized_constraint"
                                    ),
                                    "candidate": cand["name"],
                                    "candidate_type": cand["type"],
                                    "similarity_score": cand["score"],
                                    "reason": res.get("reason", ""),
                                    "concretized_specification": res[
                                        "concretized_specification"
                                    ],
                                }
                            )
                except Exception as exc:
                    print(f"[stage2] {hexsha} {cand['name']} failed: "
                          f"{str(exc)[:100]}", flush=True)

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = [pool.submit(_process, c) for c in candidates[:max_per_seed]]
                for _ in as_completed(futs):
                    pass
            # checkpoint after each seed
            with open(os.path.join(out_dir, "stage2_out.json"), "w",
                      encoding="utf-8") as f:
                json.dump(all_generated, f, ensure_ascii=False, indent=2)
            print(f"[stage2] {hexsha}: {len(all_generated)} specs so far",
                  flush=True)
        return all_generated

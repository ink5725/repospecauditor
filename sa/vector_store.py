"""Lightweight vector store backed by numpy.

Implements the retrieval scheme described in the paper:
- embeddings are L2-normalized
- distance = L2 distance on normalized vectors
- similarity score = 1 - distance (as used in the paper)
- top-k retrieval with a similarity threshold
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np


class VectorStore:
    def __init__(self, persist_dir: Optional[str] = None):
        self.persist_dir = persist_dir
        self._ids: List[str] = []
        self._metas: List[dict] = []
        self._matrix: Optional[np.ndarray] = None  # (N, D) float32 normalized
        if persist_dir:
            os.makedirs(persist_dir, exist_ok=True)
            self._load()

    # ------------------------------------------------------------------ #
    @property
    def size(self) -> int:
        return len(self._ids)

    def add(self, ids: List[str], metas: List[dict], vectors: List[np.ndarray]) -> None:
        new_ids, new_metas, new_vecs = [], [], []
        for i, vid in enumerate(ids):
            if vid in self._ids:
                continue
            new_ids.append(vid)
            new_metas.append(metas[i])
            new_vecs.append(vectors[i])
        self._ids.extend(new_ids)
        self._metas.extend(new_metas)
        if new_vecs:
            mat = np.stack([self._normalize(v) for v in new_vecs])
            self._matrix = (
                mat if self._matrix is None else np.vstack([self._matrix, mat])
            )
        self._save()

    def search(
        self, query_vec: np.ndarray, top_k: int = 50, threshold: float = 0.0
    ) -> List[Tuple[str, dict, float]]:
        """Return (id, meta, similarity) sorted desc, similarity >= threshold."""
        if self._matrix is None or self._matrix.shape[0] == 0:
            return []
        q = self._normalize(query_vec)
        # L2 distance on normalized vectors: d^2 = 2 - 2*cos_sim
        dists = np.linalg.norm(self._matrix - q, axis=1)
        scores = 1.0 - dists  # paper: score = 1 - distance
        order = np.argsort(scores)[::-1]
        out = []
        for idx in order[:top_k]:
            s = float(scores[idx])
            if s < threshold:
                break  # sorted descending -> rest also below
            out.append((self._ids[idx], self._metas[idx], s))
        return out

    def get_meta(self, vid: str) -> Optional[dict]:
        try:
            i = self._ids.index(vid)
        except ValueError:
            return None
        return self._metas[i]

    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize(vec: np.ndarray) -> np.ndarray:
        v = np.asarray(vec, dtype=np.float32)
        norm = np.linalg.norm(v)
        if norm == 0:
            return v
        return v / norm

    # ------------------------------------------------------------------ #
    def _save(self) -> None:
        if not self.persist_dir:
            return
        if self._matrix is not None:
            np.save(os.path.join(self.persist_dir, "matrix.npy"), self._matrix)
        with open(os.path.join(self.persist_dir, "index.json"), "w", encoding="utf-8") as f:
            json.dump(
                {"ids": self._ids, "metas": self._metas},
                f,
                ensure_ascii=False,
            )

    def _load(self) -> None:
        mat_path = os.path.join(self.persist_dir, "matrix.npy")
        idx_path = os.path.join(self.persist_dir, "index.json")
        if not (os.path.exists(mat_path) and os.path.exists(idx_path)):
            return
        self._matrix = np.load(mat_path)
        with open(idx_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._ids = data["ids"]
        self._metas = data["metas"]

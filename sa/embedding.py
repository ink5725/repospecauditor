"""Embedding client (OpenAI-compatible embeddings endpoint).

Paper uses BAAI/bge-large-en-v1.5 through SiliconFlow's API. We support any
OpenAI-compatible embeddings endpoint and cache results on disk.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import List, Optional

import numpy as np
import requests


class EmbeddingClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        cache_dir: Optional[str] = None,
        timeout: int = 120,
        max_retries: int = 4,
        local: bool = False,
    ):
        self.base_url = (
            base_url or os.environ.get("EMBEDDING_BASE_URL", "")
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("EMBEDDING_API_KEY", "")
        self.model = model or os.environ.get("EMBEDDING_MODEL", "")
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_dir = cache_dir
        # local backend when no API is configured or explicitly requested
        self.local = local or (not self.base_url)
        self._local_model = None
        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    def _get_local_model(self):
        if self._local_model is None:
            from sentence_transformers import SentenceTransformer
            name = self.model or "BAAI/bge-large-en-v1.5"
            print(f"[embed] loading local model {name} (first use may take a while)")
            self._local_model = SentenceTransformer(name)
        return self._local_model

    def _embed_local(self, texts: List[str]) -> List[np.ndarray]:
        model = self._get_local_model()
        # inputs already truncated in embed/embed_batch
        vecs = model.encode(texts, normalize_embeddings=True,
                            show_progress_bar=False, batch_size=32)
        return [np.asarray(v, dtype=np.float32) for v in vecs]

    # ------------------------------------------------------------------ #
    def _endpoint(self) -> str:
        if self.base_url.endswith("/embeddings"):
            return self.base_url
        return f"{self.base_url}/embeddings"

    @staticmethod
    def _truncate(text: str, max_chars: int = 2048) -> str:
        """Truncate inputs to approx 512 tokens (4 chars/token) for the
        local bge model; long inputs are dramatically slower to embed."""
        if len(text) > max_chars:
            return text[:max_chars]
        return text

    def _cache_path(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
        return os.path.join(self.cache_dir, f"{digest}.npy")

    def embed(self, text: str) -> np.ndarray:
        """Embed a single text, returning a float32 vector (normalized)."""
        text = self._truncate(text)
        if self.cache_dir:
            path = self._cache_path(text)
            if os.path.exists(path):
                return np.load(path)
        vec = self._embed_batch([text])[0]
        if self.cache_dir:
            np.save(self._cache_path(text), vec)
        return vec

    def embed_batch(self, texts: List[str], batch_size: int = 64) -> List[np.ndarray]:
        """Embed a list of texts with batching + disk caching."""
        texts = [self._truncate(t) for t in texts]
        results: List[Optional[np.ndarray]] = [None] * len(texts)
        pending: List[int] = []
        if self.cache_dir:
            for i, t in enumerate(texts):
                path = self._cache_path(t)
                if os.path.exists(path):
                    results[i] = np.load(path)
                else:
                    pending.append(i)
        else:
            pending = list(range(len(texts)))
        for start in range(0, len(pending), batch_size):
            chunk = pending[start : start + batch_size]
            vecs = self._embed_batch([texts[i] for i in chunk])
            for i, v in zip(chunk, vecs):
                results[i] = v
                if self.cache_dir:
                    np.save(self._cache_path(texts[i]), v)
        return [r for r in results if r is not None]

    # ------------------------------------------------------------------ #
    def _embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        if self.local:
            return self._embed_local(texts)
        try:
            return self._embed_api(texts)
        except RuntimeError as exc:
            print(f"[embed] API failed ({exc}); falling back to local model")
            return self._embed_local(texts)

    # ------------------------------------------------------------------ #
    def _embed_api(self, texts: List[str]) -> List[np.ndarray]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {"model": self.model, "input": texts}
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(
                    self._endpoint(), headers=headers, json=payload, timeout=self.timeout
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = sorted(data["data"], key=lambda d: d["index"])
                    return [np.asarray(it["embedding"], dtype=np.float32) for it in items]
                if resp.status_code in (429, 500, 502, 503):
                    time.sleep(2 ** attempt + 1)
                    last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    continue
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")
            except requests.RequestException as exc:
                last_err = exc
                time.sleep(2 ** attempt + 1)
        raise RuntimeError(f"Embedding request failed: {last_err}")

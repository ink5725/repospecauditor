"""LLM client wrapper with OpenAI-compatible interface.

Provides:
- chat completion with temperature=0 and JSON-friendly output
- robust JSON extraction from model responses
- retry on rate-limit / transient errors
- token usage statistics
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Optional

import requests


class LLMError(RuntimeError):
    pass


class LLMClient:
    """Minimal OpenAI-compatible chat client (no SDK dependency)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_retries: int = 5,
        timeout: int = 120,
    ):
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        self.model = model or os.environ.get("LLM_MODEL", "")
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = timeout
        if not self.base_url:
            raise LLMError("LLM base_url is not configured (set LLM_BASE_URL)")
        if not self.api_key:
            raise LLMError("LLM api_key is not configured (set LLM_API_KEY)")
        if not self.model:
            raise LLMError("LLM model is not configured (set LLM_MODEL)")
        # input_tokens / output_tokens cumulative counters
        self.input_tokens = 0
        self.output_tokens = 0
        self.request_count = 0

    # ------------------------------------------------------------------ #
    def _endpoint(self) -> str:
        # accept either .../chat/completions or a bare v1 base
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _post(self, payload: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(
                    self._endpoint(), headers=headers, json=payload, timeout=self.timeout
                )
                if resp.status_code == 200:
                    return resp.json()
                # transient / capacity errors -> retry with backoff
                if resp.status_code in (429, 500, 502, 503, 529):
                    wait = 2 ** attempt + 1
                    time.sleep(wait)
                    last_err = LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    continue
                raise LLMError(f"HTTP {resp.status_code}: {resp.text[:400]}")
            except requests.RequestException as exc:  # network level
                last_err = exc
                time.sleep(2 ** attempt + 1)
        raise LLMError(f"LLM request failed after retries: {last_err}")

    # ------------------------------------------------------------------ #
    def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: Optional[float] = None,
    ) -> str:
        """Single chat completion, returns raw text content."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        data = self._post(payload)
        self.request_count += 1
        usage = data.get("usage", {})
        self.input_tokens += int(usage.get("prompt_tokens", 0))
        self.output_tokens += int(usage.get("completion_tokens", 0))
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected response shape: {str(data)[:300]}") from exc
        return content or ""

    def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: Optional[float] = None,
    ) -> dict:
        """Chat completion parsed as a JSON object (robust)."""
        raw = self.complete(system, user, max_tokens=max_tokens, temperature=temperature)
        obj = extract_json_object(raw)
        if obj is None:
            raise LLMError(f"Could not parse JSON from model output: {raw[:500]}")
        return obj

    # ------------------------------------------------------------------ #
    def usage_summary(self) -> dict:
        return {
            "requests": self.request_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
        }


def extract_json_object(text: str) -> Optional[Any]:
    """Best-effort JSON extraction: code fences -> first balanced {...}."""
    if not text:
        return None
    # 1) try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 2) strip markdown code fences
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    # 3) locate the first balanced {...} region (handles stray prose)
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None

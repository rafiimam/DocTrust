"""Reader providers.

A Reader reads one field from one document image under a named perturbation
("original", "zoom", "contrast", "stamp_masked"). The agent loop depends
only on this interface; provider choice is configuration:

- MetaReader — Muse Spark (muse-spark-1.3 by default) via the Meta
  Model API (api.meta.ai), OpenAI-compatible chat completions with
  Bearer auth. Needs MODEL_API_KEY; model override via META_MODEL.
- BasetenReader — Muse Spark Open (meta-models/muse-spark-open-1026) via
  Baseten's OpenAI-compatible chat completions API. Needs BASETEN_API_KEY.
- MockReader — deterministic stand-in for tests and offline development.
  Scripted per (doc_type, field): a list of values returned in order, so a
  test can script disagreement ("reads differ under perturbation") exactly.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Protocol

MODEL_ID = "meta-models/muse-spark-open-1026"
BASETEN_URL = "https://model-apis.baseten.net/v1/chat/completions"

META_URL = "https://api.meta.ai/v1/chat/completions"
META_MODEL_ID = "muse-spark-1.3"

READ_PROMPT = (
    "You are reading one field from a Bangladeshi identity document image. "
    "Return only the field's value as printed. For names, return the name "
    "transliterated into Latin letters. Keep digits exactly as printed "
    "(Bangla or Latin). If the field is not visible or not legible, "
    "return exactly: UNREADABLE"
)


class Reader(Protocol):
    def read_field(self, image_path: str, doc_type: str, field: str,
                   perturbation: str) -> str:
        ...


def _read_payload(model: str, image_path: str, doc_type: str, field: str,
                  perturbation: str, max_tokens: int = 128,
                  reasoning_effort: str | None = None) -> dict:
    """The chat-completions payload shared by both live providers.

    Both endpoints are OpenAI-compatible and accept the same image
    input shape (an image_url content part carrying a data URL), so
    only the URL, auth header, model id and generation knobs differ
    between them. ``reasoning_effort`` is only included when set —
    BasetenReader leaves it (and the max_tokens default) untouched.
    """
    image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text",
                 "text": f"{READ_PROMPT}\nField: {field} "
                         f"(document: {doc_type}, view: {perturbation})"},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ],
        }],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    return payload


class MockReader:
    def __init__(self, script: dict[tuple[str, str], list[str]]):
        self._script = {k: list(v) for k, v in script.items()}
        self.calls: list[tuple[str, str, str]] = []

    def read_field(self, image_path: str, doc_type: str, field: str,
                   perturbation: str) -> str:
        self.calls.append((doc_type, field, perturbation))
        queue = self._script.get((doc_type, field))
        if not queue:
            return "UNREADABLE"
        if len(queue) > 1:
            return queue.pop(0)
        return queue[0]


class BasetenReader:
    # UNVERIFIED — recheck when the Baseten key arrives: this reader
    # still uses max_tokens=128. Muse Spark is a reasoning model, and
    # on the Meta Model API a 128-token budget is entirely consumed by
    # reasoning, returning finish_reason="length" and null content
    # (see MetaReader, which defaults to 1024 + reasoning_effort
    # "minimal"). If the Baseten-served open model reasons the same
    # way, this reader will need the same headroom. Behaviour is
    # intentionally left unchanged until it can be verified live.
    def __init__(self, api_key: str | None = None, model: str = MODEL_ID):
        self.api_key = api_key or os.environ.get("BASETEN_API_KEY", "")
        self.model = model

    def read_field(self, image_path: str, doc_type: str, field: str,
                   perturbation: str) -> str:
        import httpx  # deferred so tests never need the network stack

        payload = _read_payload(self.model, image_path, doc_type, field,
                                perturbation)
        resp = httpx.post(
            BASETEN_URL,
            headers={"Authorization": f"Api-Key {self.api_key}"},
            json=payload, timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


class MetaReader:
    """Muse Spark via the Meta Model API (https://api.meta.ai/v1).

    OpenAI-compatible chat completions, Bearer auth with the key from
    MODEL_API_KEY. The model defaults to muse-spark-1.3 and can be
    overridden with the META_MODEL environment variable (or the
    ``model`` argument).

    Calibration (verified live against the real API, 2026-10-27):
    Muse Spark is a REASONING model — the completion budget is spent
    on reasoning before any answer text is produced. With
    max_tokens=128 every call returned finish_reason="length" and
    null content. The working configuration is max_tokens=1024 AND
    reasoning_effort="minimal": finish_reason="stop", exact reads,
    ~69 completion tokens (~56 of them reasoning), ~1,000 total
    tokens and ~10 s per field read. Do NOT "optimise" max_tokens
    back down — that silently turns every read into a null. Both
    knobs are configurable: META_MAX_TOKENS / META_REASONING_EFFORT
    env vars, or the constructor arguments of the same names.
    """

    def __init__(self, api_key: str | None = None,
                 model: str | None = None,
                 max_tokens: int | None = None,
                 reasoning_effort: str | None = None):
        self.api_key = api_key or os.environ.get("MODEL_API_KEY", "")
        self.model = model or os.environ.get("META_MODEL", META_MODEL_ID)
        try:
            self.max_tokens = int(
                max_tokens or os.environ.get("META_MAX_TOKENS", "1024"))
        except (TypeError, ValueError):
            self.max_tokens = 1024
        self.reasoning_effort = (
            reasoning_effort
            or os.environ.get("META_REASONING_EFFORT", "minimal"))

    def read_field(self, image_path: str, doc_type: str, field: str,
                   perturbation: str) -> str:
        import httpx  # deferred so tests never need the network stack

        payload = _read_payload(
            self.model, image_path, doc_type, field, perturbation,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort)
        try:
            resp = httpx.post(
                META_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload, timeout=60,
            )
        except httpx.HTTPError as exc:
            # Transport failure: the exception text carries no key
            # material (the key only ever travels in the header).
            raise RuntimeError(
                f"Meta Model API request failed: {exc}") from exc
        if resp.status_code >= 400:
            excerpt = " ".join((resp.text or "").split())[:200]
            raise RuntimeError(
                f"Meta Model API returned HTTP {resp.status_code}: "
                f"{excerpt}")
        choice = resp.json()["choices"][0]
        content = choice["message"]["content"]
        if content is None:
            # The classic reasoning-budget failure: the whole budget
            # went to reasoning and no answer was produced.
            raise RuntimeError(
                "Meta Model API returned no content "
                f"(finish_reason={choice.get('finish_reason')!r}); the "
                "completion budget was likely consumed by reasoning — "
                "raise META_MAX_TOKENS or keep META_REASONING_EFFORT "
                "at 'minimal'.")
        return content.strip()

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
                  perturbation: str) -> dict:
    """The chat-completions payload shared by both live providers.

    Both endpoints are OpenAI-compatible and accept the same image
    input shape (an image_url content part carrying a data URL), so
    only the URL, auth header and model id differ between them.
    """
    image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    return {
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
        "max_tokens": 128,
        "temperature": 0.0,
    }


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
    """

    def __init__(self, api_key: str | None = None,
                 model: str | None = None):
        self.api_key = api_key or os.environ.get("MODEL_API_KEY", "")
        self.model = model or os.environ.get("META_MODEL", META_MODEL_ID)

    def read_field(self, image_path: str, doc_type: str, field: str,
                   perturbation: str) -> str:
        import httpx  # deferred so tests never need the network stack

        payload = _read_payload(self.model, image_path, doc_type, field,
                                perturbation)
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
        return resp.json()["choices"][0]["message"]["content"].strip()

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

Readers may also act as the investigation *planner* (see Planner):
when a field is unsettled, the agent loop asks the planner which
investigation step to run next. The planner chooses where to look —
it never decides a field's value or a verdict; the deterministic
comparator keeps that authority. Both live readers implement it
against the same chat endpoints as their reads.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Protocol

MODEL_ID = "meta-models/muse-spark-open-1026"
# Baseten's documented chat-completions route for the hackathon's
# Muse Spark Open grant. Dedicated deployments are served from the
# model-apis host instead; the BASETEN_URL environment variable
# overrides this default without a code change (see BasetenReader).
BASETEN_URL = "https://inference.baseten.co/v1/chat/completions"

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


class Planner(Protocol):
    """Optional reader capability: direct the investigation of one
    unsettled field. The agent loop uses it opportunistically (a
    reader without it — or one whose call fails — simply means the
    deterministic fallback sequence runs).

    ``reads`` is the field's reads so far, [{"view", "value"}, ...];
    ``actions`` maps each offered action name to a one-line
    description. Returns {"action": <one of the offered names>,
    "reason": <one short sentence>}. Any exception is a planner
    failure as far as the agent is concerned.
    """

    def plan_investigation(self, image_path: str, doc_type: str,
                           field: str, reads: list[dict],
                           actions: dict[str, str]) -> dict:
        ...


PLANNER_PROMPT = (
    "You are the investigation planner for a document-review agent. "
    "One field of one document could not be settled by the reads "
    "listed below. Choose the single most useful next investigation "
    "step from the offered actions. You choose where to look next — "
    "you never decide the field's value or whether documents agree; "
    "a deterministic comparator makes every verdict. Reply with ONLY "
    "a JSON object of the form {\"action\": \"<action name>\", "
    "\"reason\": \"<one short sentence>\"} — no prose, no code "
    "fences, nothing else."
)


def _plan_payload(model: str, image_path: str, doc_type: str, field: str,
                  reads: list[dict], actions: dict[str, str],
                  max_tokens: int = 1024,
                  reasoning_effort: str | None = None) -> dict:
    """The planner chat-completions payload: same image-input shape
    as a field read, but the text asks for the next investigation
    step as strict JSON instead of a field value."""
    image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    read_lines = "\n".join(f"- {r['view']}: {r['value']}" for r in reads)
    if not read_lines:
        read_lines = "- (no reads yet)"
    action_lines = "\n".join(f"- {name}: {desc}"
                             for name, desc in actions.items())
    text = (f"{PLANNER_PROMPT}\nDocument: {doc_type}\nField: {field}\n"
            f"Reads so far:\n{read_lines}\n"
            f"Available actions:\n{action_lines}")
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": text},
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


def _parse_plan(content: str) -> dict:
    """Parse a planner reply into {"action", "reason"}.

    The prompt demands a bare JSON object; a surrounding code fence
    is tolerated, anything else unparseable raises ValueError — the
    agent treats every planner failure alike and falls back to its
    fixed investigation sequence. Whether the action is one of the
    offered ones is the agent's check, not this parser's.
    """
    text = content.strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines()
                         if not line.strip().startswith("```")).strip()
    try:
        decision = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"planner reply was not a JSON object: {text[:120]!r}") from exc
    if not isinstance(decision, dict) or not decision.get("action"):
        raise ValueError(
            f"planner reply has no action: {text[:120]!r}")
    return {"action": str(decision["action"]),
            "reason": str(decision.get("reason") or "")}


def _post_planner(url: str, headers: dict, payload: dict,
                  label: str) -> dict:
    """POST one planner call and parse its decision.

    ``label`` ("Meta Model API" / "Baseten") prefixes every error, in
    the same style as the readers' own errors; the API key travels
    only in the header and never appears in an error message. Every
    failure raises — RuntimeError for transport/HTTP/shape problems,
    ValueError for an unparseable decision.
    """
    import httpx  # deferred so tests never need the network stack

    try:
        resp = httpx.post(url, headers=headers, json=payload, timeout=60)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"{label} planner request failed: {exc}") from exc
    if resp.status_code >= 400:
        excerpt = " ".join((resp.text or "").split())[:200]
        raise RuntimeError(
            f"{label} planner returned HTTP {resp.status_code}: {excerpt}")
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(
            f"{label} planner returned no choices — unexpected "
            f"response shape: {str(data)[:200]}")
    choice = choices[0]
    content = (choice.get("message") or {}).get("content")
    if content is None or not content.strip():
        raise RuntimeError(
            f"{label} planner returned no content "
            f"(finish_reason={choice.get('finish_reason')!r}); the "
            "completion budget was likely consumed by reasoning.")
    return _parse_plan(content)


def _read_payload(model: str, image_path: str, doc_type: str, field: str,
                  perturbation: str, max_tokens: int = 128,
                  reasoning_effort: str | None = None) -> dict:
    """The chat-completions payload shared by both live providers.

    Both endpoints are OpenAI-compatible and accept the same image
    input shape (an image_url content part carrying a data URL), so
    only the URL, auth header, model id and generation knobs differ
    between them. ``reasoning_effort`` is only included when set —
    BasetenReader leaves it unset but passes its own max_tokens.
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
    """Scripted reader for tests.

    ``planner`` scripts plan_investigation: a list of decisions
    ({"action", "reason"} dicts, or Exception instances to raise)
    consumed in order with the last one repeating — mirroring the
    read script — or a callable invoked with the planner arguments.
    Unscripted (the default), plan_investigation raises, so the
    agent's deterministic fallback sequence is what a test exercises
    unless it scripts the planner explicitly.
    """

    def __init__(self, script: dict[tuple[str, str], list[str]],
                 planner=None):
        self._script = {k: list(v) for k, v in script.items()}
        self._planner = list(planner) if isinstance(planner, list) \
            else planner
        self.calls: list[tuple[str, str, str]] = []
        self.planner_calls: list[dict] = []

    def read_field(self, image_path: str, doc_type: str, field: str,
                   perturbation: str) -> str:
        self.calls.append((doc_type, field, perturbation))
        queue = self._script.get((doc_type, field))
        if not queue:
            return "UNREADABLE"
        if len(queue) > 1:
            return queue.pop(0)
        return queue[0]

    def plan_investigation(self, image_path: str, doc_type: str,
                           field: str, reads: list[dict],
                           actions: dict[str, str]) -> dict:
        self.planner_calls.append({
            "doc_type": doc_type, "field": field,
            "reads": [dict(r) for r in reads],
            "actions": dict(actions),
        })
        planner = self._planner
        if planner is None:
            raise RuntimeError("MockReader: no planner scripted")
        if callable(planner):
            return planner(image_path, doc_type, field, reads, actions)
        if not planner:
            raise RuntimeError("MockReader: planner script exhausted")
        item = planner.pop(0) if len(planner) > 1 else planner[0]
        if isinstance(item, BaseException):
            raise item
        return item


class BasetenReader:
    """Muse Spark Open via Baseten's OpenAI-compatible API.

    UNVERIFIED live — prepared for the verification slot once the
    Baseten hackathon key is in hand; nothing here claims results.

    The default endpoint is Baseten's documented inference route for
    the hackathon grant (https://inference.baseten.co/v1). A dedicated
    deployment on the model-apis host stays selectable via the
    BASETEN_URL environment variable (or the ``url`` argument).

    Reasoning headroom: Muse Spark Open always reasons, and on the
    Meta Model API a 128-token budget was entirely consumed by
    reasoning, returning finish_reason="length" and null content (see
    MetaReader). This reader therefore defaults to max_tokens=1024
    (override with the ``max_tokens`` argument or BASETEN_MAX_TOKENS).
    It deliberately does NOT send reasoning_effort — whether the
    Baseten endpoint accepts that parameter is unverified, so the
    budget headroom alone carries the fix. An empty or null content
    raises a clear error naming the likely cause instead of returning
    an empty string a caller could mistake for a read.
    """

    def __init__(self, api_key: str | None = None, model: str = MODEL_ID,
                 url: str | None = None, max_tokens: int | None = None):
        self.api_key = api_key or os.environ.get("BASETEN_API_KEY", "")
        self.model = model
        self.url = url or os.environ.get("BASETEN_URL") or BASETEN_URL
        try:
            self.max_tokens = int(
                max_tokens or os.environ.get("BASETEN_MAX_TOKENS", "1024"))
        except (TypeError, ValueError):
            self.max_tokens = 1024

    def read_field(self, image_path: str, doc_type: str, field: str,
                   perturbation: str) -> str:
        import httpx  # deferred so tests never need the network stack

        payload = _read_payload(self.model, image_path, doc_type, field,
                                perturbation, max_tokens=self.max_tokens)
        try:
            resp = httpx.post(
                self.url,
                headers={"Authorization": f"Api-Key {self.api_key}"},
                json=payload, timeout=60,
            )
        except httpx.HTTPError as exc:
            # Transport failure: the exception text carries no key
            # material (the key only ever travels in the header).
            raise RuntimeError(
                f"Baseten request failed: {exc}") from exc
        if resp.status_code >= 400:
            excerpt = " ".join((resp.text or "").split())[:200]
            raise RuntimeError(
                f"Baseten returned HTTP {resp.status_code}: {excerpt}")
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(
                "Baseten returned no choices — unexpected response "
                f"shape: {str(data)[:200]}")
        choice = choices[0]
        content = (choice.get("message") or {}).get("content")
        if content is None or not content.strip():
            # The reasoning-budget failure mode (or a response shape
            # this parser does not understand): never surface it as
            # an empty read.
            raise RuntimeError(
                "Baseten returned no content "
                f"(finish_reason={choice.get('finish_reason')!r}); "
                "Muse Spark Open always reasons, so the completion "
                "budget was likely consumed by reasoning — raise "
                "BASETEN_MAX_TOKENS — or the response shape was "
                "unexpected.")
        return content.strip()

    def plan_investigation(self, image_path: str, doc_type: str,
                           field: str, reads: list[dict],
                           actions: dict[str, str]) -> dict:
        """Planner call on the same endpoint/budget as the reads
        (no reasoning_effort — see the class docstring)."""
        payload = _plan_payload(self.model, image_path, doc_type, field,
                                reads, actions,
                                max_tokens=self.max_tokens)
        return _post_planner(
            self.url, {"Authorization": f"Api-Key {self.api_key}"},
            payload, "Baseten")


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

    def plan_investigation(self, image_path: str, doc_type: str,
                           field: str, reads: list[dict],
                           actions: dict[str, str]) -> dict:
        """Planner call on the same endpoint and reasoning
        calibration as the reads (max_tokens 1024,
        reasoning_effort "minimal" by default)."""
        payload = _plan_payload(
            self.model, image_path, doc_type, field, reads, actions,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort)
        return _post_planner(
            META_URL, {"Authorization": f"Bearer {self.api_key}"},
            payload, "Meta Model API")

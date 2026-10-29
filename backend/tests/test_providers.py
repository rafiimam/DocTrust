"""Provider tests: MetaReader (Meta Model API) + resolve_reader wiring.

Everything is offline: httpx.post is monkeypatched with a fake that
captures the request and returns a canned response, so URL, auth
header, payload shape, response parsing and error handling are all
exercised without a network or a real API key.
"""

import base64

import httpx
import pytest

from app import judge as judge_module
from app.providers import (META_URL, BasetenReader, MetaReader,
                           MockReader)

# A 1x1 transparent PNG; read_field only needs *some* image bytes.
_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "Xw8AAwMCAO+ip1sAAAAASUVORK5CYII=")


@pytest.fixture()
def image_path(tmp_path):
    path = tmp_path / "nid.png"
    path.write_bytes(_PNG_BYTES)
    return str(path)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(
                f"fake response has HTTP {self.status_code}")


def _chat_payload(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _install_fake_post(monkeypatch, response):
    """Replace httpx.post; returns the list of captured call kwargs."""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers or {},
                      "json": json, "timeout": timeout})
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


# --- MetaReader request shape ------------------------------------------------

def test_meta_reader_posts_to_meta_url_with_bearer_auth(
        monkeypatch, image_path):
    calls = _install_fake_post(
        monkeypatch, _FakeResponse(200, _chat_payload("  12/03/1990 \n")))
    reader = MetaReader(api_key="test-key-123")
    got = reader.read_field(image_path, "nid", "dob", "original")

    assert got == "12/03/1990"  # response text extracted + stripped
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == META_URL
    assert call["url"] == "https://api.meta.ai/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer test-key-123"
    assert call["json"]["model"] == "muse-spark-1.3"  # default model
    # Reasoning-model calibration: the budget must leave room for the
    # reasoning *and* the answer (see MetaReader docstring).
    assert call["json"]["max_tokens"] == 1024
    assert call["json"]["reasoning_effort"] == "minimal"


def test_meta_reader_image_payload_shape(monkeypatch, image_path):
    calls = _install_fake_post(
        monkeypatch, _FakeResponse(200, _chat_payload("Abdul Karim")))
    MetaReader(api_key="k").read_field(
        image_path, "bank_form", "father_name", "zoom")

    content = calls[0]["json"]["messages"][0]["content"]
    text_part, image_part = content[0], content[1]
    assert text_part["type"] == "text"
    assert "father_name" in text_part["text"]
    assert "bank_form" in text_part["text"]
    assert image_part["type"] == "image_url"
    url = image_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == _PNG_BYTES


def test_meta_reader_model_env_override_and_constructor_arg(
        monkeypatch, image_path):
    monkeypatch.setenv("META_MODEL", "muse-spark-1.1")
    monkeypatch.setenv("MODEL_API_KEY", "env-key")
    calls = _install_fake_post(
        monkeypatch, _FakeResponse(200, _chat_payload("x")))

    reader = MetaReader()  # key + model both from env
    assert reader.api_key == "env-key"
    assert reader.model == "muse-spark-1.1"
    reader.read_field(image_path, "nid", "name", "original")
    assert calls[0]["json"]["model"] == "muse-spark-1.1"
    assert calls[0]["headers"]["Authorization"] == "Bearer env-key"

    # An explicit constructor model beats the environment.
    assert MetaReader(model="muse-spark-1.3").model == "muse-spark-1.3"


def test_meta_reader_reasoning_config_env_and_constructor(
        monkeypatch, image_path):
    monkeypatch.setenv("META_MAX_TOKENS", "2048")
    monkeypatch.setenv("META_REASONING_EFFORT", "low")
    reader = MetaReader(api_key="k")
    assert reader.max_tokens == 2048
    assert reader.reasoning_effort == "low"

    # Constructor arguments beat the environment.
    reader = MetaReader(api_key="k", max_tokens=512,
                        reasoning_effort="minimal")
    assert reader.max_tokens == 512
    assert reader.reasoning_effort == "minimal"

    # ...and the values land in the payload actually sent.
    calls = _install_fake_post(
        monkeypatch, _FakeResponse(200, _chat_payload("x")))
    reader.read_field(image_path, "nid", "name", "original")
    assert calls[0]["json"]["max_tokens"] == 512
    assert calls[0]["json"]["reasoning_effort"] == "minimal"


def test_meta_reader_null_content_raises_with_finish_reason(
        monkeypatch, image_path):
    # What the API returns when the budget is eaten by reasoning:
    # finish_reason "length", content null. Must not crash with an
    # AttributeError on None.strip() or leak the key.
    payload = {"choices": [{"message": {"content": None},
                            "finish_reason": "length"}]}
    _install_fake_post(monkeypatch, _FakeResponse(200, payload))
    reader = MetaReader(api_key="super-secret-key")
    with pytest.raises(RuntimeError) as excinfo:
        reader.read_field(image_path, "nid", "dob", "original")
    message = str(excinfo.value)
    assert "length" in message
    assert "super-secret-key" not in message


# --- BasetenReader: documented endpoint + reasoning headroom ------------------

def test_baseten_reader_posts_to_inference_endpoint_with_headroom(
        monkeypatch, image_path):
    from app.providers import BASETEN_URL

    calls = _install_fake_post(
        monkeypatch, _FakeResponse(200, _chat_payload("  12/03/1990 \n")))
    got = BasetenReader(api_key="bk").read_field(
        image_path, "nid", "dob", "original")
    assert got == "12/03/1990"  # response text extracted + stripped
    call = calls[0]
    # Default route is Baseten's documented hackathon inference host.
    assert call["url"] == BASETEN_URL
    assert call["url"] == "https://inference.baseten.co/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Api-Key bk"
    assert call["json"]["model"] == "meta-models/muse-spark-open-1026"
    # Spark Open always reasons: the budget must leave room for the
    # reasoning *and* the answer (the 128 default returned nulls on
    # the Meta route). No reasoning_effort is sent — whether Baseten
    # accepts it is unverified.
    assert call["json"]["max_tokens"] == 1024
    assert "reasoning_effort" not in call["json"]


def test_baseten_reader_url_env_override_and_constructor_arg(
        monkeypatch, image_path):
    # The dedicated model-apis route stays selectable via env...
    monkeypatch.setenv(
        "BASETEN_URL", "https://model-apis.baseten.net/v1/chat/completions")
    reader = BasetenReader(api_key="bk")
    assert reader.url == "https://model-apis.baseten.net/v1/chat/completions"
    calls = _install_fake_post(
        monkeypatch, _FakeResponse(200, _chat_payload("x")))
    reader.read_field(image_path, "nid", "dob", "original")
    assert calls[0]["url"] == \
        "https://model-apis.baseten.net/v1/chat/completions"

    # ...and an explicit constructor url beats the environment.
    assert BasetenReader(
        api_key="bk",
        url="https://example.invalid/v1/chat/completions").url == \
        "https://example.invalid/v1/chat/completions"


def test_baseten_reader_max_tokens_env_and_constructor(
        monkeypatch, image_path):
    monkeypatch.setenv("BASETEN_MAX_TOKENS", "2048")
    assert BasetenReader(api_key="bk").max_tokens == 2048
    # Constructor argument beats the environment, and lands in the
    # payload actually sent.
    reader = BasetenReader(api_key="bk", max_tokens=512)
    assert reader.max_tokens == 512
    calls = _install_fake_post(
        monkeypatch, _FakeResponse(200, _chat_payload("x")))
    reader.read_field(image_path, "nid", "name", "original")
    assert calls[0]["json"]["max_tokens"] == 512


def test_baseten_reader_null_content_raises_with_finish_reason(
        monkeypatch, image_path):
    # What a reasoning model returns when the budget is eaten by
    # reasoning: finish_reason "length", content null. Must raise a
    # clear error — never an empty string treated as a read, and
    # never a crash on None.strip().
    payload = {"choices": [{"message": {"content": None},
                            "finish_reason": "length"}]}
    _install_fake_post(monkeypatch, _FakeResponse(200, payload))
    reader = BasetenReader(api_key="super-secret-key")
    with pytest.raises(RuntimeError) as excinfo:
        reader.read_field(image_path, "nid", "dob", "original")
    message = str(excinfo.value)
    assert "length" in message
    assert "reasoning" in message
    assert "super-secret-key" not in message


def test_baseten_reader_empty_content_raises(monkeypatch, image_path):
    _install_fake_post(
        monkeypatch, _FakeResponse(200, _chat_payload("   ")))
    reader = BasetenReader(api_key="bk")
    with pytest.raises(RuntimeError):
        reader.read_field(image_path, "nid", "dob", "original")


def test_baseten_reader_no_choices_raises(monkeypatch, image_path):
    _install_fake_post(monkeypatch, _FakeResponse(200, {}))
    reader = BasetenReader(api_key="bk")
    with pytest.raises(RuntimeError) as excinfo:
        reader.read_field(image_path, "nid", "dob", "original")
    assert "no choices" in str(excinfo.value)


def test_baseten_reader_http_error_raises_cleanly(
        monkeypatch, image_path):
    body = '{\n  "error": {"message": "Invalid API key"}\n}'
    _install_fake_post(monkeypatch, _FakeResponse(401, {}, text=body))
    reader = BasetenReader(api_key="super-secret-key")
    with pytest.raises(RuntimeError) as excinfo:
        reader.read_field(image_path, "nid", "dob", "original")
    message = str(excinfo.value)
    assert "401" in message
    assert "Invalid API key" in message  # short body excerpt
    assert "super-secret-key" not in message  # never leak the key


# --- MetaReader error handling -------------------------------------------------

def test_meta_reader_http_error_raises_cleanly(monkeypatch, image_path):
    body = '{\n  "error": {"message": "Invalid API key provided"}\n}'
    _install_fake_post(monkeypatch, _FakeResponse(401, {}, text=body))
    reader = MetaReader(api_key="super-secret-key")
    with pytest.raises(RuntimeError) as excinfo:
        reader.read_field(image_path, "nid", "dob", "original")
    message = str(excinfo.value)
    assert "401" in message
    assert "Invalid API key provided" in message  # short body excerpt
    assert "super-secret-key" not in message      # never leak the key


def test_meta_reader_transport_error_raises_cleanly(
        monkeypatch, image_path):
    _install_fake_post(monkeypatch, httpx.ConnectError("connection refused"))
    reader = MetaReader(api_key="super-secret-key")
    with pytest.raises(RuntimeError) as excinfo:
        reader.read_field(image_path, "nid", "dob", "original")
    assert "super-secret-key" not in str(excinfo.value)


# --- Investigation planner calls (Meta + Baseten) -----------------------------

_PLAN_READS = [{"view": "original", "value": "UNREADABLE"},
               {"view": "zoom", "value": "12/03/1990"},
               {"view": "contrast", "value": "UNREADABLE"}]
_PLAN_ACTIONS = {"stamp_masked": "Mask the stamp and re-read.",
                  "zoom_tight": "Re-read a tighter crop.",
                  "recapture": "Stop; request a recapture."}
_PLAN_JSON = '{"action": "stamp_masked", "reason": "A stamp covers it."}'


def test_meta_planner_posts_with_read_calibration_and_parses(
        monkeypatch, image_path):
    calls = _install_fake_post(
        monkeypatch, _FakeResponse(200, _chat_payload(_PLAN_JSON)))
    decision = MetaReader(api_key="test-key-123").plan_investigation(
        image_path, "birth_certificate", "dob", _PLAN_READS,
        _PLAN_ACTIONS)

    assert decision == {"action": "stamp_masked",
                        "reason": "A stamp covers it."}
    call = calls[0]
    assert call["url"] == META_URL
    assert call["headers"]["Authorization"] == "Bearer test-key-123"
    # Same reasoning calibration as the reads (1024 / minimal).
    assert call["json"]["max_tokens"] == 1024
    assert call["json"]["reasoning_effort"] == "minimal"
    text = call["json"]["messages"][0]["content"][0]["text"]
    assert "birth_certificate" in text and "dob" in text
    assert "stamp_masked" in text and "12/03/1990" in text
    # The prompt reserves verdicts for the deterministic comparator.
    assert "never decide" in text


def test_meta_planner_garbage_reply_raises(monkeypatch, image_path):
    # An unparseable decision is a planner failure (ValueError) —
    # the agent answers those with its fallback sequence.
    _install_fake_post(monkeypatch, _FakeResponse(
        200, _chat_payload("I would zoom in, probably.")))
    with pytest.raises(ValueError):
        MetaReader(api_key="k").plan_investigation(
            image_path, "nid", "dob", _PLAN_READS, _PLAN_ACTIONS)


def test_meta_planner_null_content_raises(monkeypatch, image_path):
    payload = {"choices": [{"message": {"content": None},
                            "finish_reason": "length"}]}
    _install_fake_post(monkeypatch, _FakeResponse(200, payload))
    with pytest.raises(RuntimeError) as excinfo:
        MetaReader(api_key="super-secret-key").plan_investigation(
            image_path, "nid", "dob", _PLAN_READS, _PLAN_ACTIONS)
    assert "super-secret-key" not in str(excinfo.value)


def test_baseten_planner_posts_to_inference_endpoint(monkeypatch,
                                                     image_path):
    calls = _install_fake_post(
        monkeypatch, _FakeResponse(200, _chat_payload(_PLAN_JSON)))
    decision = BasetenReader(api_key="bk").plan_investigation(
        image_path, "nid", "dob", _PLAN_READS, _PLAN_ACTIONS)
    assert decision["action"] == "stamp_masked"
    call = calls[0]
    assert call["url"] == "https://inference.baseten.co/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Api-Key bk"
    assert call["json"]["model"] == "meta-models/muse-spark-open-1026"
    assert call["json"]["max_tokens"] == 1024
    assert "reasoning_effort" not in call["json"]


def test_parse_plan_accepts_fenced_json_and_rejects_the_rest():
    from app.providers import _parse_plan

    assert _parse_plan('{"action": "zoom_tight", "reason": "faint"}') == \
        {"action": "zoom_tight", "reason": "faint"}
    assert _parse_plan('```json\n{"action": "recapture"}\n```') == \
        {"action": "recapture", "reason": ""}
    for bad in ("", "zoom in please", '{"reason": "no action"}',
                '["stamp_masked"]'):
        with pytest.raises(ValueError):
            _parse_plan(bad)


def test_mock_reader_planner_scripting():
    # Unscripted: raises, so agent tests exercise the fallback.
    reader = MockReader({})
    with pytest.raises(RuntimeError):
        reader.plan_investigation("x.png", "nid", "dob",
                                  _PLAN_READS, _PLAN_ACTIONS)
    # Scripted queue: decisions in order, exceptions raised, calls
    # recorded with the reads/actions the planner was shown.
    reader = MockReader({}, planner=[
        {"action": "zoom_tight", "reason": "faint"},
        RuntimeError("down")])
    got = reader.plan_investigation("x.png", "nid", "dob",
                                    _PLAN_READS, _PLAN_ACTIONS)
    assert got == {"action": "zoom_tight", "reason": "faint"}
    with pytest.raises(RuntimeError):
        reader.plan_investigation("x.png", "nid", "dob",
                                  _PLAN_READS, _PLAN_ACTIONS)
    assert len(reader.planner_calls) == 2
    assert reader.planner_calls[0]["actions"] == _PLAN_ACTIONS


# --- resolve_reader: the meta path, and the unchanged baseten/mock paths ------

def test_resolve_reader_meta_with_and_without_key(monkeypatch):
    monkeypatch.setenv("JUDGE_READER", "meta")
    monkeypatch.setenv("MODEL_API_KEY", "k")
    reader = judge_module.resolve_reader()
    assert isinstance(reader, MetaReader)
    assert reader.model == "muse-spark-1.3"

    monkeypatch.delenv("MODEL_API_KEY")
    assert judge_module.resolve_reader() is None


def test_resolve_reader_baseten_and_mock_unchanged(monkeypatch):
    monkeypatch.setenv("JUDGE_READER", "baseten")
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    assert judge_module.resolve_reader() is None
    monkeypatch.setenv("BASETEN_API_KEY", "k")
    assert isinstance(judge_module.resolve_reader(), BasetenReader)

    # Default (JUDGE_READER unset) still keys off Baseten only.
    monkeypatch.delenv("JUDGE_READER")
    monkeypatch.delenv("BASETEN_API_KEY")
    monkeypatch.setenv("MODEL_API_KEY", "k")
    assert judge_module.resolve_reader() is None

    monkeypatch.setenv("JUDGE_READER", "mock")
    assert isinstance(judge_module.resolve_reader(), MockReader)

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

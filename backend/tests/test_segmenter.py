"""Segmenter tests: fallback masker, mock, Modal client (offline),
and agent integration. No network and no GPU are used anywhere here;
the Modal deployment itself is smoke-tested separately (modal_sam/).
"""

from PIL import Image, ImageDraw

from app import agent, judge as judge_module
from app.providers import MockReader
from app.segmenter import (META_SAM_URL, Box, MetaSAMSegmenter,
                           MockSegmenter, ModalSegmenter,
                           PillowFallbackSegmenter, detect_stamp_box,
                           mask_region)


def _doc_with_stamp(tmp_path):
    """White page, dark text block, saturated blue stamp block."""
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 200, 40], fill=(30, 30, 30))       # "text"
    draw.rectangle([240, 180, 340, 250], fill=(40, 40, 200))   # "stamp"
    path = tmp_path / "doc.png"
    img.save(path)
    return str(path)


def _plain_doc(tmp_path):
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([20, 20, 200, 40], fill=(30, 30, 30))
    path = tmp_path / "plain.png"
    img.save(path)
    return str(path)


# --- Pillow fallback ---

def test_mask_region_covers_exactly_the_box(tmp_path):
    src = _doc_with_stamp(tmp_path)
    out = mask_region(src, Box(240, 180, 340, 250),
                      out_path=str(tmp_path / "masked.png"))
    masked = Image.open(out).convert("RGB")
    assert masked.getpixel((290, 215)) == (255, 255, 255)  # stamp covered
    assert masked.getpixel((100, 30)) == (30, 30, 30)      # text untouched
    original = Image.open(src).convert("RGB")
    assert original.getpixel((290, 215)) == (40, 40, 200)  # source unmodified


def test_detect_stamp_box_finds_blue_stamp(tmp_path):
    box = detect_stamp_box(_doc_with_stamp(tmp_path))
    assert box is not None
    assert box.x_min <= 245 and box.x_max >= 335
    assert box.y_min <= 185 and box.y_max >= 245


def test_detect_stamp_box_none_without_stamp(tmp_path):
    assert detect_stamp_box(_plain_doc(tmp_path)) is None


def test_fallback_segmenter_masks_detected_stamp(tmp_path):
    seg = PillowFallbackSegmenter()
    out = seg.masked_image(_doc_with_stamp(tmp_path), "stamp")
    assert out is not None
    assert Image.open(out).convert("RGB").getpixel((290, 215)) == (255, 255, 255)


def test_fallback_segmenter_no_stamp_returns_none(tmp_path):
    seg = PillowFallbackSegmenter()
    assert seg.masked_image(_plain_doc(tmp_path), "stamp") is None
    result = seg.segment(_plain_doc(tmp_path), "signature")
    assert result.boxes == []  # non-stamp prompts are not guessed at


# --- Mock segmenter ---

def test_mock_segmenter_records_calls_and_masks(tmp_path):
    seg = MockSegmenter(boxes=[Box(240, 180, 340, 250)])
    out = seg.masked_image(_doc_with_stamp(tmp_path), "stamp")
    assert out is not None
    assert Image.open(out).convert("RGB").getpixel((290, 215)) == (255, 255, 255)
    result = seg.segment("anything.png", "stamp")
    assert result.boxes[0].x_max == 340
    assert len(seg.calls) == 2


# --- Modal segmenter (offline behavior only) ---

def test_modal_segmenter_unconfigured_fails_soft(tmp_path, monkeypatch):
    monkeypatch.delenv("SAM_MODAL_ENDPOINT", raising=False)
    seg = ModalSegmenter()
    assert seg.configured is False
    assert seg.segment(_doc_with_stamp(tmp_path), "stamp") is None
    assert seg.masked_image(_doc_with_stamp(tmp_path), "stamp") is None


def test_modal_segmenter_parses_response_and_masks(tmp_path, monkeypatch):
    import httpx

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, json=json)
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={
            "boxes": [[240, 180, 340, 250]], "scores": [0.93],
            "mask_base64": None,
        })

    monkeypatch.setattr(httpx, "post", fake_post)
    seg = ModalSegmenter(endpoint="https://example.invalid/sam")
    src = _doc_with_stamp(tmp_path)
    result = seg.segment(src, "stamp")
    assert result is not None and result.provider == "modal_sam3.1"
    assert result.boxes[0].as_list() == [240, 180, 340, 250]
    assert result.boxes[0].score == 0.93
    assert captured["json"]["prompt"] == "stamp"
    out = seg.masked_image(src, "stamp")
    assert Image.open(out).convert("RGB").getpixel((290, 215)) == (255, 255, 255)


def test_modal_segmenter_http_failure_fails_soft(tmp_path, monkeypatch):
    import httpx

    def failing_post(url, headers=None, json=None, timeout=None):
        raise httpx.ConnectError("no network", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", failing_post)
    seg = ModalSegmenter(endpoint="https://example.invalid/sam")
    assert seg.segment(_doc_with_stamp(tmp_path), "stamp") is None
    assert seg.masked_image(_doc_with_stamp(tmp_path), "stamp") is None


# --- Agent integration ---

class _PathRecordingReader(MockReader):
    def __init__(self, script):
        super().__init__(script)
        self.paths: list[tuple[str, str]] = []

    def read_field(self, image_path, doc_type, field, perturbation):
        self.paths.append((perturbation, image_path))
        return super().read_field(image_path, doc_type, field, perturbation)


def _script(dob_reads):
    return {
        ("nid", "name"): ["Md. Abdul Rahman"],
        ("nid", "dob"): dob_reads,
        ("nid", "id_number"): ["1234567890"],
        ("nid", "father_name"): ["Abdul Karim"],
        ("bank_form", "name"): ["Mohammed Abdul Rahman"],
        ("bank_form", "dob"): ["12/03/1990"],
        ("bank_form", "id_number"): ["1234567890"],
        ("bank_form", "father_name"): ["Abdul Karim"],
    }


def test_agent_uses_segmenter_for_stamp_masked_read(tmp_path):
    src = _doc_with_stamp(tmp_path)
    # dob reads disagree on the first pass -> investigation is triggered.
    reader = _PathRecordingReader(_script(
        ["12/03/1990", "12/03/1996", "12/03/1990",
         "12/03/1990", "12/03/1990"]))
    seg = MockSegmenter(boxes=[Box(240, 180, 340, 250)])
    outcome = agent.run_review(reader, {"nid": src, "bank_form": src},
                               segmenter=seg)
    assert outcome.verdict == "CONSISTENT"
    assert seg.calls, "segmenter was never consulted"
    stamp_reads = [p for view, p in reader.paths if view == "stamp_masked"]
    zoom_reads = [p for view, p in reader.paths if view == "zoom_tight"]
    assert stamp_reads and all(p != src for p in stamp_reads)
    assert zoom_reads and all(p == src for p in zoom_reads)


def test_agent_without_segmenter_reads_original_for_all_views(tmp_path):
    src = _doc_with_stamp(tmp_path)
    reader = _PathRecordingReader(_script(
        ["12/03/1990", "12/03/1996", "12/03/1990",
         "12/03/1990", "12/03/1990"]))
    agent.run_review(reader, {"nid": src, "bank_form": src})
    assert all(p == src for _, p in reader.paths)


def test_agent_broken_segmenter_still_reviews(tmp_path):
    class BrokenSegmenter:
        def segment(self, image_path, prompt):
            raise RuntimeError("boom")

        def masked_image(self, image_path, prompt, out_path=None):
            raise RuntimeError("boom")

    src = _doc_with_stamp(tmp_path)
    reader = MockReader(_script(["12/03/1990"]))
    outcome = agent.run_review(reader, {"nid": src, "bank_form": src},
                               segmenter=BrokenSegmenter())
    assert outcome.verdict == "CONSISTENT"


# --- Meta-hosted SAM segmenter (offline behavior only) ---

def _image_file(tmp_path, name="sam_doc.png", size=(800, 600)):
    path = tmp_path / name
    Image.new("RGB", size, (255, 255, 255)).save(path)
    return str(path)


def _sam_payload(lane: str) -> dict:
    return {"output": [{"content": [
        {"type": "output_text", "text": lane}]}]}


def _install_sam_post(monkeypatch, response):
    import httpx

    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers or {},
                      "json": json, "timeout": timeout})
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


def _sam_response(lane: str, status: int = 200):
    import httpx

    request = httpx.Request("POST", META_SAM_URL)
    return httpx.Response(status, request=request,
                          json=_sam_payload(lane))


_SINGLE_LANE = (
    "<0f>0<|box;x1=251;y1=151;x2=550;y2=449;w=800;h=600|>"
    "<|mask;x=0;y=0;data=299,300,~|>"
)
_MULTI_LANE = (
    _SINGLE_LANE
    + ",1<|box;x1=10;y1=20;x2=110;y2=90;w=800;h=600|>"
    "<|mask;x=0;y=0;data=70,100,~|>"
)
# A complete valid mask payload (the meta-sam-parser package's own
# documented example), used to exercise the optional mask decoder.
_VALID_MASK_LANE = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,60,"
    "~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
)


def test_meta_sam_unconfigured_fails_soft(tmp_path, monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    seg = MetaSAMSegmenter()
    assert seg.configured is False
    assert seg.segment(_image_file(tmp_path), "stamp") is None
    assert seg.masked_image(_image_file(tmp_path), "stamp") is None


def test_meta_sam_request_shape_and_single_box(tmp_path, monkeypatch):
    calls = _install_sam_post(monkeypatch, _sam_response(_SINGLE_LANE))
    seg = MetaSAMSegmenter(api_key="test-key-123")
    src = _image_file(tmp_path)
    result = seg.segment(src, "stamp")

    assert result is not None and result.provider == "meta_sam3.1"
    assert [box.as_list() for box in result.boxes] == [
        [251, 151, 550, 449]]
    # The SAM wire format carries no confidence score.
    assert result.boxes[0].score is None
    assert result.boxes[0].label == "stamp"

    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == META_SAM_URL
    assert call["url"] == "https://api.meta.ai/v1/responses"
    assert call["headers"]["Authorization"] == "Bearer test-key-123"
    assert call["json"]["model"] == "sam-3.1"  # default model
    content = call["json"]["input"][0]["content"]
    assert content[0]["type"] == "input_image"
    image_url = content[0]["image_url"]
    assert image_url.startswith("data:image/png;base64,")
    import base64
    assert base64.b64decode(image_url.split(",", 1)[1]) == \
        (tmp_path / "sam_doc.png").read_bytes()
    assert content[1] == {"type": "input_text", "text": "stamp"}


def test_meta_sam_parses_multiple_records(tmp_path, monkeypatch):
    _install_sam_post(monkeypatch, _sam_response(_MULTI_LANE))
    seg = MetaSAMSegmenter(api_key="k")
    result = seg.segment(_image_file(tmp_path), "stamp")
    assert result is not None
    assert [box.as_list() for box in result.boxes] == [
        [251, 151, 550, 449], [10, 20, 110, 90]]
    assert all(box.score is None for box in result.boxes)


def test_meta_sam_model_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SAM_META_MODEL", "sam-3.1-custom")
    monkeypatch.setenv("MODEL_API_KEY", "env-key")
    calls = _install_sam_post(monkeypatch, _sam_response(_SINGLE_LANE))
    seg = MetaSAMSegmenter()  # key + model both from env
    assert seg.api_key == "env-key"
    assert seg.model == "sam-3.1-custom"
    seg.segment(_image_file(tmp_path), "stamp")
    assert calls[0]["json"]["model"] == "sam-3.1-custom"
    # A constructor model beats the environment.
    assert MetaSAMSegmenter(model="sam-3.1").model == "sam-3.1"


def test_meta_sam_empty_lane_is_empty_result(tmp_path, monkeypatch):
    _install_sam_post(monkeypatch, _sam_response(""))
    seg = MetaSAMSegmenter(api_key="k")
    src = _image_file(tmp_path)
    result = seg.segment(src, "stamp")
    assert result is not None and result.boxes == []
    assert seg.masked_image(src, "stamp") is None


def test_meta_sam_http_and_transport_errors_fail_soft(
        tmp_path, monkeypatch):
    import httpx

    _install_sam_post(monkeypatch, _sam_response("nope", status=500))
    seg = MetaSAMSegmenter(api_key="super-secret-key")
    assert seg.segment(_image_file(tmp_path), "stamp") is None

    _install_sam_post(
        monkeypatch,
        httpx.ConnectError("no network",
                           request=httpx.Request("POST", META_SAM_URL)))
    assert seg.segment(_image_file(tmp_path), "stamp") is None
    assert seg.masked_image(_image_file(tmp_path), "stamp") is None


def test_meta_sam_masked_image_masks_first_box(tmp_path, monkeypatch):
    _install_sam_post(monkeypatch, _sam_response(_SINGLE_LANE))
    seg = MetaSAMSegmenter(api_key="k")
    src = _image_file(tmp_path)
    out = seg.masked_image(src, "stamp")
    assert out is not None
    masked = Image.open(out).convert("RGB")
    assert masked.getpixel((400, 300)) == (255, 255, 255)
    # A coloured pixel inside the box proves the mask was applied.
    img = Image.open(src).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle([251, 151, 550, 449], fill=(40, 40, 200))
    img.save(src)
    out = seg.masked_image(src, "stamp")
    assert Image.open(out).convert("RGB").getpixel((400, 300)) == \
        (255, 255, 255)
    assert Image.open(src).convert("RGB").getpixel((400, 300)) == \
        (40, 40, 200)  # source unmodified


def test_meta_sam_decodes_mask_when_parser_available(
        tmp_path, monkeypatch):
    _install_sam_post(monkeypatch, _sam_response(_VALID_MASK_LANE))
    seg = MetaSAMSegmenter(api_key="k")
    src = _image_file(tmp_path, name="small.png", size=(320, 334))
    result = seg.segment(src, "stamp")
    assert result is not None
    assert [box.as_list() for box in result.boxes] == [
        [211, 228, 270, 254]]
    assert result.mask_path is not None
    with Image.open(result.mask_path) as mask:
        assert mask.size == (320, 334)
        assert mask.convert("L").getbbox() is not None


# --- resolve_segmenter selection ---

def _clear_segmenter_env(monkeypatch):
    for name in ("SEGMENTER", "MODEL_API_KEY", "SAM_MODAL_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)


def test_resolve_segmenter_defaults_to_meta_when_key_present(
        monkeypatch):
    _clear_segmenter_env(monkeypatch)
    monkeypatch.setenv("MODEL_API_KEY", "k")
    monkeypatch.setenv("SAM_MODAL_ENDPOINT", "https://example.invalid/sam")
    # Meta wins over Modal in the default chain.
    assert isinstance(judge_module.resolve_segmenter(),
                      MetaSAMSegmenter)


def test_resolve_segmenter_explicit_modes(monkeypatch):
    _clear_segmenter_env(monkeypatch)
    monkeypatch.setenv("MODEL_API_KEY", "k")
    monkeypatch.setenv("SAM_MODAL_ENDPOINT", "https://example.invalid/sam")
    monkeypatch.setenv("SEGMENTER", "modal")
    assert isinstance(judge_module.resolve_segmenter(), ModalSegmenter)
    monkeypatch.setenv("SEGMENTER", "meta")
    assert isinstance(judge_module.resolve_segmenter(),
                      MetaSAMSegmenter)


def test_resolve_segmenter_modal_then_fallback_defaults(monkeypatch):
    _clear_segmenter_env(monkeypatch)
    monkeypatch.setenv("SAM_MODAL_ENDPOINT", "https://example.invalid/sam")
    assert isinstance(judge_module.resolve_segmenter(), ModalSegmenter)
    monkeypatch.delenv("SAM_MODAL_ENDPOINT")
    assert isinstance(judge_module.resolve_segmenter(),
                      PillowFallbackSegmenter)

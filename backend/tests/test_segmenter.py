"""Segmenter tests: fallback masker, mock, Modal client (offline),
and agent integration. No network and no GPU are used anywhere here;
the Modal deployment itself is smoke-tested separately (modal_sam/).
"""

from PIL import Image, ImageDraw

from app import agent
from app.providers import MockReader
from app.segmenter import (Box, MockSegmenter, ModalSegmenter,
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

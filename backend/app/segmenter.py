"""Segmentation providers.

A Segmenter finds a concept ("stamp", "signature", ...) in a document
image and can produce a copy of the image with that region masked out.
The agent loop uses the masked copy for its "stamp_masked" investigation
read. The agent depends only on this interface; provider choice is
configuration:

- PillowFallbackSegmenter — deterministic, offline, Pillow only. Masks a
  given bounding box, and detects stamp-like regions with a colour
  heuristic (saturated blue/purple ink). This is the resilience path: it
  works with no GPU, no network and no credits, and the reviewer trace
  records that a fallback produced the mask.
- ModalSegmenter — SAM 3.1 self-hosted on Modal (see modal_sam/). Needs
  SAM_MODAL_ENDPOINT. Fails soft: every failure returns None so the
  agent falls back to reading the original image.
- MetaSAMSegmenter — SAM 3.1 hosted on the Meta Model API, using the
  Responses API and the same MODEL_API_KEY as MetaReader. This is the
  segmenter the deployed backend uses. Masks are decoded through the
  optional meta-sam-parser package when it is installed; without it,
  the returned boxes still let the agent mask by box.
- MockSegmenter — scripted stand-in for tests. Returns fixed boxes and
  produces a real masked image with the Pillow masker.

Masking here only ever *covers* a region on a working copy — originals
are never modified, and masks are evidence in the trace, not edits to
the applicant's document.
"""

from __future__ import annotations

import base64
import os
import re
import tempfile
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Protocol


@dataclass
class Box:
    """A region in pixel coordinates, xyxy (origin top-left)."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float
    score: float | None = None
    label: str | None = None

    def as_list(self) -> list[float]:
        return [self.x_min, self.y_min, self.x_max, self.y_max]


@dataclass
class SegmentResult:
    prompt: str
    boxes: list[Box] = dc_field(default_factory=list)
    mask_path: str | None = None  # PNG of the union mask, if produced
    provider: str = ""


class Segmenter(Protocol):
    def segment(self, image_path: str, prompt: str) -> SegmentResult | None:
        ...

    def masked_image(self, image_path: str, prompt: str,
                     out_path: str | None = None) -> str | None:
        """Path to a copy of the image with the prompted region covered,
        or None if no region could be produced."""
        ...


# --------------------------------------------------------------------------
# Pillow helpers (shared by the fallback, the mock, and the Modal client
# when it applies returned boxes/masks locally)
# --------------------------------------------------------------------------

def mask_region(image_path: str, box: Box, out_path: str | None = None,
                fill: tuple[int, int, int] = (255, 255, 255)) -> str:
    """Write a copy of the image with `box` covered; return its path."""
    from PIL import Image, ImageDraw

    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle(box.as_list(), fill=fill)
    out = out_path or _sibling_out_path(image_path, "masked")
    img.save(out)
    return out


def apply_mask_png(image_path: str, mask_png: bytes,
                   out_path: str | None = None,
                   fill: tuple[int, int, int] = (255, 255, 255)) -> str:
    """Write a copy of the image with every white mask pixel covered."""
    import io

    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    mask = Image.open(io.BytesIO(mask_png)).convert("L").resize(img.size)
    cover = Image.new("RGB", img.size, fill)
    out = out_path or _sibling_out_path(image_path, "masked")
    Image.composite(cover, img, mask).save(out)
    return out


def _sibling_out_path(image_path: str, suffix: str) -> str:
    p = Path(image_path)
    out_dir = Path(tempfile.mkdtemp(prefix="doctrust_mask_"))
    return str(out_dir / f"{p.stem}_{suffix}{p.suffix or '.png'}")


def detect_stamp_box(image_path: str) -> Box | None:
    """Heuristic stamp detector (Pillow only).

    Stamps on these documents are saturated blue/purple ink while the
    page and text are near-grey or black. Downscale, collect ink-like
    pixels, and return their bounding box if there are enough of them
    and the box is a plausible stamp size. Deterministic; returns None
    when nothing stamp-like is present. This is a heuristic for the
    fallback path, not a detector to trust on real documents.
    """
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    orig_w, orig_h = img.size
    scale = min(1.0, 400 / max(orig_w, 1))
    if scale < 1.0:
        img = img.resize((max(1, int(orig_w * scale)),
                          max(1, int(orig_h * scale))))
    w, h = img.size
    pixels = img.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            blue_ink = b > 110 and b - r > 55 and b - g > 35
            purple_ink = r > 80 and b > 100 and g < min(r, b) - 35
            if blue_ink or purple_ink:
                xs.append(x)
                ys.append(y)
    if len(xs) < 150:  # too little ink to be a stamp
        return None
    box = Box(x_min=min(xs) / scale, y_min=min(ys) / scale,
              x_max=max(xs) / scale, y_max=max(ys) / scale)
    area_frac = ((box.x_max - box.x_min) * (box.y_max - box.y_min)
                 / max(orig_w * orig_h, 1))
    if not (0.002 < area_frac < 0.6):  # implausible stamp size
        return None
    return box


class PillowFallbackSegmenter:
    """Deterministic offline segmenter: heuristic detection + masking."""

    provider = "pillow_fallback"

    def segment(self, image_path: str, prompt: str) -> SegmentResult | None:
        if "stamp" not in prompt.lower():
            return SegmentResult(prompt=prompt, provider=self.provider)
        box = detect_stamp_box(image_path)
        boxes = [box] if box else []
        return SegmentResult(prompt=prompt, boxes=boxes,
                             provider=self.provider)

    def masked_image(self, image_path: str, prompt: str,
                     out_path: str | None = None) -> str | None:
        result = self.segment(image_path, prompt)
        if not result or not result.boxes:
            return None
        return mask_region(image_path, result.boxes[0], out_path)


class MockSegmenter:
    """Scripted segmenter for tests: fixed boxes, real masked output."""

    provider = "mock"

    def __init__(self, boxes: list[Box] | None = None):
        self._boxes = boxes or [Box(10, 10, 60, 40, score=0.99, label="stamp")]
        self.calls: list[tuple[str, str]] = []

    def segment(self, image_path: str, prompt: str) -> SegmentResult:
        self.calls.append((image_path, prompt))
        return SegmentResult(prompt=prompt, boxes=list(self._boxes),
                             provider=self.provider)

    def masked_image(self, image_path: str, prompt: str,
                     out_path: str | None = None) -> str | None:
        self.calls.append((image_path, prompt))
        if not self._boxes:
            return None
        return mask_region(image_path, self._boxes[0], out_path)


class ModalSegmenter:
    """SAM 3.1 on Modal, over HTTP. See modal_sam/sam_app.py.

    POSTs {image_base64, prompt} to SAM_MODAL_ENDPOINT and parses
    {boxes, scores, mask_base64}. Fails soft by design: unconfigured,
    unreachable, or an unusable response all return None, and the agent
    reads the original image instead of failing the whole review.
    """

    provider = "modal_sam3.1"

    def __init__(self, endpoint: str | None = None,
                 api_key: str | None = None, timeout: float = 180):
        self.endpoint = endpoint or os.environ.get("SAM_MODAL_ENDPOINT", "")
        self.api_key = api_key or os.environ.get("SAM_MODAL_API_KEY", "")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.endpoint)

    def segment(self, image_path: str, prompt: str) -> SegmentResult | None:
        if not self.configured:
            return None
        try:
            return self._segment_remote(image_path, prompt)
        except Exception:
            return None  # fail soft: segmentation is an aid, not a gate

    def _segment_remote(self, image_path: str,
                        prompt: str) -> SegmentResult | None:
        import httpx  # deferred so tests never need the network stack

        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = httpx.post(self.endpoint, headers=headers,
                          json={"image_base64": image_b64, "prompt": prompt},
                          timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        boxes: list[Box] = []
        scores = data.get("scores") or []
        for i, raw in enumerate(data.get("boxes") or []):
            if isinstance(raw, dict):
                box = Box(float(raw["x_min"]), float(raw["y_min"]),
                          float(raw["x_max"]), float(raw["y_max"]))
            else:  # [x1, y1, x2, y2]
                box = Box(float(raw[0]), float(raw[1]),
                          float(raw[2]), float(raw[3]))
            box.score = float(scores[i]) if i < len(scores) else None
            box.label = prompt
            boxes.append(box)

        mask_path = None
        if data.get("mask_base64"):
            mask_bytes = base64.b64decode(data["mask_base64"])
            fd, mask_path = tempfile.mkstemp(prefix="doctrust_sam_mask_",
                                             suffix=".png")
            with os.fdopen(fd, "wb") as fh:
                fh.write(mask_bytes)
        return SegmentResult(prompt=prompt, boxes=boxes,
                             mask_path=mask_path, provider=self.provider)

    def masked_image(self, image_path: str, prompt: str,
                     out_path: str | None = None) -> str | None:
        result = self.segment(image_path, prompt)
        if not result:
            return None
        try:
            if result.mask_path:
                mask_png = Path(result.mask_path).read_bytes()
                return apply_mask_png(image_path, mask_png, out_path)
            if result.boxes:
                return mask_region(image_path, result.boxes[0], out_path)
        except Exception:
            return None
        return None


META_SAM_URL = "https://api.meta.ai/v1/responses"
META_SAM_MODEL_ID = "sam-3.1"
_BOX_TOKEN_RE = re.compile(r"<\|box;([^|]*)\|>")
_BOX_FIELD_RE = re.compile(
    r"\b(x1|y1|x2|y2)=(-?\d+(?:\.\d+)?)")


def _meta_sam_lane(response_data: dict) -> str | None:
    """Extract the SAM special-token lane from a Responses API payload.

    Returns None when the response has no output-text lane at all. A
    present but empty lane is returned as an empty string: SAM ran and
    found nothing, which callers represent as an empty SegmentResult.
    """
    output = response_data.get("output")
    if not isinstance(output, list):
        return None
    lanes: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if (isinstance(part, dict)
                    and part.get("type") == "output_text"
                    and isinstance(part.get("text"), str)):
                lanes.append(part["text"])
    if not lanes:
        return None
    return "\n".join(lanes)


def _parse_meta_sam_boxes(lane: str, prompt: str) -> list[Box]:
    """Parse every box record in a SAM lane, preserving source pixels.

    The wire format carries no confidence score, so Box.score stays
    None. Malformed individual records are skipped rather than making
    the whole segmentation fail.
    """
    boxes: list[Box] = []
    for match in _BOX_TOKEN_RE.finditer(lane):
        fields = {name: float(value) for name, value in
                  _BOX_FIELD_RE.findall(match.group(1))}
        if not all(name in fields for name in ("x1", "y1", "x2", "y2")):
            continue
        if fields["x2"] < fields["x1"] or fields["y2"] < fields["y1"]:
            continue
        boxes.append(Box(
            x_min=fields["x1"], y_min=fields["y1"],
            x_max=fields["x2"], y_max=fields["y2"],
            score=None, label=prompt))
    return boxes


def _decode_meta_sam_mask(lane: str, image_path: str) -> str | None:
    """Best-effort union-mask PNG from a SAM lane, via meta-sam-parser.

    The parser package is optional. Import or decoding failure returns
    None and the caller falls back to masking the first returned box —
    exactly how a SegmentResult without a mask is consumed elsewhere.
    The package validates each mask payload; this function only places
    the decoded box-local rasters at their recorded bounds on a
    full-frame mask.
    """
    try:
        from meta_sam_parser import (CompletedOutcome,
                                      decode_mask_to_raster,
                                      image_segmentation_format)
        from PIL import Image, ImageChops

        parser = image_segmentation_format().create_parser()
        parser.push(lane)
        finished = parser.finish(CompletedOutcome())
        mask_records = [record for record in finished.result.records
                        if getattr(record, "kind", None) == "mask"]
        if not mask_records:
            return None

        with Image.open(image_path) as source:
            frame_size = source.size
        union = Image.new("L", frame_size, 0)
        decoded_any = False
        for record in mask_records:
            mask = record.mask
            raster = decode_mask_to_raster(mask)
            if len(raster) != mask.width * mask.height:
                continue
            local = Image.frombytes(
                "L", (mask.width, mask.height),
                bytes(255 if value else 0 for value in raster))
            left = int(record.bounds.left)
            top = int(record.bounds.top)
            if left >= frame_size[0] or top >= frame_size[1]:
                continue
            if left < 0 or top < 0:
                local = local.crop((max(0, -left), max(0, -top),
                                    local.width, local.height))
                left, top = max(0, left), max(0, top)
            local = local.crop((0, 0,
                                min(local.width, frame_size[0] - left),
                                min(local.height, frame_size[1] - top)))
            if local.width <= 0 or local.height <= 0:
                continue
            region = union.crop((left, top, left + local.width,
                                 top + local.height))
            union.paste(ImageChops.lighter(region, local), (left, top))
            decoded_any = True
        if not decoded_any or union.getbbox() is None:
            return None
        fd, mask_path = tempfile.mkstemp(prefix="doctrust_meta_sam_mask_",
                                         suffix=".png")
        with os.fdopen(fd, "wb") as fh:
            union.save(fh, format="PNG")
        return mask_path
    except Exception:
        return None


class MetaSAMSegmenter:
    """SAM 3.1 hosted on the Meta Model API (Responses API).

    The request carries the image as a data URL and the concept prompt
    as input text. SAM answers with a special-token output-text lane:
    one or more box records in source-image pixels, each optionally
    paired with an encoded mask. The wire format has no confidence
    score, so returned boxes keep score=None.

    Configuration is MODEL_API_KEY (the same key MetaReader uses);
    SAM_META_MODEL overrides the model id (default "sam-3.1"). Like
    ModalSegmenter, every failure — unconfigured, HTTP, transport,
    malformed response — fails soft so segmentation never fails a
    review. A successful response whose lane contains no records is a
    successful no-detection: segment() returns an empty SegmentResult
    and masked_image() returns None.
    """

    provider = "meta_sam3.1"

    def __init__(self, api_key: str | None = None,
                 model: str | None = None, timeout: float = 180):
        self.api_key = api_key or os.environ.get("MODEL_API_KEY", "")
        self.model = model or os.environ.get("SAM_META_MODEL",
                                             META_SAM_MODEL_ID)
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def segment(self, image_path: str, prompt: str) -> SegmentResult | None:
        if not self.configured:
            return None
        try:
            return self._segment_remote(image_path, prompt)
        except Exception:
            return None  # fail soft: segmentation is an aid, not a gate

    def _segment_remote(self, image_path: str,
                        prompt: str) -> SegmentResult | None:
        import httpx  # deferred so tests never need the network stack

        suffix = Path(image_path).suffix.lower()
        media_type = "image/jpeg" if suffix in (".jpg", ".jpeg") \
            else "image/png"
        image_b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        payload = {
            "model": self.model,
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_image",
                     "image_url": f"data:{media_type};base64,{image_b64}"},
                    {"type": "input_text", "text": prompt},
                ],
            }],
        }
        resp = httpx.post(
            META_SAM_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload, timeout=self.timeout)
        resp.raise_for_status()
        lane = _meta_sam_lane(resp.json())
        if lane is None:
            return None
        boxes = _parse_meta_sam_boxes(lane, prompt)
        mask_path = _decode_meta_sam_mask(lane, image_path) if boxes \
            else None
        return SegmentResult(prompt=prompt, boxes=boxes,
                             mask_path=mask_path, provider=self.provider)

    def masked_image(self, image_path: str, prompt: str,
                     out_path: str | None = None) -> str | None:
        result = self.segment(image_path, prompt)
        if not result or not result.boxes:
            return None
        try:
            if result.mask_path:
                mask_png = Path(result.mask_path).read_bytes()
                return apply_mask_png(image_path, mask_png, out_path)
            return mask_region(image_path, result.boxes[0], out_path)
        except Exception:
            return None

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
- MockSegmenter — scripted stand-in for tests. Returns fixed boxes and
  produces a real masked image with the Pillow masker.

Masking here only ever *covers* a region on a working copy — originals
are never modified, and masks are evidence in the trace, not edits to
the applicant's document.
"""

from __future__ import annotations

import base64
import os
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

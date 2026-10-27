"""Judge mode: uploaded document sets reviewed live, in memory.

This module backs the /api/review endpoints in app/main.py. A judge
uploads three synthetic document images; the job runs the *existing*
agent loop (app/agent.py) with the configured reader and segmenter,
records an ordered event trace, and captures the intermediate evidence
views the agent actually reads — the perturbed views (zoom / contrast /
tight zoom, generated here as real image transforms) and the masked view
when the segmenter produces one — as PNG data URLs in the result.

Honesty rules (do not weaken these):
- If no vision reader is configured (no BASETEN_API_KEY and
  JUDGE_READER unset/unusable), the job still runs the preprocessing
  and segmentation steps that need no reader, then stops in the
  "reader_not_configured" state with a clear message. Field reads are
  NEVER faked, stubbed or copied from anywhere.
- Judge mode is for SYNTHETIC documents only (see README). Uploads live
  in a per-job temp directory that is deleted when the job finishes;
  results and traces live in memory only, capped and TTL-evicted.

Configuration is environment-only, read per job so flipping env is the
only change needed once a key exists:
- JUDGE_READER=baseten (default when BASETEN_API_KEY is set) -> BasetenReader
- JUDGE_READER=mock with JUDGE_MOCK_SCRIPT_JSON -> MockReader, for local
  development/tests only. Script JSON maps "doc_type|field" -> [values].
- Segmenter: ModalSegmenter when SAM_MODAL_ENDPOINT is set, else the
  deterministic PillowFallbackSegmenter.
"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from . import agent as agent_module
from .comparator import _canonical
from .providers import BasetenReader, MockReader, Reader
from .segmenter import (ModalSegmenter, PillowFallbackSegmenter,
                        Segmenter)

DOC_TYPES = ("nid", "birth_certificate", "bank_form")
CASE_VARIANTS = ("clean", "variation", "discrepancy", "degraded")

MAX_UPLOAD_BYTES = 8 * 1024 * 1024          # per file
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg"}
JOB_TIMEOUT_SECONDS = float(os.environ.get("JUDGE_JOB_TIMEOUT", "300"))
MAX_CONCURRENT_JOBS = 2
MAX_ACTIVE_JOBS = 4                          # queued + running, else 429
MAX_STORED_JOBS = 50
JOB_TTL_SECONDS = 30 * 60
EVIDENCE_MAX_WIDTH = 640                     # px; evidence copies only

VERDICT_LABELS = {
    "CONSISTENT": "Consistent",
    "DISCREPANCY": "Discrepancy, needs human review",
    "UNREADABLE": "Unreadable, request recapture",
}

READER_NOT_CONFIGURED_MESSAGE = (
    "No vision reader is configured on this backend, so no field reads "
    "were attempted and no verdict was produced. Preprocessing and "
    "segmentation (which need no reader) did run — see the trace and "
    "evidence. To enable live reading, set BASETEN_API_KEY (and "
    "JUDGE_READER=baseten) on the server and re-run."
)


# ---------------------------------------------------------------------------
# Configuration (dependency-injected into the routes; tests override these)
# ---------------------------------------------------------------------------

def resolve_reader() -> Reader | None:
    """The configured reader, or None when live reading is not possible."""
    mode = os.environ.get("JUDGE_READER", "").strip().lower()
    if mode == "mock":
        raw = os.environ.get("JUDGE_MOCK_SCRIPT_JSON", "")
        if raw:
            try:
                script = {tuple(k.split("|", 1)): list(v)
                          for k, v in json.loads(raw).items()}
                return MockReader(script)
            except (ValueError, AttributeError):
                return None
        return MockReader({})
    if mode in ("", "baseten"):
        if os.environ.get("BASETEN_API_KEY"):
            return BasetenReader()
        return None
    return None


def resolve_segmenter() -> Segmenter:
    if os.environ.get("SAM_MODAL_ENDPOINT"):
        return ModalSegmenter()
    return PillowFallbackSegmenter()


# ---------------------------------------------------------------------------
# Job state
# ---------------------------------------------------------------------------

@dataclass
class Job:
    id: str
    state: str = "queued"  # queued|running|done|failed|reader_not_configured
    created_at: float = dc_field(default_factory=time.time)
    events: list[dict] = dc_field(default_factory=list)
    result: dict | None = None
    message: str | None = None
    reader_configured: bool = False
    _seq: int = 0
    _lock: threading.Lock = dc_field(default_factory=threading.Lock)

    def emit(self, event: dict) -> None:
        with self._lock:
            self._seq += 1
            self.events.append({"seq": self._seq, **event})

    def snapshot_events(self) -> list[dict]:
        with self._lock:
            return list(self.events)

    @property
    def finished(self) -> bool:
        return self.state in ("done", "failed", "reader_not_configured")


class JobStore:
    """In-memory job registry with a simple cap + TTL eviction."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._slots = threading.Semaphore(MAX_CONCURRENT_JOBS)

    def _evict_locked(self) -> None:
        now = time.time()
        stale = [jid for jid, j in self._jobs.items()
                 if j.finished and now - j.created_at > JOB_TTL_SECONDS]
        for jid in stale:
            del self._jobs[jid]
        if len(self._jobs) > MAX_STORED_JOBS:
            oldest = sorted(self._jobs.values(), key=lambda j: j.created_at)
            for job in oldest[: len(self._jobs) - MAX_STORED_JOBS]:
                if job.finished:
                    del self._jobs[job.id]

    def create(self) -> Job | None:
        with self._lock:
            self._evict_locked()
            active = sum(1 for j in self._jobs.values() if not j.finished)
            if active >= MAX_ACTIVE_JOBS:
                return None
            job = Job(id=uuid.uuid4().hex[:12])
            self._jobs[job.id] = job
            return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            self._evict_locked()
            return self._jobs.get(job_id)


STORE = JobStore()


# ---------------------------------------------------------------------------
# Evidence capture + tracing wrappers around the real agent loop
# ---------------------------------------------------------------------------

def _evidence_data_url(image_path: str) -> str | None:
    """A downscaled PNG data URL of an image the agent actually read."""
    try:
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        if img.width > EVIDENCE_MAX_WIDTH:
            img = img.resize((EVIDENCE_MAX_WIDTH,
                              int(img.height * EVIDENCE_MAX_WIDTH / img.width)))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def _make_perturbed_views(image_path: str, work_dir: Path) -> dict[str, str]:
    """Real perturbed copies of one document: zoom, contrast, zoom_tight.

    The agent loop names views; judge mode gives those names actual
    transformed images so the reader genuinely reads a different view
    (and the reviewer can see it as evidence).
    """
    from PIL import Image, ImageEnhance

    views: dict[str, str] = {}
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception:
        return views
    stem = Path(image_path).stem

    def _save(name: str, im) -> None:
        out = work_dir / f"{stem}_{name}.png"
        im.save(out)
        views[name] = str(out)

    w, h = img.size
    _save("zoom", img.crop((int(w * .15), int(h * .10),
                            int(w * .85), int(h * .75))).resize((w, h)))
    _save("contrast", ImageEnhance.Contrast(img).enhance(1.8))
    _save("zoom_tight", img.crop((int(w * .25), int(h * .18),
                                  int(w * .75), int(h * .60))).resize((w, h)))
    return views


class _TracingSegmenter:
    """Wraps the configured segmenter; records masked views it produces."""

    def __init__(self, inner: Segmenter, job: Job, capture) -> None:
        self._inner = inner
        self._job = job
        self._capture = capture  # fn(doc_type, view_label, path)
        self.masked_by_source: dict[str, str] = {}

    def segment(self, image_path, prompt):
        return self._inner.segment(image_path, prompt)

    def masked_image(self, image_path, prompt, out_path=None):
        masked = self._inner.masked_image(image_path, prompt, out_path)
        if masked:
            self.masked_by_source[image_path] = masked
            provider = getattr(self._inner, "provider", "segmenter")
            self._job.emit({
                "type": "segment", "phase": "Segment",
                "text": f"Masked the {prompt} region ({provider}) to "
                        f"re-read the field underneath it.",
                "image_path": image_path,
            })
            self._capture(None, "stamp_masked", masked,
                          source_path=image_path)
        return masked


class _TracingReader:
    """Wraps the configured reader; resolves views to real image files,
    records every read as a trace event, and captures evidence views."""

    def __init__(self, inner: Reader, job: Job, views_by_doc: dict,
                 segmenter: _TracingSegmenter, capture,
                 deadline: float) -> None:
        self._inner = inner
        self._job = job
        self._views_by_doc = views_by_doc      # doc_type -> {view: path}
        self._segmenter = segmenter
        self._capture = capture                # fn(doc_type, view, path)
        self._deadline = deadline
        self.read_log: list[dict] = []

    def read_field(self, image_path: str, doc_type: str, field: str,
                   perturbation: str) -> str:
        if time.time() > self._deadline:
            raise TimeoutError("judge job exceeded its time budget")
        resolved = image_path
        if perturbation == "stamp_masked":
            # The agent passes the segmenter's masked copy directly when
            # one was produced; otherwise fall back to the original.
            resolved = image_path
        elif perturbation in self._views_by_doc.get(doc_type, {}):
            resolved = self._views_by_doc[doc_type][perturbation]
        value = self._inner.read_field(resolved, doc_type, field,
                                       perturbation)
        self._capture(doc_type, perturbation, resolved)
        entry = {"doc_type": doc_type, "field": field,
                 "view": perturbation, "value": value}
        self.read_log.append(entry)
        self._job.emit({
            "type": "read", "phase": f"Read · {perturbation}",
            "doc_type": doc_type, "field": field, "view": perturbation,
            "value": value,
            "text": f"{doc_type} · {field} · {perturbation} → "
                    f"{value if value else 'UNREADABLE'}",
        })
        return value


# ---------------------------------------------------------------------------
# The job itself
# ---------------------------------------------------------------------------

def process_job(job: Job, uploads: dict[str, bytes],
                reader: Reader | None, segmenter: Segmenter) -> None:
    """Run one judge job synchronously (called from a background task).

    uploads: {doc_type: raw image bytes}. Nothing is persisted beyond a
    per-job temp directory that is removed before this returns.
    """
    with STORE._slots:
        job.state = "running"
        job.reader_configured = reader is not None
        work_dir = Path(tempfile.mkdtemp(prefix=f"doctrust_job_{job.id}_"))
        try:
            _run(job, uploads, reader, segmenter, work_dir)
        except TimeoutError:
            job.state = "failed"
            job.message = (f"Review exceeded the per-job time budget "
                           f"({JOB_TIMEOUT_SECONDS:.0f}s) and was stopped.")
            job.emit({"type": "error", "phase": "Error",
                      "text": job.message})
        except Exception as exc:  # surface, never swallow silently
            job.state = "failed"
            job.message = f"Review failed: {exc}"
            job.emit({"type": "error", "phase": "Error",
                      "text": job.message})
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


def _run(job: Job, uploads: dict[str, bytes], reader: Reader | None,
         segmenter: Segmenter, work_dir: Path) -> None:
    job.emit({"type": "job_started", "phase": "Intake",
              "text": "Received 3 synthetic documents "
                      "(NID, birth certificate, bank form). "
                      "Judge mode is for synthetic documents only."})

    # Save uploads into the job temp dir and build real perturbed views.
    paths: dict[str, str] = {}
    views_by_doc: dict[str, dict[str, str]] = {}
    evidence: list[dict] = []
    captured: set = set()

    def capture(doc_type: str | None, view: str, path: str,
                source_path: str | None = None) -> None:
        # For masked views the agent passes the masked path directly and
        # doc_type arrives as None; attribute it via the source path.
        if doc_type is None and source_path is not None:
            doc_type = next((d for d, p in paths.items()
                             if p == source_path), "document")
        key = (doc_type or "document", view, path)
        if key in captured:
            return
        captured.add(key)
        url = _evidence_data_url(path)
        if url:
            evidence.append({"doc_type": doc_type or "document",
                             "view": view, "data_url": url})

    for doc_type in DOC_TYPES:
        raw = uploads[doc_type]
        suffix = ".jpg" if raw[:2] == b"\xff\xd8" else ".png"
        path = work_dir / f"{doc_type}{suffix}"
        path.write_bytes(raw)
        paths[doc_type] = str(path)
        views_by_doc[doc_type] = _make_perturbed_views(str(path), work_dir)
        job.emit({"type": "preprocess", "phase": "Preprocess",
                  "doc_type": doc_type,
                  "text": f"{doc_type}: prepared zoom / contrast / "
                          f"tight-zoom views for perturbation reads."})
        capture(doc_type, "original", str(path))

    # Segmentation probe (no reader needed): does a stamp-like region
    # exist that the agent could mask during investigation?
    tracing_segmenter = _TracingSegmenter(segmenter, job, capture)
    for doc_type in DOC_TYPES:
        try:
            result = segmenter.segment(paths[doc_type], "stamp")
        except Exception:
            result = None
        boxes = len(result.boxes) if result and result.boxes else 0
        job.emit({"type": "segment_probe", "phase": "Segment",
                  "doc_type": doc_type,
                  "text": f"{doc_type}: stamp probe found "
                          f"{boxes} region(s) "
                          f"({getattr(segmenter, 'provider', 'segmenter')})."})

    if reader is None:
        job.state = "reader_not_configured"
        job.message = READER_NOT_CONFIGURED_MESSAGE
        job.result = {
            "job_id": job.id, "state": job.state, "verdict": None,
            "verdict_label": None, "message": job.message,
            "documents": {}, "findings": [], "evidence": evidence,
        }
        job.emit({"type": "reader_not_configured", "phase": "Reader",
                  "text": job.message})
        return

    tracing_reader = _TracingReader(
        reader, job, views_by_doc, tracing_segmenter, capture,
        deadline=time.time() + JOB_TIMEOUT_SECONDS)
    outcome = agent_module.run_review(tracing_reader, paths,
                                      segmenter=tracing_segmenter)

    job.emit({"type": "compare", "phase": "Cross-examine",
              "text": "Normalized every field (digits, dates, name "
                      "variants) and compared shared facts across the "
                      "three documents."})

    documents: dict[str, dict] = {}
    reads_by_key: dict[tuple[str, str], list[dict]] = {}
    for entry in tracing_reader.read_log:
        reads_by_key.setdefault((entry["doc_type"], entry["field"]),
                                []).append({"view": entry["view"],
                                            "value": entry["value"]})
    for fr in outcome.field_reads:
        raw = outcome.documents.get(fr.doc_type, {}).get(fr.field)
        documents.setdefault(fr.doc_type, {})[fr.field] = {
            "value": fr.value,
            "canonical": _canonical(fr.field, raw) or "",
            "uncertain": fr.uncertain,
            "reads": reads_by_key.get((fr.doc_type, fr.field), []),
        }

    verdict_label = VERDICT_LABELS.get(outcome.verdict, outcome.verdict)
    job.result = {
        "job_id": job.id, "state": "done", "verdict": outcome.verdict,
        "verdict_label": verdict_label, "message": None,
        "documents": documents, "findings": outcome.findings,
        "evidence": evidence,
    }
    job.state = "done"
    job.emit({"type": "verdict", "phase": "Verdict",
              "verdict": outcome.verdict, "verdict_label": verdict_label,
              "text": f"Verdict: {verdict_label}."})

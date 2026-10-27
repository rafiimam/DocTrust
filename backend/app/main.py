"""DocTrust backend — FastAPI entry point.

Routes:
- GET  /health                          service health
- POST /api/review                      judge mode: upload 3 synthetic
                                        document images, run the agent
                                        loop as a background job
- GET  /api/review/{job_id}/events      SSE stream of the job's trace
- GET  /api/review/{job_id}             job state / final result JSON
- GET  /api/case-pack/{variant}         freshly generated synthetic set
                                        (ZIP) a judge can download and
                                        then upload to /api/review

Judge mode is for SYNTHETIC documents only. If no vision reader is
configured on the server, /api/review still accepts uploads and runs
preprocessing/segmentation, but the job ends in the honest
"reader_not_configured" state — reads are never faked. See app/judge.py.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

from fastapi import (BackgroundTasks, Depends, FastAPI, File, HTTPException,
                     Request, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from . import judge as judge_module

# The synthetic generator lives at the repository root (generator/).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

app = FastAPI(title="DocTrust", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://rafiimam.github.io",   # the GitHub Pages demo
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- Dependencies (tests override these to inject a MockReader) -----------

def get_reader():
    return judge_module.resolve_reader()


def get_segmenter():
    return judge_module.resolve_segmenter()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "doctrust"}


# --- Judge mode ------------------------------------------------------------

async def _read_upload(upload: UploadFile, doc_type: str) -> bytes:
    suffix = Path(upload.filename or "").suffix.lower()
    content_type = (upload.content_type or "").split(";")[0].strip()
    if suffix not in judge_module.ALLOWED_SUFFIXES or \
            content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(
            status_code=415,
            detail=f"{doc_type}: only PNG or JPG images are accepted.")
    data = await upload.read()
    if len(data) > judge_module.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"{doc_type}: file exceeds the "
                   f"{judge_module.MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
    if not data:
        raise HTTPException(status_code=400,
                            detail=f"{doc_type}: empty file.")
    # Verify the bytes really are an image Pillow can open.
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"{doc_type}: file is not a readable image.")
    return data


@app.post("/api/review", status_code=202)
async def create_review(
    background: BackgroundTasks,
    nid: UploadFile = File(...),
    birth_certificate: UploadFile = File(...),
    bank_form: UploadFile = File(...),
    reader=Depends(get_reader),
    segmenter=Depends(get_segmenter),
):
    """Accept three synthetic document images and start a review job."""
    uploads = {
        "nid": await _read_upload(nid, "nid"),
        "birth_certificate": await _read_upload(
            birth_certificate, "birth_certificate"),
        "bank_form": await _read_upload(bank_form, "bank_form"),
    }
    try:
        job = judge_module.STORE.create(
            live=judge_module.is_live_reader(reader))
    except judge_module.DailyCapReached:
        raise HTTPException(status_code=429,
                            detail=judge_module.DAILY_CAP_MESSAGE)
    if job is None:
        raise HTTPException(
            status_code=429,
            detail="Too many reviews in progress; try again shortly.")
    job.reader_configured = reader is not None
    job.emit({"type": "queued", "phase": "Intake",
              "text": "Upload accepted; review queued."})
    background.add_task(judge_module.process_job, job, uploads,
                        reader, segmenter)
    return {"job_id": job.id, "state": job.state,
            "reader_configured": reader is not None,
            "events_url": f"/api/review/{job.id}/events",
            "result_url": f"/api/review/{job.id}"}


@app.get("/api/review/{job_id}")
def get_review(job_id: str):
    job = judge_module.STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id.")
    if job.result is not None:
        return job.result
    return {"job_id": job.id, "state": job.state,
            "verdict": None, "verdict_label": None,
            "message": job.message, "documents": {}, "findings": [],
            "evidence": []}


@app.get("/api/review/{job_id}/events")
async def review_events(job_id: str, request: Request):
    """SSE: replay the job's trace, stream new events, then 'done'."""
    job = judge_module.STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id.")

    async def stream():
        sent = 0
        while True:
            if await request.is_disconnected():
                return
            events = job.snapshot_events()
            for event in events[sent:]:
                sent += 1
                yield (f"id: {event['seq']}\nevent: trace\n"
                       f"data: {json.dumps(event)}\n\n")
            if job.finished:
                done = {"job_id": job.id, "state": job.state,
                        "verdict": (job.result or {}).get("verdict"),
                        "verdict_label": (job.result or {}).get(
                            "verdict_label"),
                        "message": job.message}
                yield f"event: done\ndata: {json.dumps(done)}\n\n"
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# --- Case packs --------------------------------------------------------------

@app.get("/api/case-pack/{variant}")
def case_pack(variant: str):
    """Generate a fresh synthetic set on the fly and stream it as a ZIP.

    Gives judges real downloadable inputs (PNGs + ground_truth.json)
    without any binary files living in the repository.
    """
    if variant not in judge_module.CASE_VARIANTS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown variant; choose one of "
                   f"{', '.join(judge_module.CASE_VARIANTS)}.")
    from generator.generate import generate_set

    with tempfile.TemporaryDirectory(prefix="doctrust_pack_") as tmp:
        generate_set(tmp, variant)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in ("nid.png", "birth_certificate.png",
                         "bank_form.png", "ground_truth.json"):
                zf.write(Path(tmp) / name, arcname=name)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition":
                 f'attachment; filename="doctrust-case-{variant}.zip"'})

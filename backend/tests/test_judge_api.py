"""Judge-mode API tests (backend/app/main.py + backend/app/judge.py).

Everything runs offline: a MockReader scripted from the generator's own
ground truth stands in for the vision model, exactly like the agent
tests. The reader_not_configured path is tested with the reader
dependency overridden to None — the API must report that state honestly
and never invent field reads.
"""

import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.main import app
from app.providers import MockReader
from app.segmenter import PillowFallbackSegmenter
from generator.generate import build_person, generate_set


@pytest.fixture()
def generated(tmp_path):
    """Generate each variant once per test into tmp_path/<variant>/."""
    def _gen(variant: str) -> Path:
        out = tmp_path / variant
        generate_set(out, variant)
        return out
    return _gen


def _script_for(variant: str) -> dict:
    """MockReader script that reads exactly what each document says."""
    _person, truth, _extra = build_person(variant, __import__("random").Random(7))
    return {(doc, field): [value]
            for doc, fields in truth.items()
            for field, value in fields.items()}


def _client(reader, segmenter=None):
    app.dependency_overrides[main_module.get_reader] = lambda: reader
    app.dependency_overrides[main_module.get_segmenter] = (
        lambda: segmenter or PillowFallbackSegmenter())
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _upload(client, doc_dir: Path):
    files = {}
    for name in ("nid", "birth_certificate", "bank_form"):
        files[name] = (f"{name}.png", (doc_dir / f"{name}.png").read_bytes(),
                       "image/png")
    return client.post("/api/review", files=files)


def _wait_result(client, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/review/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["state"] in ("done", "failed", "reader_not_configured"):
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


# --- Case packs -------------------------------------------------------------

def test_case_pack_zip_contents_and_ground_truth(generated):
    with _client(MockReader({})) as client:
        resp = client.get("/api/case-pack/discrepancy")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert sorted(zf.namelist()) == [
        "bank_form.png", "birth_certificate.png", "ground_truth.json",
        "nid.png",
    ]
    truth = json.loads(zf.read("ground_truth.json"))
    assert truth["variant"] == "discrepancy"
    # The pack is the generator's own set: the form carries the DOB swap.
    assert truth["documents"]["bank_form"]["dob"] == "12/03/1991"
    assert truth["documents"]["nid"]["dob"] == "12/03/1990"
    for name in ("nid.png", "birth_certificate.png", "bank_form.png"):
        assert zf.getinfo(name).file_size > 1000


def test_case_pack_unknown_variant_404(generated):
    with _client(MockReader({})) as client:
        assert client.get("/api/case-pack/bogus").status_code == 404


# --- Full upload -> events -> result flow -----------------------------------

def test_upload_events_result_discrepancy(generated):
    doc_dir = generated("discrepancy")
    reader = MockReader(_script_for("discrepancy"))
    with _client(reader) as client:
        resp = _upload(client, doc_dir)
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        assert resp.json()["reader_configured"] is True

        result = _wait_result(client, job_id)
        assert result["state"] == "done"
        assert result["verdict"] == "DISCREPANCY"
        assert result["verdict_label"] == "Discrepancy, needs human review"

        # Per-field reads with canonical forms and per-view readings.
        dob = result["documents"]["bank_form"]["dob"]
        assert dob["value"] == "12/03/1991"
        assert dob["canonical"] == "1991-03-12"
        assert dob["reads"], "expected per-view readings to be recorded"
        assert {r["view"] for r in dob["reads"]} >= {"original", "zoom",
                                                     "contrast"}
        nid_id = result["documents"]["nid"]["id_number"]
        assert nid_id["canonical"] == "1234567890"  # Bangla digits folded

        findings = {f["field"]: f["status"] for f in result["findings"]}
        assert findings["dob"] == "mismatch"

        # Evidence: at least the original views were captured as PNG
        # data URLs.
        assert result["evidence"], "expected evidence views in the result"
        assert all(e["data_url"].startswith("data:image/png;base64,")
                   for e in result["evidence"])
        assert any(e["view"] == "original" for e in result["evidence"])

        # SSE: replayed trace ends with a 'done' event for this job.
        with client.stream("GET", f"/api/review/{job_id}/events") as sse:
            body = "".join(sse.iter_text())
        assert "event: trace" in body
        assert "event: done" in body
        assert '"state": "done"' in body
        assert "Cross-examine" in body or "Read" in body


def test_investigation_captures_masked_evidence(generated):
    # First-pass reads of the birth certificate's DOB disagree, so the
    # agent investigates: the segmenter masks the stamp (the certificate
    # really has one) and the masked view is re-read and captured as
    # evidence. The majority still settles on the true date.
    doc_dir = generated("clean")
    script = _script_for("clean")
    script[("birth_certificate", "dob")] = [
        "১২/০৩/১৯৯০", "১২/০৮/১৯৯০", "১২/০৩/১৯৯০",
        "১২/০৩/১৯৯০", "১২/০৩/১৯৯০",
    ]
    reader = MockReader(script)
    with _client(reader) as client:
        resp = _upload(client, doc_dir)
        result = _wait_result(client, resp.json()["job_id"])
    assert result["verdict"] == "CONSISTENT"
    dob = result["documents"]["birth_certificate"]["dob"]
    assert dob["uncertain"] is True
    assert "stamp_masked" in {r["view"] for r in dob["reads"]}
    masked = [e for e in result["evidence"] if e["view"] == "stamp_masked"]
    assert masked and masked[0]["doc_type"] == "birth_certificate"
    assert masked[0]["data_url"].startswith("data:image/png;base64,")


def test_upload_consistent_set(generated):
    doc_dir = generated("clean")
    reader = MockReader(_script_for("clean"))
    with _client(reader) as client:
        resp = _upload(client, doc_dir)
        result = _wait_result(client, resp.json()["job_id"])
    assert result["verdict"] == "CONSISTENT"


# --- Validation ---------------------------------------------------------------

def test_upload_rejects_wrong_file_type(generated):
    doc_dir = generated("clean")
    with _client(MockReader(_script_for("clean"))) as client:
        files = {
            "nid": ("nid.txt", b"not an image", "text/plain"),
            "birth_certificate": (
                "birth_certificate.png",
                (doc_dir / "birth_certificate.png").read_bytes(),
                "image/png"),
            "bank_form": (
                "bank_form.png",
                (doc_dir / "bank_form.png").read_bytes(), "image/png"),
        }
        resp = client.post("/api/review", files=files)
    assert resp.status_code == 415


def test_upload_rejects_oversize(generated, monkeypatch):
    doc_dir = generated("clean")
    monkeypatch.setattr(main_module.judge_module, "MAX_UPLOAD_BYTES", 1024)
    with _client(MockReader(_script_for("clean"))) as client:
        resp = _upload(client, doc_dir)
    assert resp.status_code == 413


def test_upload_rejects_missing_document(generated):
    doc_dir = generated("clean")
    with _client(MockReader(_script_for("clean"))) as client:
        files = {
            "nid": ("nid.png", (doc_dir / "nid.png").read_bytes(),
                    "image/png"),
        }
        resp = client.post("/api/review", files=files)
    assert resp.status_code == 422


def test_unknown_job_404():
    with _client(MockReader({})) as client:
        assert client.get("/api/review/nope").status_code == 404
        assert client.get("/api/review/nope/events").status_code == 404


# --- Honest reader_not_configured path ----------------------------------------

def test_reader_not_configured_is_honest(generated):
    doc_dir = generated("clean")
    with _client(None) as client:  # no reader configured on the server
        resp = _upload(client, doc_dir)
        assert resp.status_code == 202
        assert resp.json()["reader_configured"] is False
        result = _wait_result(client, resp.json()["job_id"])

        assert result["state"] == "reader_not_configured"
        assert result["verdict"] is None
        assert "No vision reader is configured" in result["message"]
        # Preprocessing/segmentation evidence exists, but NO field reads
        # were invented.
        assert result["documents"] == {}
        assert result["findings"] == []
        assert result["evidence"], "preprocessing evidence should exist"

        job_id = resp.json()["job_id"]
        with client.stream("GET", f"/api/review/{job_id}/events") as sse:
            body = "".join(sse.iter_text())
        assert "reader_not_configured" in body

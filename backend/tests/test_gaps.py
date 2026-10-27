"""Evidence-gap report tests (backend/app/gaps.py + judge wiring).

The gap list is a deterministic projection of a completed review's
recorded state — uploaded document types, final field values, and
comparator findings — into three states that must stay distinct:
missing_document (not a contradiction), unresolved_field (not a
mismatch), unresolved_discrepancy (not proof of fraud). Everything
here runs offline; the judge-level tests drive process_job directly
with a MockReader scripted from the generator's ground truth.
"""

import random
from pathlib import Path

from app import judge as judge_module
from app.agent import FIELDS_BY_DOC
from app.gaps import build_evidence_gaps
from app.providers import MockReader
from app.segmenter import PillowFallbackSegmenter
from generator.generate import build_person, generate_set

ALL_DOCS = ("nid", "birth_certificate", "bank_form")


def _entry(value):
    """One field record in the exact shape judge.py puts in the result."""
    return {"value": value, "canonical": "", "uncertain": False,
            "reads": []}


def _documents(values=None):
    """Full three-document records, every field read as "x" by default."""
    values = values or {}
    return {
        doc: {field: _entry(values.get((doc, field), "x"))
              for field in FIELDS_BY_DOC[doc]}
        for doc in ALL_DOCS
    }


def _finding(field, status, values=None):
    return {"field": field, "status": status,
            "values": values or {}, "canonical": {}}


# --- Pure builder -------------------------------------------------------------

def test_clean_consistent_packet_has_no_gaps():
    findings = [_finding("name", "match"), _finding("dob", "variant"),
                _finding("id_number", "single_source")]
    assert build_evidence_gaps(ALL_DOCS, _documents(), findings) == []


def test_missing_document_gap_names_it_and_nothing_else():
    present = ("nid", "birth_certificate")
    documents = {doc: _documents()[doc] for doc in present}
    gaps = build_evidence_gaps(present, documents, [])
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["kind"] == "missing_document"
    assert gap["doc_type"] == "bank_form"
    assert gap["field"] is None
    assert "bank form" in gap["detail"]
    assert gap["next_step"] == (
        "Request the missing document before completing the review.")
    # The never-uploaded document's fields must NOT also appear as
    # unresolved fields — nobody attempted to read them.
    assert not any(g["kind"] == "unresolved_field" for g in gaps)


def test_unresolved_field_gap_for_none_value():
    documents = _documents({("nid", "dob"): None})
    gaps = build_evidence_gaps(ALL_DOCS, documents, [])
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["kind"] == "unresolved_field"
    assert gap["doc_type"] == "nid"
    assert gap["field"] == "dob"
    assert "clearer image" in gap["next_step"]
    assert "accepted source" in gap["next_step"]


def test_discrepancy_gap_for_mismatch_finding():
    finding = _finding("dob", "mismatch",
                       {"nid": "12/03/1990", "bank_form": "12/03/1991"})
    gaps = build_evidence_gaps(ALL_DOCS, _documents(), [finding])
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["kind"] == "unresolved_discrepancy"
    assert gap["field"] == "dob"
    assert gap["doc_type"] is None
    assert "12/03/1990" in gap["detail"]
    assert "12/03/1991" in gap["detail"]
    assert "established verification process" in gap["next_step"]


def test_combined_states_stay_distinct_and_ordered():
    present = ("nid", "birth_certificate")  # bank_form missing
    documents = {doc: _documents()[doc] for doc in present}
    documents["nid"]["dob"] = _entry(None)  # unreadable after investigation
    findings = [_finding(
        "name", "mismatch",
        {"nid": "Mohammad Rahman", "birth_certificate": "Mohammed Rahman"})]
    gaps = build_evidence_gaps(present, documents, findings)
    assert [g["kind"] for g in gaps] == [
        "missing_document", "unresolved_field", "unresolved_discrepancy"]
    assert gaps[0]["doc_type"] == "bank_form"
    assert (gaps[1]["doc_type"], gaps[1]["field"]) == ("nid", "dob")
    assert gaps[2]["field"] == "name"


def test_gaps_never_say_fraud_or_recommend_rejection():
    present = ("nid", "birth_certificate")
    documents = {doc: _documents()[doc] for doc in present}
    documents["nid"]["dob"] = _entry(None)
    findings = [_finding("dob", "mismatch",
                         {"nid": "12/03/1990",
                          "birth_certificate": "12/03/1991"})]
    for gap in build_evidence_gaps(present, documents, findings):
        text = (gap["detail"] + " " + gap["next_step"]).lower()
        assert "fraud" not in text
        assert "reject" not in text


# --- Judge-level wiring ---------------------------------------------------------

def _script_for(variant: str) -> dict:
    """MockReader script that reads exactly what each document says."""
    _person, truth, _extra = build_person(variant, random.Random(7))
    return {(doc, field): [value]
            for doc, fields in truth.items()
            for field, value in fields.items()}


def _run_job(tmp_path: Path, variant: str, doc_types) -> judge_module.Job:
    out = tmp_path / variant
    generate_set(out, variant)
    uploads = {doc: (out / f"{doc}.png").read_bytes() for doc in doc_types}
    job = judge_module.Job(id="gaptest")
    judge_module.process_job(job, uploads,
                             MockReader(_script_for(variant)),
                             PillowFallbackSegmenter())
    return job


def test_judge_result_contains_evidence_gaps_clean(tmp_path):
    job = _run_job(tmp_path, "clean", ALL_DOCS)
    assert job.state == "done"
    assert job.result["verdict"] == "CONSISTENT"
    assert job.result["evidence_gaps"] == []


def test_judge_missing_bank_form_reports_gap_only(tmp_path):
    job = _run_job(tmp_path, "clean", ("nid", "birth_certificate"))
    assert job.state == "done"
    gaps = job.result["evidence_gaps"]
    assert [g["kind"] for g in gaps] == ["missing_document"]
    assert gaps[0]["doc_type"] == "bank_form"
    # No bank_form field was read, so none may be reported unresolved.
    assert not any(g["doc_type"] == "bank_form"
                   and g["kind"] == "unresolved_field" for g in gaps)


def test_judge_discrepancy_result_reports_discrepancy_gap(tmp_path):
    job = _run_job(tmp_path, "discrepancy", ALL_DOCS)
    assert job.state == "done"
    assert job.result["verdict"] == "DISCREPANCY"
    kinds = [g["kind"] for g in job.result["evidence_gaps"]]
    assert kinds == ["unresolved_discrepancy"]
    assert job.result["evidence_gaps"][0]["field"] == "dob"

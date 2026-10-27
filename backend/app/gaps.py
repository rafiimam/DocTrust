"""Evidence gaps & next steps — a deterministic section of the report.

The verdict says what the evidence supports. This section says what the
evidence is *missing*, in three states that must never be blurred:

- ``missing_document`` — a document the case profile expects was not
  uploaded at all. A missing document is not a contradiction.
- ``unresolved_field`` — a field whose final recorded value is None:
  unreadable even after investigation. An unreadable field is not a
  mismatch.
- ``unresolved_discrepancy`` — readable documents disagree on a field
  (a comparator ``mismatch`` finding). A mismatch is not proof of
  fraud: that word never appears here, and no gap ever recommends
  rejection.

Every gap is derived deterministically from the recorded job state —
the uploaded document types, the final field values, and the comparator
findings. No model calls and no invented requirements: the case profile
is exactly the document set the pipeline already knows
(``agent.FIELDS_BY_DOC``), and a field is reported unresolved only when
its recorded final value is None.

Order: missing documents first (what evidence exists at all), then
unresolved fields (what could not be read), then discrepancies (what
conflicts) — a reviewer should learn what is absent before what is
unreadable before what disagrees. Within a kind, gaps follow the
profile's document order and the comparator's finding order, so the
list is stable for identical inputs.

Input shapes are the ones judge mode already produces
(``app/judge.py``): ``documents`` maps doc_type -> field ->
``{"value": ..., "canonical": ..., "uncertain": ..., "reads": [...]}``
and ``findings`` is the serialized comparator output (dicts with
``field``, ``status``, ``values``, ``canonical``).
"""

from __future__ import annotations

from .agent import FIELDS_BY_DOC

# The configured case profile for judge mode: the KYC document set the
# pipeline already knows. Nothing else is ever "expected".
PROFILE_DOC_TYPES = tuple(FIELDS_BY_DOC)

DOC_LABELS = {
    "nid": "national ID (NID)",
    "birth_certificate": "birth certificate",
    "bank_form": "bank form",
}

FIELD_LABELS = {
    "name": "name",
    "dob": "date of birth",
    "id_number": "ID number",
    "father_name": "father's name",
}

NEXT_STEP_MISSING_DOCUMENT = (
    "Request the missing document before completing the review."
)
NEXT_STEP_UNRESOLVED_DISCREPANCY = (
    "Inspect the cited fields and follow the institution's established "
    "verification process."
)


def _doc_label(doc_type: str) -> str:
    return DOC_LABELS.get(doc_type, doc_type)


def _field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


def _final_value(entry) -> object:
    """The recorded final value of one field entry (None = unreadable)."""
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def build_evidence_gaps(present_doc_types, documents, findings) -> list[dict]:
    """Derive the evidence-gap list from a completed review's records.

    present_doc_types: the document types actually uploaded.
    documents: the judge result's per-document field records.
    findings: the serialized comparator findings.

    Returns a list of {"kind", "doc_type", "field", "detail",
    "next_step"} dicts (doc_type/field are None where a gap is not
    about one document or one field). A document that was never
    uploaded produces only its missing_document gap — never
    unresolved_field gaps for fields nobody attempted to read.
    """
    gaps: list[dict] = []
    present_set = set(present_doc_types or ())
    documents = documents or {}

    # 1. Expected evidence not provided (profile order).
    for doc_type in PROFILE_DOC_TYPES:
        if doc_type not in present_set:
            gaps.append({
                "kind": "missing_document",
                "doc_type": doc_type,
                "field": None,
                "detail": f"The {_doc_label(doc_type)} was not included "
                          f"in the upload, so none of its evidence could "
                          f"be checked.",
                "next_step": NEXT_STEP_MISSING_DOCUMENT,
            })

    # 2. Fields that stayed unreadable after investigation — present
    # documents only, and only where a final value was recorded as None.
    for doc_type in PROFILE_DOC_TYPES:
        if doc_type not in present_set:
            continue
        recorded = documents.get(doc_type) or {}
        for field in FIELDS_BY_DOC[doc_type]:
            if field in recorded and _final_value(recorded[field]) is None:
                gaps.append({
                    "kind": "unresolved_field",
                    "doc_type": doc_type,
                    "field": field,
                    "detail": f"The {_field_label(field)} on the "
                              f"{_doc_label(doc_type)} could not be read "
                              f"reliably, even after investigation.",
                    "next_step": f"Obtain a clearer image of the "
                                 f"{_doc_label(doc_type)}, or verify the "
                                 f"{_field_label(field)} against an "
                                 f"accepted source.",
                })

    # 3. Readable documents that disagree (comparator mismatches).
    for finding in findings or []:
        if finding.get("status") != "mismatch":
            continue
        field = finding.get("field")
        values = finding.get("values") or {}
        cited = "; ".join(
            f"{_doc_label(doc)} reads '{value}'"
            for doc, value in values.items() if value)
        gaps.append({
            "kind": "unresolved_discrepancy",
            "doc_type": None,
            "field": field,
            "detail": f"Readable documents disagree on the "
                      f"{_field_label(field)}: {cited}.",
            "next_step": NEXT_STEP_UNRESOLVED_DISCREPANCY,
        })

    return gaps

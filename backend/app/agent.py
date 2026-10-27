"""The DocTrust agent loop (v1).

For every field of every document in a set:
  1. Read the field under several perturbations.
  2. If the reads disagree, the field is *uncertain* — investigate with
     additional views (the production investigation also masks occluding
     regions via SAM 3.1; v1 uses the extra views as the investigation
     step, and the trace records that this is where masking plugs in).
  3. A field still unreadable after investigation stays unreadable —
     the comparator turns that into the recapture verdict, never a flag.

Everything after the reads is deterministic (normalize + comparator), so
the verdict a reviewer sees is traceable end to end.
"""

from __future__ import annotations

from dataclasses import asdict

from . import comparator
from .providers import Reader
from .schemas import FieldRead, ReviewOutcome

FIELDS_BY_DOC = {
    "nid": ["name", "dob", "id_number", "father_name"],
    "birth_certificate": ["name", "dob", "father_name"],
    "bank_form": ["name", "dob", "id_number", "father_name"],
}

FIRST_PASS_VIEWS = ["original", "zoom", "contrast"]
INVESTIGATION_VIEWS = ["stamp_masked", "zoom_tight"]


def _majority(values: list[str]) -> str | None:
    readable = [v for v in values if v and v != "UNREADABLE"]
    if not readable:
        return None
    return max(set(readable), key=readable.count)


def read_field_with_uncertainty(reader: Reader, image_path: str,
                                doc_type: str, field: str) -> FieldRead:
    reads = [reader.read_field(image_path, doc_type, field, view)
             for view in FIRST_PASS_VIEWS]
    readable = {v for v in reads if v and v != "UNREADABLE"}
    uncertain = len(readable) > 1
    if uncertain or not readable:
        for view in INVESTIGATION_VIEWS:
            reads.append(reader.read_field(image_path, doc_type, field, view))
    return FieldRead(doc_type=doc_type, field=field,
                     value=_majority(reads), uncertain=uncertain, reads=reads)


def run_review(reader: Reader, images: dict[str, str]) -> ReviewOutcome:
    """images: {doc_type: image_path}. Returns verdict + full trace."""
    field_reads: list[FieldRead] = []
    documents: dict[str, dict[str, str]] = {}
    for doc_type, image_path in images.items():
        documents[doc_type] = {}
        for field in FIELDS_BY_DOC.get(doc_type, []):
            fr = read_field_with_uncertainty(reader, image_path, doc_type, field)
            field_reads.append(fr)
            # Keep None explicitly: the comparator must see "attempted but
            # unreadable" to produce the recapture verdict instead of
            # silently treating the field as absent.
            documents[doc_type][field] = fr.value

    result = comparator.compare(documents)
    return ReviewOutcome(
        verdict=result.verdict,
        documents=documents,
        field_reads=field_reads,
        findings=[asdict(f) for f in result.findings],
    )

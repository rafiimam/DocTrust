"""The DocTrust agent loop (v1).

For every field of every document in a set:
  1. Read the field under several perturbations.
  2. If the reads disagree, the field is *uncertain* — investigate with
     additional views. For the "stamp_masked" investigation view, if a
     Segmenter is injected (SAM 3.1 on Modal in production, the Pillow
     fallback offline), the stamp region is masked on a working copy
     and the field is re-read from that copy; with no segmenter — or if
     masking fails — the view is read from the original image exactly
     as before.
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
from .segmenter import Segmenter

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


def _investigation_image(segmenter: Segmenter | None, image_path: str,
                           view: str) -> str:
    """Image to read an investigation view from.

    Only "stamp_masked" changes the image, and only when a segmenter is
    injected and actually produces a masked copy. Any failure returns
    the original path: masking is an aid, never a gate on the review.
    """
    if view != "stamp_masked" or segmenter is None:
        return image_path
    try:
        masked = segmenter.masked_image(image_path, "stamp")
    except Exception:
        return image_path
    return masked or image_path


def read_field_with_uncertainty(reader: Reader, image_path: str,
                                doc_type: str, field: str,
                                segmenter: Segmenter | None = None
                                ) -> FieldRead:
    reads = [reader.read_field(image_path, doc_type, field, view)
             for view in FIRST_PASS_VIEWS]
    readable = {v for v in reads if v and v != "UNREADABLE"}
    uncertain = len(readable) > 1
    if uncertain or not readable:
        for view in INVESTIGATION_VIEWS:
            view_image = _investigation_image(segmenter, image_path, view)
            reads.append(reader.read_field(view_image, doc_type, field, view))
    return FieldRead(doc_type=doc_type, field=field,
                     value=_majority(reads), uncertain=uncertain, reads=reads)


def run_review(reader: Reader, images: dict[str, str],
               segmenter: Segmenter | None = None) -> ReviewOutcome:
    """images: {doc_type: image_path}. Returns verdict + full trace.

    segmenter is optional: without one the loop behaves exactly as the
    reader-only version (investigation views read the original image).
    """
    field_reads: list[FieldRead] = []
    documents: dict[str, dict[str, str]] = {}
    for doc_type, image_path in images.items():
        documents[doc_type] = {}
        for field in FIELDS_BY_DOC.get(doc_type, []):
            fr = read_field_with_uncertainty(reader, image_path, doc_type,
                                             field, segmenter=segmenter)
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

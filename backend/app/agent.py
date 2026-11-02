"""The DocTrust agent loop (v1).

For every field of every document in a set:
  1. Read the field under several perturbations.
  2. If the reads disagree, the field is *uncertain* — investigate.
     Disagreement includes a view failing to read the field at all
     (UNREADABLE/empty): partial unreadability is not agreement, so a
     single surviving value never settles a field on its own.
     Investigation is *model-directed*: before each step the reader
     is consulted as a planner and chooses the next step (mask the
     stamp, zoom in tighter, or stop and request a recapture) with
     its reason logged on the FieldRead. The planner chooses where
     to look, never the answer — normalization and the comparator
     keep full verdict authority. If the planner cannot be consulted
     (the reader has none, or any call fails), the deterministic
     fallback runs the fixed view sequence instead, and the review
     proceeds exactly as it did before the planner existed. For the
     "stamp_masked" view, if a Segmenter is injected (SAM 3.1 on
     Modal in production, the Pillow fallback offline), the stamp
     region is masked on a working copy and the field is re-read from
     that copy; with no segmenter — or if masking fails — the view is
     read from the original image exactly as before.
  3. A field still unreadable after investigation stays unreadable —
     the comparator turns that into the recapture verdict, never a flag.

Everything after the reads is deterministic (normalize + comparator), so
the verdict a reviewer sees is traceable end to end.
"""

from __future__ import annotations

from dataclasses import asdict

from . import comparator
from .providers import DEFAULT_SEGMENT_PROMPT, SEGMENT_PROMPTS, Reader
from .schemas import FieldRead, ReviewOutcome
from .segmenter import Segmenter

FIELDS_BY_DOC = {
    "nid": ["name", "dob", "id_number", "father_name"],
    "birth_certificate": ["name", "dob", "father_name"],
    "bank_form": ["name", "dob", "id_number", "father_name"],
}

FIRST_PASS_VIEWS = ["original", "zoom", "contrast"]
INVESTIGATION_VIEWS = ["stamp_masked", "stamp_removed", "zoom_tight"]

# The actions the investigation planner may choose from, with the
# one-line descriptions it is shown. "stamp_masked" and "zoom_tight"
# are the investigation views above; "recapture" runs no view at
# all — it ends the investigation and leaves the field unreadable.
PLANNER_ACTIONS = {
    "stamp_masked": "Re-read the field from a copy of the document "
                    "with the located stamp region masked out — best "
                    "when a stamp or seal may be covering the field.",
    "stamp_removed": "Re-read the field from a copy of the document "
                     "with the stamp's ink lifted instead of covered: "
                     "the coloured ink is faded so print underneath "
                     "can show through. Prefer this over stamp_masked "
                     "when the stamp covers the field itself, because "
                     "masking hides the covered print too.",
    "zoom_tight": "Re-read the field from a tighter zoomed crop of "
                  "the document — best when the print is small, "
                  "faint or blurry.",
    "recapture": "Stop investigating: leave the field unreadable "
                 "and ask the reviewer for a recapture instead of "
                 "guessing.",
}
MAX_PLANNER_CONSULTATIONS = 2  # per field; then investigation stops
REASON_MAX_CHARS = 200
FALLBACK_REASON = ("Planner unavailable — ran the standard "
                   "investigation sequence.")


def _majority(values: list[str]) -> str | None:
    """Settle a field's reads into one value, or None.

    The value is returned only when it is the unique plurality winner —
    strictly more reads than every other distinct readable value. Any
    tie for the top count, including all-distinct reads, returns None:
    scattered reads are not certainty, so the field stays unreadable
    and the comparator asks for a recapture rather than a coin-flip
    flag. UNREADABLE/empty reads are ignored, as before.
    """
    readable = [v for v in values if v and v != "UNREADABLE"]
    if not readable:
        return None
    counts: dict[str, int] = {}
    for value in readable:
        counts[value] = counts.get(value, 0) + 1
    top = max(counts.values())
    winners = [v for v, c in counts.items() if c == top]
    if len(winners) != 1:
        return None
    return winners[0]


def _investigation_image(segmenter: Segmenter | None, image_path: str,
                           view: str,
                           prompt: str = DEFAULT_SEGMENT_PROMPT) -> str:
    """Image to read an investigation view from.

    Only the stamp views change the image, and only when a segmenter
    is injected and actually produces a transformed copy. ``prompt``
    is what the segmenter is asked to locate — chosen by the planner
    for its stamp views (see _investigate), "stamp" by default. Any
    failure returns the original path: transformation is an aid,
    never a gate on the review.
    """
    if segmenter is None:
        return image_path
    producer = {"stamp_masked": getattr(segmenter, "masked_image", None),
                "stamp_removed": getattr(segmenter, "removed_image",
                                         None)}.get(view)
    if producer is None:
        return image_path
    try:
        transformed = producer(image_path, prompt)
    except Exception:
        return image_path
    return transformed or image_path


def _clean_reason(raw) -> str:
    """A planner reason as recorded in the investigation log:
    whitespace-collapsed and length-capped, so a verbose model cannot
    bloat the trace."""
    return " ".join(str(raw or "").split())[:REASON_MAX_CHARS]


def _validate_decision(decision) -> tuple[str, str, str]:
    """Validate one planner decision; returns (action, clean reason,
    segment prompt).

    Anything else — a non-dict, a missing action, an action outside
    PLANNER_ACTIONS — raises ValueError, which the investigation loop
    treats exactly like a failed planner call: fallback. The segment
    prompt is softer: a missing or unlisted phrase is not a planner
    failure, it just falls back to "stamp" — SAM is prompt-sensitive,
    so the planner picks from SEGMENT_PROMPTS and only from those.
    """
    if not isinstance(decision, dict):
        raise ValueError(f"planner decision was not an object: "
                         f"{decision!r:.80}")
    action = decision.get("action")
    if action not in PLANNER_ACTIONS:
        raise ValueError(f"planner chose an unknown action: {action!r}")
    prompt = str(decision.get("segment_prompt") or "").strip().lower()
    if prompt not in SEGMENT_PROMPTS:
        prompt = DEFAULT_SEGMENT_PROMPT
    return action, _clean_reason(decision.get("reason")), prompt


def _investigate(reader: Reader, image_path: str, doc_type: str,
                 field: str, segmenter: Segmenter | None,
                 reads: list[str], view_names: list[str]) -> list[dict]:
    """Investigate one uncertain field; returns the investigation log.

    Appends investigation reads to ``reads`` (and their view names to
    ``view_names``) as they happen. Two modes:

    - planner: before each step, the reader's plan_investigation is
      consulted (at most MAX_PLANNER_CONSULTATIONS times). A chosen
      view is read; if a unique-plurality value then exists, the
      investigation stops. "recapture" stops it immediately. After
      the second consultation's step, it stops regardless.
    - fallback: the fixed INVESTIGATION_VIEWS sequence, in order,
      skipping any view already read. Entered when the reader has
      no planner, and the moment any planner consultation fails —
      a broken planner must never break (or even delay the verdict
      of) a review.
    """
    log: list[dict] = []
    planner = getattr(reader, "plan_investigation", None)
    mode = "planner" if planner is not None else "fallback"
    consultations = 0
    fallback_idx = 0

    def _do_view(view: str, prompt: str = DEFAULT_SEGMENT_PROMPT) -> None:
        view_image = _investigation_image(segmenter, image_path, view,
                                          prompt)
        reads.append(reader.read_field(view_image, doc_type, field, view))
        view_names.append(view)

    while True:
        if mode == "planner":
            if consultations >= MAX_PLANNER_CONSULTATIONS:
                break
            consultations += 1
            try:
                decision = planner(
                    image_path, doc_type, field,
                    [{"view": v, "value": val}
                     for v, val in zip(view_names, reads)],
                    dict(PLANNER_ACTIONS))
                action, reason, prompt = _validate_decision(decision)
            except Exception:
                mode = "fallback"
                continue
            entry = {"action": action, "reason": reason,
                     "source": "planner"}
            if action in ("stamp_masked", "stamp_removed"):
                entry["segment_prompt"] = prompt
            log.append(entry)
            if action == "recapture":
                break
            _do_view(action, prompt)
            if _majority(reads) is not None:
                break
        else:
            if fallback_idx >= len(INVESTIGATION_VIEWS):
                break
            view = INVESTIGATION_VIEWS[fallback_idx]
            fallback_idx += 1
            if view in view_names:
                continue
            entry = {"action": view, "reason": FALLBACK_REASON,
                     "source": "fallback"}
            if view in ("stamp_masked", "stamp_removed"):
                entry["segment_prompt"] = DEFAULT_SEGMENT_PROMPT
            log.append(entry)
            _do_view(view)
    return log


def read_field_with_uncertainty(reader: Reader, image_path: str,
                                doc_type: str, field: str,
                                segmenter: Segmenter | None = None
                                ) -> FieldRead:
    """Read one field under the first-pass views, investigating if unsettled.

    The field is *uncertain* — and the investigation fires — when
    the first-pass views disagree. Disagreement means either two views
    returned different readable values, or any view failed to read the
    field at all (UNREADABLE/empty): a view that cannot read is not
    agreement with the views that could, so one surviving value never
    settles the field on its own. A field no view could read is
    uncertain by the same rule; the investigation still runs, and if it
    recovers nothing the value stays None (recapture, never a guess).

    The investigation itself is model-directed with a deterministic
    fallback — see _investigate. The planner only ever chooses the
    next step; the value still comes from _majority over the reads,
    and the verdict from the comparator.
    """
    reads = [reader.read_field(image_path, doc_type, field, view)
             for view in FIRST_PASS_VIEWS]
    view_names = list(FIRST_PASS_VIEWS)
    readable = [v for v in reads if v and v != "UNREADABLE"]
    uncertain = len(set(readable)) > 1 or len(readable) < len(reads)
    investigation: list[dict] = []
    if uncertain:
        investigation = _investigate(reader, image_path, doc_type,
                                     field, segmenter, reads, view_names)
    return FieldRead(doc_type=doc_type, field=field,
                     value=_majority(reads), uncertain=uncertain,
                     reads=reads, investigation=investigation)


NAME_FIELDS = ("name", "father_name")


def collect_script_reads(reader: Reader, images: dict[str, str],
                         fields: list[str]) -> dict[str, dict[str, str]]:
    """Original-script transcriptions of the given name fields.

    Only collected when the reader offers read_field_script; every
    failure or UNREADABLE answer is simply absent from the result —
    a missing script read means the comparator's script-agreement
    rule cannot fire for that pair, never an error.
    """
    script_reader = getattr(reader, "read_field_script", None)
    if script_reader is None:
        return {}
    collected: dict[str, dict[str, str]] = {}
    for doc_type, image_path in images.items():
        for field in fields:
            if field not in FIELDS_BY_DOC.get(doc_type, []):
                continue
            try:
                value = script_reader(image_path, doc_type, field)
            except Exception:
                continue
            if value and value != "UNREADABLE":
                collected.setdefault(doc_type, {})[field] = value
    return collected


def rescue_script_mismatches(reader: Reader, images: dict[str, str],
                             documents: dict[str, dict[str, str]],
                             result) -> comparator.ComparisonResult:
    """Second comparison pass for name fields that mismatched.

    Transliteration variance is the known false-flag source on new
    names (the Latin reads disagree on consonants the skeleton rule
    does not fold). When a name field mismatches, the documents are
    re-read in their original script and the comparison re-run with
    those reads attached: where the script spellings agree, the
    comparator reports a variant instead of a mismatch. Sets with no
    name mismatch never pay for the extra reads, and a reader
    without script support leaves the first result untouched. The
    rule itself is deterministic and lives in the comparator, so
    every configuration that compares through it inherits the same
    behaviour.
    """
    mismatching = [f.field for f in result.findings
                   if f.field in NAME_FIELDS and f.status == "mismatch"]
    if not mismatching:
        return result
    script_documents = collect_script_reads(reader, images, mismatching)
    if not script_documents:
        return result
    return comparator.compare(documents, script_documents=script_documents)


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
    result = rescue_script_mismatches(reader, images, documents, result)
    return ReviewOutcome(
        verdict=result.verdict,
        documents=documents,
        field_reads=field_reads,
        findings=[asdict(f) for f in result.findings],
        visual_review=_visual_review(reader, images),
    )


def _visual_review(reader: Reader, images: dict[str, str]) -> dict | None:
    """The advisory visual cross-examination, when the reader
    offers it. Fail-soft in both directions: a reader without the
    capability, a failed call, or an unusable reply all mean no
    visual review — and a produced one is attached to the outcome
    as evidence for the human reviewer. It is computed AFTER the
    verdict and is never an input to it."""
    visual = getattr(reader, "visual_cross_check", None)
    if visual is None:
        return None
    try:
        result = visual(images)
    except Exception:
        return None
    if not isinstance(result, dict) or \
            not isinstance(result.get("concerns"), list):
        return None
    return result

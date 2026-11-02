"""Deterministic cross-document comparator.

Takes the fields read from each document in a set and compares every shared
fact. Output is a list of per-field findings plus an overall verdict, in the
plan's verdict language:

- CONSISTENT          — everything shared agrees
- DISCREPANCY         — a shared fact disagrees; needs human review
- UNREADABLE          — a needed field could not be read; request recapture

A field that failed to parse is *unreadable*, never a discrepancy: we do not
punish an applicant for a bad photo.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from . import normalize

SHARED_FIELDS = ("name", "dob", "id_number", "father_name")


@dataclass
class FieldFinding:
    field: str
    status: str  # match | variant | mismatch | unreadable | single_source
    values: dict[str, str]  # doc_type -> raw value as read
    canonical: dict[str, str]  # doc_type -> canonical value compared
    note: str = ""  # e.g. script-agreement rescue (see compare)


@dataclass
class ComparisonResult:
    findings: list[FieldFinding] = dc_field(default_factory=list)

    @property
    def verdict(self) -> str:
        statuses = {f.status for f in self.findings}
        if "mismatch" in statuses:
            return "DISCREPANCY"
        if "unreadable" in statuses:
            return "UNREADABLE"
        return "CONSISTENT"


def _canonical(field: str, raw) -> str | None:
    if raw is None or str(raw).strip() == "":
        return None
    if field == "dob":
        parsed = normalize.parse_date(str(raw))
        return parsed.isoformat() if parsed else None
    if field == "id_number":
        return normalize.normalize_id(str(raw)) or None
    if field in ("name", "father_name"):
        tokens = normalize.normalize_name(str(raw))
        return " ".join(tokens) if tokens else None
    return str(raw).strip()


def _script_pair_agrees(script_documents, field: str,
                        doc_a: str, doc_b: str) -> bool:
    """True when both documents have an original-script read of the
    field and the two reads canonicalize to the same non-empty string.

    This is the script-agreement rescue: transliteration into Latin
    letters is where reader variance lives ("Rafiqul" vs "Rafikul"),
    while the Bangla/Devanagari spelling on the documents either
    agrees or it does not. Agreement can only *downgrade* a Latin
    mismatch to a variant — it never upgrades, never touches a match,
    and requires a script read from both documents.
    """
    if not script_documents:
        return False
    a = script_documents.get(doc_a, {}).get(field)
    b = script_documents.get(doc_b, {}).get(field)
    if not a or not b:
        return False
    na = normalize.normalize_script_name(a)
    nb = normalize.normalize_script_name(b)
    return bool(na) and na == nb


def compare(documents: dict[str, dict[str, str]],
            script_documents: dict[str, dict[str, str]] | None = None
            ) -> ComparisonResult:
    """documents: {doc_type: {field: raw_value_as_read}}.

    script_documents (optional): the same shape, holding name reads
    transcribed in their original script. For name fields only, a
    Latin mismatch between two documents whose script reads agree is
    reported as a variant, not a mismatch — see _script_pair_agrees.
    """
    result = ComparisonResult()
    for field in SHARED_FIELDS:
        present = {
            doc: fields[field]
            for doc, fields in documents.items()
            if field in fields
        }
        if len(present) < 2:
            if len(present) == 1:
                result.findings.append(
                    FieldFinding(field, "single_source", dict(present),
                                 {d: _canonical(field, v) or "" for d, v in present.items()})
                )
            continue

        canonical = {d: _canonical(field, v) for d, v in present.items()}
        note = ""
        if any(v is None for v in canonical.values()):
            status = "unreadable"
        elif field in ("name", "father_name"):
            docs = list(present)
            status = "match"
            for i in range(len(docs)):
                for j in range(i + 1, len(docs)):
                    pair = normalize.names_match(present[docs[i]], present[docs[j]])
                    if pair == "mismatch" and _script_pair_agrees(
                            script_documents, field, docs[i], docs[j]):
                        pair = "variant"
                        note = ("transliterations differ; "
                                "original-script reads agree")
                    if pair == "mismatch":
                        status = "mismatch"
                    elif pair == "variant" and status == "match":
                        status = "variant"
        else:
            status = "match" if len(set(canonical.values())) == 1 else "mismatch"

        result.findings.append(
            FieldFinding(field, status, dict(present),
                         {d: v or "" for d, v in canonical.items()},
                         note=note)
        )
    return result

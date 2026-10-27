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


def compare(documents: dict[str, dict[str, str]]) -> ComparisonResult:
    """documents: {doc_type: {field: raw_value_as_read}}."""
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
        if any(v is None for v in canonical.values()):
            status = "unreadable"
        elif field in ("name", "father_name"):
            docs = list(present)
            status = "match"
            for i in range(len(docs)):
                for j in range(i + 1, len(docs)):
                    pair = normalize.names_match(present[docs[i]], present[docs[j]])
                    if pair == "mismatch":
                        status = "mismatch"
                    elif pair == "variant" and status == "match":
                        status = "variant"
        else:
            status = "match" if len(set(canonical.values())) == 1 else "mismatch"

        result.findings.append(
            FieldFinding(field, status, dict(present),
                         {d: v or "" for d, v in canonical.items()})
        )
    return result

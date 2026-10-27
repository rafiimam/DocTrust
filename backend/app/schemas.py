"""Data shapes shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field


@dataclass
class FieldRead:
    """One field of one document, after the read + investigation loop."""

    doc_type: str
    field: str
    value: str | None  # None = could not be read even after investigation
    uncertain: bool = False  # perturbation reads disagreed at some point
    reads: list[str] = dc_field(default_factory=list)  # every raw read, in order


@dataclass
class ReviewOutcome:
    verdict: str  # CONSISTENT | DISCREPANCY | UNREADABLE
    documents: dict[str, dict[str, str]]  # values fed to the comparator
    field_reads: list[FieldRead]
    findings: list[dict]  # serialized comparator findings for the UI

"""Offline tests for the evaluation runner (eval/run_eval.py).

No network, no live readers: a TruthReader answers every read from
the set's own ground truth, with per-field override queues where a
test needs controlled noise. Fast by construction — the scripted
readers return immediately.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.segmenter import MockSegmenter  # noqa: E402
from eval import run_eval  # noqa: E402


class TruthReader:
    """Reads exactly what the ground truth says, unless an override
    queue for (doc_type, field) supplies values in call order."""

    def __init__(self, truth_docs, overrides=None):
        self._truth = truth_docs
        self._overrides = {k: list(v) for k, v in (overrides or {}).items()}
        self.calls = []

    def read_field(self, image_path, doc_type, field, perturbation):
        self.calls.append((doc_type, field, perturbation))
        queue = self._overrides.get((doc_type, field))
        if queue:
            if len(queue) > 1:
                return queue.pop(0)
            return queue[0]
        return self._truth[doc_type][field]


def _run(tmp_path, counts, factory, **kwargs):
    return run_eval.run_evaluation(
        counts=counts, data_dir=tmp_path / "data",
        out_path=tmp_path / "results.json",
        reader_factory=factory, segmenter=MockSegmenter(),
        workers=1, **kwargs)


def _counts(**overrides):
    base = {"clean": 0, "variation": 0, "discrepancy": 0, "degraded": 0}
    base.update(overrides)
    return base


def test_exact_match_false_flags_variation_that_single_pass_passes(tmp_path):
    # The variation set's facts agree; only the surface forms differ
    # (Md./Mohammed name spellings, Bangla vs Latin digits). The raw
    # baseline must flag it; normalization must not.
    factory = lambda spec, phase, truth: TruthReader(truth["documents"])  # noqa: E731
    result = _run(tmp_path, _counts(variation=1), factory)
    record = result.records[0]
    assert record["configs"]["exact"]["verdict"] == "DISCREPANCY"
    assert record["configs"]["single"]["verdict"] == "CONSISTENT"
    assert record["configs"]["agent"]["verdict"] == "CONSISTENT"
    configs = result.summary["configs"]
    assert (configs["exact"]["false_flags"], configs["exact"]["genuine_n"]) == (1, 1)
    assert configs["single"]["false_flags"] == 0
    assert configs["agent"]["false_flags"] == 0


def test_agent_recovers_over_dob_discrepancy_after_disagreement(tmp_path):
    # The stamp sits over the birth certificate's DOB. First-pass reads
    # disagree (one misread digit, one UNREADABLE); the investigation
    # re-reads settle on the true value, and the planted form DOB swap
    # is what remains flagged.
    misread = "১২/০৮/১৯৯০"
    truth_dob = "১২/০৩/১৯৯০"

    def factory(spec, phase, truth):
        docs = truth["documents"]
        if phase == "single":
            return TruthReader(docs, {("birth_certificate", "dob"): [misread]})
        return TruthReader(docs, {("birth_certificate", "dob"): [
            misread, truth_dob, "UNREADABLE", truth_dob, truth_dob]})

    result = _run(tmp_path, _counts(discrepancy=1), factory, over_dob=1)
    record = result.records[0]
    assert record["stamp_position"] == "over_dob"
    assert record["injected_fields"] == ["dob"]
    # Single-pass keeps the misread as the certificate's DOB.
    assert record["configs"]["single"]["documents"]["birth_certificate"]["dob"] == misread
    # The agent's investigation recovered the true value...
    agent_cfg = record["configs"]["agent"]
    assert agent_cfg["documents"]["birth_certificate"]["dob"] == truth_dob
    assert "birth_certificate.dob" in agent_cfg["uncertain_fields"]
    # ...and the verdict still catches the planted discrepancy.
    assert agent_cfg["verdict"] == "DISCREPANCY"
    assert agent_cfg["flagged_fields"] == ["dob"]
    assert result.summary["configs"]["agent"]["caught"] == 1
    assert result.summary["configs"]["agent"]["silent_errors"] == 0


def test_metrics_counting_on_tiny_fixture(tmp_path):
    # Four sets: clean, variation (both genuine), one discrepancy the
    # reader silently "corrects" (reads the true DOB on the form), one
    # degraded set read perfectly.
    def factory(spec, phase, truth):
        docs = truth["documents"]
        if spec.category == "discrepancy":
            return TruthReader(docs, {("bank_form", "dob"): ["12/03/1990"]})
        return TruthReader(docs)

    result = _run(tmp_path, _counts(clean=1, variation=1, discrepancy=1,
                                    degraded=1), factory)
    configs = result.summary["configs"]
    for name in ("single", "agent"):
        # The discrepancy was read as consistent: one silent error,
        # nothing caught.
        assert configs[name]["silent_errors"] == 1
        assert (configs[name]["caught"], configs[name]["discrepancy_n"]) == (0, 1)
    # The exact baseline cannot be silent here — the certificate's
    # Bangla-digit DOB and ID always differ raw from the Latin ones —
    # so it "catches" the set vacuously: DISCREPANCY with the injected
    # field among the flagged, for format reasons alone. The catch is
    # only meaningful read next to its 2/2 false-flag rate below.
    assert configs["exact"]["silent_errors"] == 0
    assert (configs["exact"]["caught"], configs["exact"]["discrepancy_n"]) == (1, 1)
    disc = next(r for r in result.records if r["category"] == "discrepancy")
    assert disc["configs"]["exact"]["verdict"] == "DISCREPANCY"
    assert set(disc["configs"]["exact"]["flagged_fields"]) == {"dob", "id_number"}
    # Degraded set, read perfectly: the normalizing configurations
    # recover it. The raw baseline cannot recover ANY set from this
    # generator (digit systems always differ raw) — it false-flags
    # the degraded set instead.
    for name in ("single", "agent"):
        assert (configs[name]["recovered"], configs[name]["degraded_n"]) == (1, 1)
        assert configs[name]["recapture"] == 0
        assert configs[name]["degraded_false_flags"] == 0
    assert configs["exact"]["recovered"] == 0
    assert configs["exact"]["recapture"] == 0
    assert configs["exact"]["degraded_false_flags"] == 1
    # Raw matching flags both genuine sets (Bangla vs Latin ID digits
    # on the clean set, name spellings on the variation set).
    assert (configs["exact"]["false_flags"], configs["exact"]["genuine_n"]) == (2, 2)
    assert configs["single"]["false_flags"] == 0
    assert configs["agent"]["false_flags"] == 0
    # Read counts: 11 fields per set per phase; the agent needs no
    # investigation when every read is unanimous.
    assert configs["exact"]["reads_mean"] == 11
    assert configs["single"]["reads_mean"] == 11
    assert configs["agent"]["reads_mean"] == 33  # 11 fields x 3 views


def test_per_set_errors_are_recorded_not_fatal(tmp_path):
    def factory(spec, phase, truth):
        raise RuntimeError("reader exploded")

    result = _run(tmp_path, _counts(discrepancy=1), factory)
    record = result.records[0]
    assert record["status"] == "error"
    assert "reader exploded" in record["error"]
    assert result.summary["sets_error"] == 1
    assert result.summary["configs"]["agent"]["discrepancy_n"] == 0


def test_resume_skips_completed_sets(tmp_path):
    calls = []

    def factory(spec, phase, truth):
        calls.append((spec.set_id, phase))
        return TruthReader(truth["documents"])

    _run(tmp_path, _counts(clean=1), factory)
    assert {s for s, _ in calls} == {"clean-01"}

    calls.clear()
    result = _run(tmp_path, _counts(clean=1, variation=1), factory,
                  resume=True)
    # The completed clean set was not re-read; only the new set ran.
    assert {s for s, _ in calls} == {"variation-01"}
    assert [r["set_id"] for r in result.records] == ["clean-01", "variation-01"]
    on_disk = json.loads((tmp_path / "results.json").read_text())
    assert [s["set_id"] for s in on_disk["sets"]] == ["clean-01", "variation-01"]
    assert (tmp_path / "results.md").exists()

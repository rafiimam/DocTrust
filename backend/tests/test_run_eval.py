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


def test_agent_investigations_recorded_and_no_planner_ablation(tmp_path):
    # The agent record must carry the per-field investigation logs
    # (planner stats are computed from them), and --no-planner must
    # turn a planning reader into the deterministic fallback sequence
    # without changing the verdict.
    misread = "১২/০৮/১৯৯০"
    truth_dob = "১২/০৩/১৯৯০"

    class PlanningTruthReader(TruthReader):
        def plan_investigation(self, image_path, doc_type, field,
                               reads, actions):
            return {"action": "zoom_tight",
                    "reason": "test planner choice"}

    def factory(spec, phase, truth):
        docs = truth["documents"]
        if phase == "single":
            return TruthReader(
                docs, {("birth_certificate", "dob"): [misread]})
        return PlanningTruthReader(
            docs, {("birth_certificate", "dob"): [
                misread, truth_dob, "UNREADABLE", truth_dob, truth_dob]})

    result = _run(tmp_path, _counts(discrepancy=1), factory, over_dob=1)
    record = result.records[0]
    inv = record["configs"]["agent"]["investigations"]
    assert "birth_certificate.dob" in inv
    assert inv["birth_certificate.dob"][0]["source"] == "planner"
    assert inv["birth_certificate.dob"][0]["action"] == "zoom_tight"
    assert result.meta["no_planner"] is False

    ablated = _run(tmp_path, _counts(discrepancy=1), factory,
                   over_dob=1, no_planner=True)
    arec = ablated.records[0]
    ainv = arec["configs"]["agent"]["investigations"]
    assert "birth_certificate.dob" in ainv
    assert all(e["source"] == "fallback"
               for e in ainv["birth_certificate.dob"])
    assert ainv["birth_certificate.dob"][0]["action"] == "stamp_masked"
    assert arec["configs"]["agent"]["verdict"] == "DISCREPANCY"
    assert ablated.meta["no_planner"] is True


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


def test_counting_reader_counts_planner_consultations():
    # The agent's reads figure must include planner consultations —
    # they are billed model calls, and configuration 3's cost would
    # be understated without them. A wrapped reader with no planner
    # raises before the counter moves (no model call happened), so
    # the agent falls back exactly as it would unwrapped.
    import pytest

    class _PlanningReader(TruthReader):
        def plan_investigation(self, image_path, doc_type, field,
                               reads, actions):
            return {"action": "recapture", "reason": "scripted"}

    counting = run_eval.CountingReader(_PlanningReader({}))
    decision = counting.plan_investigation(
        "x.png", "nid", "dob", [], {"recapture": "stop"})
    assert decision["action"] == "recapture"
    assert counting.calls == 1

    counting = run_eval.CountingReader(TruthReader({}))
    with pytest.raises(RuntimeError):
        counting.plan_investigation("x.png", "nid", "dob", [], {})
    assert counting.calls == 0


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


# ---------------------------------------------------------------------------
# Physically captured sets
# ---------------------------------------------------------------------------

def _write_physical_set(tmp_path, name, variant, seed=11, documents=None,
                        expectation=None, injected_field=None):
    """Render a synthetic set and republish its images as a physical
    capture folder under tmp_path/physical/<name>: the generated
    PNGs stand in for phone photos, and the manifest is built from
    the set's ground truth (see eval/PHYSICAL_CAPTURE.md)."""
    from generator.generate import generate_set

    truth = generate_set(tmp_path / f"src-{name}", variant, seed)
    folder = tmp_path / "physical" / name
    folder.mkdir(parents=True)
    for doc in run_eval.DOC_TYPES:
        (folder / f"{doc}.png").write_bytes(
            (tmp_path / f"src-{name}" / f"{doc}.png").read_bytes())
    if expectation is None:
        expectation = {"clean": "genuine", "variation": "genuine",
                       "discrepancy": "discrepancy",
                       "degraded": "degraded"}[variant]
    manifest = {"expectation": expectation,
                "documents": documents or truth["documents"]}
    if expectation == "discrepancy":
        manifest["injected_field"] = injected_field or "dob"
    (folder / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False))
    return truth


def test_physical_genuine_set_scored_through_all_configs(tmp_path):
    _write_physical_set(tmp_path, "kitchen-table", "variation")
    factory = lambda spec, phase, truth: TruthReader(truth["documents"])  # noqa: E731
    result = _run(tmp_path, _counts(), factory,
                  physical_dir=tmp_path / "physical")
    record = result.records[0]
    assert record["set_id"] == "physical-kitchen-table"
    assert record["category"] == "physical"
    assert record["expectation"] == "genuine"
    # The same surface-form trap as the synthetic variation set: raw
    # matching flags it; normalization and the agent do not.
    assert record["configs"]["exact"]["verdict"] == "DISCREPANCY"
    assert record["configs"]["single"]["verdict"] == "CONSISTENT"
    assert record["configs"]["agent"]["verdict"] == "CONSISTENT"
    # Headline: the physical genuine set joins the genuine pool.
    headline = result.summary["configs"]
    assert (headline["exact"]["false_flags"],
            headline["exact"]["genuine_n"]) == (1, 1)
    assert headline["agent"]["false_flags"] == 0
    # …and it is also reported under its own category, split by
    # expectation.
    assert result.summary["physical_sets"] == 1
    physical = result.summary["physical"]["configs"]
    assert (physical["exact"]["false_flags"],
            physical["exact"]["genuine_n"]) == (1, 1)
    assert physical["agent"]["false_flags"] == 0
    by_exp = result.summary["physical"]["by_expectation"]["agent"]
    assert by_exp["genuine"]["genuine_n"] == 1
    assert by_exp["discrepancy"]["discrepancy_n"] == 0
    md = (tmp_path / "results.md").read_text()
    assert "### Physically captured sets" in md
    assert "By expectation" in md


def test_physical_discrepancy_caught_and_silent_error(tmp_path):
    _write_physical_set(tmp_path, "disc-caught", "discrepancy", seed=12)
    _write_physical_set(tmp_path, "disc-missed", "discrepancy", seed=13)

    def factory(spec, phase, truth):
        docs = truth["documents"]
        if spec.set_id == "physical-disc-missed":
            # The reader silently "corrects" the swapped form DOB in
            # every phase: the discrepancy is never seen.
            return TruthReader(docs, {("bank_form", "dob"): ["12/03/1990"]})
        return TruthReader(docs)

    result = _run(tmp_path, _counts(), factory,
                  physical_dir=tmp_path / "physical")
    by_id = {r["set_id"]: r for r in result.records}
    caught = by_id["physical-disc-caught"]
    assert caught["injected_fields"] == ["dob"]
    assert caught["configs"]["agent"]["verdict"] == "DISCREPANCY"
    assert caught["configs"]["agent"]["flagged_fields"] == ["dob"]
    assert by_id["physical-disc-missed"]["configs"]["agent"]["verdict"] \
        == "CONSISTENT"
    physical = result.summary["physical"]["by_expectation"]["agent"]
    assert (physical["discrepancy"]["caught"],
            physical["discrepancy"]["discrepancy_n"]) == (1, 2)
    assert physical["discrepancy"]["silent_errors"] == 1
    headline = result.summary["configs"]["agent"]
    assert (headline["caught"], headline["discrepancy_n"]) == (1, 2)
    assert headline["silent_errors"] == 1


def test_physical_degraded_set_recovered(tmp_path):
    _write_physical_set(tmp_path, "glare-shot", "degraded", seed=14)
    factory = lambda spec, phase, truth: TruthReader(truth["documents"])  # noqa: E731
    result = _run(tmp_path, _counts(), factory,
                  physical_dir=tmp_path / "physical")
    record = result.records[0]
    assert record["expectation"] == "degraded"
    assert record["configs"]["agent"]["verdict"] == "CONSISTENT"
    by_exp = result.summary["physical"]["by_expectation"]["agent"]
    assert (by_exp["degraded"]["recovered"],
            by_exp["degraded"]["degraded_n"]) == (1, 1)
    assert by_exp["degraded"]["recapture"] == 0
    headline = result.summary["configs"]["agent"]
    assert (headline["recovered"], headline["degraded_n"]) == (1, 1)


def test_physical_malformed_folders_are_skipped(tmp_path, capsys):
    _write_physical_set(tmp_path, "good", "clean", seed=15)
    physical_dir = tmp_path / "physical"

    def bare_folder(name):
        folder = physical_dir / name
        folder.mkdir()
        for doc in run_eval.DOC_TYPES:
            (folder / f"{doc}.png").write_bytes(b"x")
        return folder

    bare_folder("no-manifest")
    bad = bare_folder("bad-json")
    (bad / "manifest.json").write_text("{not json")
    missing = physical_dir / "missing-image"
    missing.mkdir()
    (missing / "nid.png").write_bytes(b"x")
    (missing / "manifest.json").write_text(
        json.dumps({"expectation": "genuine", "documents": {}}))
    _write_physical_set(tmp_path, "disc-no-field", "discrepancy", seed=16)
    manifest_path = physical_dir / "disc-no-field" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["injected_field"]
    manifest_path.write_text(json.dumps(manifest))

    factory = lambda spec, phase, truth: TruthReader(truth["documents"])  # noqa: E731
    result = _run(tmp_path, _counts(), factory, physical_dir=physical_dir)
    # Only the one well-formed set ran; the run itself succeeded.
    assert [r["set_id"] for r in result.records] == ["physical-good"]
    assert result.summary["sets_ok"] == 1
    err = capsys.readouterr().err
    assert "warning:" in err
    for name in ("no-manifest", "bad-json", "missing-image",
                 "disc-no-field"):
        assert name in err


def test_physical_discovery_accepts_jpg_and_jpeg(tmp_path):
    folder = tmp_path / "mixed-ext"
    folder.mkdir()
    (folder / "nid.jpg").write_bytes(b"x")
    (folder / "birth_certificate.jpeg").write_bytes(b"x")
    (folder / "bank_form.png").write_bytes(b"x")
    documents = {
        "nid": {"name": "Abdul Rahman", "dob": "12/03/1990",
                "id_number": "1234567890", "father_name": "Abdul Karim"},
        "birth_certificate": {"name": "Abdul Rahman",
                              "dob": "১২/০৩/১৯৯০",
                              "father_name": "Abdul Karim"},
        "bank_form": {"name": "Abdul Rahman", "dob": "12/03/1990",
                      "id_number": "1234567890",
                      "father_name": "Abdul Karim"},
    }
    (folder / "manifest.json").write_text(json.dumps(
        {"expectation": "genuine", "documents": documents},
        ensure_ascii=False))
    specs, warnings = run_eval.discover_physical_sets(tmp_path)
    assert warnings == []
    assert len(specs) == 1
    spec = specs[0]
    assert spec.set_id == "physical-mixed-ext"
    assert spec.images["nid"].endswith("nid.jpg")
    assert spec.images["birth_certificate"].endswith(
        "birth_certificate.jpeg")
    assert spec.images["bank_form"].endswith("bank_form.png")
    # A missing directory is simply no sets, not an error.
    assert run_eval.discover_physical_sets(tmp_path / "nope") == ([], [])


def test_physical_resume_skips_completed_sets(tmp_path):
    _write_physical_set(tmp_path, "porch-light", "clean", seed=17)
    calls = []

    def factory(spec, phase, truth):
        calls.append((spec.set_id, phase))
        return TruthReader(truth["documents"])

    _run(tmp_path, _counts(), factory, physical_dir=tmp_path / "physical")
    assert {s for s, _ in calls} == {"physical-porch-light"}

    calls.clear()
    result = _run(tmp_path, _counts(clean=1), factory,
                  physical_dir=tmp_path / "physical", resume=True)
    # The completed physical set was not re-read; only the new
    # synthetic set ran.
    assert {s for s, _ in calls} == {"clean-01"}
    assert [r["set_id"] for r in result.records] == [
        "clean-01", "physical-porch-light"]


# ---------------------------------------------------------------------------
# Hindi-script sets (--hindi): separately scored, never in the headline
# ---------------------------------------------------------------------------

def test_hindi_counts_composition():
    assert run_eval._hindi_counts(10) == {
        "clean": 4, "variation": 3, "discrepancy": 2, "degraded": 1}
    for n in (0, 1, 3, 5, 20, 37):
        counts = run_eval._hindi_counts(n)
        assert sum(counts.values()) == n
        assert counts["clean"] >= counts["variation"] \
            >= counts["discrepancy"] >= counts["degraded"]


def test_build_dataset_hindi_specs():
    counts = {"clean": 2, "variation": 0, "discrepancy": 0, "degraded": 0}
    specs = run_eval.build_dataset(counts, seed_base=7, hindi=10)
    bangla = [s for s in specs if s.script == "bangla"]
    hindi = [s for s in specs if s.script == "hindi"]
    assert len(bangla) == 2 and len(hindi) == 10
    assert [s.set_id for s in hindi] == [
        "hindi-clean-01", "hindi-clean-02", "hindi-clean-03",
        "hindi-clean-04", "hindi-variation-01", "hindi-variation-02",
        "hindi-variation-03", "hindi-discrepancy-01",
        "hindi-discrepancy-02", "hindi-degraded-01"]
    # Seeds continue the Bangla sequence — no collisions anywhere.
    assert hindi[0].seed == 7 + 2
    assert len({s.seed for s in specs}) == len(specs)
    # The first Hindi discrepancy set mirrors the Bangla emphasis:
    # stamp over the birth-certificate DOB.
    disc = [s for s in hindi if s.category == "discrepancy"]
    assert [s.stamp_position for s in disc] == ["over_dob", "margin"]
    # Default: no Hindi sets at all.
    assert all(s.script == "bangla"
               for s in run_eval.build_dataset(counts, seed_base=7))


def test_hindi_sets_scored_separately_from_headline(tmp_path):
    def factory(spec, phase, truth):
        return TruthReader(truth["documents"])

    result = _run(tmp_path,
                  _counts(clean=1, variation=1, discrepancy=1, degraded=1),
                  factory, hindi=10)
    assert result.summary["hindi_sets"] == 10
    headline = result.summary["configs"]
    # Headline pools are the 4 Bangla sets only — Hindi sets never
    # leak in (genuine = clean + variation, degraded scored apart).
    for name in ("single", "agent"):
        assert headline[name]["genuine_n"] == 2
        assert headline[name]["discrepancy_n"] == 1
        assert headline[name]["degraded_n"] == 1
    hindi = result.summary["hindi"]["configs"]
    for name in ("single", "agent"):
        # Hindi genuine pool: 4 clean + 3 variation; 2 discrepancies,
        # both caught by a truthful reader; 1 degraded, recovered.
        assert hindi[name]["genuine_n"] == 7
        assert hindi[name]["false_flags"] == 0
        assert (hindi[name]["caught"], hindi[name]["discrepancy_n"]) == (2, 2)
        assert hindi[name]["silent_errors"] == 0
        assert (hindi[name]["recovered"], hindi[name]["degraded_n"]) == (1, 1)
    records = {r["set_id"]: r for r in result.records}
    assert all(r["script"] == "hindi" for r in result.records
               if r["set_id"].startswith("hindi-"))
    assert records["hindi-clean-01"]["expected_verdict"] == "CONSISTENT"
    assert records["hindi-discrepancy-01"]["expected_verdict"] == "DISCREPANCY"
    assert records["hindi-discrepancy-01"]["injected_fields"] == ["dob"]
    md = run_eval.render_markdown(result.summary, result.meta,
                                  result.records)
    assert "Hindi-script sets (secondary, small n)" in md
    assert "Bangla primary" in md

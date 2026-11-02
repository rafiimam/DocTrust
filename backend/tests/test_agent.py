from app import agent
from app.providers import MockReader


def _script(**overrides):
    base = {
        ("nid", "name"): ["Md. Abdul Rahman"],
        ("nid", "dob"): ["12/03/1990"],
        ("nid", "id_number"): ["১২৩৪৫৬৭৮৯০"],
        ("nid", "father_name"): ["Abdul Karim"],
        ("bank_form", "name"): ["Mohammed Abdul Rahaman"],
        ("bank_form", "dob"): ["12/03/1990"],
        ("bank_form", "id_number"): ["1234567890"],
        ("bank_form", "father_name"): ["Abdul Karim"],
    }
    base.update(overrides)
    return base


def test_agent_consistent_set():
    reader = MockReader(_script())
    outcome = agent.run_review(reader, {"nid": "nid.png", "bank_form": "form.png"})
    assert outcome.verdict == "CONSISTENT"


def test_agent_disagreement_marks_uncertain_and_investigates():
    # First reads disagree on the NID dob; the majority after investigation
    # agrees with the form, and the field is recorded as uncertain.
    script = _script()
    script[("nid", "dob")] = ["12/03/1990", "12/03/1996", "12/03/1990",
                               "12/03/1990", "12/03/1990"]
    reader = MockReader(script)
    outcome = agent.run_review(reader, {"nid": "nid.png", "bank_form": "form.png"})
    dob = next(fr for fr in outcome.field_reads
               if fr.doc_type == "nid" and fr.field == "dob")
    assert dob.uncertain is True
    assert len(dob.reads) == 6  # 3 first-pass + 3 investigation views
    assert outcome.verdict == "CONSISTENT"


def test_agent_unreadable_field_gives_recapture_verdict():
    script = _script()
    script[("bank_form", "dob")] = ["UNREADABLE"]
    reader = MockReader(script)
    outcome = agent.run_review(reader, {"nid": "nid.png", "bank_form": "form.png"})
    assert outcome.verdict == "UNREADABLE"


def test_agent_partial_unreadable_marks_uncertain_and_investigates():
    # Live-probe shape: a stamp covers the birth certificate's DOB and
    # two of the three first-pass views cannot read it at all. The one
    # surviving value must not settle the field — a view failing to
    # read counts as disagreement — so the field is uncertain and the
    # investigation views fire; their reads confirm the value.
    script = _script()
    script[("birth_certificate", "name")] = ["Mohammad Abdul Rahman"]
    script[("birth_certificate", "dob")] = ["UNREADABLE", "12/03/1990",
                                            "UNREADABLE",
                                            "12/03/1990", "12/03/1990"]
    script[("birth_certificate", "father_name")] = ["Abdul Karim"]
    reader = MockReader(script)
    outcome = agent.run_review(reader, {"nid": "nid.png",
                                        "birth_certificate": "bc.png",
                                        "bank_form": "form.png"})
    dob = next(fr for fr in outcome.field_reads
               if fr.doc_type == "birth_certificate" and fr.field == "dob")
    assert dob.uncertain is True
    assert len(dob.reads) == 6  # 3 first-pass + 3 investigation views
    assert dob.value == "12/03/1990"
    assert outcome.verdict == "CONSISTENT"


def test_agent_agreeing_reads_do_not_investigate():
    # The clean path must not gain extra calls: when every first-pass
    # view returns the same readable value, no field is uncertain and
    # no investigation views are read.
    reader = MockReader(_script())
    outcome = agent.run_review(reader, {"nid": "nid.png", "bank_form": "form.png"})
    assert outcome.verdict == "CONSISTENT"
    for fr in outcome.field_reads:
        assert fr.uncertain is False
        assert len(fr.reads) == 3


def test_majority_unique_plurality_wins():
    # [A, A, B]: A has strictly more reads than every other distinct
    # value, so it settles the field exactly as before the tie fix.
    assert agent._majority(["A", "A", "B"]) == "A"
    assert agent._majority(["A"]) == "A"
    assert agent._majority(["A", "A", "A", "B", "B"]) == "A"


def test_majority_tie_returns_none():
    # Any tie for the top count — including all-distinct reads — is
    # not certainty: the field stays unreadable rather than picking
    # an arbitrary winner by set iteration order.
    assert agent._majority(["A", "B"]) is None
    assert agent._majority(["A", "B", "C"]) is None
    assert agent._majority(["A", "A", "B", "B"]) is None
    assert agent._majority(["UNREADABLE", "A", "UNREADABLE", "B"]) is None


def test_majority_no_readable_returns_none():
    assert agent._majority([]) is None
    assert agent._majority(["UNREADABLE", "UNREADABLE"]) is None
    assert agent._majority(["", "UNREADABLE"]) is None


def test_agent_tied_reads_after_investigation_give_recapture():
    # The investigation leaves the NID dob at [A, B] — one read each,
    # the rest UNREADABLE. A tie must not coin-flip a winner: the
    # field stays unreadable and the otherwise-clean set asks for a
    # recapture instead of flagging or clearing on an arbitrary value.
    script = _script()
    script[("nid", "dob")] = ["12/03/1990", "12/03/1996", "UNREADABLE",
                              "UNREADABLE", "UNREADABLE"]
    reader = MockReader(script)
    outcome = agent.run_review(reader, {"nid": "nid.png", "bank_form": "form.png"})
    dob = next(fr for fr in outcome.field_reads
               if fr.doc_type == "nid" and fr.field == "dob")
    assert dob.uncertain is True
    assert len(dob.reads) == 6  # 3 first-pass + 3 investigation views
    assert dob.value is None
    assert outcome.verdict == "UNREADABLE"


def test_agent_scattered_probe_reads_give_recapture_not_flag():
    # The live-probe shape (2026-10-27): the stamp-covered birth
    # certificate DOB read [UNREADABLE, wrong, UNREADABLE, UNREADABLE,
    # correct] across the five views — the correct value and a wrong
    # value once each. The old tie-break picked an arbitrary winner
    # and falsely flagged the genuine set DISCREPANCY; scattered reads
    # like these must end in a recapture request instead. The sixth
    # scripted read is the stamp_removed view failing too (opaque
    # ink), keeping the reads scattered.
    script = _script()
    script[("birth_certificate", "name")] = ["Mohammad Abdul Rahman"]
    script[("birth_certificate", "dob")] = ["UNREADABLE", "১২/০৯/১৯৯০",
                                            "UNREADABLE", "UNREADABLE",
                                            "১২/০৩/১৯৯০", "UNREADABLE"]
    script[("birth_certificate", "father_name")] = ["Abdul Karim"]
    reader = MockReader(script)
    outcome = agent.run_review(reader, {"nid": "nid.png",
                                        "birth_certificate": "bc.png",
                                        "bank_form": "form.png"})
    dob = next(fr for fr in outcome.field_reads
               if fr.doc_type == "birth_certificate" and fr.field == "dob")
    assert dob.uncertain is True
    assert len(dob.reads) == 6  # 3 first-pass + 3 investigation views
    assert dob.value is None
    assert outcome.verdict == "UNREADABLE"


def test_agent_all_unreadable_investigates_and_stays_unreadable():
    # No first-pass view can read the field: the investigation still
    # runs (5 reads), the field is marked uncertain, and with nothing
    # recovered the value stays None so the verdict asks for a recapture.
    script = _script()
    script[("bank_form", "dob")] = ["UNREADABLE"]
    reader = MockReader(script)
    outcome = agent.run_review(reader, {"nid": "nid.png", "bank_form": "form.png"})
    dob = next(fr for fr in outcome.field_reads
               if fr.doc_type == "bank_form" and fr.field == "dob")
    assert dob.uncertain is True
    assert len(dob.reads) == 6  # 3 first-pass + 3 investigation views
    assert dob.value is None
    assert outcome.verdict == "UNREADABLE"


# --- Model-directed investigation (planner) ----------------------------------
#
# The planner chooses the next investigation step; the comparator
# still decides the verdict. Unscripted, MockReader.plan_investigation
# raises, so every test above already exercises the fallback path —
# the two-view, five-read shapes there ARE the fallback contract.


def _dob(outcome, doc_type="birth_certificate"):
    return next(fr for fr in outcome.field_reads
                if fr.doc_type == doc_type and fr.field == "dob")


def _three_doc_script(bc_dob_reads):
    script = _script()
    script[("birth_certificate", "name")] = ["Mohammad Abdul Rahman"]
    script[("birth_certificate", "dob")] = bc_dob_reads
    script[("birth_certificate", "father_name")] = ["Abdul Karim"]
    return script


def test_planner_chosen_view_settles_field_in_one_step():
    # First pass cannot settle the certificate DOB (one read, two
    # failures). The planner picks the stamp-masked re-read; its read
    # settles the field, so there is exactly one investigation read
    # and no second consultation.
    script = _three_doc_script(
        ["UNREADABLE", "১২/০৩/১৯৯০", "UNREADABLE", "১২/০৩/১৯৯০"])
    reader = MockReader(script, planner=[
        {"action": "stamp_masked",
         "reason": "A stamp appears to cover the date."}])
    outcome = agent.run_review(reader, {"nid": "nid.png",
                                        "birth_certificate": "bc.png",
                                        "bank_form": "form.png"})
    dob = _dob(outcome)
    assert dob.value == "১২/০৩/১৯৯০"
    assert len(dob.reads) == 4  # 3 first-pass + 1 planner-chosen read
    assert dob.investigation == [
        {"action": "stamp_masked",
         "reason": "A stamp appears to cover the date.",
         "source": "planner", "segment_prompt": "stamp"}]
    assert len(reader.planner_calls) == 1
    # The planner saw the reads so far and the offered actions.
    call = reader.planner_calls[0]
    assert call["doc_type"] == "birth_certificate"
    assert call["field"] == "dob"
    assert [r["view"] for r in call["reads"]] == agent.FIRST_PASS_VIEWS
    assert set(call["actions"]) == {"stamp_masked", "stamp_removed",
                                    "zoom_tight", "recapture"}
    assert outcome.verdict == "CONSISTENT"


def test_planner_recapture_ends_investigation_without_reads():
    # The planner judges the capture hopeless: no investigation views
    # are read at all, the field stays unreadable, and the otherwise
    # clean set asks for a recapture.
    script = _script()
    script[("bank_form", "dob")] = ["12/03/1990", "12/03/1996",
                                    "UNREADABLE"]
    reader = MockReader(script, planner=[
        {"action": "recapture",
         "reason": "The capture is too degraded to trust."}])
    outcome = agent.run_review(reader, {"nid": "nid.png",
                                        "bank_form": "form.png"})
    dob = _dob(outcome, doc_type="bank_form")
    assert dob.value is None
    assert len(dob.reads) == 3  # first pass only — no investigation
    assert dob.investigation == [
        {"action": "recapture",
         "reason": "The capture is too degraded to trust.",
         "source": "planner"}]
    assert outcome.verdict == "UNREADABLE"


def test_planner_garbage_decision_falls_back_to_fixed_views():
    # An unknown action is not a decision: the deterministic fallback
    # runs both fixed views, logged as fallback, and the field still
    # settles on the majority the fixed sequence recovers.
    script = _three_doc_script(
        ["UNREADABLE", "১২/০৩/১৯৯০", "UNREADABLE",
         "১২/০৩/১৯৯০", "১২/০৩/১৯৯০"])
    reader = MockReader(script, planner=[
        {"action": "enhance_everything", "reason": "???"}])
    outcome = agent.run_review(reader, {"nid": "nid.png",
                                        "birth_certificate": "bc.png",
                                        "bank_form": "form.png"})
    dob = _dob(outcome)
    assert len(dob.reads) == 6  # fallback ran all three fixed views
    assert [e["source"] for e in dob.investigation] == ["fallback",
                                                        "fallback",
                                                        "fallback"]
    assert [e["action"] for e in dob.investigation] == \
        agent.INVESTIGATION_VIEWS
    assert dob.value == "১২/০৩/১৯৯০"
    assert outcome.verdict == "CONSISTENT"


def test_planner_exception_falls_back_to_fixed_views():
    # A planner that blows up mid-review must not break the review:
    # same fallback, same recovered majority.
    script = _three_doc_script(
        ["UNREADABLE", "১২/০৩/১৯৯০", "UNREADABLE",
         "১২/০৩/১৯৯০", "১২/০৩/১৯৯০"])
    reader = MockReader(script, planner=[RuntimeError("planner down")])
    outcome = agent.run_review(reader, {"nid": "nid.png",
                                        "birth_certificate": "bc.png",
                                        "bank_form": "form.png"})
    dob = _dob(outcome)
    assert len(dob.reads) == 6
    assert [e["source"] for e in dob.investigation] == ["fallback",
                                                        "fallback",
                                                        "fallback"]
    assert dob.value == "১২/০৩/১৯৯০"
    assert outcome.verdict == "CONSISTENT"


def test_planner_second_consultation_is_the_last():
    # Both chosen steps still leave the reads scattered (all distinct
    # values): the planner is consulted exactly twice — never a
    # third time — and the unsettled field stays unreadable.
    script = _script()
    script[("bank_form", "dob")] = ["12/03/1990", "12/03/1996",
                                    "UNREADABLE", "12/03/1992",
                                    "12/03/1994"]
    reader = MockReader(script, planner=[
        {"action": "zoom_tight", "reason": "Print looks faint."},
        {"action": "stamp_masked", "reason": "Try under the stamp."}])
    outcome = agent.run_review(reader, {"nid": "nid.png",
                                        "bank_form": "form.png"})
    dob = _dob(outcome, doc_type="bank_form")
    assert len(reader.planner_calls) == 2
    assert len(dob.reads) == 5  # 3 first-pass + 2 chosen steps
    assert [e["action"] for e in dob.investigation] == ["zoom_tight",
                                                        "stamp_masked"]
    assert all(e["source"] == "planner" for e in dob.investigation)
    # The second consultation saw the first chosen step's read.
    assert [r["view"] for r in reader.planner_calls[1]["reads"]] == \
        agent.FIRST_PASS_VIEWS + ["zoom_tight"]
    assert dob.value is None
    assert outcome.verdict == "UNREADABLE"


def test_clean_fields_never_consult_the_planner():
    # Unanimous first-pass reads: no uncertainty, no investigation,
    # and the planner is never even asked.
    reader = MockReader(_script(), planner=[
        {"action": "recapture", "reason": "must never be used"}])
    outcome = agent.run_review(reader, {"nid": "nid.png",
                                        "bank_form": "form.png"})
    assert outcome.verdict == "CONSISTENT"
    assert reader.planner_calls == []
    for fr in outcome.field_reads:
        assert fr.investigation == []
        assert len(fr.reads) == 3


def test_planner_reason_is_collapsed_and_capped_in_the_log():
    script = _three_doc_script(
        ["UNREADABLE", "১২/০৩/১৯৯০", "UNREADABLE", "১২/০৩/১৯৯০"])
    reader = MockReader(script, planner=[
        {"action": "stamp_masked",
         "reason": "  a   stamp\n covers\tit " + "x" * 400}])
    outcome = agent.run_review(reader, {"nid": "nid.png",
                                        "birth_certificate": "bc.png",
                                        "bank_form": "form.png"})
    reason = _dob(outcome).investigation[0]["reason"]
    assert reason.startswith("a stamp covers it")
    assert len(reason) == agent.REASON_MAX_CHARS


def test_run_review_script_rescue_clears_transliteration_flag():
    # father_name reads settle on different Latin spellings per doc
    # (skeleton rule cannot fold q/k); script reads agree, so the
    # review ends Consistent and the rescue only read the one field.
    script = _script()
    script[("nid", "father_name")] = ["Rafiqul Islam"] * 3
    script[("bank_form", "father_name")] = ["Rafikul Islam"] * 3
    reader = MockReader(script, script_reads={
        ("nid", "father_name"): "রফিকুল ইসলাম",
        ("bank_form", "father_name"): "রফিকুল ইসলাম",
    })
    outcome = agent.run_review(reader, {"nid": "n.png", "bank_form": "b.png"})
    assert outcome.verdict == "CONSISTENT"
    assert reader.script_calls == [("nid", "father_name"),
                                   ("bank_form", "father_name")]
    finding = next(f for f in outcome.findings
                   if f["field"] == "father_name")
    assert finding["status"] == "variant"
    assert "original-script" in finding["note"]


def test_run_review_no_script_reads_without_name_mismatch():
    reader = MockReader(_script(), script_reads={
        ("nid", "father_name"): "আবদুল করিম",
        ("bank_form", "father_name"): "আবদুল করিম",
    })
    outcome = agent.run_review(reader, {"nid": "n.png", "bank_form": "b.png"})
    assert outcome.verdict == "CONSISTENT"
    assert reader.script_calls == []


def _tiny_png(tmp_path):
    from PIL import Image

    path = tmp_path / "bc.png"
    Image.new("RGB", (80, 60), (240, 240, 230)).save(path)
    return str(path)


def _stamp_investigation_script():
    script = _script()
    script[("birth_certificate", "name")] = ["Mohammad Abdul Rahman"]
    script[("birth_certificate", "father_name")] = ["Abdul Karim"]
    script[("birth_certificate", "dob")] = [
        "১২/০৩/১৯৯০", "১২/০৮/১৯৯০", "১২/০৩/১৯৯০", "১২/০৩/১৯৯০"]
    return script


def test_planner_segment_prompt_reaches_segmenter(tmp_path):
    from app.segmenter import MockSegmenter

    bc = _tiny_png(tmp_path)
    reader = MockReader(_stamp_investigation_script(), planner=[
        {"action": "stamp_removed", "reason": "Ink over the date.",
         "segment_prompt": "circular ink stamp"}])
    segmenter = MockSegmenter()
    outcome = agent.run_review(
        reader, {"nid": "n.png", "birth_certificate": bc,
                 "bank_form": "f.png"}, segmenter=segmenter)
    assert outcome.verdict == "CONSISTENT"
    assert (bc, "circular ink stamp") in segmenter.calls
    dob = next(fr for fr in outcome.field_reads
               if fr.doc_type == "birth_certificate" and fr.field == "dob")
    assert dob.investigation[0]["segment_prompt"] == "circular ink stamp"


def test_unlisted_segment_prompt_defaults_to_stamp(tmp_path):
    from app.segmenter import MockSegmenter

    bc = _tiny_png(tmp_path)
    reader = MockReader(_stamp_investigation_script(), planner=[
        {"action": "stamp_masked", "reason": "Covered.",
         "segment_prompt": "rubber stamp"}])  # not an offered phrase
    segmenter = MockSegmenter()
    agent.run_review(reader, {"nid": "n.png", "birth_certificate": bc,
                              "bank_form": "f.png"}, segmenter=segmenter)
    assert (bc, "stamp") in segmenter.calls
    assert (bc, "rubber stamp") not in segmenter.calls


def test_visual_review_attached_but_never_changes_verdict():
    visual = {"concerns": [{"doc": "birth_certificate", "area": "dob",
                            "type": "stamp_overlap",
                            "detail": "Stamp over the date."}],
              "summary": "Stamp overlap on the certificate."}
    reader = MockReader(_script(), visual=visual)
    outcome = agent.run_review(reader, {"nid": "n.png", "bank_form": "f.png"})
    assert outcome.verdict == "CONSISTENT"  # advisory only
    assert outcome.visual_review == visual
    assert len(reader.visual_calls) == 1


def test_visual_failure_means_no_visual_review():
    reader = MockReader(_script(), visual=RuntimeError("down"))
    outcome = agent.run_review(reader, {"nid": "n.png", "bank_form": "f.png"})
    assert outcome.verdict == "CONSISTENT"
    assert outcome.visual_review is None


def test_reader_without_visual_capability_gets_none():
    class BareReader:
        def read_field(self, image_path, doc_type, field, perturbation):
            return "UNREADABLE"

    outcome = agent.run_review(BareReader(), {"nid": "n.png"})
    assert outcome.visual_review is None

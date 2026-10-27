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
    assert len(dob.reads) == 5  # 3 first-pass + 2 investigation views
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
    assert len(dob.reads) == 5  # 3 first-pass + 2 investigation views
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
    assert len(dob.reads) == 5  # 3 first-pass + 2 investigation views
    assert dob.value is None
    assert outcome.verdict == "UNREADABLE"


def test_agent_scattered_probe_reads_give_recapture_not_flag():
    # The live-probe shape (2026-10-27): the stamp-covered birth
    # certificate DOB read [UNREADABLE, wrong, UNREADABLE, UNREADABLE,
    # correct] across the five views — the correct value and a wrong
    # value once each. The old tie-break picked an arbitrary winner
    # and falsely flagged the genuine set DISCREPANCY; scattered reads
    # like these must end in a recapture request instead.
    script = _script()
    script[("birth_certificate", "name")] = ["Mohammad Abdul Rahman"]
    script[("birth_certificate", "dob")] = ["UNREADABLE", "১২/০৯/১৯৯০",
                                            "UNREADABLE", "UNREADABLE",
                                            "১২/০৩/১৯৯০"]
    script[("birth_certificate", "father_name")] = ["Abdul Karim"]
    reader = MockReader(script)
    outcome = agent.run_review(reader, {"nid": "nid.png",
                                        "birth_certificate": "bc.png",
                                        "bank_form": "form.png"})
    dob = next(fr for fr in outcome.field_reads
               if fr.doc_type == "birth_certificate" and fr.field == "dob")
    assert dob.uncertain is True
    assert len(dob.reads) == 5  # 3 first-pass + 2 investigation views
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
    assert len(dob.reads) == 5  # 3 first-pass + 2 investigation views
    assert dob.value is None
    assert outcome.verdict == "UNREADABLE"

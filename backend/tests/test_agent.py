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

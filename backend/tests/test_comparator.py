from app import comparator


def test_consistent_set_with_variants_passes():
    docs = {
        "nid": {"name": "Md. Abdul Rahman", "dob": "12/03/1990",
                "id_number": "1234 567890", "father_name": "Abdul Karim"},
        "birth_certificate": {"name": "Mohammad Abdul Rahaman",
                              "dob": "১২/০৩/১৯৯০", "father_name": "Abdul Karim"},
        "bank_form": {"name": "Mohammad Abdul Rahman", "dob": "12 March 1990",
                      "id_number": "1234567890"},
    }
    result = comparator.compare(docs)
    assert result.verdict == "CONSISTENT"
    assert all(f.status in ("match", "variant", "single_source")
               for f in result.findings)


def test_swapped_dob_digit_is_a_discrepancy():
    docs = {
        "nid": {"name": "Ayesha Siddiqua", "dob": "05/07/1995"},
        "bank_form": {"name": "Ayesha Siddiqua", "dob": "05/07/1996"},
    }
    result = comparator.compare(docs)
    assert result.verdict == "DISCREPANCY"
    dob = next(f for f in result.findings if f.field == "dob")
    assert dob.status == "mismatch"


def test_unparsable_field_is_unreadable_not_discrepancy():
    docs = {
        "nid": {"name": "Tanvir Ahmed", "dob": "##/##/####"},
        "bank_form": {"name": "Tanvir Ahmed", "dob": "01/01/1992"},
    }
    result = comparator.compare(docs)
    assert result.verdict == "UNREADABLE"


def test_transliterated_father_name_is_consistent():
    # The 2026-10-29 evaluation failure: the birth certificate renders
    # the father name in Bangla and the reader transliterates it back as
    # "Abdul Karami" while the other documents read "Abdul Karim".
    docs = {
        "nid": {"name": "Mohammad Abdul Rahman", "dob": "12/03/1990",
                "id_number": "1234567890", "father_name": "Abdul Karim"},
        "birth_certificate": {"name": "Mohammad Abdul Rahman",
                              "dob": "১২/০৩/১৯৯০",
                              "father_name": "Abdul Karami"},
        "bank_form": {"name": "Mohammad Abdul Rahman", "dob": "12/03/1990",
                      "id_number": "1234567890",
                      "father_name": "Abdul Karim"},
    }
    result = comparator.compare(docs)
    assert result.verdict == "CONSISTENT"
    father = next(f for f in result.findings if f.field == "father_name")
    assert father.status == "variant"


def test_genuinely_different_father_name_still_flags():
    docs = {
        "nid": {"name": "Mohammad Abdul Rahman", "father_name": "Abdul Karim"},
        "birth_certificate": {"name": "Mohammad Abdul Rahman",
                              "father_name": "Abdul Rahim"},
        "bank_form": {"name": "Mohammad Abdul Rahman",
                      "father_name": "Abdul Karim"},
    }
    result = comparator.compare(docs)
    assert result.verdict == "DISCREPANCY"
    father = next(f for f in result.findings if f.field == "father_name")
    assert father.status == "mismatch"


def test_id_written_in_bangla_digits_matches():
    docs = {
        "nid": {"id_number": "৯৮৭৬৫৪৩২১০"},
        "bank_form": {"id_number": "98765 43210"},
    }
    result = comparator.compare(docs)
    assert result.verdict == "CONSISTENT"


def _finding(result, field):
    return next(f for f in result.findings if f.field == field)


def test_script_agreement_rescues_transliteration_mismatch():
    # Latin reads disagree on a consonant (Rafiqul vs Rafikul — the
    # skeleton rule does not fold q/k); the Bangla spelling on both
    # documents is identical, so this is a variant, not a mismatch.
    docs = {
        "nid": {"father_name": "Rafiqul Islam"},
        "bank_form": {"father_name": "Rafikul Islam"},
    }
    script = {
        "nid": {"father_name": "রফিকুল ইসলাম"},
        "bank_form": {"father_name": "রফিকুল ইসলাম"},
    }
    finding = _finding(comparator.compare(docs, script), "father_name")
    assert finding.status == "variant"
    assert "original-script" in finding.note


def test_script_agreement_rescues_hindi_name():
    # Same shape in Devanagari: Vijay vs Bijay (v/b) mismatches in
    # Latin; विजय on both documents rescues it.
    docs = {
        "nid": {"name": "Vijay Kumar"},
        "bank_form": {"name": "Bijay Kumar"},
    }
    script = {
        "nid": {"name": "विजय कुमार"},
        "bank_form": {"name": "विजय कुमार"},
    }
    finding = _finding(comparator.compare(docs, script), "name")
    assert finding.status == "variant"


def test_different_script_spelling_still_flags():
    # A genuinely different father name differs in Bangla too —
    # the rescue must not fire.
    docs = {
        "nid": {"father_name": "Abdul Karim"},
        "bank_form": {"father_name": "Abdul Kamal"},
    }
    script = {
        "nid": {"father_name": "আবদুল করিম"},
        "bank_form": {"father_name": "আবদুল কামাল"},
    }
    finding = _finding(comparator.compare(docs, script), "father_name")
    assert finding.status == "mismatch"


def test_missing_script_read_on_one_side_still_flags():
    docs = {
        "nid": {"father_name": "Rafiqul Islam"},
        "bank_form": {"father_name": "Rafikul Islam"},
    }
    script = {"nid": {"father_name": "রফিকুল ইসলাম"}}
    finding = _finding(comparator.compare(docs, script), "father_name")
    assert finding.status == "mismatch"


def test_no_script_documents_behaves_as_before():
    docs = {
        "nid": {"father_name": "Rafiqul Islam"},
        "bank_form": {"father_name": "Rafikul Islam"},
    }
    finding = _finding(comparator.compare(docs), "father_name")
    assert finding.status == "mismatch"
    assert finding.note == ""

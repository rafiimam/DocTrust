"""Generator multi-persona tests (generator/generate.py, BANGLA_PERSONAS).

The persona pool exists because every earlier batch reused the one
base person: the name comparator's transliteration rules were only
ever exercised on the names they were tuned against. These tests pin
the pool's shape, the person/injection plumbing in generate_set, and
— critically — that the legacy default path is unchanged: the
hardcoded ground truth below was captured from the generator BEFORE
the persona work landed.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import comparator, normalize  # noqa: E402
from generator.generate import (  # noqa: E402
    BANGLA_PERSONAS, BASE_PERSON, generate_set)

# Captured from the pre-persona generator: seed 7, clean, all
# defaults. If a change alters legacy output in any way, this fails.
LEGACY_CLEAN_TRUTH = {
    "variant": "clean",
    "script": "bangla",
    "documents": {
        "nid": {"name": "Mohammad Abdul Rahman", "dob": "12/03/1990",
                "id_number": "১২৩৪৫৬৭৮৯০", "father_name": "Abdul Karim"},
        "birth_certificate": {"name": "Mohammad Abdul Rahman",
                              "dob": "১২/০৩/১৯৯০",
                              "father_name": "Abdul Karim"},
        "bank_form": {"name": "Mohammad Abdul Rahman",
                      "dob": "12/03/1990", "id_number": "1234567890",
                      "father_name": "Abdul Karim"},
    },
    "stamp_box": [750, 440, 900, 590],
    "stamp_document": "birth_certificate",
    "stamp_style": "purple",
    "stamp_position": "margin",
}

PERSON_KEYS = {"name_en", "name_bn", "father_en", "father_bn", "dob",
               "dob_bn_digits", "id_number", "id_bn_digits",
               "address_en"}


def test_persona_pool_shape():
    assert len(BANGLA_PERSONAS) == 10
    # Persona 0 IS the base person — the pool extends the legacy
    # identity, it does not replace it.
    assert BANGLA_PERSONAS[0] == BASE_PERSON
    for persona in BANGLA_PERSONAS:
        assert set(persona) == PERSON_KEYS
    # Distinct identities: no two personas share a name, father,
    # DOB or ID.
    for key in ("name_en", "father_en", "dob", "id_number"):
        values = [p[key] for p in BANGLA_PERSONAS]
        assert len(set(values)) == len(values), key


def test_persona_indic_digits_are_the_latin_values_transliterated():
    for persona in BANGLA_PERSONAS:
        assert normalize.digits_to_latin(persona["dob_bn_digits"]) \
            == persona["dob"]
        assert normalize.digits_to_latin(persona["id_bn_digits"]) \
            == persona["id_number"]
        assert len(persona["id_number"]) == 10
        assert persona["id_number"].isdigit()
        # Day <= 27, so the eval's day+1 DOB injection is always a
        # valid date in the same month.
        day, month, _year = (int(p) for p in persona["dob"].split("/"))
        assert 1 <= day <= 27 and 1 <= month <= 12


def test_legacy_default_output_is_unchanged(tmp_path):
    out = tmp_path / "s"
    truth = generate_set(out, "clean", 7)
    assert truth == LEGACY_CLEAN_TRUTH
    assert "persona" not in truth and "injection" not in truth
    # The file on disk is byte-identical to the legacy serialization.
    assert (out / "ground_truth.json").read_text() == json.dumps(
        LEGACY_CLEAN_TRUTH, indent=2, ensure_ascii=False)


def test_legacy_discrepancy_keeps_the_form_dob_swap(tmp_path):
    truth = generate_set(tmp_path / "s", "discrepancy", 7)
    docs = truth["documents"]
    assert docs["bank_form"]["dob"] == "12/03/1991"
    assert docs["nid"]["dob"] == "12/03/1990"
    assert "persona" not in truth and "injection" not in truth


def test_persona_clean_set_uses_the_persona_and_agrees(tmp_path):
    persona = BANGLA_PERSONAS[3]
    truth = generate_set(tmp_path / "s", "clean", 7, person=persona)
    docs = truth["documents"]
    assert docs["nid"]["name"] == persona["name_en"]
    assert docs["nid"]["id_number"] == persona["id_bn_digits"]
    assert docs["birth_certificate"]["dob"] == persona["dob_bn_digits"]
    assert docs["bank_form"]["father_name"] == persona["father_en"]
    assert truth["persona"] == persona["name_en"]
    assert "injection" not in truth
    assert comparator.compare(docs).verdict == "CONSISTENT"


@pytest.mark.parametrize("field,value", [
    ("dob", "06/02/1992"),
    ("id_number", "4567890124"),
    ("father_name", "Abdul Kamal"),
    ("name", "Md. Tanvir Hossain"),
])
def test_injection_lands_on_the_form_only_and_flags_exactly_it(
        tmp_path, field, value):
    persona = BANGLA_PERSONAS[3]  # Md. Tanvir Hasan / Abdul Malek
    injection = {"field": field, "value": value}
    truth = generate_set(tmp_path / "s", "discrepancy", 7,
                         person=persona, injection=injection)
    docs = truth["documents"]
    assert docs["bank_form"][field] == value
    # Nothing else moved: the NID and certificate still carry the
    # persona's true values, and the legacy DOB swap did NOT also
    # happen (an injection replaces it).
    assert docs["nid"]["dob"] == persona["dob"]
    assert docs["birth_certificate"]["dob"] == persona["dob_bn_digits"]
    if field != "dob":
        assert docs["bank_form"]["dob"] == persona["dob"]
    assert truth["persona"] == persona["name_en"]
    assert truth["injection"] == injection
    result = comparator.compare(docs)
    assert result.verdict == "DISCREPANCY"
    flagged = [f.field for f in result.findings if f.status == "mismatch"]
    assert flagged == [field]


def test_degraded_discrepancy_combination(tmp_path):
    persona = BANGLA_PERSONAS[1]
    injection = {"field": "father_name", "value": "Abdul Kamal"}
    plain = generate_set(tmp_path / "plain", "discrepancy", 7,
                         person=persona, injection=injection)
    hurt = generate_set(tmp_path / "hurt", "discrepancy", 7,
                        person=persona, injection=injection,
                        degrade=True)
    # Same ground truth either way — degradation is a rendering
    # treatment, not a fact change.
    assert hurt == plain
    assert hurt["variant"] == "discrepancy"
    result = comparator.compare(hurt["documents"])
    assert result.verdict == "DISCREPANCY"
    # ...but the degraded rendering really was applied: glare on the
    # NID, blur on the bank form; the birth certificate is untouched
    # by the degradation treatment.
    for name in ("nid.png", "bank_form.png"):
        assert (tmp_path / "hurt" / name).read_bytes() != \
            (tmp_path / "plain" / name).read_bytes()
    assert (tmp_path / "hurt" / "birth_certificate.png").read_bytes() == \
        (tmp_path / "plain" / "birth_certificate.png").read_bytes()


def test_unknown_injection_field_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        generate_set(tmp_path / "s", "discrepancy", 7,
                     person=BANGLA_PERSONAS[0],
                     injection={"field": "address", "value": "Elsewhere"})

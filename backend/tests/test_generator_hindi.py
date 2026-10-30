"""Generator Hindi-persona tests (generator/generate.py, script="hindi").

The Hindi persona is the eval's cheap second script: the same document
family and per-document script pattern as the Bangla persona —
Devanagari names on the birth certificate, Devanagari digits for the
NID number and the certificate's Born row, Latin on the bank form —
so a reader faces the same cross-script comparison, in Devanagari.
Claims stay narrow: Bangla primary, Hindi secondary, small n.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import comparator  # noqa: E402
from generator.generate import HINDI_PERSON, generate_set  # noqa: E402


@pytest.mark.parametrize("variant", ["clean", "variation", "discrepancy",
                                     "degraded"])
def test_hindi_set_renders_all_documents(tmp_path, variant):
    out = tmp_path / variant
    truth = generate_set(out, variant, script="hindi")
    for name in ("nid.png", "birth_certificate.png", "bank_form.png"):
        assert (out / name).is_file()
        assert (out / name).stat().st_size > 1000
    assert truth["script"] == "hindi"
    assert truth["variant"] == variant


def test_hindi_ground_truth_uses_devanagari_where_the_bangla_set_does(tmp_path):
    truth = generate_set(tmp_path / "s", "clean", script="hindi")
    docs = truth["documents"]
    # Indic digits as printed on the NID and the birth certificate;
    # Latin digits on the bank form — the Bangla persona's pattern.
    assert docs["nid"]["id_number"] == HINDI_PERSON["id_hi_digits"]
    assert docs["birth_certificate"]["dob"] == HINDI_PERSON["dob_hi_digits"]
    assert docs["bank_form"]["id_number"] == HINDI_PERSON["id_number"]
    assert docs["bank_form"]["dob"] == HINDI_PERSON["dob"]
    # Names: ground truth is the Latin form the reader must return.
    for doc in docs.values():
        assert doc["name"] == HINDI_PERSON["name_en"]
        assert doc["father_name"] == HINDI_PERSON["father_en"]


def test_hindi_ground_truth_verdicts_via_comparator(tmp_path):
    # Expected verdicts derive from the ground truth through the same
    # comparator the eval scores with — no parallel expectation logic.
    for variant, verdict in (("clean", "CONSISTENT"),
                             ("variation", "CONSISTENT"),
                             ("degraded", "CONSISTENT"),
                             ("discrepancy", "DISCREPANCY")):
        truth = generate_set(tmp_path / variant, variant, script="hindi")
        result = comparator.compare(truth["documents"])
        assert result.verdict == verdict, variant
    disc = generate_set(tmp_path / "d2", "discrepancy", script="hindi")
    findings = {f.field: f.status
                for f in comparator.compare(disc["documents"]).findings}
    assert findings["dob"] == "mismatch"


def test_bangla_remains_the_default_script(tmp_path):
    truth = generate_set(tmp_path / "s", "clean")
    assert truth["script"] == "bangla"
    assert truth["documents"]["nid"]["id_number"] == "১২৩৪৫৬৭৮৯০"


def test_unknown_script_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        generate_set(tmp_path / "s", "clean", script="urdu")

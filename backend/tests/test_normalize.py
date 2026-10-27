from datetime import date

from app import normalize


def test_bangla_digits_convert_both_ways():
    assert normalize.digits_to_latin("১৯৯০") == "1990"
    assert normalize.digits_to_bangla("1990") == "১৯৯০"
    assert normalize.digits_to_latin("জন্ম ১২/০৩/১৯৯০") == "জন্ম 12/03/1990"


def test_parse_date_shapes():
    assert normalize.parse_date("12/03/1990") == date(1990, 3, 12)  # day-first
    assert normalize.parse_date("12-03-1990") == date(1990, 3, 12)
    assert normalize.parse_date("1990-03-12") == date(1990, 3, 12)
    assert normalize.parse_date("12 March 1990") == date(1990, 3, 12)
    assert normalize.parse_date("১২/০৩/১৯৯০") == date(1990, 3, 12)  # Bangla digits
    assert normalize.parse_date("not a date") is None
    assert normalize.parse_date("31/02/1990") is None  # invalid -> unreadable


def test_normalize_id_strips_separators_and_converts_digits():
    assert normalize.normalize_id("1234 5678-90") == "1234567890"
    assert normalize.normalize_id("১২৩৪৫৬৭৮৯০") == "1234567890"


def test_name_variants_fold():
    assert normalize.names_match("Md. Abdul Rahman", "Mohammad Abdul Rahaman") == "match"
    assert normalize.names_match("Mohammed Hossain", "Muhammad Hossein") == "match"
    assert normalize.names_match("Fatima Akter", "Fatima Khatun") == "mismatch"
    assert normalize.names_match("", "Someone") == "unknown"

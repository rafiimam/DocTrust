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


def test_devanagari_digits_convert():
    assert normalize.digits_to_latin("१९९०") == "1990"
    assert normalize.digits_to_latin("जन्म १२/०३/१९९०") == "जन्म 12/03/1990"
    assert normalize.normalize_id("९८७६५४३२१०") == "9876543210"
    assert normalize.parse_date("१२/०३/१९९०") == date(1990, 3, 12)
    # Mixed scripts in one string all fold to Latin digits.
    assert normalize.digits_to_latin("১2३") == "123"


def test_transliteration_skeleton_equivalences():
    # The measured failure: করিম read back from the Bangla birth
    # certificate as Karami/Karimi/Karomi must equal Latin "Karim".
    for variant in ("Abdul Karami", "Abdul Karimi", "Abdul Karomi"):
        assert normalize.names_match("Abdul Karim", variant) == "variant"
    assert normalize.names_match("Mohammad", "Mohammed") == "match"  # folded
    assert normalize.names_match("Rahman", "Rahamana") == "variant"
    assert normalize.names_match(
        "Mohammad Abdul Rahman", "Mohammed Abdul Rahamana") == "variant"


def test_transliteration_skeleton_non_equivalences():
    # Same-looking but genuinely different names stay mismatches:
    # skeletons differ (krm vs rhm) even where edit distance is small.
    assert normalize.names_match("Karim", "Rahim") == "mismatch"
    assert normalize.names_match("Abdul Karim", "Abdul Rahim") == "mismatch"
    assert normalize.names_match(
        "Mohammad Abdul Rahman", "Mohammad Abdul Rahim") == "mismatch"
    # Different token counts never merge.
    assert normalize.names_match("Abdul Karim", "Abdul Karim Hossain") == "mismatch"
    assert normalize.names_match("Abdul Karim", "Karim") == "mismatch"
    # Short tokens get no skeleton slack.
    assert normalize.names_match("Ali", "Aly") == "mismatch"

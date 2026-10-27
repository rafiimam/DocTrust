"""Generator stamp-style tests (generator/generate.py).

The birth-certificate stamp is selectable so the SAM-vs-heuristic
comparison (eval/SAM_TEST.md) can use stamps the Pillow colour
heuristic was not built for. These tests pin the contract: every
style renders a full set, the ground truth records a plausible
stamp_box on the birth certificate, the default style stays
"purple" (the original rendering), and styles actually change the
rendered certificate.
"""

import pytest
from PIL import Image

from app.segmenter import detect_stamp_box
from generator.generate import (STAMP_BOX, STAMP_CENTER, STAMP_RADIUS,
                                STAMP_STYLES, generate_set)


@pytest.mark.parametrize("style", sorted(STAMP_STYLES))
def test_each_stamp_style_renders_a_set(tmp_path, style):
    out = tmp_path / style
    truth = generate_set(out, "clean", stamp_style=style)
    for name in ("nid.png", "birth_certificate.png", "bank_form.png"):
        assert (out / name).is_file()
        assert (out / name).stat().st_size > 1000
    assert truth["stamp_style"] == style
    assert truth["stamp_document"] == "birth_certificate"


@pytest.mark.parametrize("variant", ["clean", "variation", "discrepancy",
                                     "degraded"])
def test_stamp_box_recorded_for_every_variant(tmp_path, variant):
    truth = generate_set(tmp_path / variant, variant)
    box = truth["stamp_box"]
    assert box == STAMP_BOX
    x0, y0, x1, y1 = box
    # Plausible: a non-empty rectangle inside the 1000x640 page.
    assert 0 <= x0 < x1 <= 1000
    assert 0 <= y0 < y1 <= 640
    assert (x1 - x0) >= 100 and (y1 - y0) >= 40
    # The stamp is a circle: its AABB is square, centred on the
    # stamp centre with side 2 * radius.
    assert (x1 - x0) == (y1 - y0) == 2 * STAMP_RADIUS
    assert ((x0 + x1) / 2, (y0 + y1) / 2) == STAMP_CENTER


def test_default_stamp_style_is_purple(tmp_path):
    truth = generate_set(tmp_path / "default", "clean")
    assert truth["stamp_style"] == "purple"


def test_stamp_styles_change_the_certificate(tmp_path):
    purple = generate_set(tmp_path / "purple", "clean",
                          stamp_style="purple")
    black = generate_set(tmp_path / "black", "clean", stamp_style="black")
    faded = generate_set(tmp_path / "faded", "clean",
                         stamp_style="faded_grey")
    assert purple["stamp_box"] == black["stamp_box"] == faded["stamp_box"]
    certs = {}
    for name, directory in (("purple", "purple"), ("black", "black"),
                            ("faded", "faded")):
        with Image.open(tmp_path / directory
                        / "birth_certificate.png") as img:
            certs[name] = img.convert("RGB").tobytes()
    assert certs["purple"] != certs["black"]
    assert certs["purple"] != certs["faded"]
    # The other documents do not depend on the stamp style.
    with Image.open(tmp_path / "purple" / "nid.png") as a, \
            Image.open(tmp_path / "black" / "nid.png") as b:
        assert a.convert("RGB").tobytes() == b.convert("RGB").tobytes()


def test_unknown_stamp_style_rejected(tmp_path):
    with pytest.raises(ValueError):
        generate_set(tmp_path / "bogus", "clean", stamp_style="green")


def test_generated_purple_stamp_detected_close_to_truth(tmp_path):
    # The Pillow colour heuristic must still find the (now circular)
    # purple stamp, at close to the recorded ground-truth box. The
    # detector works on a downscaled copy, so a few pixels of slack.
    out = tmp_path / "detect"
    truth = generate_set(out, "clean", stamp_style="purple")
    box = detect_stamp_box(str(out / "birth_certificate.png"))
    assert box is not None
    x0, y0, x1, y1 = truth["stamp_box"]
    assert abs(box.x_min - x0) <= 4
    assert abs(box.y_min - y0) <= 4
    assert abs(box.x_max - x1) <= 4
    assert abs(box.y_max - y1) <= 6

"""Synthetic document-set generator (v1).

Renders SPECIMEN-watermarked sample document sets with PIL — a national-ID
style card, a birth certificate, and a bank account form — plus a
ground_truth.json describing exactly what each document says.

Design constraints from the plan:
- Synthetic data only. Every page is watermarked SPECIMEN.
- Layouts are *inspired by* the shape of these documents, never copies of
  real templates, and no real security features are imitated.
- Bangla text is rendered with a Bengali font via libraqm shaping.

Usage:
    python -m generator.generate --out ../data/sample_clean --variant clean
Variants: clean | variation | discrepancy | degraded
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_LATIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_LATIN_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_BANGLA = "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf"
FONT_BANGLA_BOLD = "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf"

W, H = 1000, 640

BASE_PERSON = {
    "name_en": "Mohammad Abdul Rahman",
    "name_bn": "মোহাম্মদ আব্দুল রহমান",
    "father_en": "Abdul Karim",
    "father_bn": "আব্দুল করিম",
    "dob": "12/03/1990",
    "dob_bn_digits": "১২/০৩/১৯৯০",
    "id_number": "1234567890",
    "id_bn_digits": "১২৩৪৫৬৭৮৯০",
    "address_en": "House 12, Rajshahi, Bangladesh",
}


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _watermark(img: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    f = _font(FONT_LATIN_BOLD, 64)
    for y in range(60, img.height, 220):
        for x in range(-40, img.width, 460):
            d.text((x, y), "SPECIMEN", font=f, fill=(200, 30, 30, 70))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _header(d: ImageDraw.ImageDraw, title_en: str, title_bn: str) -> None:
    d.rectangle([0, 0, W, 84], fill=(22, 101, 52))
    d.text((28, 14), title_bn, font=_font(FONT_BANGLA_BOLD, 30), fill="white")
    d.text((28, 50), title_en, font=_font(FONT_LATIN, 20), fill=(210, 235, 218))


def _row(d: ImageDraw.ImageDraw, y: int, label: str, value: str,
         bangla_value: bool = False, label_x: int = 36,
         value_x: int = 300) -> int:
    d.text((label_x, y), label, font=_font(FONT_LATIN, 21), fill=(90, 90, 90))
    d.text((value_x, y - 3), value,
           font=_font(FONT_BANGLA if bangla_value else FONT_LATIN, 26),
           fill=(15, 15, 15))
    return y + 52


def render_nid(p: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), (240, 246, 240))
    d = ImageDraw.Draw(img)
    _header(d, "National Identity Card (sample)", "জাতীয় পরিচয় পত্র")
    d.rectangle([36, 116, 196, 316], outline=(120, 120, 120), width=3)
    d.text((58, 196), "PHOTO", font=_font(FONT_LATIN, 22), fill=(120, 120, 120))
    y = 120
    kw = {"label_x": 225, "value_x": 430}
    y = _row(d, y, "Name (BN)", p["name_bn"], bangla_value=True, **kw); y += 66
    y = _row(d, y, "Name", p["name_en"], **kw)
    y = _row(d, y, "Father", p["father_en"], **kw)
    y = _row(d, y, "Date of Birth", p["dob"], **kw)
    y = _row(d, y, "ID No", p["id_bn_digits"], bangla_value=True, **kw)
    return _watermark(img)


def render_birth_certificate(p: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), (250, 248, 238))
    d = ImageDraw.Draw(img)
    _header(d, "Birth Certificate (sample)", "জন্ম সনদ")
    y = 130
    y = _row(d, y, "Name", p["name_en"])
    y = _row(d, y, "Name (BN)", p["name_bn"], bangla_value=True)
    y = _row(d, y, "Father", p["father_bn"], bangla_value=True)
    y = _row(d, y, "Born", p["dob_bn_digits"], bangla_value=True)
    y = _row(d, y, "Address", p["address_en"])
    d.rectangle([700, 470, 950, 560], outline=(40, 40, 160), width=3)
    d.text((742, 500), "OFFICE STAMP", font=_font(FONT_LATIN, 20), fill=(40, 40, 160))
    return _watermark(img)


def render_bank_form(p: dict) -> Image.Image:
    img = Image.new("RGB", (W, H), (244, 246, 250))
    d = ImageDraw.Draw(img)
    _header(d, "Account Opening Form (sample)", "হিসাব খোলার ফরম")
    y = 130
    y = _row(d, y, "Applicant", p["name_en"])
    y = _row(d, y, "Father's Name", p["father_en"])
    y = _row(d, y, "DOB (DD/MM/YYYY)", p["dob"])
    y = _row(d, y, "NID Number", p["id_number"])
    y = _row(d, y, "Address", p["address_en"])
    return _watermark(img)


def apply_degradation(img: Image.Image, kind: str, rng: random.Random) -> Image.Image:
    if kind == "blur":
        return img.filter(ImageFilter.GaussianBlur(radius=2.2))
    if kind == "rotate":
        return img.rotate(rng.uniform(-3.5, 3.5), expand=True, fillcolor=(30, 30, 30))
    if kind == "glare":
        glare = Image.new("L", img.size, 0)
        gd = ImageDraw.Draw(glare)
        gd.ellipse([img.width // 3, 40, img.width, 380], fill=170)
        white = Image.new("RGB", img.size, (255, 255, 255))
        return Image.composite(white, img, glare.filter(ImageFilter.GaussianBlur(60)))
    return img


def build_person(variant: str, rng: random.Random) -> tuple[dict, dict, dict]:
    """Returns (nid_fields, birth_fields, form_fields) — what each document
    *says*, which is the ground truth the comparator is scored against."""
    p = dict(BASE_PERSON)
    nid = {"name": p["name_en"], "dob": p["dob"],
           "id_number": p["id_bn_digits"], "father_name": p["father_en"]}
    # The birth certificate renders name/father/dates in Bangla. Ground truth
    # records what the pipeline's reader is asked to return: names
    # transliterated to Latin, digits as printed. The comparator canonicalizes
    # from there (see backend/app/normalize.py).
    birth = {"name": p["name_en"], "dob": p["dob_bn_digits"],
             "father_name": p["father_en"]}
    form = {"name": p["name_en"], "dob": p["dob"],
            "id_number": p["id_number"], "father_name": p["father_en"]}

    if variant == "variation":
        # Legitimate inconsistency: transliteration + digit systems differ,
        # the underlying facts are the same. Must NOT be flagged.
        nid["name"] = "Md. Abdul Rahman"
        form["name"] = "Mohammed Abdul Rahaman"
    elif variant == "discrepancy":
        # One-digit DOB swap on the form — the demo's catch.
        form["dob"] = "12/03/1991"
    return p, {"nid": nid, "birth_certificate": birth, "bank_form": form}, {}


def generate_set(out_dir, variant: str = "clean", seed: int = 7) -> dict:
    """Render one synthetic set into `out_dir`; return its ground truth.

    Writes nid.png, birth_certificate.png, bank_form.png and
    ground_truth.json — the same files the CLI produces — and returns
    the parsed ground_truth.json content. Used by the CLI below and by
    the backend's judge-mode case-pack endpoint.
    """
    rng = random.Random(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    person, truth, _ = build_person(variant, rng)

    render_person = dict(person)
    if variant == "variation":
        render_person["name_en"] = "Md. Abdul Rahman"
    if variant == "discrepancy":
        render_person["dob"] = "12/03/1990"  # NID + certificate stay true…

    nid_img = render_nid(render_person)
    birth_img = render_birth_certificate(render_person)
    form_person = dict(render_person)
    if variant == "discrepancy":
        form_person["dob"] = "12/03/1991"     # …the form carries the swap
    if variant == "variation":
        form_person["name_en"] = "Mohammed Abdul Rahaman"
    form_img = render_bank_form(form_person)

    images = {"nid": nid_img, "birth_certificate": birth_img, "bank_form": form_img}
    if variant == "degraded":
        images["nid"] = apply_degradation(nid_img, "glare", rng)
        images["bank_form"] = apply_degradation(form_img, "blur", rng)

    for name, img in images.items():
        img.save(out / f"{name}.png")

    ground_truth = {"variant": variant, "documents": truth}
    (out / "ground_truth.json").write_text(json.dumps(
        ground_truth, indent=2, ensure_ascii=False))
    return ground_truth


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--variant", default="clean",
                    choices=["clean", "variation", "discrepancy", "degraded"])
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    generate_set(args.out, args.variant, args.seed)
    print(f"wrote {args.out} ({args.variant})")


if __name__ == "__main__":
    main()

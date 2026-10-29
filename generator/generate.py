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

The birth certificate carries an office stamp. Its style is selectable
(--stamp-style; default "purple", the original rendering) so the
SAM-vs-heuristic comparison in eval/SAM_TEST.md can use stamps the
colour heuristic was not built for. Its placement is selectable too
(--stamp-position; default "margin", the original rendering, which
occludes no field; "over_dob" centres the stamp on the Born row's
value). The stamp's bounding box, style and position are recorded in
ground_truth.json either way.
"""

from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Canonical Linux (Debian) locations of the four fonts the generator
# renders with. _font() uses these verbatim when they exist; when they
# do not (e.g. on macOS), it falls back to searching other font
# directories for the same files — see _resolve_font().
FONT_LATIN = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_LATIN_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_BANGLA = "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf"
FONT_BANGLA_BOLD = "/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf"

_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}


def _font_search_dirs() -> list[Path]:
    """Directories searched for a font file, in priority order."""
    dirs: list[Path] = []
    env_dir = os.environ.get("DOCTRUST_FONTS_DIR")
    if env_dir:
        dirs.append(Path(env_dir).expanduser())
    dirs.append(Path(__file__).resolve().parent / "fonts")
    dirs.append(Path.home() / "Library" / "Fonts")  # macOS user fonts
    dirs.append(Path("/Library/Fonts"))  # macOS system / Homebrew casks
    dirs.append(Path("/usr/share/fonts/truetype/dejavu"))
    dirs.append(Path("/usr/share/fonts/truetype/noto"))
    return dirs


def _resolve_font(filename: str) -> Path | None:
    """Find `filename` in the search directories, or None.

    Matching tolerates the naming differences between font packagers:
    an exact filename match wins; failing that, a file with the same
    stem under another font extension (e.g. NotoSansBengali-Bold.otf);
    failing that, a file whose stem starts with the family name, which
    covers variable fonts (e.g. "NotoSansBengali[wdth,wght].ttf").
    Candidates are considered directory by directory in search order
    and sorted within a directory, so resolution is deterministic.
    """
    stem = Path(filename).stem
    family = stem.split("-")[0]
    dirs = _font_search_dirs()
    for directory in dirs:
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    for directory in dirs:
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.iterdir()):
            if (candidate.is_file() and candidate.stem == stem
                    and candidate.suffix.lower() in _FONT_EXTENSIONS):
                return candidate
    for directory in dirs:
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.iterdir()):
            if (candidate.is_file() and candidate.stem.startswith(family)
                    and candidate.suffix.lower() in _FONT_EXTENSIONS):
                return candidate
    return None


_FONT_CACHE: dict[str, str] = {}

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

# The birth-certificate office stamp: a circular graphic at a fixed
# position, with selectable ink. "purple" stays the default style.
# The other styles exist for the SAM-vs-heuristic comparison
# (eval/SAM_TEST.md): the Pillow fallback detector keys on saturated
# blue/purple ink, so black, red-orange and faded-grey stamps are
# exactly the cases it is expected to struggle with.
STAMP_CENTER = (825, 515)
STAMP_RADIUS = 75
# Axis-aligned bounding box of the circular stamp graphic. Rotation
# about the stamp's own centre does not change a circle's AABB, and
# all text/ring strokes are drawn inside that circle.
STAMP_BOX = [STAMP_CENTER[0] - STAMP_RADIUS,
             STAMP_CENTER[1] - STAMP_RADIUS,
             STAMP_CENTER[0] + STAMP_RADIUS,
             STAMP_CENTER[1] + STAMP_RADIUS]
STAMP_STYLES = {
    "purple": ((40, 40, 160), 255),
    "black": ((20, 20, 20), 255),
    "red_orange": ((198, 66, 20), 255),
    "faded_grey": ((140, 140, 140), 110),
}
DEFAULT_STAMP_STYLE = "purple"

# Birth-certificate row layout (see _row and render_birth_certificate):
# rows start at BC_FIRST_ROW_Y and step ROW_STEP apart; field values
# are drawn at VALUE_X. "Born" is the fourth row.
BC_FIRST_ROW_Y = 130
ROW_STEP = 52
VALUE_X = 300
BORN_ROW_INDEX = 3  # Name, Name (BN), Father, Born
BORN_ROW_Y = BC_FIRST_ROW_Y + BORN_ROW_INDEX * ROW_STEP  # 286

# Stamp placement. "margin" is the original position: the stamp sits
# in the bottom margin and occludes no field. "over_dob" re-centres
# the same graphic on the Born row's value — that value (Bangla digits
# drawn at (VALUE_X, BORN_ROW_Y - 3) in the 26px Bangla font) has a
# measured ink box of x 300..446, y 286..310, whose centre is
# (373, 298) — so the stamp covers the date-of-birth digits, and
# masking it is what makes them readable again. The recovered-read
# stage of eval/SAM_TEST.md needs exactly that.
STAMP_CENTER_OVER_DOB = (373, 298)
STAMP_POSITIONS = {
    "margin": STAMP_CENTER,
    "over_dob": STAMP_CENTER_OVER_DOB,
}
DEFAULT_STAMP_POSITION = "margin"


def _stamp_box(center: tuple[int, int]) -> list[int]:
    """Axis-aligned bounding box of the stamp graphic at `center`."""
    cx, cy = center
    return [cx - STAMP_RADIUS, cy - STAMP_RADIUS,
            cx + STAMP_RADIUS, cy + STAMP_RADIUS]


STAMP_BOX_OVER_DOB = _stamp_box(STAMP_CENTER_OVER_DOB)  # [298, 223, 448, 373]


def _stamp_center(position: str) -> tuple[int, int]:
    if position not in STAMP_POSITIONS:
        raise ValueError(
            f"unknown stamp position {position!r}; choose one of "
            f"{', '.join(sorted(STAMP_POSITIONS))}")
    return STAMP_POSITIONS[position]


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    resolved = _FONT_CACHE.get(path)
    if resolved is None:
        if Path(path).is_file():
            resolved = path
        else:
            found = _resolve_font(Path(path).name)
            if found is not None:
                resolved = str(found)
        if resolved is None:
            # PIL's own message ("cannot open resource") does not say
            # which file was missing; name it, list where was searched
            # and point at the fixes (on Modal these packages are
            # apt-installed in modal_backend/backend_app.py).
            searched = ", ".join(
                str(d) for d in _font_search_dirs())
            raise OSError(
                f"font file not found: {path}. Searched: {searched}. "
                "The generator needs the DejaVu and Noto Bengali fonts "
                "— on Debian/Ubuntu install the fonts-dejavu-core and "
                "fonts-noto-core packages; on macOS run: brew install "
                "--cask font-dejavu font-noto-sans-bengali (or set "
                "DOCTRUST_FONTS_DIR to a folder containing the fonts)."
            )
        _FONT_CACHE[path] = resolved
    try:
        return ImageFont.truetype(resolved, size)
    except OSError as exc:
        raise OSError(f"could not load font file: {resolved}") from exc


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
         value_x: int = VALUE_X) -> int:
    d.text((label_x, y), label, font=_font(FONT_LATIN, 21), fill=(90, 90, 90))
    d.text((value_x, y - 3), value,
           font=_font(FONT_BANGLA if bangla_value else FONT_LATIN, 26),
           fill=(15, 15, 15))
    return y + ROW_STEP


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


def _draw_stamp(img: Image.Image, style: str,
                center: tuple[int, int] = STAMP_CENTER) -> Image.Image:
    """Draw the office stamp as a rotated circular graphic.

    The stamp is a double-ring circle with OFFICE / STAMP lettering
    inside, centred at `center` and rotated by about -12 degrees
    (Pillow's positive rotation angle is counter-clockwise on screen,
    so the layer is rotated by +12). It is drawn on a transparent
    overlay so every style, including the low-alpha faded style, is
    composited the same way.
    """
    if style not in STAMP_STYLES:
        raise ValueError(
            f"unknown stamp style {style!r}; choose one of "
            f"{', '.join(sorted(STAMP_STYLES))}")
    (r, g, b), alpha = STAMP_STYLES[style]
    ink = (r, g, b, alpha)
    cx, cy = center
    radius = STAMP_RADIUS

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
               outline=ink, width=5)
    inner = radius - 11
    od.ellipse([cx - inner, cy - inner, cx + inner, cy + inner],
               outline=ink, width=2)

    font = _font(FONT_LATIN_BOLD, 20)
    for text, dy in (("OFFICE", -24), ("STAMP", 4)):
        bbox = od.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        od.text((cx - text_w / 2 - bbox[0], cy + dy - bbox[1]),
                text, font=font, fill=ink)
    # A short rule between the two words, like the line/date slot on a
    # real office stamp.
    od.line([cx - 34, cy - 2, cx + 34, cy - 2], fill=ink, width=2)

    overlay = overlay.rotate(12, resample=Image.Resampling.BICUBIC,
                             center=center)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def render_birth_certificate(p: dict,
                             stamp_style: str = DEFAULT_STAMP_STYLE,
                             stamp_position: str = DEFAULT_STAMP_POSITION
                             ) -> Image.Image:
    img = Image.new("RGB", (W, H), (250, 248, 238))
    d = ImageDraw.Draw(img)
    _header(d, "Birth Certificate (sample)", "জন্ম সনদ")
    y = BC_FIRST_ROW_Y
    y = _row(d, y, "Name", p["name_en"])
    y = _row(d, y, "Name (BN)", p["name_bn"], bangla_value=True)
    y = _row(d, y, "Father", p["father_bn"], bangla_value=True)
    y = _row(d, y, "Born", p["dob_bn_digits"], bangla_value=True)
    y = _row(d, y, "Address", p["address_en"])
    img = _draw_stamp(img, stamp_style, _stamp_center(stamp_position))
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


def generate_set(out_dir, variant: str = "clean", seed: int = 7,
                 stamp_style: str = DEFAULT_STAMP_STYLE,
                 stamp_position: str = DEFAULT_STAMP_POSITION) -> dict:
    """Render one synthetic set into `out_dir`; return its ground truth.

    Writes nid.png, birth_certificate.png, bank_form.png and
    ground_truth.json — the same files the CLI produces — and returns
    the parsed ground_truth.json content. Used by the CLI below and by
    the backend's judge-mode case-pack endpoint.

    The ground truth also records the birth certificate's stamp:
    "stamp_box" ([x0, y0, x1, y1] in image pixels, the true box for
    whichever placement was used), "stamp_document", "stamp_style"
    and "stamp_position", so the SAM-vs-heuristic comparison can
    score masks against the exact region that was drawn.
    """
    if stamp_style not in STAMP_STYLES:
        raise ValueError(
            f"unknown stamp style {stamp_style!r}; choose one of "
            f"{', '.join(sorted(STAMP_STYLES))}")
    stamp_center = _stamp_center(stamp_position)  # validates the name
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
    birth_img = render_birth_certificate(render_person,
                                         stamp_style=stamp_style,
                                         stamp_position=stamp_position)
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

    ground_truth = {
        "variant": variant,
        "documents": truth,
        # The stamp lives on the birth certificate; the other two
        # documents carry no stamp (no stamp_box is recorded for them).
        "stamp_box": _stamp_box(stamp_center),
        "stamp_document": "birth_certificate",
        "stamp_style": stamp_style,
        "stamp_position": stamp_position,
    }
    (out / "ground_truth.json").write_text(json.dumps(
        ground_truth, indent=2, ensure_ascii=False))
    return ground_truth


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--variant", default="clean",
                    choices=["clean", "variation", "discrepancy", "degraded"])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--stamp-style", default=DEFAULT_STAMP_STYLE,
                    choices=sorted(STAMP_STYLES),
                    help="birth-certificate stamp ink (default: purple)")
    ap.add_argument("--stamp-position", default=DEFAULT_STAMP_POSITION,
                    choices=sorted(STAMP_POSITIONS),
                    help="birth-certificate stamp placement "
                         "(default: margin; over_dob covers the Born "
                         "row's value)")
    args = ap.parse_args()

    generate_set(args.out, args.variant, args.seed,
                 stamp_style=args.stamp_style,
                 stamp_position=args.stamp_position)
    print(f"wrote {args.out} ({args.variant})")


if __name__ == "__main__":
    main()

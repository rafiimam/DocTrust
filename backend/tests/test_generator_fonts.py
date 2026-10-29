"""Cross-platform font resolution tests (generator/generate.py).

The generator renders with DejaVu Sans and Noto Sans Bengali. On
Debian they live at fixed system paths; on macOS they do not exist
there, so _font() falls back to searching other font directories
(DOCTRUST_FONTS_DIR, a repo-local generator/fonts/, the macOS font
folders, then the Linux paths) and tolerates packager naming
differences — another extension, or a variable-font filename.
"""

import shutil

import pytest

import generator.generate as gen

REAL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BANGLA_BOLD = "NotoSansBengali-Bold.ttf"


@pytest.fixture(autouse=True)
def _clear_font_cache():
    gen._FONT_CACHE.clear()
    yield
    gen._FONT_CACHE.clear()


def _search_dirs(monkeypatch, *dirs):
    monkeypatch.setattr(gen, "_font_search_dirs", lambda: list(dirs))


def _plant(directory, name):
    """Copy a real TTF into `directory` under `name` (PIL sniffs the
    font format from the content, so a renamed copy still loads)."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    shutil.copy(REAL_FONT, target)
    return target


def test_exact_name_wins_over_stem_match(tmp_path, monkeypatch):
    first = tmp_path / "first"
    second = tmp_path / "second"
    stem_match = _plant(first, "NotoSansBengali-Bold.otf")
    exact = _plant(second, BANGLA_BOLD)
    _search_dirs(monkeypatch, first, second)
    # Exact filename beats a same-stem file, even in an earlier dir.
    assert gen._resolve_font(BANGLA_BOLD) == exact
    assert stem_match.is_file()


def test_search_order_decides_between_exact_matches(tmp_path, monkeypatch):
    first = tmp_path / "first"
    second = tmp_path / "second"
    expected = _plant(first, BANGLA_BOLD)
    _plant(second, BANGLA_BOLD)
    _search_dirs(monkeypatch, first, second)
    assert gen._resolve_font(BANGLA_BOLD) == expected


def test_same_stem_other_extension_accepted(tmp_path, monkeypatch):
    fonts = tmp_path / "fonts"
    expected = _plant(fonts, "NotoSansBengali-Bold.otf")
    _search_dirs(monkeypatch, fonts)
    assert gen._resolve_font(BANGLA_BOLD) == expected
    # …and _font loads through the fallback.
    assert gen._font(f"/nonexistent/{BANGLA_BOLD}", 20).size == 20


def test_variable_font_filename_accepted(tmp_path, monkeypatch):
    fonts = tmp_path / "fonts"
    expected = _plant(fonts, "NotoSansBengali[wdth,wght].ttf")
    _search_dirs(monkeypatch, fonts)
    assert gen._resolve_font("NotoSansBengali-Regular.ttf") == expected


def test_env_dir_is_searched_first(tmp_path, monkeypatch):
    env_fonts = tmp_path / "env"
    expected = _plant(env_fonts, BANGLA_BOLD)
    monkeypatch.setenv("DOCTRUST_FONTS_DIR", str(env_fonts))
    assert gen._font_search_dirs()[0] == env_fonts
    assert gen._resolve_font(BANGLA_BOLD) == expected


def test_existing_system_path_used_verbatim(monkeypatch, tmp_path):
    _search_dirs(monkeypatch, tmp_path)  # nothing planted anywhere
    assert gen._font(REAL_FONT, 20).size == 20
    assert gen._FONT_CACHE[REAL_FONT] == REAL_FONT


def test_missing_font_error_lists_locations_and_fixes(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    _search_dirs(monkeypatch, empty)
    with pytest.raises(OSError) as excinfo:
        gen._font(f"/nonexistent/{BANGLA_BOLD}", 20)
    message = str(excinfo.value)
    assert BANGLA_BOLD in message
    assert str(empty) in message  # searched locations are named
    assert "fonts-dejavu-core" in message  # Debian fix
    assert "fonts-noto-core" in message
    assert "brew install --cask font-dejavu font-noto-sans-bengali" in message
    assert "DOCTRUST_FONTS_DIR" in message

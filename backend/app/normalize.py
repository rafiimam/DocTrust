"""Deterministic normalization for cross-document comparison.

Rule from the plan: the model reads; normalization and comparison are
deterministic code, so every flag a reviewer sees is traceable to a rule
here — never to a model's mood.

Conventions are Bangladesh-first: slash dates are read as DD/MM/YYYY,
Bangla digits are first-class, and name matching is transliteration-aware
rather than string equality.
"""

from __future__ import annotations

import re
from datetime import date

_BANGLA_DIGITS = "০১২৩৪৫৬৭৮৯"
_TO_LATIN = str.maketrans(_BANGLA_DIGITS, "0123456789")
_TO_BANGLA = str.maketrans("0123456789", _BANGLA_DIGITS)


def digits_to_latin(text: str) -> str:
    """Convert Bangla digits to Latin digits; leave everything else."""
    return text.translate(_TO_LATIN)


def digits_to_bangla(text: str) -> str:
    """Convert Latin digits to Bangla digits (used by the generator)."""
    return text.translate(_TO_BANGLA)


def normalize_id(text: str) -> str:
    """Canonical ID form: Latin digits only, no separators."""
    return re.sub(r"\D", "", digits_to_latin(text or ""))


_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
    "december": 12,
}


def parse_date(text: str) -> date | None:
    """Parse a date in the shapes Bangladeshi documents actually use.

    Accepts DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, YYYY-MM-DD, and
    'D Month YYYY' with English month names; Bangla digits are converted
    first. Ambiguous slash dates are read day-first (local convention).
    Returns None when nothing parses — the caller treats that as
    unreadable, never as a mismatch.
    """
    if not text:
        return None
    s = digits_to_latin(text).strip().lower()

    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:  # ISO order
        y, mo, d = (int(g) for g in m.groups())
        return _safe_date(y, mo, d)

    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", s)
    if m:  # day-first
        d, mo, y = (int(g) for g in m.groups())
        return _safe_date(y, mo, d)

    m = re.search(r"(\d{1,2})\s+([a-z]+)\s*,?\s*(\d{4})", s)
    if m and m.group(2) in _MONTHS:
        return _safe_date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))

    m = re.search(r"([a-z]+)\s+(\d{1,2})\s*,?\s*(\d{4})", s)
    if m and m.group(1) in _MONTHS:
        return _safe_date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))

    return None


def _safe_date(y: int, mo: int, d: int) -> date | None:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


# --- Names -----------------------------------------------------------------

# Variant folding for the most common Bangladeshi name spellings. Deliberately
# small and explicit: a wrong fold hides a real discrepancy, so this list
# grows only from observed generator/eval cases, never by guessing.
_NAME_VARIANTS = {
    "md": "mohammad",
    "mohammed": "mohammad",
    "mohamed": "mohammad",
    "muhammad": "mohammad",
    "muhammed": "mohammad",
    "mohamad": "mohammad",
    "abdul": "abdul",
    "abdur": "abdul",
    "rahman": "rahman",
    "rahaman": "rahman",
    "hossein": "hossain",
    "hussain": "hossain",
    "hossain": "hossain",
    "akhtar": "akter",
    "akter": "akter",
    "begum": "begum",
    "khatun": "khatun",
    "katun": "khatun",
    "sarker": "sarkar",
    "sarkar": "sarkar",
}

_HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "sk", "sheikh"}


def normalize_name(text: str) -> list[str]:
    """Canonical name tokens: folded variants, no honorifics/punctuation."""
    s = digits_to_latin((text or "").lower())
    s = re.sub(r"[^a-z\s]", " ", s)
    tokens = []
    for tok in s.split():
        if tok in _HONORIFICS:
            continue
        tokens.append(_NAME_VARIANTS.get(tok, tok))
    return tokens


_VOWELS = frozenset("aeiou")


def _consonant_skeleton(token: str) -> str:
    """Token with vowels removed ('y' counts as a consonant and stays).

    Transliteration between Bangla/Devanagari and Latin scripts mostly
    disagrees about vowels — করিম comes back as Karim, Karami, Karimi or
    Karomi depending on the reader — while the consonant frame is stable.
    """
    return "".join(ch for ch in token if ch not in _VOWELS)


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance (tokens are short; a plain DP is fine)."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(
                previous[j] + 1,                # delete
                current[j - 1] + 1,             # insert
                previous[j - 1] + (ca != cb),   # substitute
            ))
        previous = current
    return previous[-1]


def _token_pair_matches(a: str, b: str) -> bool:
    """One folded token pair: identical, or transliteration-equivalent.

    Equivalence is deliberately narrow — both tokens at least 4 chars,
    identical non-empty consonant skeletons, and edit distance <= 2 — so
    it bridges vowel residue (Karim≈Karami, Rahman≈Rahamana) without ever
    merging different names (Karim≁Rahim: skeletons krm vs rhm).
    """
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    sa, sb = _consonant_skeleton(a), _consonant_skeleton(b)
    if not sa or sa != sb:
        return False
    return _edit_distance(a, b) <= 2


def _token_lists_equivalent(ta: list[str], tb: list[str]) -> bool:
    """Same token count and every token pair matching, in order or —
    mirroring the sorted 'variant' rule — in sorted order."""
    if len(ta) != len(tb) or not ta:
        return False
    if all(_token_pair_matches(x, y) for x, y in zip(ta, tb)):
        return True
    return all(_token_pair_matches(x, y)
               for x, y in zip(sorted(ta), sorted(tb)))


def names_match(a: str, b: str) -> str:
    """'match' if canonical tokens are identical, 'variant' if they share
    every token but differ in order/spelling residue, else 'mismatch'.

    'variant' exists so a reviewer sees "same person, different
    transliteration" instead of a false discrepancy flag. Residue includes
    transliteration vowel differences: token lists that pair up under
    consonant-skeleton equivalence (see _token_pair_matches) are 'variant',
    never 'mismatch'.
    """
    ta, tb = normalize_name(a), normalize_name(b)
    if not ta or not tb:
        return "unknown"
    if ta == tb:
        return "match"
    if sorted(ta) == sorted(tb):
        return "variant"
    if _token_lists_equivalent(ta, tb):
        return "variant"
    return "mismatch"

"""Hjelpere for mer forutsigbare Treeview-kolonnebredder.

Maal:
- bedre standardbredder enn faste "120 over alt"
- rimelig autofit basert paa synlig innhold
- mer Excel-lignende oppfoersel med smalere tallkolonner og bredere tekstfelt
"""

from __future__ import annotations

from typing import Iterable


_NUMERIC_HINTS = ("belop", "beløp", "sum", "andel", "prosent", "ib", "ub", "endring", "antall")
_TEXT_HINTS = ("tekst", "beskrivelse", "melding", "comment")
_NAME_HINTS = ("navn", "regnskapslinje")
_DATE_HINTS = ("dato", "date", "periode")
_CODE_HINTS = ("konto", "bilag", "kode", "valuta")
_NARROW_CODE_HINTS = ("nr",)  # svært smale koder (regnskapslinje-nr etc.)


def _normalize_name(name: object) -> str:
    text = str(name or "").strip().lower()
    return (
        text.replace("ø", "o")
        .replace("æ", "ae")
        .replace("å", "a")
    )


def column_anchor(name: object) -> str:
    text = _normalize_name(name)
    if any(hint in text for hint in _NUMERIC_HINTS):
        return "e"
    return "w"


def default_column_width(name: object) -> int:
    text = _normalize_name(name)

    if not text:
        return 120
    if any(hint in text for hint in _TEXT_HINTS):
        return 320
    if any(hint in text for hint in _NAME_HINTS):
        return 240
    if any(hint in text for hint in _DATE_HINTS):
        return 95
    if any(hint in text for hint in _NUMERIC_HINTS):
        return 115
    if any(hint in text for hint in _CODE_HINTS):
        return 90
    if any(hint in text for hint in _NARROW_CODE_HINTS):
        return 55
    return 140


def _width_limits(name: object) -> tuple[int, int]:
    text = _normalize_name(name)
    if any(hint in text for hint in _TEXT_HINTS):
        return (140, 420)
    if any(hint in text for hint in _NAME_HINTS):
        return (140, 340)
    if any(hint in text for hint in _NUMERIC_HINTS):
        return (80, 160)
    if any(hint in text for hint in _DATE_HINTS):
        return (80, 120)
    if any(hint in text for hint in _CODE_HINTS):
        return (70, 180)
    if any(hint in text for hint in _NARROW_CODE_HINTS):
        return (40, 80)
    return (90, 260)


def suggest_column_width(name: object, values: Iterable[object], *, sample_limit: int = 200) -> int:
    """Anslå en praktisk Treeview-bredde fra kolonnenavn og eksempelverdier."""
    header = str(name or "").strip()
    max_len = len(header)

    for idx, value in enumerate(values):
        if idx >= sample_limit:
            break
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        max_len = max(max_len, min(len(text), 60))

    base = default_column_width(name)
    min_width, max_width = _width_limits(name)
    # 8px per tegn gir bedre estimat for Segoe UI / norske tallformater
    # med mellomrom som tusenskilletegn
    width = max(base, (max_len * 8) + 24)
    return max(min_width, min(max_width, int(width)))

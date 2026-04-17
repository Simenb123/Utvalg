"""Hjelpere for mer forutsigbare Treeview-kolonnebredder.

Maal:
- bedre standardbredder enn faste "120 over alt"
- rimelig autofit basert paa synlig innhold
- mer Excel-lignende oppfoersel med smalere tallkolonner og bredere tekstfelt
"""

from __future__ import annotations

from typing import Iterable


_AMOUNT_HINTS = ("belop", "beløp", "sum", "ib", "ub", "endring", "bevegelse")  # formaterte beløp
_NARROW_NUMERIC_HINTS = ("antall", "andel", "prosent")  # smale tall (teller, %)
_TEXT_HINTS = ("tekst", "beskrivelse", "melding", "comment")
_NAME_HINTS = ("navn", "regnskapslinje", "kontonavn")
_DATE_HINTS = ("dato", "date", "periode")
_CODE_HINTS = ("konto", "bilag", "kode", "valuta")
_NARROW_CODE_HINTS = ("nr",)  # svært smale koder (regnskapslinje-nr etc.)
# Combined for backward compat — anything that should right-align
_NUMERIC_HINTS = _AMOUNT_HINTS + _NARROW_NUMERIC_HINTS


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
    if any(hint in text for hint in _NARROW_CODE_HINTS):
        return 42
    if any(hint in text for hint in _NARROW_NUMERIC_HINTS):
        return 58
    if any(hint in text for hint in _TEXT_HINTS):
        return 320
    if any(hint in text for hint in _NAME_HINTS):
        return 260
    if any(hint in text for hint in _DATE_HINTS):
        return 88
    if any(hint in text for hint in _AMOUNT_HINTS):
        return 105
    if any(hint in text for hint in _CODE_HINTS):
        return 72
    return 120


def _width_limits(name: object) -> tuple[int, int]:
    text = _normalize_name(name)
    if any(hint in text for hint in _NARROW_CODE_HINTS):
        return (30, 60)
    if any(hint in text for hint in _NARROW_NUMERIC_HINTS):
        return (38, 90)
    if any(hint in text for hint in _TEXT_HINTS):
        return (120, 500)
    if any(hint in text for hint in _NAME_HINTS):
        return (120, 450)
    if any(hint in text for hint in _AMOUNT_HINTS):
        return (65, 150)
    if any(hint in text for hint in _DATE_HINTS):
        return (68, 110)
    if any(hint in text for hint in _CODE_HINTS):
        return (45, 150)
    return (60, 260)


def suggest_column_width(name: object, values: Iterable[object], *, sample_limit: int = 200) -> int:
    """Anslå en praktisk Treeview-bredde fra kolonnenavn og eksempelverdier.

    Når det finnes faktiske dataverdier brukes innholdsdrevet bredde
    (klippet mot kolonnetypen sine min/max-grenser). Standardbredden
    brukes bare som fallback når det ikke er noen data.
    """
    header = str(name or "").strip()
    max_len = len(header)
    has_data = False

    for idx, value in enumerate(values):
        if idx >= sample_limit:
            break
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        max_len = max(max_len, min(len(text), 60))
        has_data = True

    min_width, max_width = _width_limits(name)

    if not has_data:
        return default_column_width(name)

    # ~8px per tegn gir godt estimat for Segoe UI / norske tallformater
    content_width = (max_len * 8) + 20
    return max(min_width, min(max_width, int(content_width)))


def column_minwidth(name: object) -> int:
    """Returnér en fornuftig minwidth for en kolonne basert på type."""
    return _width_limits(name)[0]

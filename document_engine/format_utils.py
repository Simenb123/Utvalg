"""Shared amount and org.nr formatting helpers for document control.

Before this module, every consumer (engine, review dialog, app service,
profiles, batch service) had its own near-duplicate ``_parse_amount`` and
its own idea of how to reformat numbers. The results disagreed on
edge-cases like ``1,175.00`` (interpreted as ``1.175`` in app service but
``1175.0`` everywhere else), which caused the 940,00-vs-940.00 matching
bug and polluted learned profiles.

This module is the single source of truth:

``parse_amount_flexible(v)``
    Robust decimal parser that handles Norwegian (``1 175,00``,
    ``1.175,00``), international (``1,175.00``), currency-prefixed
    (``NOK 1,175.00``), and thousands-only forms (``1,175`` → 1175.0).

``normalize_amount_text(v)``
    Canonical ``"{:.2f}"`` string — the engine uses this as the stable
    internal representation for amount fields.

``amount_search_variants(v)``
    Full ordered list of text forms to probe a PDF for. Full decimal
    forms come before the bare integer so we never lock onto a substring
    match (``940`` inside ``9400``).

``amount_value_markers(v)``
    Subset used by profile hint inference — the shapes that can realistically
    appear as standalone tokens in PDF lines.

``normalize_orgnr(v)``, ``orgnr_matches(a, b)``
    Digits-only org.nr. normalisation, with a strict 9-digit equality
    check that never returns True for empty/short values.
"""

from __future__ import annotations

import re
from typing import Any

try:
    import pandas as pd  # optional — only used to recognise NaN amounts
except Exception:  # pragma: no cover
    pd = None  # type: ignore[assignment]


_NBSP = " "


def parse_amount_flexible(value: Any) -> float | None:
    """Parse *value* as a decimal number, tolerating mixed locale formats.

    Returns ``None`` for empty, non-numeric, or NaN input.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if pd is not None:
            try:
                if pd.isna(value):
                    return None
            except Exception:
                pass
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    text = text.replace(_NBSP, "")
    text = re.sub(r"[^\d,.\-]+", "", text)
    if not text:
        return None
    sign = -1.0 if text.startswith("-") else 1.0
    body = text.lstrip("-").replace("-", "")
    if not body:
        return None

    has_comma = "," in body
    has_dot = "." in body

    if has_comma and has_dot:
        # Both separators — the LAST one is the decimal.
        if body.rfind(",") > body.rfind("."):
            body = body.replace(".", "").replace(",", ".")
        else:
            body = body.replace(",", "")
    elif has_comma:
        if body.count(",") > 1:
            body = body.replace(",", "")
        else:
            left, _, right = body.partition(",")
            if (
                left.isdigit()
                and right.isdigit()
                and 1 <= len(left) <= 3
                and len(right) == 3
            ):
                body = body.replace(",", "")
            else:
                body = body.replace(",", ".")
    elif has_dot:
        if body.count(".") > 1:
            body = body.replace(".", "")
        else:
            left, _, right = body.partition(".")
            if (
                left.isdigit()
                and right.isdigit()
                and 1 <= len(left) <= 3
                and len(right) == 3
            ):
                body = body.replace(".", "")

    try:
        return sign * float(body)
    except Exception:
        return None


def normalize_amount_text(value: Any) -> str:
    """Return the canonical ``"{:.2f}"`` text for *value* (``""`` if unparseable)."""
    number = parse_amount_flexible(value)
    if number is None:
        return ""
    return f"{number:.2f}"


def amount_search_variants(value: Any) -> list[str]:
    """Return ordered, de-duplicated text variants to probe a PDF for *value*.

    The direct string form is always first. Full-decimal variants
    (``1 175,00``, ``1.175,00``, ``1,175.00``, ``1175.00``…) come before
    any bare-integer form, so PDF searches do not lock onto a substring
    match of a larger number.
    """
    text = str(value or "").strip()
    if not text:
        return []

    variants: list[str] = [text]
    seen = {text}

    def _add(v: str) -> None:
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            variants.append(v)

    num = parse_amount_flexible(text)
    if num is None:
        return variants

    abs_num = abs(num)
    sign = "-" if num < 0 else ""
    int_part = int(abs_num)
    frac_cents = round((abs_num - int_part) * 100)

    int_str = str(int_part)
    grouped_space = f"{int_part:,}".replace(",", " ")  # 1 175
    grouped_dot = f"{int_part:,}".replace(",", ".")    # 1.175
    grouped_comma = f"{int_part:,}"                    # 1,175

    if frac_cents == 0:
        frac_forms = ["00"]
        emit_int_only = True
    else:
        frac_forms = [f"{frac_cents:02d}"]
        emit_int_only = False

    for frac in frac_forms:
        _add(f"{sign}{int_str},{frac}")
        _add(f"{sign}{grouped_space},{frac}")
        if grouped_dot != int_str:
            _add(f"{sign}{grouped_dot},{frac}")
        if grouped_comma != int_str:
            _add(f"{sign}{grouped_comma}.{frac}")
        _add(f"{sign}{int_str}.{frac}")
        _add(f"{sign}{grouped_space}.{frac}")

    if emit_int_only:
        _add(f"{sign}{int_str}")
        _add(f"{sign}{grouped_space}")
        if grouped_dot != int_str:
            _add(f"{sign}{grouped_dot}")
            _add(f"{sign}{grouped_comma}")
    return variants


def amount_value_markers(value: Any) -> list[str]:
    """Return the shapes profile inference should look for on segment lines.

    Narrower than ``amount_search_variants`` — only the forms that can
    appear as a standalone token in a PDF line get emitted. Always
    includes the Norwegian-grouped full-decimal form first.
    """
    text = str(value or "").strip()
    if not text:
        return []

    markers: list[str] = []
    seen: set[str] = set()

    def _add(v: str) -> None:
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            markers.append(v)

    # Always include the raw value (NBSP collapsed to regular space).
    _add(text.replace(_NBSP, " "))

    num = parse_amount_flexible(text)
    if num is None:
        return markers

    # Emit a narrow set of likely-standalone tokens, full-decimal first.
    abs_num = abs(num)
    sign = "-" if num < 0 else ""
    int_part = int(abs_num)
    frac_cents = round((abs_num - int_part) * 100)
    int_str = str(int_part)
    grouped_space = f"{int_part:,}".replace(",", " ")
    grouped_dot = f"{int_part:,}".replace(",", ".")
    grouped_comma = f"{int_part:,}"

    if frac_cents == 0:
        frac = "00"
        have_fraction = False
    else:
        frac = f"{frac_cents:02d}"
        have_fraction = True

    # Norwegian full-decimal — the canonical form profiles already learn.
    _add(f"{sign}{grouped_space},{frac}")
    _add(f"{sign}{int_str},{frac}")
    if grouped_dot != int_str:
        _add(f"{sign}{grouped_dot},{frac}")
    # International full-decimal.
    if grouped_comma != int_str:
        _add(f"{sign}{grouped_comma}.{frac}")
    _add(f"{sign}{int_str}.{frac}")
    _add(f"{sign}{grouped_space}.{frac}")
    # Bare integer forms are only emitted when the amount really has no
    # fraction. We still put them LAST to keep full-decimal preference.
    if not have_fraction:
        _add(f"{sign}{grouped_space}")
        _add(f"{sign}{int_str}")
        if grouped_dot != int_str:
            _add(f"{sign}{grouped_dot}")
            _add(f"{sign}{grouped_comma}")
    return markers


def normalize_orgnr(value: Any) -> str:
    """Strip everything except digits. ``None``/empty → ``""``."""
    return re.sub(r"\D+", "", str(value or ""))


def orgnr_matches(left: Any, right: Any) -> bool:
    """Return True iff both sides normalise to the same 9-digit org.nr.

    Shorter or empty normalised values never match.
    """
    a = normalize_orgnr(left)
    b = normalize_orgnr(right)
    if len(a) != 9 or len(b) != 9:
        return False
    return a == b

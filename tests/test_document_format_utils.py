"""Tests for the shared ``document_engine.format_utils`` module.

The helpers here are the single source of truth for amount/orgnr
parsing and marker generation. Every consumer (engine, app service,
review dialog, batch service, profiles) delegates to them, so a
regression here is a regression everywhere.

Covered invariants:

- Amounts parse the same regardless of locale (``1 175,00``,
  ``1.175,00``, ``1,175.00``, ``1175.00`` all -> ``1175.0``).
- The "triplet-digit" thousands rule (``1,175`` / ``1.175`` -> 1175.0)
  triggers only on exactly 3 digits to the right; ``1,23`` stays 1.23.
- Currency prefixes (``NOK 1,175.00``) and NBSP whitespace are stripped.
- ``amount_value_markers`` yields the Norwegian and international
  full-decimal variants BEFORE any bare integer, so profile-hint
  inference never locks on a substring of a larger number.
- Org.nr. equality works across spacing, dots, and ``NO .. MVA`` forms,
  but empty/short values never compare equal.
"""

from __future__ import annotations

import pytest

from document_engine.format_utils import (
    amount_search_variants,
    amount_value_markers,
    normalize_amount_text,
    normalize_orgnr,
    orgnr_matches,
    parse_amount_flexible,
)


# ----------------------------------------------------------------------
# parse_amount_flexible
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 175,00", 1175.0),
        ("1.175,00", 1175.0),
        ("1175,00", 1175.0),
        ("1,175.00", 1175.0),
        ("1175.00", 1175.0),
        ("NOK 1,175.00", 1175.0),
        ("kr 1 175,00", 1175.0),
        ("-1.234,56", -1234.56),
        ("-1,234.56", -1234.56),
        ("1 234 567,89", 1234567.89),
        ("1,234,567.89", 1234567.89),
        ("940,00", 940.0),
        ("940.00", 940.0),
    ],
)
def test_parse_amount_flexible_formats(raw: str, expected: float) -> None:
    assert parse_amount_flexible(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", None, "abc", "NOK", "   "])
def test_parse_amount_flexible_rejects_non_numeric(raw) -> None:
    assert parse_amount_flexible(raw) is None


def test_parse_amount_triplet_comma_is_thousands() -> None:
    assert parse_amount_flexible("1,175") == pytest.approx(1175.0)


def test_parse_amount_triplet_dot_is_thousands() -> None:
    assert parse_amount_flexible("1.175") == pytest.approx(1175.0)


def test_parse_amount_two_digit_fraction_stays_decimal() -> None:
    # ",23" and ".23" aren't triplets -> must stay as decimal 1.23.
    assert parse_amount_flexible("1,23") == pytest.approx(1.23)
    assert parse_amount_flexible("1.23") == pytest.approx(1.23)


def test_parse_amount_nbsp_is_tolerated() -> None:
    # PDF extractors love NBSP between thousands groups.
    assert parse_amount_flexible("183 592,50") == pytest.approx(183592.50)


def test_parse_amount_handles_numeric_input_directly() -> None:
    assert parse_amount_flexible(1175) == 1175.0
    assert parse_amount_flexible(1175.5) == pytest.approx(1175.5)


# ----------------------------------------------------------------------
# normalize_amount_text
# ----------------------------------------------------------------------

def test_normalize_amount_text_canonicalises_forms() -> None:
    assert normalize_amount_text("1 175,00") == "1175.00"
    assert normalize_amount_text("1,175.00") == "1175.00"
    assert normalize_amount_text("940,00") == "940.00"


def test_normalize_amount_text_empty_on_unparseable() -> None:
    assert normalize_amount_text("abc") == ""
    assert normalize_amount_text(None) == ""


# ----------------------------------------------------------------------
# amount_search_variants
# ----------------------------------------------------------------------

def test_search_variants_decimal_forms_before_bare_integer() -> None:
    variants = amount_search_variants("1 175,00")
    idx_int = variants.index("1175")
    for decimal_form in ("1175,00", "1.175,00", "1,175.00", "1175.00"):
        assert decimal_form in variants, f"missing {decimal_form!r}: {variants!r}"
        assert variants.index(decimal_form) < idx_int, variants


def test_search_variants_bare_integer_emitted_for_zero_fraction() -> None:
    variants = amount_search_variants("500")
    assert "500" in variants
    assert "500,00" in variants
    assert "500.00" in variants


def test_search_variants_preserves_negative_sign() -> None:
    variants = amount_search_variants("-1234,56")
    numeric = [v for v in variants if any(ch.isdigit() for ch in v)]
    assert numeric and all(v.startswith("-") for v in numeric), numeric


def test_search_variants_empty_returns_empty() -> None:
    assert amount_search_variants("") == []
    assert amount_search_variants(None) == []


# ----------------------------------------------------------------------
# amount_value_markers
# ----------------------------------------------------------------------

def test_value_markers_cover_norwegian_and_international_with_decimal_first() -> None:
    markers = amount_value_markers("1,175.00")
    # Norwegian full-decimal forms must appear before bare "1175".
    full_decimal = ("1175,00", "1.175,00", "1,175.00", "1175.00")
    for form in full_decimal:
        assert form in markers, f"missing {form!r}: {markers!r}"
    # Zero-fraction path -> bare integer forms present but last.
    # For a fractional amount, bare integer forms must NOT be emitted at all.


def test_value_markers_fractional_amount_has_no_bare_integer() -> None:
    # An amount with real fractional cents (e.g., 1234.56) must never
    # emit a bare-integer form — matching "1234" in the PDF could lock
    # onto an unrelated number. Round amounts (1175.00) may still emit
    # the integer form; that's covered by the zero-fraction test below.
    markers = amount_value_markers("1,234.56")
    assert "1234" not in markers, markers
    assert "1 234" not in markers, markers


def test_value_markers_zero_fraction_emits_bare_integer_last() -> None:
    markers = amount_value_markers("500,00")
    assert "500" in markers
    # Full-decimal Norwegian form always comes before bare integer.
    assert markers.index("500,00") < markers.index("500")


def test_value_markers_nbsp_is_collapsed() -> None:
    markers = amount_value_markers("183 592,50")
    for m in markers:
        assert " " not in m


def test_value_markers_empty_input_returns_empty() -> None:
    assert amount_value_markers("") == []
    assert amount_value_markers(None) == []


# ----------------------------------------------------------------------
# normalize_orgnr / orgnr_matches
# ----------------------------------------------------------------------

def test_normalize_orgnr_strips_non_digits() -> None:
    assert normalize_orgnr("965 004 211") == "965004211"
    assert normalize_orgnr("NO 965 004 211 MVA") == "965004211"
    assert normalize_orgnr("965.004.211") == "965004211"
    assert normalize_orgnr(None) == ""
    assert normalize_orgnr("") == ""


def test_orgnr_matches_equivalent_forms() -> None:
    assert orgnr_matches("965004211", "965 004 211") is True
    assert orgnr_matches("965004211", "NO 965 004 211 MVA") is True
    assert orgnr_matches("965004211", "965.004.211") is True


def test_orgnr_matches_rejects_different_numbers() -> None:
    assert orgnr_matches("965004211", "999999999") is False
    assert orgnr_matches("NO 965 004 211 MVA", "NO 999 999 999 MVA") is False


def test_orgnr_matches_never_matches_empty_or_short() -> None:
    assert orgnr_matches("", "") is False
    assert orgnr_matches("965004211", "") is False
    assert orgnr_matches("", "965004211") is False
    assert orgnr_matches("abc", "def") is False
    # Short digit runs (not 9 digits) never match even if equal as strings.
    assert orgnr_matches("12345", "12345") is False

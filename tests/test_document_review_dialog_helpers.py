"""Tests for format-agnostic helpers in document_control_review_dialog.

These cover the three invariants added for robust amount/orgnr matching:
1. ``_parse_amount`` handles Norwegian and international formats, plus
   currency prefixes.
2. ``_field_matches`` treats formatted equivalents as the same value.
3. ``_pdf_search_variants`` emits the alternative text forms that
   ``_search_pdf_for_field`` cycles through when a literal search yields
   no hits.
"""

from __future__ import annotations

import pytest

from src.shared.document_control.review_dialog import (
    _field_matches,
    _parse_amount,
    _pdf_search_variants,
)


# ----------------------------------------------------------------------
# _parse_amount
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 175,00", 1175.0),         # Norwegian, space thousands
        ("1.175,00", 1175.0),         # Norwegian, dot thousands
        ("1175,00", 1175.0),          # Norwegian, no thousands
        ("1,175.00", 1175.0),         # International, comma thousands
        ("1175.00", 1175.0),          # International, no thousands
        ("NOK 1,175.00", 1175.0),     # Currency prefix
        ("kr 1 175,00", 1175.0),      # Norwegian currency prefix
        ("-1.234,56", -1234.56),      # Negative Norwegian
        ("-1,234.56", -1234.56),      # Negative international
        ("1 234 567,89", 1234567.89), # Big Norwegian
        ("1,234,567.89", 1234567.89), # Big international
    ],
)
def test_parse_amount_formats(raw: str, expected: float) -> None:
    got = _parse_amount(raw)
    assert got == pytest.approx(expected), f"{raw!r}: expected {expected}, got {got}"


@pytest.mark.parametrize("raw", ["", None, "abc", "NOK"])
def test_parse_amount_returns_none_for_non_numeric(raw) -> None:
    assert _parse_amount(raw) is None


# ----------------------------------------------------------------------
# _field_matches — amount equivalence across formats
# ----------------------------------------------------------------------

def test_field_matches_amount_norwegian_vs_international() -> None:
    assert _field_matches("total_amount", "1 175,00", "1,175.00") is True


def test_field_matches_amount_subtotal_and_vat() -> None:
    assert _field_matches("subtotal_amount", "940,00", "940.00") is True
    assert _field_matches("vat_amount", "235,00", "235.00") is True


def test_field_matches_amount_tolerance_boundary() -> None:
    # Max 1 kr or 0.1% — 500 vs 500.99 within tolerance, 500 vs 502 is not.
    assert _field_matches("total_amount", "500,00", "500,99") is True
    assert _field_matches("total_amount", "500,00", "502,00") is False


def test_field_matches_amount_rejects_real_mismatch() -> None:
    # Negative control from the plan: 1,175.00 ≠ 1 275,00
    assert _field_matches("total_amount", "1,175.00", "1 275,00") is False


# ----------------------------------------------------------------------
# _field_matches — orgnr equivalence across spacing / prefix / suffix
# ----------------------------------------------------------------------

def test_field_matches_orgnr_digits_only_vs_spaced() -> None:
    assert _field_matches("supplier_orgnr", "965004211", "965 004 211") is True


def test_field_matches_orgnr_digits_only_vs_NO_MVA_form() -> None:
    assert _field_matches("supplier_orgnr", "965004211", "NO 965 004 211 MVA") is True


def test_field_matches_orgnr_dotted() -> None:
    assert _field_matches("supplier_orgnr", "965004211", "965.004.211") is True


def test_field_matches_orgnr_rejects_different_numbers() -> None:
    assert _field_matches("supplier_orgnr", "965004211", "NO 999 999 999 MVA") is False


# ----------------------------------------------------------------------
# _pdf_search_variants
# ----------------------------------------------------------------------

def test_search_variants_amount_covers_norwegian_and_international() -> None:
    variants = _pdf_search_variants("total_amount", "1 175,00")
    # Direct value always first
    assert variants[0] == "1 175,00"
    # Must include the formats users typically see in PDFs
    for expected in ("1175,00", "1.175,00", "1 175.00", "1,175.00", "1175.00"):
        assert expected in variants, f"missing variant {expected!r}; got {variants!r}"


def test_search_variants_amount_no_fraction_emits_both_styles() -> None:
    variants = _pdf_search_variants("total_amount", "500")
    # A bare "500" should also be searchable as "500,00" and "500.00"
    assert "500" in variants
    assert "500,00" in variants
    assert "500.00" in variants


def test_search_variants_amount_preserves_sign() -> None:
    variants = _pdf_search_variants("total_amount", "-1234,56")
    # Every amount variant must carry the leading minus
    numeric_variants = [v for v in variants if any(ch.isdigit() for ch in v)]
    assert numeric_variants, variants
    assert all(v.startswith("-") for v in numeric_variants), numeric_variants


def test_search_variants_orgnr_covers_NO_and_MVA_forms() -> None:
    variants = _pdf_search_variants("supplier_orgnr", "965004211")
    # Direct value must come first so the common case stays fast
    assert variants[0] == "965004211"
    for expected in ("965 004 211", "NO 965 004 211", "NO 965 004 211 MVA"):
        assert expected in variants, f"missing variant {expected!r}; got {variants!r}"


def test_search_variants_orgnr_falls_back_for_non_nine_digits() -> None:
    # Edge case: bogus input (too few digits). Helper must not crash, and
    # must always include at least the original and digits-only form.
    variants = _pdf_search_variants("supplier_orgnr", "123-45")
    assert "123-45" in variants
    assert "12345" in variants


def test_search_variants_text_field_returns_single_variant() -> None:
    # Non-amount, non-orgnr fields should not try to reformat
    variants = _pdf_search_variants("description", "Månedsleie juni")
    assert variants == ["Månedsleie juni"]


def test_search_variants_empty_value_returns_empty_list() -> None:
    assert _pdf_search_variants("total_amount", "") == []
    assert _pdf_search_variants("supplier_orgnr", "   ") == []


# ----------------------------------------------------------------------
# Format-bug regressions: decimal forms must outrank bare integers, and
# the parser must treat "1,175"/"1.175" as thousands-grouped 1175.0.
# ----------------------------------------------------------------------

def test_field_matches_subtotal_amount_norwegian_vs_international() -> None:
    # Explicit regression: HB=940,00 matched against PDF=940.00.
    assert _field_matches("subtotal_amount", "940,00", "940.00") is True


def test_search_variants_amount_full_decimal_before_bare_integer() -> None:
    # "940.00" must come before "940" so the PDF search does not lock
    # onto a substring match (e.g. "940" inside "9400") when the real
    # value is "940.00".
    variants = _pdf_search_variants("subtotal_amount", "940,00")
    assert "940.00" in variants and "940" in variants
    assert variants.index("940.00") < variants.index("940"), variants


def test_search_variants_amount_all_decimal_forms_before_bare_integer() -> None:
    # Every full-decimal formatting variant must precede the bare
    # integer form for the same amount.
    variants = _pdf_search_variants("total_amount", "1 175,00")
    idx_int = variants.index("1175")
    for decimal_form in ("1175,00", "1.175,00", "1,175.00", "1175.00"):
        assert decimal_form in variants, f"missing {decimal_form!r}: {variants!r}"
        assert variants.index(decimal_form) < idx_int, (
            f"{decimal_form!r} should come before '1175' — got {variants!r}"
        )


def test_parse_amount_treats_comma_triplet_as_thousands() -> None:
    # "1,175" with exactly 3 digits after the comma is a thousands
    # grouping, not the decimal 1.175.
    assert _parse_amount("1,175") == pytest.approx(1175.0)


def test_parse_amount_treats_dot_triplet_as_thousands() -> None:
    assert _parse_amount("1.175") == pytest.approx(1175.0)


def test_parse_amount_does_not_misread_two_digit_fractions() -> None:
    # Guard the new rule: ",23" and ".23" are NOT 3-digit triplets,
    # so they must stay decimal.
    assert _parse_amount("1,23") == pytest.approx(1.23)
    assert _parse_amount("1.23") == pytest.approx(1.23)


# ----------------------------------------------------------------------
# _is_dirty — auto-save dirty-check logic
# ----------------------------------------------------------------------
#
# The method is bound to the Tkinter dialog, so we exercise it through
# a minimal fake-instance that carries the same state dicts / StringVars
# the real dialog uses. The method only reads state; no window required.

from src.shared.document_control.review_dialog import DocumentControlReviewDialog, FIELD_DEFS


class _FakeStringVar:
    def __init__(self, value: str = "") -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value


class _FakeText:
    def __init__(self, value: str = "") -> None:
        self._value = value

    def get(self, _start: str, _end: str) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value


def _make_dialog_stub(
    *,
    saved_fields=None,
    notes="",
    saved_notes="",
    saved_evidence=None,
    gui_values=None,
    gui_notes="",
    field_evidence=None,
    edited_bilag=None,
) -> DocumentControlReviewDialog:
    """Build a minimal stand-in for DocumentControlReviewDialog with just
    the attributes ``_is_dirty`` reads."""
    stub = DocumentControlReviewDialog.__new__(DocumentControlReviewDialog)
    stub._current_index = 0
    stub._results = [object()]   # one placeholder bilag
    stub._saved_fields = [saved_fields]
    stub._notes_state = [saved_notes]
    stub._saved_evidence = [saved_evidence]
    stub._field_evidence = dict(field_evidence or {})
    stub._edited_bilag = set(edited_bilag or [])
    stub.pdf_vars = {
        key: _FakeStringVar((gui_values or {}).get(key, ""))
        for key, _ in FIELD_DEFS
    }
    stub._txt_notes = _FakeText(gui_notes)
    return stub


def test_is_dirty_never_saved_without_user_edit_returns_false() -> None:
    """A fresh bilag with extraction-filled values but no user action
    must not be considered dirty — auto-save shouldn't fire on idle
    navigation."""
    stub = _make_dialog_stub(
        saved_fields=None,
        gui_values={"invoice_number": "INV-1"},  # filled by auto_analyse
    )
    assert stub._is_dirty() is False


def test_is_dirty_never_saved_with_user_edit_returns_true() -> None:
    """Same scenario, but the user has touched the bilag — auto-save
    should fire to persist their work."""
    stub = _make_dialog_stub(
        saved_fields=None,
        gui_values={"invoice_number": "INV-1"},
        edited_bilag=[0],
    )
    assert stub._is_dirty() is True


def test_is_dirty_saved_with_identical_gui_returns_false() -> None:
    """GUI matches disk byte-for-byte → not dirty."""
    fields = {"invoice_number": "INV-1", "total_amount": "1 000,00"}
    stub = _make_dialog_stub(
        saved_fields=fields,
        gui_values=fields,
    )
    assert stub._is_dirty() is False


def test_is_dirty_saved_with_differing_value_returns_true() -> None:
    stub = _make_dialog_stub(
        saved_fields={"invoice_number": "INV-1"},
        gui_values={"invoice_number": "INV-2"},
    )
    assert stub._is_dirty() is True


def test_is_dirty_saved_with_changed_notes_returns_true() -> None:
    stub = _make_dialog_stub(
        saved_fields={"invoice_number": "INV-1"},
        gui_values={"invoice_number": "INV-1"},
        saved_notes="old note",
        gui_notes="new note",
    )
    assert stub._is_dirty() is True


def test_is_dirty_saved_with_changed_bbox_returns_true() -> None:
    """User cycled to a different PDF hit — the evidence bbox differs
    from what was saved, so navigating away MUST persist the new pick."""
    from document_engine.models import FieldEvidence

    saved_ev = {
        "total_amount": {"page": 2, "bbox": [100.0, 100.0, 150.0, 110.0]},
    }
    current_ev = {
        "total_amount": FieldEvidence(
            field_name="total_amount",
            normalized_value="1000.00",
            page=2,
            bbox=(200.0, 200.0, 250.0, 210.0),  # different bbox
        ),
    }
    stub = _make_dialog_stub(
        saved_fields={"total_amount": "1000.00"},
        gui_values={"total_amount": "1000.00"},
        saved_evidence=saved_ev,
        field_evidence=current_ev,
    )
    assert stub._is_dirty() is True

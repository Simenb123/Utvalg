"""Tests for joint amount extraction + self-consistency selection.

Covers Plan B ("940,00 vs 940.00 i faktisk beløpsuttrekk"):
    * Arkitektbedriftene-style invoice with punktum-desimal (940.00).
    * Percent-tail values (``25.00%``) must never become ``vat_amount``.
    * Norwegian-format parity (``940,00``) still works.
    * Hint regression: a hint locked onto a percentage rate cannot win
      against a self-consistent combination.
    * Zero-VAT invoice treated as consistent.
    * Wrong independent picks overridden by joint selection.
"""
from __future__ import annotations

import document_engine.engine as engine


def test_arkitektbedriftene_punktum_decimal_extracts_consistent_triple() -> None:
    """English/punktum-formatted invoice still parses and stays consistent.

    This is the Arkitektbedriftene-style body that previously tripped up the
    extractor: MVA section carries the rate (``25.00%``) right next to a
    base amount, which ranked higher than the actual VAT amount.
    """
    text = "\n".join(
        [
            "Faktura nr: 7091",
            "Fakturadato: 10.02.2026",
            "Beløp eksl. MVA 940.00",
            "MVA 25.00% av 940.00",
            "MVA beløp 235.00",
            "Å betale NOK 1,175.00",
        ]
    )

    facts, evidence = engine.extract_invoice_fields_from_text(text)

    assert facts.subtotal_amount == "940.00"
    assert facts.vat_amount == "235.00"
    assert facts.total_amount == "1175.00"
    assert engine._amounts_self_consistent(evidence) is True


def test_percent_tail_never_becomes_vat_amount() -> None:
    """``25.00%`` is a rate, not an amount — must not surface as ``vat_amount``.

    Layout mimics invoices where the rate line sits between the subtotal and
    the actual VAT-amount line. The percent-tail filter must drop the
    ``25.00`` capture so the later ``200,00`` survives in the candidate pool
    and joint selection picks the consistent triple ``(800, 200, 1000)``.
    """
    text = "\n".join(
        [
            "Beløp eksl. MVA 800,00",
            "MVA 25.00% av 800,00",
            "MVA 200,00",
            "Total 1000,00",
        ]
    )

    _, evidence = engine.extract_invoice_fields_from_text(text)

    vat = evidence.get("vat_amount")
    assert vat is not None
    assert vat.normalized_value == "200.00"
    assert vat.normalized_value != "25.00"


def test_norwegian_format_parity_still_works() -> None:
    """``940,00`` (comma-desimal) continues to parse after punktum support."""
    text = "\n".join(
        [
            "Netto: 940,00",
            "MVA: 235,00",
            "Total: 1 175,00",
        ]
    )

    facts, _ = engine.extract_invoice_fields_from_text(text)

    assert facts.subtotal_amount == "940.00"
    assert facts.vat_amount == "235.00"
    assert facts.total_amount == "1175.00"


def test_zero_vat_invoice_is_self_consistent() -> None:
    """Subtotal + 0 MVA = total should be treated as consistent."""
    text = "\n".join(
        [
            "Sum eks. MVA 10980.00",
            "MVA 0.00",
            "Total 10980.00",
        ]
    )

    facts, evidence = engine.extract_invoice_fields_from_text(text)

    assert facts.subtotal_amount == "10980.00"
    assert facts.vat_amount == "0.00"
    assert facts.total_amount == "10980.00"
    assert engine._amounts_self_consistent(evidence) is True


def test_hint_locked_onto_percentage_loses_to_consistent_combo() -> None:
    """Profile hints pointing at a rate (``25.00%``) cannot override a
    combination that satisfies ``subtotal + vat ≈ total``.

    The percentage-rejection filter in :func:`_collect_ranked_candidates`
    drops the ``25.00`` candidate before ranking, so even with a heavy hint
    boost for that label, the consistent ``(940, 235, 1175)`` triple wins.
    """
    text = "\n".join(
        [
            "Beløp eksl. MVA 940.00",
            "MVA 25.00% av 940.00",
            "MVA beløp 235.00",
            "Å betale NOK 1,175.00",
        ]
    )
    hints = {
        "vat_amount": [
            {"label": "MVA 25.00% av", "page": 1, "count": 5},
        ],
    }

    facts, evidence = engine.extract_invoice_fields_from_text_with_hints(
        text, profile_hints=hints,
    )

    assert facts.vat_amount == "235.00"
    assert facts.subtotal_amount == "940.00"
    assert facts.total_amount == "1175.00"
    assert evidence["vat_amount"].normalized_value != "25.00"


def test_joint_selection_overrides_wrong_independent_pick() -> None:
    """Independent per-field picks land on an inconsistent combo; joint
    selection falls back to the consistent triple and flags the swap via
    ``metadata["selected_by"] = "joint_amount_ranking"``.
    """
    text = "\n".join(
        [
            "Sum eks. MVA 500,00",
            "Netto 940,00",
            "MVA 235,00",
            "Total 1175,00",
        ]
    )

    facts, evidence = engine.extract_invoice_fields_from_text(text)

    assert facts.subtotal_amount == "940.00"
    assert facts.vat_amount == "235.00"
    assert facts.total_amount == "1175.00"
    assert engine._amounts_self_consistent(evidence) is True
    for fname in ("subtotal_amount", "vat_amount", "total_amount"):
        assert evidence[fname].metadata.get("selected_by") == "joint_amount_ranking", fname


def test_match_is_percentage_helper_flags_rate_tails() -> None:
    """Unit-level sanity check of :func:`_match_is_percentage`."""
    import re

    pattern = re.compile(r"(\d+\.\d+)")
    percent_text = "MVA 25.00% av 940.00"
    m1 = pattern.search(percent_text)
    assert m1 is not None
    assert engine._match_is_percentage(percent_text, m1) is True

    plain_text = "Beløp 940.00 NOK"
    m2 = pattern.search(plain_text)
    assert m2 is not None
    assert engine._match_is_percentage(plain_text, m2) is False

    spaced_percent = "Rate 25 % bonus"
    m3 = re.compile(r"(\d+)").search(spaced_percent)
    assert m3 is not None
    assert engine._match_is_percentage(spaced_percent, m3) is True

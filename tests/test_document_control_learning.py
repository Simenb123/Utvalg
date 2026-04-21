from __future__ import annotations

from document_control_learning import (
    apply_supplier_profile,
    build_supplier_profile,
    match_supplier_profile,
)
from document_engine.engine import TextSegment
from document_engine.profiles import _find_hint_in_segments, infer_field_hints


def test_build_supplier_profile_collects_vendor_specific_hints() -> None:
    fields = {
        "supplier_name": "Eksempel Partner AS",
        "supplier_orgnr": "987654321",
        "invoice_number": "INV-2025-001",
        "due_date": "01.03.2025",
        "total_amount": "995.00",
        "currency": "NOK",
    }
    raw_text = "\n".join(
        [
            "Eksempel Partner AS",
            "Org.nr: 987654321",
            "Vår referanse: INV-2025-001",
            "Forfall: 01.03.2025",
            "Til betaling: 995,00 NOK",
        ]
    )

    profile = build_supplier_profile(fields, raw_text)

    assert profile is not None
    assert profile["profile_key"] == "orgnr:987654321"
    assert profile["schema_version"] == 1
    assert profile["field_hints"]["invoice_number"][0]["label"] == "vår referanse"
    assert profile["field_hints"]["due_date"][0]["label"] == "forfall"
    assert profile["field_hints"]["total_amount"][0]["label"] == "til betaling"


def test_apply_supplier_profile_reuses_learned_hints_on_new_document() -> None:
    fields = {
        "supplier_name": "Eksempel Partner AS",
        "supplier_orgnr": "987654321",
        "invoice_number": "INV-2025-001",
        "due_date": "01.03.2025",
        "total_amount": "995.00",
        "currency": "NOK",
    }
    raw_text = "\n".join(
        [
            "Eksempel Partner AS",
            "Vår referanse: INV-2025-001",
            "Forfall: 01.03.2025",
            "Til betaling: 995,00 NOK",
        ]
    )
    profile = build_supplier_profile(fields, raw_text)

    extracted = apply_supplier_profile(
        profile or {},
        "\n".join(
            [
                "Eksempel Partner AS",
                "Vår referanse: INV-2025-002",
                "Forfall: 15.03.2025",
                "Til betaling: 1 250,00 NOK",
            ]
        ),
    )

    assert extracted["supplier_name"] == "Eksempel Partner AS"
    assert extracted["supplier_orgnr"] == "987654321"
    assert extracted["invoice_number"] == "INV-2025-002"
    assert extracted["due_date"] == "15.03.2025"
    assert extracted["total_amount"] == "1 250,00 NOK"


def test_match_supplier_profile_can_match_on_alias_in_raw_text() -> None:
    profile = {
        "profile_key": "orgnr:987654321",
        "supplier_name": "Eksempel Partner AS",
        "supplier_orgnr": "987654321",
        "aliases": ["eksempel partner as", "987654321"],
        "sample_count": 2,
        "field_hints": {},
        "static_fields": {"supplier_name": "Eksempel Partner AS"},
    }

    matched, score = match_supplier_profile(
        {"orgnr:987654321": profile},
        fields={},
        raw_text="Leverandør Eksempel Partner AS\nTil betaling: 250,00 NOK",
    )

    assert matched is not None
    assert matched["profile_key"] == "orgnr:987654321"
    assert matched["supplier_name"] == "Eksempel Partner AS"
    assert score >= 60.0


def test_infer_field_hints_handles_nbsp_in_amount_values() -> None:
    # Regression: PDF extraction produces NBSP (\u00a0) in grouped amounts
    # like "183\xa0592,50". `_candidate_lines` collapses NBSP → space, but
    # `_value_markers` used to preserve NBSP, so markers never matched the
    # normalized segment lines. Result: 23 Brage saves, 0 amount hints.
    segments = [
        TextSegment(
            text="Beløp ekskl. mva 183\u00a0592,50 NOK",
            source="pdf_text_pdfplumber",
            page=2,
            bbox=(0.0, 400.0, 500.0, 440.0),
        ),
    ]
    hints = infer_field_hints(
        raw_text="",
        fields={"subtotal_amount": "183\u00a0592,50"},
        segments=segments,
        field_evidence={"subtotal_amount": {"page": 2, "bbox": (388.0, 429.0, 438.0, 438.0)}},
    )
    assert "subtotal_amount" in hints
    assert hints["subtotal_amount"][0]["label"] == "beløp ekskl mva"
    assert hints["subtotal_amount"][0]["page"] == 2


def test_value_markers_amount_nbsp_matches_normalized_segment_line() -> None:
    # Direct check: `_find_hint_in_segments` must find the value even when
    # the stored value keeps the NBSP but the segment text has been
    # whitespace-collapsed.
    seg = TextSegment(
        text="Totalt 229\u00a0490,63 NOK",
        source="pdf_text",
        page=2,
        bbox=(0.0, 0.0, 1.0, 1.0),
    )
    hint = _find_hint_in_segments(
        [seg], "total_amount", "229\u00a0490,63",
        evidence_page=2, evidence_bbox=None,
    )
    assert hint is not None
    assert hint["label"] == "totalt"

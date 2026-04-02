from __future__ import annotations

from document_control_learning import (
    apply_supplier_profile,
    build_supplier_profile,
    match_supplier_profile,
)


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

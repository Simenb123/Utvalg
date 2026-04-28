from __future__ import annotations

import json
from pathlib import Path

import src.shared.document_control.store as document_control_store


def test_save_and_load_document_record_roundtrip(tmp_path: Path, monkeypatch) -> None:
    store_file = tmp_path / "document_control_store.json"
    monkeypatch.setattr(document_control_store, "_store_path", lambda: store_file)

    saved = document_control_store.save_document_record(
        "Demo AS",
        "2025",
        "1001",
        {
            "file_path": str(tmp_path / "invoice.pdf"),
            "fields": {"invoice_number": "INV-2025-001"},
            "field_evidence": {
                "invoice_number": {
                    "normalized_value": "INV-2025-001",
                    "raw_value": "INV-2025-001",
                    "source": "pdf_text",
                    "confidence": 0.93,
                    "page": 1,
                    "bbox": [11.0, 22.5, 140.0, 36.0],
                }
            },
            "validation_messages": ["match"],
            "notes": "ok",
        },
    )

    loaded = document_control_store.load_document_record("Demo AS", "2025", "1001")

    assert saved["bilag"] == "1001"
    assert loaded is not None
    assert loaded["file_path"].endswith("invoice.pdf")
    assert loaded["fields"]["invoice_number"] == "INV-2025-001"
    assert loaded["field_evidence"]["invoice_number"]["page"] == 1
    assert loaded["field_evidence"]["invoice_number"]["bbox"] == [11.0, 22.5, 140.0, 36.0]
    assert loaded["notes"] == "ok"


def test_upsert_supplier_profile_from_document_persists_profile(tmp_path: Path, monkeypatch) -> None:
    store_file = tmp_path / "document_control_store.json"
    monkeypatch.setattr(document_control_store, "_store_path", lambda: store_file)

    profile = document_control_store.upsert_supplier_profile_from_document(
        {
            "supplier_name": "Eksempel Partner AS",
            "supplier_orgnr": "987654321",
            "invoice_number": "INV-2025-001",
            "total_amount": "995.00",
        },
        "\n".join(
            [
                "Eksempel Partner AS",
                "Vår referanse: INV-2025-001",
                "Til betaling: 995,00 NOK",
            ]
        ),
    )

    profiles = document_control_store.load_supplier_profiles()

    assert profile is not None
    assert profile["profile_key"] == "orgnr:987654321"
    assert "orgnr:987654321" in profiles
    assert profiles["orgnr:987654321"]["field_hints"]["invoice_number"][0]["label"] == "vår referanse"


def test_export_and_import_supplier_profiles_keep_schema_version(tmp_path: Path, monkeypatch) -> None:
    store_file = tmp_path / "document_control_store.json"
    export_file = tmp_path / "profiles.json"
    monkeypatch.setattr(document_control_store, "_store_path", lambda: store_file)

    document_control_store.upsert_supplier_profile_from_document(
        {
            "supplier_name": "Eksempel Partner AS",
            "supplier_orgnr": "987654321",
            "invoice_number": "INV-2025-001",
            "total_amount": "995.00",
        },
        "\n".join(
            [
                "Eksempel Partner AS",
                "Vår referanse: INV-2025-001",
                "Til betaling: 995,00 NOK",
            ]
        ),
    )

    exported = document_control_store.export_supplier_profiles(export_file)
    payload = json.loads(export_file.read_text(encoding="utf-8"))

    assert exported["profile_count"] == 1
    assert payload["schema_version"] == 1
    assert "orgnr:987654321" in payload["profiles"]

    imported = document_control_store.import_supplier_profiles(export_file)
    assert imported["profile_count"] == 1

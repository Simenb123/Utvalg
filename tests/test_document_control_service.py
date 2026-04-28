from __future__ import annotations

from pathlib import Path

import pandas as pd

import src.shared.document_control.app_service as app_service
import src.shared.document_control.service as service
import document_engine.engine as engine
from document_engine.models import SupplierProfile


def test_extract_invoice_fields_from_text_reads_key_invoice_fields() -> None:
    text = """
    Leverandør: Eksempel Partner AS
    Org.nr: 987654321
    Fakturanr: INV-2025-001
    Fakturadato: 15.02.2025
    Forfallsdato: 01.03.2025
    Netto: 1 000,00
    MVA: 250,00
    Beløp å betale: 1 250,00 NOK
    """

    fields, confidence = service.extract_invoice_fields_from_text(text)

    assert fields["supplier_name"] == "Eksempel Partner AS"
    assert fields["supplier_orgnr"] == "987654321"
    assert fields["invoice_number"] == "INV-2025-001"
    assert fields["invoice_date"] == "15.02.2025"
    assert fields["due_date"] == "01.03.2025"
    assert fields["subtotal_amount"] == "1000.00"
    assert fields["vat_amount"] == "250.00"
    assert fields["total_amount"] == "1250.00"
    assert fields["currency"] == "NOK"
    assert confidence["total_amount"] >= 0.8


def test_extract_invoice_fields_from_xml_reads_ubl_invoice() -> None:
    xml_text = """
    <Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
             xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
             xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
      <cbc:ID>2025-77</cbc:ID>
      <cbc:IssueDate>2025-02-15</cbc:IssueDate>
      <cbc:DueDate>2025-03-01</cbc:DueDate>
      <cbc:DocumentCurrencyCode>NOK</cbc:DocumentCurrencyCode>
      <cac:AccountingSupplierParty>
        <cac:Party>
          <cac:PartyLegalEntity>
            <cbc:RegistrationName>Eksempel Partner AS</cbc:RegistrationName>
            <cbc:CompanyID>987654321</cbc:CompanyID>
          </cac:PartyLegalEntity>
        </cac:Party>
      </cac:AccountingSupplierParty>
      <cac:LegalMonetaryTotal>
        <cbc:TaxExclusiveAmount>1000.00</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount>1250.00</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount>1250.00</cbc:PayableAmount>
      </cac:LegalMonetaryTotal>
      <cac:TaxTotal>
        <cbc:TaxAmount>250.00</cbc:TaxAmount>
      </cac:TaxTotal>
    </Invoice>
    """

    fields, confidence = service.extract_invoice_fields_from_xml(xml_text)

    assert fields == {
        "invoice_number": "2025-77",
        "invoice_date": "15.02.2025",
        "due_date": "01.03.2025",
        "currency": "NOK",
        "supplier_name": "Eksempel Partner AS",
        "supplier_orgnr": "987654321",
        "subtotal_amount": "1000.00",
        "total_amount": "1250.00",
        "vat_amount": "250.00",
        "description": "",
        "period": "",
    }
    assert confidence["total_amount"] == 0.99


def test_analyze_document_reads_text_file_and_builds_validation_messages(tmp_path: Path) -> None:
    file_path = tmp_path / "invoice.txt"
    file_path.write_text(
        "\n".join(
            [
                "Leverandør: Eksempel Partner AS",
                "Fakturanr: INV-2025-001",
                "Fakturadato: 15.02.2025",
                "Beløp å betale: 1 250,00 NOK",
            ]
        ),
        encoding="utf-8",
    )

    bilag_rows = pd.DataFrame(
        {
            "Bilag": [1001, 1001],
            "Dato": ["15.02.2025", "15.02.2025"],
            "Tekst": ["INV-2025-001 Eksempel Partner AS", "MVA faktura INV-2025-001"],
            "Beløp": [1250.0, 250.0],
        }
    )

    analysis = service.analyze_document(file_path, bilag_rows=bilag_rows)

    assert analysis.source == "text"
    assert analysis.fields["invoice_number"] == "INV-2025-001"
    assert analysis.fields["total_amount"] == "1250.00"
    assert analysis.metadata["text_char_count"] > 0
    assert analysis.field_evidence["invoice_number"].validated_against_voucher is True
    assert any("Fakturanummer INV-2025-001" in message for message in analysis.validation_messages)
    assert any("Totalbeløp 1250.00 matcher minst én regnskapslinje." in message for message in analysis.validation_messages)


def test_build_validation_messages_handles_missing_bilag_context() -> None:
    messages = service.build_validation_messages({"invoice_number": "INV-1"}, None)
    assert messages == ["Ingen bilagsrader tilgjengelig for kontroll."]


def test_normalize_bilag_key_removes_excel_suffix() -> None:
    assert service.normalize_bilag_key(1001.0) == "1001"


def test_extract_text_from_file_prefers_best_pdf_candidate(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(engine, "_count_pdf_pages", lambda _path: 2)
    monkeypatch.setattr(engine, "_extract_pdf_text_with_pypdf", lambda _path: ("Kort tekst", [engine.TextSegment(text="Kort tekst", source="pdf_text_pypdf", page=1)]))
    monkeypatch.setattr(engine, "_extract_pdf_text_with_pdfplumber", lambda _path: ("", []))
    monkeypatch.setattr(
        engine,
        "_extract_pdf_text_with_fitz_blocks",
        lambda _path: (
            "\n".join(
                [
                    "Eksempel Partner AS",
                    "Fakturanr: INV-2025-002",
                    "Fakturadato: 15.02.2025",
                    "Beløp å betale: 1 250,00 NOK",
                ]
            ),
            [
                engine.TextSegment(text="Eksempel Partner AS", source="pdf_text_fitz_blocks", page=1, bbox=(1.0, 1.0, 10.0, 10.0)),
                engine.TextSegment(text="Fakturanr: INV-2025-002", source="pdf_text_fitz_blocks", page=1, bbox=(1.0, 12.0, 30.0, 22.0)),
            ],
        ),
    )
    monkeypatch.setattr(engine, "_extract_pdf_text_with_fitz", lambda _path: ("", []))
    monkeypatch.setattr(engine, "_ocr_pdf_with_ocrmypdf", lambda _path: ("", []))
    monkeypatch.setattr(engine, "_ocr_pdf_with_fitz", lambda _path: ("", []))

    extracted = service.extract_text_from_file(pdf_path)

    assert extracted.source == "pdf_text_fitz_blocks"
    assert extracted.ocr_used is False
    assert extracted.metadata["page_count"] == 2
    assert extracted.metadata["candidate_count"] >= 2
    assert extracted.metadata["selected_score"] > 0
    assert extracted.metadata["candidate_sources"][0]["source"] == "pdf_text_fitz_blocks"


def test_extract_text_from_file_can_use_ocr_candidate_when_text_layers_are_empty(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(engine, "_count_pdf_pages", lambda _path: 1)
    monkeypatch.setattr(engine, "_extract_pdf_text_with_pypdf", lambda _path: ("", []))
    monkeypatch.setattr(engine, "_extract_pdf_text_with_pdfplumber", lambda _path: ("", []))
    monkeypatch.setattr(engine, "_extract_pdf_text_with_fitz_blocks", lambda _path: ("", []))
    monkeypatch.setattr(engine, "_extract_pdf_text_with_fitz", lambda _path: ("", []))
    monkeypatch.setattr(
        engine,
        "_ocr_pdf_with_ocrmypdf",
        lambda _path: (
            "\n".join(
                [
                    "Leverandør: Demo OCR AS",
                    "Fakturanr: OCR-77",
                    "Beløp å betale: 995,00 NOK",
                ]
            ),
            [engine.TextSegment(text="Fakturanr: OCR-77", source="pdf_ocrmypdf", page=1)],
        ),
    )
    monkeypatch.setattr(engine, "_ocr_pdf_with_fitz", lambda _path: ("", []))

    extracted = service.extract_text_from_file(pdf_path)

    assert extracted.source == "pdf_ocrmypdf"
    assert extracted.ocr_used is True
    assert extracted.metadata["candidate_sources"][0]["ocr_used"] is True


def test_extract_invoice_fields_from_text_keeps_page_and_bbox_in_evidence() -> None:
    facts, evidence = engine.extract_invoice_fields_from_text(
        "Fakturanr: INV-2025-002",
        segments=[
            engine.TextSegment(
                text="Fakturanr: INV-2025-002",
                source="pdf_text_fitz_blocks",
                page=2,
                bbox=(10.0, 20.0, 30.0, 40.0),
            )
        ],
        source_hint="pdf_text_fitz_blocks",
    )

    assert facts.invoice_number == "INV-2025-002"
    assert evidence["invoice_number"].page == 2
    assert evidence["invoice_number"].bbox == (10.0, 20.0, 30.0, 40.0)


def test_extract_invoice_fields_from_text_prefers_invoice_page_over_voucher_cover_page() -> None:
    facts, evidence = engine.extract_invoice_fields_from_text(
        "\n\n".join(
            [
                "\n".join(
                    [
                        "Bilag nummer 4-2025",
                        "Firma: Dalekovod Norge AS",
                        "Org.nr.: 998628253",
                        "Bilag",
                        "Nummer: 4-2025",
                        "Dato: 2025-05-31",
                        "Opprettet: 2025-06-17 16:31:09 Tandem AS / Jon Faldaas",
                        "Konteringssammendrag",
                    ]
                ),
                "\n".join(
                    [
                        "Tandem AS",
                        "INVOICE 373713",
                        "Invoice Date: 31.05.2025",
                        "Invoice Due Date: 10.06.2025",
                        "Org no: 947857169",
                        "Total Amount 5 300,00 NOK",
                    ]
                ),
            ]
        ),
        segments=[
            engine.TextSegment(
                text="\n".join(
                    [
                        "Bilag nummer 4-2025",
                        "Firma: Dalekovod Norge AS",
                        "Org.nr.: 998628253",
                        "Bilag",
                        "Nummer: 4-2025",
                        "Dato: 2025-05-31",
                        "Opprettet: 2025-06-17 16:31:09 Tandem AS / Jon Faldaas",
                        "Konteringssammendrag",
                    ]
                ),
                source="pdf_text_pdfplumber",
                page=1,
            ),
            engine.TextSegment(
                text="\n".join(
                    [
                        "Tandem AS",
                        "INVOICE 373713",
                        "Invoice Date: 31.05.2025",
                        "Invoice Due Date: 10.06.2025",
                        "Org no: 947857169",
                        "Total Amount 5 300,00 NOK",
                    ]
                ),
                source="pdf_text_pdfplumber",
                page=2,
            ),
        ],
        source_hint="pdf_text_pdfplumber",
    )

    assert facts.supplier_name == "Tandem AS"
    assert facts.supplier_orgnr == "947857169"
    assert facts.invoice_number == "373713"
    assert facts.invoice_date == "31.05.2025"
    assert facts.due_date == "10.06.2025"
    assert facts.total_amount == "5300.00"
    assert facts.currency == "NOK"
    assert evidence["supplier_name"].page == 2
    assert evidence["invoice_date"].page == 2
    assert evidence["total_amount"].page == 2


def test_analyze_document_applies_supplier_profile_when_generic_parser_misses_field(
    tmp_path: Path,
    monkeypatch,
) -> None:
    profile = {
        "profile_key": "orgnr:987654321",
        "supplier_name": "Eksempel Partner AS",
        "supplier_orgnr": "987654321",
        "aliases": ["eksempel partner as", "987654321"],
        "sample_count": 2,
        "static_fields": {
            "supplier_name": "Eksempel Partner AS",
            "supplier_orgnr": "987654321",
            "currency": "NOK",
        },
        "field_hints": {
            "invoice_number": [{"label": "vår referanse", "count": 2}],
            "total_amount": [{"label": "til betaling", "count": 2}],
        },
    }
    monkeypatch.setattr(
        app_service.LocalJsonProfileRepository,
        "load_profiles",
        lambda self: {profile["profile_key"]: SupplierProfile.from_dict(profile) or SupplierProfile(profile_key="")},
    )

    file_path = tmp_path / "profile_invoice.txt"
    file_path.write_text(
        "\n".join(
            [
                "Eksempel Partner AS",
                "Vår referanse: INV-2025-777",
                "Til betaling: 1 250,00 NOK",
            ]
        ),
        encoding="utf-8",
    )

    analysis = service.analyze_document(file_path)

    assert analysis.fields["supplier_name"] == "Eksempel Partner AS"
    assert analysis.fields["supplier_orgnr"] == "987654321"
    assert analysis.fields["invoice_number"] == "INV-2025-777"
    assert analysis.fields["total_amount"] == "1250.00"
    assert analysis.metadata["matched_profile_key"] == "orgnr:987654321"
    assert analysis.profile_status == "applied"
    assert analysis.field_evidence["supplier_orgnr"].inferred_from_profile is True
    assert analysis.field_evidence["invoice_number"].source == "text"

from __future__ import annotations

from src.shared.document_control.viewer import preview_kind_for_path, preview_target_from_evidence
from document_engine.models import FieldEvidence


def test_preview_kind_for_supported_extensions() -> None:
    assert preview_kind_for_path("voucher.pdf") == "pdf"
    assert preview_kind_for_path("scan.PNG") == "image"
    assert preview_kind_for_path("invoice.xml") == "text"
    assert preview_kind_for_path("notes.txt") == "text"
    assert preview_kind_for_path("archive.zip") == "unsupported"
    assert preview_kind_for_path("") == "none"


def test_preview_target_from_dataclass_evidence_includes_page_and_bbox() -> None:
    evidence = {
        "total_amount": FieldEvidence(
            field_name="total_amount",
            normalized_value="10600.00",
            raw_value="10 600,00",
            source="pdf_blocks",
            confidence=0.94,
            page=2,
            bbox=(101.0, 215.0, 188.0, 232.0),
        )
    }

    target = preview_target_from_evidence("total_amount", evidence, label="Total")

    assert target is not None
    assert target.page == 2
    assert target.bbox == (101.0, 215.0, 188.0, 232.0)
    assert target.label == "Total"
    assert target.source == "pdf_blocks"


def test_preview_target_from_saved_dict_evidence_supports_page_only_navigation() -> None:
    evidence = {
        "invoice_number": {
            "normalized_value": "373713",
            "source": "pdf_text",
            "confidence": 0.81,
            "page": 1,
            "bbox": None,
        }
    }

    target = preview_target_from_evidence("invoice_number", evidence, label="Fakturanr.")

    assert target is not None
    assert target.page == 1
    assert target.bbox is None
    assert target.label == "Fakturanr."
    assert target.source == "pdf_text"

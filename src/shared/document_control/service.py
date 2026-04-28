from __future__ import annotations

from pathlib import Path

import pandas as pd

from document_engine.engine import (
    ExtractedTextResult,
    build_validation_messages as engine_build_validation_messages,
    extract_invoice_fields_from_text as engine_extract_invoice_fields_from_text,
    extract_invoice_fields_from_xml as engine_extract_invoice_fields_from_xml,
    extract_text_from_file,
    normalize_bilag_key,
)
from document_engine.models import DocumentAnalysisResult as DocumentAnalysis
from document_engine.models import DocumentFacts
from document_control_app_service import analyze_document_for_bilag, build_voucher_context


def analyze_document(file_path: str | Path, bilag_rows: pd.DataFrame | None = None) -> DocumentAnalysis:
    return analyze_document_for_bilag(file_path, df_bilag=bilag_rows)


def extract_invoice_fields_from_text(text: str) -> tuple[dict[str, str], dict[str, float]]:
    facts, evidence = engine_extract_invoice_fields_from_text(text)
    return facts.as_dict(), {field_name: item.confidence for field_name, item in evidence.items()}


def extract_invoice_fields_from_xml(xml_text: str) -> tuple[dict[str, str], dict[str, float]]:
    facts, evidence = engine_extract_invoice_fields_from_xml(xml_text)
    return facts.as_dict(), {field_name: item.confidence for field_name, item in evidence.items()}


def build_validation_messages(fields: dict[str, str], bilag_rows: pd.DataFrame | None) -> list[str]:
    voucher_context = build_voucher_context(bilag_rows)
    facts = DocumentFacts.from_mapping(fields)
    return engine_build_validation_messages(facts, voucher_context)


__all__ = [
    "DocumentAnalysis",
    "ExtractedTextResult",
    "analyze_document",
    "build_validation_messages",
    "extract_invoice_fields_from_text",
    "extract_invoice_fields_from_xml",
    "extract_text_from_file",
    "normalize_bilag_key",
]

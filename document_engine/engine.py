from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import pandas as pd

from .format_utils import (
    normalize_amount_text as _format_normalize_amount_text,
    parse_amount_flexible as _format_parse_amount,
)
from .models import (
    DocumentAnalysisResult,
    DocumentFacts,
    ExtractedTextResult,
    FieldEvidence,
    SupplierProfile,
    TextSegment,
    VoucherContext,
)
from .profiles import apply_supplier_profile, match_supplier_profile


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".xml",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
}

# All field-matching regex patterns live in ``patterns.py``. Re-exported
# here under the original names so the rest of the module (and any
# external user of these private symbols) keeps working unchanged.
from .patterns import (
    _AMOUNT_PATTERNS,
    _BILAGSPRINT_NR_RE,
    _BILAGSPRINT_SIGNAL_RE,
    _COMPANY_SUFFIX_RE,
    _CURRENCY_PATTERNS,
    _DATE_PATTERNS,
    _DESCRIPTION_PATTERNS,
    _DUE_DATE_PATTERNS,
    _INVOICE_NUMBER_PATTERNS,
    _INVOICE_PAGE_NEGATIVE_PATTERNS,
    _INVOICE_PAGE_POSITIVE_PATTERNS,
    _NUMBER_FRAGMENT,
    _ORGNR_PATTERNS,
    _PERIOD_PATTERNS,
    _SUBTOTAL_PATTERNS,
    _SUPPLIER_LABEL_PATTERNS,
    _TEXT_MONTH_NAMES,
    _VAT_PATTERNS,
)

# Bilagsprint detection lives in ``bilagsprint.py``. Re-exported here so
# any legacy caller that does ``from document_engine.engine import
# _is_bilagsprint_segment`` still works.
# Amount self-consistency + joint selection + redo-OCR triggers live in
# ``amount_consistency.py``. Re-exported here so legacy call-sites (tests,
# external modules) keep working.
from .amount_consistency import (
    _amounts_self_consistent,
    _apply_joint_amount_selection,
    _AMOUNT_SELF_CONSISTENCY_TOLERANCE,
    _is_redo_extraction_better,
    _OCR_REDO_AMOUNT_ABS_THRESHOLD,
    _OCR_REDO_AMOUNT_REL_THRESHOLD,
    _OCR_REDO_AMOUNT_SCORE_GATE,
    _select_self_consistent_amounts,
    _should_redo_ocr_for_amounts,
    _validate_amount_self_consistency,
)

from .bilagsprint import (
    _is_bilagsprint_segment,
    _segment_is_bilagsprint,
    _tag_bilagsprint_pages,
)

# Extractors + their scoring helpers live in ``extractors.py``. Re-exported
# here so engine.py callers (and legacy imports from tests) can keep using
# the original private names.
from .extractors import (
    _TextCandidate,
    _append_candidate,
    _extract_candidate_lines,
    _normalize_whitespace,
    _build_word_segment,
    _count_pdf_pages,
    _extract_pdf_text_with_fitz,
    _extract_pdf_text_with_fitz_blocks,
    _extract_pdf_text_with_fitz_words,
    _extract_pdf_text_with_pdfplumber,
    _extract_pdf_text_with_pypdf,
    _GAP_SPLIT_MIN_GAP_PT,
    _GAP_SPLIT_MIN_LINE_WIDTH_FRAC,
    _normalize_text_payload,
    _ocr_image,
    _ocr_pdf_with_fitz,
    _ocr_pdf_with_ocrmypdf,
    _score_text_candidate,
    _split_line_by_gaps,
    _VALUE_CLUSTER_CURRENCY,
    _VALUE_CLUSTER_TOKEN_RE,
)


_PDF_TEXT_THRESHOLD = 40

# Maps field_name → (patterns, normalizer_fn, base_confidence)
# Used by _apply_supplier_profile_learning to re-run hint-boosted extraction.
# NOTE: normalizer functions are referenced by name to avoid circular imports;
#       they are bound below after all functions are defined.
_FIELD_PATTERNS: dict[str, tuple[list, Any, float]] = {}   # filled at module bottom

_XML_TEXT_TAGS = {
    "ID": "invoice_number",
    "IssueDate": "invoice_date",
    "DueDate": "due_date",
    "DocumentCurrencyCode": "currency",
    "RegistrationName": "supplier_name",
    "CompanyID": "supplier_orgnr",
}
_XML_AMOUNT_TAGS = {
    "PayableAmount": "total_amount",
    "TaxInclusiveAmount": "total_amount",
    "TaxExclusiveAmount": "subtotal_amount",
    "TaxAmount": "vat_amount",
}


def normalize_bilag_key(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        if value.is_integer():
            return str(int(value))
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def analyze_document(
    file_path: str | Path,
    *,
    voucher_context: VoucherContext | None = None,
    profiles: dict[str, SupplierProfile] | None = None,
) -> DocumentAnalysisResult:
    path = Path(file_path).expanduser()
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Ikke støttet filtype: {ext or '<ukjent>'}")
    if not path.exists():
        raise FileNotFoundError(path)

    metadata: dict[str, Any] = {
        "file_name": path.name,
        "file_size": path.stat().st_size,
    }
    facts = DocumentFacts()
    field_evidence: dict[str, FieldEvidence] = {}
    profile_status = "none"

    selected_segments: list[TextSegment] = []
    if ext == ".xml":
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
        facts, field_evidence = extract_invoice_fields_from_xml(raw_text)
        metadata.update(
            {
                "ocr_used": False,
                "text_char_count": len(raw_text.strip()),
                "line_count": len(_extract_candidate_lines(raw_text, max_lines=200)),
            }
        )
        source = "xml"
    else:
        extracted = extract_text_from_file(path)
        raw_text = extracted.text
        facts, field_evidence = extract_invoice_fields_from_text(raw_text, segments=extracted.segments, source_hint=extracted.source)
        metadata.update(extracted.metadata)
        metadata["ocr_used"] = extracted.ocr_used
        source = extracted.source

        if profiles:
            facts, field_evidence, profile_status, profile_metadata = _apply_supplier_profile_learning(
                facts,
                field_evidence,
                raw_text,
                profiles,
                segments=extracted.segments,
                source_hint=extracted.source,
            )
            metadata.update(profile_metadata)

        # Amount-inconsistency-driven redo-OCR: if all three amounts were
        # extracted but ``subtotal + vat ≠ total`` and the native text layer
        # is weak (or the deviation is large), try a forced re-OCR once.
        if ext == ".pdf" and _should_redo_ocr_for_amounts(field_evidence, extracted):
            extracted_redo = extract_text_from_file(path, force_ocr_redo=True)
            # Surface the diagnostic whether or not we ultimately use the redo
            # result, so the caller/UI can tell "we wanted a redo but ocrmypdf
            # was unavailable" apart from "we didn't try".
            if extracted_redo.metadata.get("ocr_redo_requested_but_missing"):
                metadata["ocr_redo_requested_but_missing"] = True
            redo_ran = any(
                isinstance(c, dict) and c.get("source") == "pdf_ocrmypdf_redo"
                for c in (extracted_redo.metadata.get("candidate_sources") or [])
            )
            if redo_ran:
                raw_text_redo = extracted_redo.text
                facts_redo, evidence_redo = extract_invoice_fields_from_text(
                    raw_text_redo,
                    segments=extracted_redo.segments,
                    source_hint=extracted_redo.source,
                )
                if profiles:
                    (facts_redo, evidence_redo,
                     profile_status_redo, profile_metadata_redo) = _apply_supplier_profile_learning(
                        facts_redo,
                        evidence_redo,
                        raw_text_redo,
                        profiles,
                        segments=extracted_redo.segments,
                        source_hint=extracted_redo.source,
                    )
                else:
                    profile_status_redo = profile_status
                    profile_metadata_redo = {}
                if _is_redo_extraction_better(evidence_redo, field_evidence):
                    extracted = extracted_redo
                    raw_text = raw_text_redo
                    facts = facts_redo
                    field_evidence = evidence_redo
                    profile_status = profile_status_redo
                    metadata = {
                        "file_name": path.name,
                        "file_size": path.stat().st_size,
                    }
                    metadata.update(extracted.metadata)
                    metadata["ocr_used"] = extracted.ocr_used
                    if profile_metadata_redo:
                        metadata.update(profile_metadata_redo)
                    source = extracted.source
                    metadata["ocr_redo_triggered_by"] = "amount_mismatch"
                else:
                    metadata["ocr_redo_attempted"] = True
                    metadata["ocr_redo_chosen"] = False

    self_consistent = _validate_amount_self_consistency(field_evidence)
    if self_consistent is not None:
        metadata["amount_self_consistent"] = self_consistent

    validation_messages = build_validation_messages(facts, voucher_context, field_evidence=field_evidence)
    raw_text_excerpt = raw_text[:4000] if raw_text else ""

    # Expose the segments that backed the selected extraction. Callers such
    # as the review dialog rely on this to learn hints against the SAME text
    # geometry analyze_document chose (important after a redo-OCR swap).
    if ext != ".xml":
        selected_segments = list(extracted.segments or [])

    return DocumentAnalysisResult(
        file_path=str(path),
        file_type=ext.lstrip("."),
        source=source,
        facts=facts,
        raw_text_excerpt=raw_text_excerpt,
        field_evidence=field_evidence,
        validation_messages=validation_messages,
        metadata=metadata,
        profile_status=profile_status,
        segments=selected_segments,
    )


def extract_text_from_file(
    path: Path,
    *,
    force_ocr_redo: bool = False,
) -> ExtractedTextResult:
    ext = path.suffix.lower()
    if ext == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
        segment = TextSegment(text=text, source="text", page=1)
        return ExtractedTextResult(
            text=text,
            source="text",
            ocr_used=False,
            metadata={
                "text_char_count": len(text.strip()),
                "line_count": len(_extract_candidate_lines(text, max_lines=200)),
            },
            segments=[segment],
        )
    if ext == ".pdf":
        return _extract_text_from_pdf(path, force_ocr_redo=force_ocr_redo)
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        text = _ocr_image(path)
        segment = TextSegment(text=text, source="image_ocr", page=1)
        return ExtractedTextResult(
            text=text,
            source="image_ocr",
            ocr_used=True,
            metadata={
                "ocr_engine": "pytesseract",
                "text_char_count": len(text.strip()),
                "line_count": len(_extract_candidate_lines(text, max_lines=200)),
            },
            segments=[segment],
        )
    raise ValueError(f"Ikke støttet filtype: {ext or '<ukjent>'}")


def extract_invoice_fields_from_text(
    text: str,
    *,
    segments: list[TextSegment] | None = None,
    source_hint: str = "text",
) -> tuple[DocumentFacts, dict[str, FieldEvidence]]:
    evidence_map: dict[str, FieldEvidence] = {}
    ordered_segments = _prioritize_segments_for_invoice(list(segments or []), source_hint=source_hint, text=text)

    supplier_evidence = _extract_supplier_evidence(text, ordered_segments, source_hint)
    if supplier_evidence is not None:
        evidence_map["supplier_name"] = supplier_evidence

    for field_name, patterns, normalizer, score in (
        ("supplier_orgnr", _ORGNR_PATTERNS, _normalize_orgnr, 0.9),
        ("invoice_number", _INVOICE_NUMBER_PATTERNS, _normalize_compact_text, 0.8),
        ("invoice_date", _DATE_PATTERNS, _normalize_date_text, 0.78),
        ("due_date", _DUE_DATE_PATTERNS, _normalize_date_text, 0.78),
        ("subtotal_amount", _SUBTOTAL_PATTERNS, _normalize_amount_text, 0.8),
        ("vat_amount", _VAT_PATTERNS, _normalize_amount_text, 0.8),
        ("total_amount", _AMOUNT_PATTERNS, _normalize_amount_text, 0.86),
        ("currency", _CURRENCY_PATTERNS, _normalize_currency_text, 0.72),
        ("description", _DESCRIPTION_PATTERNS, _normalize_whitespace, 0.5),
        ("period", _PERIOD_PATTERNS, _normalize_whitespace, 0.5),
    ):
        evidence = _first_match_evidence(field_name, patterns, text, ordered_segments, normalizer, score, source_hint)
        if evidence is not None:
            evidence_map[field_name] = evidence

    _apply_joint_amount_selection(evidence_map, text, ordered_segments, source_hint)

    facts = DocumentFacts.from_mapping(
        {fn: ev.normalized_value for fn, ev in evidence_map.items() if ev.normalized_value}
    )
    return facts, evidence_map


def extract_invoice_fields_from_text_with_hints(
    text: str,
    *,
    segments: list[TextSegment] | None = None,
    source_hint: str = "text",
    profile_hints: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[DocumentFacts, dict[str, FieldEvidence]]:
    """Like extract_invoice_fields_from_text but boosts candidates matching profile hints.

    profile_hints: field_name → list of hint dicts, each with keys:
        label (str), page (int|None), count (int)
    """
    evidence_map: dict[str, FieldEvidence] = {}
    ordered_segments = _prioritize_segments_for_invoice(list(segments or []), source_hint=source_hint, text=text)

    supplier_evidence = _extract_supplier_evidence(text, ordered_segments, source_hint)
    if supplier_evidence is not None:
        evidence_map["supplier_name"] = supplier_evidence

    hints = profile_hints or {}
    for field_name, patterns, normalizer, score in (
        ("supplier_orgnr", _ORGNR_PATTERNS, _normalize_orgnr, 0.9),
        ("invoice_number", _INVOICE_NUMBER_PATTERNS, _normalize_compact_text, 0.8),
        ("invoice_date", _DATE_PATTERNS, _normalize_date_text, 0.78),
        ("due_date", _DUE_DATE_PATTERNS, _normalize_date_text, 0.78),
        ("subtotal_amount", _SUBTOTAL_PATTERNS, _normalize_amount_text, 0.8),
        ("vat_amount", _VAT_PATTERNS, _normalize_amount_text, 0.8),
        ("total_amount", _AMOUNT_PATTERNS, _normalize_amount_text, 0.86),
        ("currency", _CURRENCY_PATTERNS, _normalize_currency_text, 0.72),
        ("description", _DESCRIPTION_PATTERNS, _normalize_whitespace, 0.5),
        ("period", _PERIOD_PATTERNS, _normalize_whitespace, 0.5),
    ):
        field_hints = hints.get(field_name, [])
        evidence = _first_match_evidence(
            field_name, patterns, text, ordered_segments, normalizer, score, source_hint,
            profile_hints=field_hints,
        )
        if evidence is not None:
            evidence_map[field_name] = evidence

    _apply_joint_amount_selection(
        evidence_map, text, ordered_segments, source_hint, profile_hints=hints,
    )

    facts = DocumentFacts.from_mapping(
        {field_name: evidence.normalized_value for field_name, evidence in evidence_map.items() if evidence.normalized_value}
    )
    return facts, evidence_map


def extract_invoice_fields_from_xml(xml_text: str) -> tuple[DocumentFacts, dict[str, FieldEvidence]]:
    evidence_map: dict[str, FieldEvidence] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return DocumentFacts(), evidence_map

    for element in root.iter():
        local = _local_name(element.tag)
        text = (element.text or "").strip()
        if not text:
            continue

        if local in _XML_TEXT_TAGS and _XML_TEXT_TAGS[local] not in evidence_map:
            field_name = _XML_TEXT_TAGS[local]
            normalizer = {
                "invoice_number": _normalize_compact_text,
                "invoice_date": _normalize_date_text,
                "due_date": _normalize_date_text,
                "currency": _normalize_currency_text,
                "supplier_name": _normalize_whitespace,
                "supplier_orgnr": _normalize_orgnr,
            }[field_name]
            normalized = normalizer(text)
            if normalized:
                evidence_map[field_name] = FieldEvidence(
                    field_name=field_name,
                    normalized_value=normalized,
                    raw_value=text,
                    source="xml",
                    confidence=0.98,
                )

        if local in _XML_AMOUNT_TAGS:
            field_name = _XML_AMOUNT_TAGS[local]
            normalized = _normalize_amount_text(text)
            if normalized:
                evidence_map[field_name] = FieldEvidence(
                    field_name=field_name,
                    normalized_value=normalized,
                    raw_value=text,
                    source="xml",
                    confidence=0.99,
                )

    facts = DocumentFacts.from_mapping({field_name: evidence.normalized_value for field_name, evidence in evidence_map.items()})
    return facts, evidence_map


def build_validation_messages(
    facts: DocumentFacts,
    voucher_context: VoucherContext | None,
    *,
    field_evidence: dict[str, FieldEvidence] | None = None,
) -> list[str]:
    evidence_map = field_evidence or {}
    messages: list[str] = []
    if voucher_context is None or voucher_context.row_count <= 0:
        messages.append("Ingen bilagsrader tilgjengelig for kontroll.")
        return messages

    if voucher_context.bilag:
        messages.append(f"Bilag {voucher_context.bilag} med {voucher_context.row_count} rad(er) er valgt.")
    if voucher_context.texts:
        messages.append(f"Fant tekstgrunnlag i {len(voucher_context.texts)} rad(er) for bilagskontroll.")
    if voucher_context.amounts:
        sum_net = sum(voucher_context.amounts)
        sum_abs = sum(abs(value) for value in voucher_context.amounts)
        largest = max(voucher_context.amounts, key=lambda value: abs(value))
        messages.append(
            f"Bilagssummer fra regnskapslinjene: netto {sum_net:,.2f}, absolutt {sum_abs:,.2f}, største linje {largest:,.2f}."
        )

    if facts.invoice_number:
        matched = any(facts.invoice_number.lower() in text.lower() for text in voucher_context.texts)
        _mark_validation(evidence_map.get("invoice_number"), matched, "Fakturanummer ble kontrollert mot bilagsteksten.")
        messages.append(
            f"Fakturanummer {facts.invoice_number} ble {'gjenfunnet' if matched else 'ikke gjenfunnet'} i bilagsteksten."
        )

    if facts.supplier_name:
        # Use tokens >= 3 chars; if none survive (e.g. "Bhl DA"), fall back to all tokens
        supplier_tokens = [t for t in re.split(r"\s+", facts.supplier_name) if len(t) >= 3]
        if not supplier_tokens:
            supplier_tokens = [t for t in re.split(r"\s+", facts.supplier_name) if t]
        matched = supplier_tokens and any(
            any(token.lower() in text.lower() for token in supplier_tokens) for text in voucher_context.texts
        )
        _mark_validation(evidence_map.get("supplier_name"), bool(matched), "Leverandørnavn ble kontrollert mot bilagsteksten.")
        messages.append(
            f"Leverandørnavn {'matcher' if matched else 'ble ikke sikkert gjenfunnet i'} bilaget: {facts.supplier_name}."
        )

    for field_name, label in (("total_amount", "Totalbeløp"), ("vat_amount", "MVA-beløp"), ("subtotal_amount", "Nettobeløp")):
        amount_value = _parse_amount(getattr(facts, field_name, ""))
        if amount_value is None:
            continue
        matched = any(abs(abs(row_amount) - abs(amount_value)) <= 1.0 for row_amount in voucher_context.amounts)
        _mark_validation(evidence_map.get(field_name), matched, f"{label} ble kontrollert mot regnskapslinjene.")
        messages.append(
            f"{label} {getattr(facts, field_name)} {'matcher minst én regnskapslinje' if matched else 'ble ikke direkte matchet mot en enkelt regnskapslinje'}."
        )

    # Internal consistency: subtotal + vat ≈ total. Only reported when all
    # three amounts are present AND they disagree — a silent pass is fine.
    total_ev = evidence_map.get("total_amount")
    if total_ev is not None and total_ev.metadata.get("self_consistent") is False:
        st = _parse_amount(getattr(facts, "subtotal_amount", ""))
        vt = _parse_amount(getattr(facts, "vat_amount", ""))
        tt = _parse_amount(getattr(facts, "total_amount", ""))
        if st is not None and vt is not None and tt is not None:
            messages.append(
                f"Intern beløpssjekk: {st:,.2f} + {vt:,.2f} = {st + vt:,.2f}, "
                f"men total er {tt:,.2f} — dette er inkonsistent."
            )

    if facts.invoice_date:
        matched = facts.invoice_date in set(voucher_context.dates)
        _mark_validation(evidence_map.get("invoice_date"), matched, "Fakturadato ble kontrollert mot bilagsdatoer.")
        if matched:
            messages.append(f"Fakturadato {facts.invoice_date} matcher dato i bilagslinjene.")
        elif voucher_context.dates:
            messages.append(
                f"Fakturadato {facts.invoice_date} avviker fra registrerte bilagsdatoer: {', '.join(sorted(set(voucher_context.dates)))}."
            )
    return messages


def _extract_text_from_pdf(
    path: Path,
    *,
    force_ocr_redo: bool = False,
) -> ExtractedTextResult:
    page_count = _count_pdf_pages(path)
    candidates: list[_TextCandidate] = []

    _append_candidate(candidates, "pdf_text_pypdf", _extract_pdf_text_with_pypdf(path), False)
    _append_candidate(candidates, "pdf_text_pdfplumber", _extract_pdf_text_with_pdfplumber(path), False)
    _append_candidate(candidates, "pdf_text_fitz_words", _extract_pdf_text_with_fitz_words(path), False)
    _append_candidate(candidates, "pdf_text_fitz_blocks", _extract_pdf_text_with_fitz_blocks(path), False)
    _append_candidate(candidates, "pdf_text_fitz", _extract_pdf_text_with_fitz(path), False)
    _append_candidate(candidates, "pdf_ocrmypdf", _ocr_pdf_with_ocrmypdf(path), True)
    _append_candidate(candidates, "pdf_ocr_fitz", _ocr_pdf_with_fitz(path), True)
    if force_ocr_redo:
        # Caller (analyze_document) detected an amount inconsistency and
        # wants a re-OCR pass even when the native score is high enough that
        # the low-score fallback below would not have fired.
        _append_candidate(candidates, "pdf_ocrmypdf_redo",
                          _ocr_pdf_with_ocrmypdf(path, mode="redo"), True)

    if not candidates:
        return ExtractedTextResult(
            text="",
            source="pdf_empty",
            ocr_used=False,
            metadata={
                "page_count": page_count,
                "candidate_count": 0,
                "candidate_sources": [],
                "text_char_count": 0,
                "line_count": 0,
            },
            segments=[],
        )

    best = max(candidates, key=lambda candidate: candidate.score)
    # Prefer fitz_words over fitz_blocks when they're close — words has
    # tight value-bbox which is critical for profile-hint bbox matching.
    if best.source == "pdf_text_fitz_blocks":
        words_cand = next((c for c in candidates if c.source == "pdf_text_fitz_words"), None)
        if words_cand is not None and words_cand.score >= best.score - 5.0:
            best = words_cand

    # If every native/OCR candidate is weak, re-OCR over the existing text
    # layer. A scanned invoice that was pre-OCRed with a low-quality
    # engine (e.g. a Tripletex cover page) otherwise keeps its bad text
    # forever since --skip-text leaves it alone. Skip this when the caller
    # already requested a forced redo (candidate is already present).
    already_redone = any(c.source == "pdf_ocrmypdf_redo" for c in candidates)
    if not already_redone and best.score < _OCR_REDO_SCORE_THRESHOLD:
        _append_candidate(candidates, "pdf_ocrmypdf_redo",
                          _ocr_pdf_with_ocrmypdf(path, mode="redo"), True)
        best = max(candidates, key=lambda candidate: candidate.score)

    # When the caller explicitly asked for a redo, return the redo candidate
    # if ocrmypdf actually produced one — even if another extractor happens to
    # score higher. The caller has specific reasons to want the redo result
    # (typically: native amounts are inconsistent and native is what we just
    # got), so scoring-based selection would defeat the purpose.
    redo_requested_but_missing = False
    if force_ocr_redo:
        redo_cand = next(
            (c for c in candidates if c.source == "pdf_ocrmypdf_redo"),
            None,
        )
        if redo_cand is not None:
            best = redo_cand
        else:
            # ocrmypdf not available or subprocess failed — caller asked for a
            # redo but we couldn't deliver one. Flag so analyze_document can
            # surface this in metadata instead of silently falling back.
            redo_requested_but_missing = True
    metadata: dict[str, Any] = {
        "page_count": page_count,
        "candidate_count": len(candidates),
        "candidate_sources": [
            {
                "source": candidate.source,
                "score": round(candidate.score, 2),
                "ocr_used": candidate.ocr_used,
                "char_count": len(candidate.text.strip()),
                "segment_count": len(candidate.segments),
            }
            for candidate in sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
        ],
        "selected_score": round(best.score, 2),
        "text_char_count": len(best.text.strip()),
        "line_count": len(_extract_candidate_lines(best.text, max_lines=200)),
        **best.metadata,
    }
    if redo_requested_but_missing:
        metadata["ocr_redo_requested_but_missing"] = True
    # Tag segments from Tripletex cover pages (bilagsprint) — the check
    # runs over each page's *combined* text, so word-level segments that
    # individually don't carry both signals still get flagged correctly.
    _tag_bilagsprint_pages(best.segments)
    return ExtractedTextResult(
        text=best.text,
        source=best.source,
        ocr_used=best.ocr_used,
        metadata=metadata,
        segments=best.segments,
    )


_OCR_REDO_SCORE_THRESHOLD = 30.0
def _extract_supplier_from_foretaksregisteret(
    segments: list[TextSegment], source_hint: str
) -> FieldEvidence | None:
    """Highest-priority supplier source: the legally-mandated Norwegian
    "Foretaksregisteret" footer line.

    Norwegian business invoices MUST identify the legal entity of the issuer
    via a footer line that references "Foretaksregisteret".  Common shapes:

        "Lyse Tele AS, Breiflåtveien 18, 4017 Stavanger, Foretaksregisteret NO 912 672 808 MVA"
        "... \n Lyse Tele AS \n Foretaksregisteret NO ..."

    This is authoritative because it names the *principal* supplier even
    when the visible invoice header carries an agent/processor (e.g. the
    invoicing service "Amili Collection AS" acting on behalf of Lyse Tele).
    """
    for segment in segments:
        if _segment_is_bilagsprint(segment):
            continue
        all_lines = _extract_candidate_lines(segment.text, max_lines=500)
        for i, line in enumerate(all_lines):
            if "foretaksregisteret" not in line.lower():
                continue
            # Same-line pattern: "Name AS, Address, Zipcode City, Foretaksregisteret NO ..."
            # Take text up to the first comma and see if it parses as a company.
            head = line.split(",", 1)[0].strip()
            normalized = _normalize_supplier_name(head)
            if normalized and _COMPANY_SUFFIX_RE.search(normalized):
                return FieldEvidence(
                    field_name="supplier_name",
                    normalized_value=normalized,
                    raw_value=head,
                    source=segment.source or source_hint,
                    confidence=0.75,
                    page=segment.page,
                    bbox=segment.bbox,
                )
            # Multi-line pattern: the company name is on a neighboring line.
            window = all_lines[max(0, i - 5):i] + all_lines[i + 1:i + 6]
            for nearby in window:
                normalized = _normalize_supplier_name(nearby)
                if normalized and _COMPANY_SUFFIX_RE.search(normalized):
                    return FieldEvidence(
                        field_name="supplier_name",
                        normalized_value=normalized,
                        raw_value=nearby,
                        source=segment.source or source_hint,
                        confidence=0.7,
                        page=segment.page,
                        bbox=segment.bbox,
                    )
    return None


def _extract_supplier_evidence(text: str, segments: list[TextSegment], source_hint: str) -> FieldEvidence | None:
    seg_list = segments or [TextSegment(text=text, source=source_hint)]

    # Priority 1: "Foretaksregisteret" footer — legally authoritative in Norway.
    # This must win over header text because the visible header can carry an
    # invoicing agent (e.g. Amili Collection AS) rather than the legal issuer.
    evidence = _extract_supplier_from_foretaksregisteret(seg_list, source_hint)
    if evidence is not None:
        return evidence

    # Priority 2: explicit label patterns ("Leverandør:", "Supplier:", "Fra: X").
    for segment in seg_list:
        if _segment_is_bilagsprint(segment):
            continue
        for pattern in _SUPPLIER_LABEL_PATTERNS:
            match = pattern.search(segment.text)
            if not match:
                continue
            normalized = _normalize_supplier_name(match.group(1))
            if normalized:
                return FieldEvidence(
                    field_name="supplier_name",
                    normalized_value=normalized,
                    raw_value=str(match.group(1) or ""),
                    source=segment.source or source_hint,
                    confidence=0.6 if _COMPANY_SUFFIX_RE.search(normalized) else 0.55,
                    page=segment.page,
                    bbox=segment.bbox,
                )

    # Priority 3: header candidate lines (first 20 lines, require company suffix).
    for segment in seg_list:
        if _segment_is_bilagsprint(segment):
            continue
        candidate_lines = _extract_candidate_lines(segment.text, max_lines=20)
        for line in candidate_lines:
            normalized = _normalize_supplier_name(line)
            if normalized and _COMPANY_SUFFIX_RE.search(normalized):
                return FieldEvidence(
                    field_name="supplier_name",
                    normalized_value=normalized,
                    raw_value=line,
                    source=segment.source or source_hint,
                    confidence=0.6,
                    page=segment.page,
                    bbox=segment.bbox,
                )

        # Priority 4: high-uppercase-ratio line (fallback for ALL-CAPS headers).
        for line in candidate_lines:
            candidate = _normalize_supplier_name(line)
            if not candidate:
                continue
            upper_ratio = sum(1 for char in candidate if char.isupper()) / max(len(candidate), 1)
            if upper_ratio >= 0.45 and len(candidate.split()) <= 5:
                return FieldEvidence(
                    field_name="supplier_name",
                    normalized_value=candidate,
                    raw_value=line,
                    source=segment.source or source_hint,
                    confidence=0.55,
                    page=segment.page,
                    bbox=segment.bbox,
                )
    return None


def _bbox_for_match_span(
    segment: TextSegment,
    match: re.Match[str],
) -> tuple[float, float, float, float] | None:
    """Return a bbox tight around ``match.group(1)`` using ``word_spans``.

    When a line has several amounts on the same row (``Sum 800  MVA 200
    Total 1000``), line-level bbox is useless for distinguishing fields.
    This walks the segment's word-span table and unions the word bboxes
    whose char-ranges overlap the regex match. Returns ``None`` when the
    segment lacks word-span info — callers should fall back to
    ``segment.bbox`` in that case.
    """
    spans = segment.word_spans or []
    if not spans:
        return None
    span = match.span(1) if match.groups() else match.span()
    m_start, m_end = span
    if m_start < 0 or m_end <= m_start:
        # Group didn't participate in the match — fall back to whole match.
        m_start, m_end = match.span()
        if m_start < 0 or m_end <= m_start:
            return None
    hits: list[tuple[float, float, float, float]] = []
    for s_start, s_end, bbox in spans:
        if s_end <= m_start or s_start >= m_end:
            continue
        hits.append(bbox)
    if not hits:
        return None
    x0 = min(b[0] for b in hits)
    y0 = min(b[1] for b in hits)
    x1 = max(b[2] for b in hits)
    y1 = max(b[3] for b in hits)
    return (x0, y0, x1, y1)


def _match_is_percentage(segment_text: str, match: re.Match[str]) -> bool:
    """Return True when the captured number is immediately followed by ``%``.

    Prevents rate values like ``25.00%`` or ``25 %`` from being harvested as
    monetary amounts. Looks at the first non-whitespace character after the
    end of capture group 1 (or the match as a whole when no group exists).
    """
    try:
        end = match.end(1) if match.groups() else match.end()
    except (IndexError, re.error):
        end = match.end()
    if end < 0:
        return False
    tail = segment_text[end:end + 8]
    return tail.lstrip().startswith("%")


def _collect_ranked_candidates(
    field_name: str,
    patterns: list[re.Pattern[str]] | tuple[re.Pattern[str], ...],
    text: str,
    segments: list[TextSegment],
    normalizer,
    score: float,
    source_hint: str,
    *,
    profile_hints: list[dict[str, Any]] | None = None,
) -> list[tuple[float, FieldEvidence]]:
    """Return all field-match candidates sorted by rank (highest first).

    Amount fields additionally reject percentage tails via
    :func:`_match_is_percentage` so a rate like ``25.00%`` can never become
    ``vat_amount``.
    """
    candidates: list[tuple[float, FieldEvidence]] = []
    is_amount_field = field_name in _AMOUNT_FIELDS
    for segment_index, segment in enumerate(segments or [TextSegment(text=text, source=source_hint)]):
        # Skip bilagsprint segments entirely — these are accounting-system
        # printouts (Tripletex cover pages) and should never provide field values.
        if _segment_is_bilagsprint(segment):
            continue
        for pattern_index, pattern in enumerate(patterns):
            for match in pattern.finditer(segment.text):
                raw_value = str(match.group(1) or "")
                normalized = normalizer(raw_value)
                if not normalized:
                    continue
                if is_amount_field and _match_is_percentage(segment.text, match):
                    continue
                match_bbox = _bbox_for_match_span(segment, match) or segment.bbox
                evidence = FieldEvidence(
                    field_name=field_name,
                    normalized_value=normalized,
                    raw_value=raw_value,
                    source=segment.source or source_hint,
                    confidence=score,
                    page=segment.page,
                    bbox=match_bbox,
                )
                rank = _score_field_match(
                    field_name, evidence,
                    segment_index=segment_index,
                    pattern_index=pattern_index,
                    profile_hints=profile_hints or [],
                    segment_text=segment.text,
                )
                # Explainability metadata — written here because this is the
                # single gate every candidate passes through. Downstream
                # code can inspect ``evidence.metadata`` to see *why* a
                # value was selected without re-running the scoring.
                hint_boost = _profile_hint_boost(
                    evidence, segment.text, profile_hints or [],
                )
                bbox_width = None
                if match_bbox is not None:
                    try:
                        bbox_width = float(match_bbox[2]) - float(match_bbox[0])
                    except (IndexError, TypeError, ValueError):
                        bbox_width = None
                evidence.metadata["winner_source"] = segment.source or source_hint
                evidence.metadata["pattern_index"] = pattern_index
                evidence.metadata["segment_index"] = segment_index
                evidence.metadata["hint_boost"] = round(float(hint_boost), 2)
                evidence.metadata["rank"] = round(float(rank), 2)
                if bbox_width is not None:
                    evidence.metadata["bbox_width"] = round(bbox_width, 2)
                candidates.append((rank, evidence))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates


def _first_match_evidence(
    field_name: str,
    patterns: list[re.Pattern[str]] | tuple[re.Pattern[str], ...],
    text: str,
    segments: list[TextSegment],
    normalizer,
    score: float,
    source_hint: str,
    *,
    profile_hints: list[dict[str, Any]] | None = None,
) -> FieldEvidence | None:
    candidates = _collect_ranked_candidates(
        field_name, patterns, text, segments, normalizer, score, source_hint,
        profile_hints=profile_hints,
    )
    return candidates[0][1] if candidates else None


def _score_field_match(
    field_name: str,
    evidence: FieldEvidence,
    *,
    segment_index: int,
    pattern_index: int,
    profile_hints: list[dict[str, Any]] | None = None,
    segment_text: str = "",
) -> float:
    rank = 1000.0
    rank -= segment_index * 25.0

    # Heavy penalty for bilagsprint pages — these are accounting-system
    # printouts (Tripletex cover pages) that contain registered data, NOT
    # the actual vendor invoice.  Without this penalty, fields like amount,
    # date, and invoice number on the bilagsprint can outscore the real
    # invoice fields, causing the viewer to jump to page 1.
    if _is_bilagsprint_segment(segment_text):
        rank -= 500.0

    if field_name in {"total_amount", "subtotal_amount", "vat_amount"}:
        rank -= pattern_index * 120.0
    elif field_name == "invoice_number":
        rank -= pattern_index * 10.0
        rank += min(len(evidence.normalized_value), 20)
    elif field_name == "currency":
        rank -= pattern_index * 10.0
        rank += 5.0 if evidence.normalized_value in {"NOK", "SEK", "DKK", "EUR", "USD", "GBP"} else 0.0
    else:
        rank -= pattern_index * 10.0

    # ── Profile hint boost ────────────────────────────────────────────────
    # A learned hint records the page and label text where the correct value
    # was previously confirmed by the user.  We apply a large bonus so that
    # hints win over the generic pattern ranking, but only when BOTH criteria
    # match (page AND label present in the segment text).
    if profile_hints:
        hint_boost = _profile_hint_boost(evidence, segment_text, profile_hints)
        rank += hint_boost

    return rank


def _profile_hint_boost(
    evidence: FieldEvidence,
    segment_text: str,
    hints: list[dict[str, Any]],
) -> float:
    """Return a score bonus when this candidate matches a learned profile hint.

    Scoring (before weighting):
        page match only          → +150
        label match only         → +200  (disabled for amount fields)
        page + label match       → +500
        page + bbox near         → +400
        page + label + bbox near → +700 (strongest — exact position confirmed)

    **Amount fields** (subtotal / vat / total) never receive a label-only
    boost. On invoices with repeated labels like ``sum`` or ``total``, a
    label-only match has no way of distinguishing the correct row from a
    cover-page summary or a tax-base figure. Amount fields must be
    confirmed by page (or page + bbox) before any learned hint can lift
    their rank.

    All bonuses are weighted by confirmation count; weight saturates at
    count=3 (weight=1.0) so a profile with 20 saves does not drown out the
    generic pattern ranking.
    """
    if not hints:
        return 0.0

    seg_text_norm = re.sub(r"\s+", " ", segment_text).lower()
    is_amount_field = evidence.field_name in _AMOUNT_FIELDS
    best = 0.0

    for hint in hints:
        hint_page:  int | None = hint.get("page")
        hint_label: str       = str(hint.get("label", "") or "").lower().strip()
        hint_bbox             = hint.get("bbox")
        hint_count: int       = max(1, int(hint.get("count", 1) or 1))
        weight = min(hint_count / 3.0, 1.0)   # saturates at 3 confirmed saves

        page_match  = (hint_page is not None and evidence.page is not None
                       and evidence.page == hint_page)
        label_match = bool(hint_label and hint_label in seg_text_norm)
        bbox_near   = _bbox_is_near(evidence.bbox, hint_bbox) if page_match else False

        if page_match and label_match and bbox_near:
            boost = 700.0 * weight
        elif page_match and label_match:
            boost = 500.0 * weight
        elif page_match and bbox_near:
            boost = 400.0 * weight
        elif page_match and hint_label:
            # Page-only boost is restricted to hints that DO have a
            # label — position-only hints (``hint_label == ""``) already
            # got their full +400 above via bbox_near, and must not
            # boost unrelated values on the same page.
            boost = 150.0 * weight
        elif label_match and not is_amount_field:
            boost = 200.0 * weight
        else:
            boost = 0.0

        best = max(best, boost)

    return best


def _bbox_is_near(
    a: tuple[float, ...] | None,
    b: tuple[float, ...] | None,
    threshold: float = 60.0,
) -> bool:
    """Check if two bboxes are within *threshold* points of each other.

    Compares top-left corners (x0, y0). A threshold of 60 pt (~21 mm) is
    generous enough to handle minor OCR drift between invoices from the
    same supplier.
    """
    if a is None or b is None:
        return False
    try:
        dx = abs(float(a[0]) - float(b[0]))
        dy = abs(float(a[1]) - float(b[1]))
        return (dx + dy) < threshold
    except (IndexError, TypeError, ValueError):
        return False


def _prioritize_segments_for_invoice(
    segments: list[TextSegment],
    *,
    source_hint: str,
    text: str,
) -> list[TextSegment]:
    if not segments:
        return [TextSegment(text=text, source=source_hint)]
    return sorted(
        segments,
        key=lambda segment: (
            -_segment_invoice_priority(segment),
            segment.page if segment.page is not None else 9999,
        ),
    )


def _segment_invoice_priority(segment: TextSegment) -> float:
    text = segment.text or ""
    lowered = text.lower()
    score = 0.0

    for pattern in _INVOICE_PAGE_POSITIVE_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            score += 18.0

    for pattern in _INVOICE_PAGE_NEGATIVE_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            score -= 22.0

    score += min(len(re.findall(_NUMBER_FRAGMENT, text, re.IGNORECASE)), 8) * 2.5
    score += _segment_bonus_count(text, _DATE_PATTERNS) * 9.0
    score += _segment_bonus_count(text, _DUE_DATE_PATTERNS) * 9.0
    score += _segment_bonus_count(text, _INVOICE_NUMBER_PATTERNS) * 12.0
    score += _segment_bonus_count(text, _AMOUNT_PATTERNS) * 13.0
    score += _segment_bonus_count(text, _VAT_PATTERNS) * 7.0
    score += _segment_bonus_count(text, _SUBTOTAL_PATTERNS) * 7.0
    if segment.page and segment.page > 1:
        score += 6.0
    # Strong penalty for Tripletex bilagsprint pages (accounting summary printout,
    # NOT the actual vendor invoice).  These pages must never win over a real invoice.
    if _is_bilagsprint_segment(text):
        return -500.0
    elif "firma:" in lowered and "bilag nummer" in lowered:
        score -= 40.0
    return score


def _segment_bonus_count(text: str, patterns: tuple[re.Pattern[str], ...] | list[re.Pattern[str]]) -> int:
    return sum(1 for pattern in patterns if pattern.search(text))


def _normalize_supplier_name(value: str) -> str:
    value = _normalize_whitespace(value)
    value = re.sub(r"^(?:leverand[øo]r|supplier|selger|seller|fra)\s*[:\-]?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:org(?:anisajons)?\.?\s*nr\.?|org\.?\s*no\.?)\b.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b\d{9}\b.*$", "", value)
    value = _normalize_whitespace(value)
    if not value or len(value) < 3 or re.search(r"\d{4,}", value):
        return ""
    if any(token in value.lower() for token in ("fakturanr", "invoice", "forfallsdato", "dato", "amount", "beløp", "total", "mva")):
        return ""
    return value[:120]


def _normalize_compact_text(value: str) -> str:
    return _normalize_whitespace(value).strip(":.- ")


def _normalize_currency_text(value: str) -> str:
    return _normalize_whitespace(value).upper()


def _normalize_orgnr(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    return digits[:9] if len(digits) >= 9 else digits


_MONTH_NAME_TO_NUM: dict[str, int] = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
    "january": 1, "february": 2, "march": 3, "may": 5,
    "june": 6, "july": 7, "october": 10, "december": 12,
}

_TEXT_DATE_NORM_RE = re.compile(
    r"(\d{1,2})\.?\s*(" + "|".join(_MONTH_NAME_TO_NUM.keys()) + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _normalize_date_text(value: str) -> str:
    text = _normalize_whitespace(value)

    # Try text-month format first (e.g. "5. desember 2025")
    m = _TEXT_DATE_NORM_RE.search(text)
    if m:
        day_s, month_name, year_s = m.group(1), m.group(2).lower(), m.group(3)
        month_num = _MONTH_NAME_TO_NUM.get(month_name)
        if month_num:
            return f"{int(day_s):02d}.{month_num:02d}.{int(year_s):04d}"

    text = text.replace("/", ".").replace("-", ".")
    parts = text.split(".")
    if len(parts) != 3:
        return text
    if len(parts[0]) == 4:
        year, month, day = parts
    else:
        day, month, year = parts
    if len(year) == 2:
        year = f"20{year}"
    try:
        day_int = int(day)
        month_int = int(month)
        year_int = int(year)
    except Exception:
        return text
    return f"{day_int:02d}.{month_int:02d}.{year_int:04d}"


def _normalize_amount_text(value: str) -> str:
    return _format_normalize_amount_text(value)


def _parse_amount(value: Any) -> float | None:
    return _format_parse_amount(value)


def _ev_value(evidence: FieldEvidence | None) -> str:
    if evidence is None:
        return ""
    return evidence.normalized_value or evidence.raw_value or ""


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


_AMOUNT_FIELDS = frozenset({"subtotal_amount", "vat_amount", "total_amount"})


def _apply_supplier_profile_learning(
    facts: DocumentFacts,
    field_evidence: dict[str, FieldEvidence],
    raw_text: str,
    profiles: dict[str, SupplierProfile],
    *,
    segments: list[TextSegment] | None = None,
    source_hint: str = "text",
) -> tuple[DocumentFacts, dict[str, FieldEvidence], str, dict[str, Any]]:
    profile, match_score = match_supplier_profile(profiles, facts.as_dict(), raw_text)
    if profile is None:
        return facts, field_evidence, "none", {}

    # Aggregated cross-supplier profile — labels like "til betaling" leak
    # across unrelated vendors, so we must not let its hints boost amount
    # fields. Vendor identity is the only reliable signal for amounts.
    from .profiles import GLOBAL_PROFILE_KEY
    is_global_profile = (profile.profile_key == GLOBAL_PROFILE_KEY)

    # ── Re-run field extraction with profile hints if hints exist ─────────
    # This allows the engine to boost candidates on the learned page/label,
    # overriding the generic pattern ranking.
    profile_hints = dict(profile.field_hints or {})
    hint_fields: list[str] = []
    if profile_hints and segments:
        ordered_segments = _prioritize_segments_for_invoice(
            list(segments), source_hint=source_hint, text=raw_text
        )
        facts_map = facts.as_dict()
        for field_name in profile_hints:
            hints = profile_hints[field_name]
            if not hints:
                continue
            # Re-score all candidates for this field using hints
            if field_name not in _FIELD_PATTERNS:
                continue
            if is_global_profile and field_name in _AMOUNT_FIELDS:
                # Amount labels are too vendor-specific to share across suppliers.
                continue
            patterns, normalizer, base_score = _FIELD_PATTERNS[field_name]
            new_evidence = _first_match_evidence(
                field_name, patterns, raw_text, ordered_segments,
                normalizer, base_score, source_hint,
                profile_hints=hints,
            )
            if new_evidence and new_evidence.normalized_value:
                old = field_evidence.get(field_name)
                if old is None or new_evidence.normalized_value != old.normalized_value:
                    field_evidence[field_name] = new_evidence
                    facts_map[field_name] = new_evidence.normalized_value
                    hint_fields.append(field_name)
        facts = DocumentFacts.from_mapping(facts_map)

    # ── Apply static profile values (supplier_name, orgnr, currency) ─────
    # Skip for global fallback (low match score) — no supplier identity to apply.
    applied_fields: list[str] = list(hint_fields)
    facts_map = facts.as_dict()

    if match_score >= 20:
        learned_values = apply_supplier_profile(profile, raw_text)
        for field_name, raw_value in learned_values.items():
            normalized = _normalize_field_value(field_name, raw_value)
            if not normalized or facts_map.get(field_name):
                continue
            facts_map[field_name] = normalized
            field_evidence[field_name] = FieldEvidence(
                field_name=field_name,
                normalized_value=normalized,
                raw_value=raw_value,
                source="profile",
                confidence=0.9 if field_name in {"supplier_name", "supplier_orgnr", "currency"} else 0.74,
                inferred_from_profile=True,
                metadata={"profile_key": profile.profile_key},
            )
            applied_fields.append(field_name)

    updated_facts = DocumentFacts.from_mapping(facts_map)
    profile_status = "applied" if applied_fields else "matched"
    return updated_facts, field_evidence, profile_status, {
        "matched_profile_key": profile.profile_key,
        "matched_profile_score": match_score,
        "matched_profile_samples": profile.sample_count,
        "profile_applied_fields": applied_fields,
        "profile_hint_fields": hint_fields,
    }


def _normalize_field_value(field_name: str, value: str) -> str:
    if field_name == "supplier_name":
        return _normalize_supplier_name(value)
    if field_name == "supplier_orgnr":
        return _normalize_orgnr(value)
    if field_name == "invoice_number":
        return _normalize_compact_text(value)
    if field_name in {"invoice_date", "due_date"}:
        return _normalize_date_text(value)
    if field_name in {"subtotal_amount", "vat_amount", "total_amount"}:
        return _normalize_amount_text(value)
    if field_name == "currency":
        return _normalize_currency_text(value)
    if field_name in {"description", "period"}:
        return _normalize_whitespace(value)
    return _normalize_whitespace(value)


def _mark_validation(evidence: FieldEvidence | None, matched: bool, note: str) -> None:
    if evidence is None:
        return
    evidence.validated_against_voucher = matched
    evidence.validation_note = note


# ---------------------------------------------------------------------------
# _FIELD_PATTERNS — filled after all normalizer functions are defined
# ---------------------------------------------------------------------------
_FIELD_PATTERNS.update({
    "supplier_orgnr":  (_ORGNR_PATTERNS,   _normalize_orgnr,         0.9),
    "invoice_number":  (_INVOICE_NUMBER_PATTERNS, _normalize_compact_text, 0.8),
    "invoice_date":    (_DATE_PATTERNS,     _normalize_date_text,     0.78),
    "due_date":        (_DUE_DATE_PATTERNS, _normalize_date_text,     0.78),
    "subtotal_amount": (_SUBTOTAL_PATTERNS, _normalize_amount_text,   0.8),
    "vat_amount":      (_VAT_PATTERNS,      _normalize_amount_text,   0.8),
    "total_amount":    (_AMOUNT_PATTERNS,   _normalize_amount_text,   0.86),
    "currency":        (_CURRENCY_PATTERNS, _normalize_currency_text, 0.72),
    "description":     (_DESCRIPTION_PATTERNS, _normalize_whitespace, 0.5),
    "period":          (_PERIOD_PATTERNS,      _normalize_whitespace, 0.5),
})

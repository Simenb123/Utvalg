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

# Scoring + hint-boost + bbox helpers live in ``scoring.py``. Re-exported
# here so legacy call-sites that import them from engine keep working.
from .scoring import (
    _AMOUNT_FIELDS,
    _bbox_for_match_span,
    _bbox_is_near,
    _collect_ranked_candidates,
    _first_match_evidence,
    _match_is_percentage,
    _profile_hint_boost,
    _score_field_match,
)

# Supplier extraction lives in ``supplier.py``.
from .supplier import (
    _extract_supplier_evidence,
    _extract_supplier_from_foretaksregisteret,
    _normalize_supplier_name,
)

# Field-value normalizers live in ``normalizers.py``.
from .normalizers import (
    _MONTH_NAME_TO_NUM,
    _TEXT_DATE_NORM_RE,
    _normalize_amount_text,
    _normalize_compact_text,
    _normalize_currency_text,
    _normalize_date_text,
    _normalize_field_value,
    _normalize_orgnr,
    _parse_amount,
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


_MONTH_NAME_TO_NUM: dict[str, int] = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
    "january": 1, "february": 2, "march": 3, "may": 5,
    "june": 6, "july": 7, "october": 10, "december": 12,
}

def _ev_value(evidence: FieldEvidence | None) -> str:
    if evidence is None:
        return ""
    return evidence.normalized_value or evidence.raw_value or ""


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


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

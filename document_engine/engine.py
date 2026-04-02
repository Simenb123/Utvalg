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

from .models import DocumentAnalysisResult, DocumentFacts, FieldEvidence, SupplierProfile, VoucherContext
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

_NUMBER_FRAGMENT = r"-?\d[\d\s.\u00a0]*(?:[,.]\d{2})"
_COMPANY_SUFFIX_RE = re.compile(r"\b(?:AS|ASA|ENK|AB|OY|LTD|LLC|INC|GMBH|BV|SA|SPA)\b", re.IGNORECASE)
_PDF_TEXT_THRESHOLD = 40

_AMOUNT_PATTERNS = [
    re.compile(
        rf"(?is)\b(?:bel[øo]p\s+å\s+betale|sum\s+å\s+betale|amount\s+due|invoice\s+total|total\s+amount|payable\s+amount|til\s+betaling)\b"
        rf"[^0-9\-]{{0,80}}({_NUMBER_FRAGMENT})"
    ),
    re.compile(rf"(?is)\b(?:sum|total)\b[^0-9\-]{{0,40}}({_NUMBER_FRAGMENT})"),
]
_SUBTOTAL_PATTERNS = [
    re.compile(rf"(?is)\b(?:sum\s+eks(?:l|kl)\.?\s*mva|subtotal|netto|net\s+amount|tax\s+exclusive\s+amount)\b[^0-9\-]{{0,60}}({_NUMBER_FRAGMENT})"),
]
_VAT_PATTERNS = [
    re.compile(rf"(?is)\b(?:mva|vat|merverdiavgift|tax\s+amount|vat\s+base)\b[^0-9\-]{{0,60}}({_NUMBER_FRAGMENT})"),
]
_DATE_PATTERNS = [
    re.compile(r"(?im)\b(?:fakturadato|invoice\s+date|invoice\s+dt|dato)\b[^0-9]{0,20}(\d{1,4}[./-]\d{1,2}[./-]\d{1,4})"),
]
_DUE_DATE_PATTERNS = [
    re.compile(r"(?im)\b(?:forfallsdato|forfall|due\s+date)\b[^0-9]{0,20}(\d{1,4}[./-]\d{1,2}[./-]\d{1,4})"),
]
_INVOICE_NUMBER_PATTERNS = [
    re.compile(
        r"(?im)\b(?:faktura\s*nr\.?|fakturanr\.?|fakturanummer|invoice\s*(?:no|number|nr)\.?|vår\s+referanse)\b"
        r"[^A-Z0-9]{0,10}([A-Z0-9][A-Z0-9\-\/]{2,})"
    ),
    re.compile(
        r"(?im)\binvoice\b(?!\s*(?:date|due|dt))[^A-Z0-9]{0,10}([A-Z0-9][A-Z0-9\-\/]{2,})"
    ),
]
_ORGNR_PATTERNS = [
    re.compile(r"(?im)\b(?:foretaksregisteret|company\s*registration|registration\s*no\.?)\b[^0-9A-Z]{0,30}(?:NO\s*)?((?:\d\s*){9})\s*(?:MVA|VAT)?"),
    re.compile(r"(?im)\b(?:NO\s*)?((?:\d\s*){9})\s*(?:MVA|VAT)\b"),
    re.compile(r"(?im)\b(?:org(?:anisajons)?\.?\s*nr\.?|org\.?\s*no\.?)\b[^0-9]{0,10}((?:\d\s*){9})"),
]
_CURRENCY_PATTERNS = [
    re.compile(r"(?im)\b(NOK|SEK|DKK|EUR|USD|GBP)\b"),
]
_SUPPLIER_LABEL_PATTERNS = [
    re.compile(r"(?im)\b(?:leverand[øo]r|supplier|fra)\b\s*[:\-]?\s*(.+)$"),
    re.compile(r"(?im)\b(?:selger|seller)\b\s*[:\-]?\s*(.+)$"),
]
_INVOICE_PAGE_POSITIVE_PATTERNS = (
    r"\binvoice\b",
    r"\bfaktura\b",
    r"\binvoice\s+date\b",
    r"\bdue\s+date\b",
    r"\binvoice\s+due\s+date\b",
    r"\bterms\s+of\s+payment\b",
    r"\border\s+number\b",
    r"\bcustomer\s+number\b",
    r"\bour\s+ref\b",
    r"\biban\b",
    r"\bswift\b",
    r"\bforetaksregisteret\b",
    r"\btotal\s+amount\b",
    r"\bamount\s+due\b",
    r"\bbank\s+account\b",
)
_INVOICE_PAGE_NEGATIVE_PATTERNS = (
    r"\bbilag\s+nummer\b",
    r"\bkonteringssammendrag\b",
    r"\bopprettet\b",
    r"\bsist\s+endret\b",
    r"\bbilagsgrunnlag\b",
    r"\bregnskapslinjer\b",
)

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


@dataclass
class TextSegment:
    text: str
    source: str
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None


@dataclass
class ExtractedTextResult:
    text: str
    source: str
    ocr_used: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    segments: list[TextSegment] = field(default_factory=list)


@dataclass
class _TextCandidate:
    source: str
    text: str
    ocr_used: bool
    score: float
    segments: list[TextSegment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


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
            )
            metadata.update(profile_metadata)

    validation_messages = build_validation_messages(facts, voucher_context, field_evidence=field_evidence)
    raw_text_excerpt = raw_text[:4000] if raw_text else ""

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
    )


def extract_text_from_file(path: Path) -> ExtractedTextResult:
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
        return _extract_text_from_pdf(path)
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
    ):
        evidence = _first_match_evidence(field_name, patterns, text, ordered_segments, normalizer, score, source_hint)
        if evidence is not None:
            evidence_map[field_name] = evidence

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
        supplier_tokens = [token for token in re.split(r"\s+", facts.supplier_name) if len(token) >= 4]
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


def _extract_text_from_pdf(path: Path) -> ExtractedTextResult:
    page_count = _count_pdf_pages(path)
    candidates: list[_TextCandidate] = []

    _append_candidate(candidates, "pdf_text_pypdf", _extract_pdf_text_with_pypdf(path), False)
    _append_candidate(candidates, "pdf_text_pdfplumber", _extract_pdf_text_with_pdfplumber(path), False)
    _append_candidate(candidates, "pdf_text_fitz_blocks", _extract_pdf_text_with_fitz_blocks(path), False)
    _append_candidate(candidates, "pdf_text_fitz", _extract_pdf_text_with_fitz(path), False)
    _append_candidate(candidates, "pdf_ocrmypdf", _ocr_pdf_with_ocrmypdf(path), True)
    _append_candidate(candidates, "pdf_ocr_fitz", _ocr_pdf_with_fitz(path), True)

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
    return ExtractedTextResult(
        text=best.text,
        source=best.source,
        ocr_used=best.ocr_used,
        metadata={
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
        },
        segments=best.segments,
    )


def _append_candidate(candidates: list[_TextCandidate], source: str, result: tuple[str, list[TextSegment]], ocr_used: bool) -> None:
    text, segments = result
    normalized = _normalize_text_payload(text)
    if not normalized:
        return
    candidates.append(
        _TextCandidate(
            source=source,
            text=normalized,
            ocr_used=ocr_used,
            score=_score_text_candidate(normalized),
            segments=segments,
            metadata={"ocr_engine": "ocrmypdf" if source == "pdf_ocrmypdf" else ("pytesseract" if ocr_used else "text_layer")},
        )
    )


def _normalize_text_payload(text: str) -> str:
    text = text or ""
    text = text.replace("\x00", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _score_text_candidate(text: str) -> float:
    lines = _extract_candidate_lines(text, max_lines=250)
    chars = len(text.strip())
    keyword_hits = sum(
        bool(re.search(pattern, text, re.IGNORECASE))
        for pattern in (
            r"faktura",
            r"invoice",
            r"forfallsdato",
            r"due date",
            r"mva",
            r"vat",
            r"org\.?\s*nr",
            r"bel[øo]p",
            r"total",
        )
    )
    amount_hits = len(re.findall(_NUMBER_FRAGMENT, text, re.IGNORECASE))
    company_hits = sum(bool(_COMPANY_SUFFIX_RE.search(line)) for line in lines[:12])

    score = 0.0
    score += min(chars, 6000) / 70.0
    score += min(len(lines), 80) * 0.8
    score += keyword_hits * 12.0
    score += min(amount_hits, 12) * 2.5
    score += company_hits * 5.0
    if chars < _PDF_TEXT_THRESHOLD:
        score -= 25.0
    if len(lines) <= 2:
        score -= 8.0
    return score


def _count_pdf_pages(path: Path) -> int | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return len(reader.pages)
    except Exception:
        pass

    try:
        import fitz

        with fitz.open(str(path)) as doc:
            return len(doc)
    except Exception:
        return None


def _extract_pdf_text_with_pypdf(path: Path) -> tuple[str, list[TextSegment]]:
    try:
        from pypdf import PdfReader
    except Exception:
        return "", []

    try:
        reader = PdfReader(str(path))
    except Exception:
        return "", []

    segments: list[TextSegment] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            segments.append(TextSegment(text=text, source="pdf_text_pypdf", page=index))
    return "\n".join(segment.text for segment in segments), segments


def _extract_pdf_text_with_pdfplumber(path: Path) -> tuple[str, list[TextSegment]]:
    try:
        import pdfplumber
    except Exception:
        return "", []

    segments: list[TextSegment] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text(layout=True) or page.extract_text() or ""
                except Exception:
                    text = ""
                if text.strip():
                    segments.append(TextSegment(text=text, source="pdf_text_pdfplumber", page=index))
    except Exception:
        return "", []
    return "\n".join(segment.text for segment in segments), segments


def _extract_pdf_text_with_fitz_blocks(path: Path) -> tuple[str, list[TextSegment]]:
    try:
        import fitz
    except Exception:
        return "", []

    segments: list[TextSegment] = []
    try:
        with fitz.open(str(path)) as doc:
            for page_index, page in enumerate(doc, start=1):
                blocks = page.get_text("blocks") or []
                ordered = sorted(
                    (
                        (float(block[1]), float(block[0]), str(block[4]).strip(), tuple(float(value) for value in block[:4]))
                        for block in blocks
                        if len(block) >= 5 and str(block[4]).strip()
                    ),
                    key=lambda item: (round(item[0], 1), round(item[1], 1)),
                )
                for _y, _x, text, bbox in ordered:
                    segments.append(TextSegment(text=text, source="pdf_text_fitz_blocks", page=page_index, bbox=bbox))
    except Exception:
        return "", []
    return "\n".join(segment.text for segment in segments), segments


def _extract_pdf_text_with_fitz(path: Path) -> tuple[str, list[TextSegment]]:
    try:
        import fitz
    except Exception:
        return "", []

    segments: list[TextSegment] = []
    try:
        with fitz.open(str(path)) as doc:
            for page_index, page in enumerate(doc, start=1):
                text = page.get_text() or ""
                if text.strip():
                    segments.append(TextSegment(text=text, source="pdf_text_fitz", page=page_index))
    except Exception:
        return "", []
    return "\n".join(segment.text for segment in segments), segments


def _ocr_pdf_with_ocrmypdf(path: Path) -> tuple[str, list[TextSegment]]:
    if shutil.which("ocrmypdf") is None:
        return "", []

    temp_dir = Path(tempfile.mkdtemp(prefix="utvalg_doc_ocr_"))
    out_pdf = temp_dir / "ocr.pdf"
    try:
        subprocess.run(
            [
                "ocrmypdf",
                "--skip-text",
                "--deskew",
                "--quiet",
                "--language",
                "nor+eng",
                str(path),
                str(out_pdf),
            ],
            check=True,
            timeout=180,
            capture_output=True,
        )
        for extractor in (
            _extract_pdf_text_with_pypdf,
            _extract_pdf_text_with_pdfplumber,
            _extract_pdf_text_with_fitz_blocks,
            _extract_pdf_text_with_fitz,
        ):
            text, segments = extractor(out_pdf)
            if len(text.strip()) >= _PDF_TEXT_THRESHOLD:
                remapped = [
                    TextSegment(text=segment.text, source="pdf_ocrmypdf", page=segment.page, bbox=segment.bbox)
                    for segment in segments
                ]
                return text, remapped
        return "", []
    except Exception:
        return "", []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _ocr_pdf_with_fitz(path: Path) -> tuple[str, list[TextSegment]]:
    try:
        import fitz
    except Exception:
        return "", []

    try:
        from PIL import Image
        import pytesseract
    except Exception:
        return "", []

    segments: list[TextSegment] = []
    try:
        with fitz.open(str(path)) as doc:
            for page_index, page in enumerate(doc, start=1):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                try:
                    text = pytesseract.image_to_string(image, lang="nor+eng") or ""
                except Exception:
                    text = pytesseract.image_to_string(image) or ""
                if text.strip():
                    segments.append(TextSegment(text=text, source="pdf_ocr_fitz", page=page_index))
    except Exception:
        return "", []
    return "\n".join(segment.text for segment in segments), segments


def _ocr_image(path: Path) -> str:
    try:
        from PIL import Image
        import pytesseract
    except Exception as exc:
        raise RuntimeError("OCR krever Pillow og pytesseract.") from exc

    image = Image.open(path)
    try:
        return pytesseract.image_to_string(image, lang="nor+eng") or ""
    except Exception:
        return pytesseract.image_to_string(image) or ""


def _extract_supplier_evidence(text: str, segments: list[TextSegment], source_hint: str) -> FieldEvidence | None:
    for segment in segments or [TextSegment(text=text, source=source_hint)]:
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

    for segment in segments or [TextSegment(text=text, source=source_hint)]:
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


def _first_match_evidence(
    field_name: str,
    patterns: list[re.Pattern[str]] | tuple[re.Pattern[str], ...],
    text: str,
    segments: list[TextSegment],
    normalizer,
    score: float,
    source_hint: str,
) -> FieldEvidence | None:
    candidates: list[tuple[float, FieldEvidence]] = []
    for segment_index, segment in enumerate(segments or [TextSegment(text=text, source=source_hint)]):
        for pattern_index, pattern in enumerate(patterns):
            for match in pattern.finditer(segment.text):
                raw_value = str(match.group(1) or "")
                normalized = normalizer(raw_value)
                if not normalized:
                    continue
                evidence = FieldEvidence(
                    field_name=field_name,
                    normalized_value=normalized,
                    raw_value=raw_value,
                    source=segment.source or source_hint,
                    confidence=score,
                    page=segment.page,
                    bbox=segment.bbox,
                )
                rank = _score_field_match(field_name, evidence, segment_index=segment_index, pattern_index=pattern_index)
                candidates.append((rank, evidence))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _score_field_match(field_name: str, evidence: FieldEvidence, *, segment_index: int, pattern_index: int) -> float:
    rank = 1000.0
    rank -= segment_index * 25.0
    rank -= pattern_index * 10.0

    if field_name in {"total_amount", "subtotal_amount", "vat_amount"}:
        amount = _parse_amount(evidence.normalized_value)
        if amount is not None:
            rank += min(abs(amount), 100000.0) / 100.0
    elif field_name == "invoice_number":
        rank += min(len(evidence.normalized_value), 20)
    elif field_name == "currency":
        rank += 5.0 if evidence.normalized_value in {"NOK", "SEK", "DKK", "EUR", "USD", "GBP"} else 0.0

    return rank


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
    if "firma:" in lowered and "bilag nummer" in lowered:
        score -= 20.0
    return score


def _segment_bonus_count(text: str, patterns: tuple[re.Pattern[str], ...] | list[re.Pattern[str]]) -> int:
    return sum(1 for pattern in patterns if pattern.search(text))


def _extract_candidate_lines(text: str, max_lines: int = 25) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _normalize_whitespace(raw_line)
        if not line:
            continue
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines


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


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_compact_text(value: str) -> str:
    return _normalize_whitespace(value).strip(":.- ")


def _normalize_currency_text(value: str) -> str:
    return _normalize_whitespace(value).upper()


def _normalize_orgnr(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    return digits[:9] if len(digits) >= 9 else digits


def _normalize_date_text(value: str) -> str:
    text = _normalize_whitespace(value)
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
    number = _parse_amount(value)
    if number is None:
        return ""
    return f"{number:.2f}"


def _parse_amount(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[^\d,.\- ]+", "", text)
    text = text.replace(" ", "")
    if text.count(",") > 1 and "." not in text:
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return None


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _apply_supplier_profile_learning(
    facts: DocumentFacts,
    field_evidence: dict[str, FieldEvidence],
    raw_text: str,
    profiles: dict[str, SupplierProfile],
) -> tuple[DocumentFacts, dict[str, FieldEvidence], str, dict[str, Any]]:
    profile, match_score = match_supplier_profile(profiles, facts.as_dict(), raw_text)
    if profile is None:
        return facts, field_evidence, "none", {}

    learned_values = apply_supplier_profile(profile, raw_text)
    applied_fields: list[str] = []
    facts_map = facts.as_dict()

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
    return _normalize_whitespace(value)


def _mark_validation(evidence: FieldEvidence | None, matched: bool, note: str) -> None:
    if evidence is None:
        return
    evidence.validated_against_voucher = matched
    evidence.validation_note = note

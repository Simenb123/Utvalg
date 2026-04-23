"""Supplier-name extraction from invoice text.

Extracts the supplier (vendor) name and primary evidence from a
document's text layer. Uses three prioritised strategies:

1. **Foretaksregisteret footer** — legally-mandated Norwegian footer that
   names the principal supplier (authoritative).
2. **Explicit label patterns** — ``Leverandør:``, ``Supplier:``,
   ``Fra: X``.
3. **Header candidate lines** — top of page, must contain a company
   suffix (``AS``, ``ASA``, ...).
4. **High-uppercase-ratio fallback** — for ALL-CAPS headers without a
   suffix.

All bilagsprint (cover) pages are skipped — supplier names on those
pages belong to the buyer / voucher subject, not the invoice issuer.
"""
from __future__ import annotations

import re

from .bilagsprint import _is_bilagsprint_segment, _segment_is_bilagsprint
from .extractors import _extract_candidate_lines, _normalize_whitespace
from .models import FieldEvidence, TextSegment
from .patterns import _COMPANY_SUFFIX_RE, _SUPPLIER_LABEL_PATTERNS


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

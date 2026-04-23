"""Ranking, scoring and hint-boost logic for field-match candidates.

This module is purely functional: given a set of segments, regex
patterns and optional profile hints, it produces ranked
``FieldEvidence`` candidates. It does not perform any I/O, does not
touch profiles directly, and does not orchestrate extraction.

Inputs come from :mod:`document_engine.extractors` (via ``TextSegment``)
and :mod:`document_engine.patterns` (the regex alternations). Outputs
are consumed by :func:`document_engine.engine.extract_invoice_fields_from_text`
and its ``_with_hints`` variant.

Amount fields (``subtotal_amount``, ``vat_amount``, ``total_amount``)
are singled out in several places because they require stronger
guarantees than text fields — percent-tail rejection, no label-only
hint-boost, and joint self-consistency checks (the last lives in
:mod:`document_engine.amount_consistency`).
"""
from __future__ import annotations

import re
from typing import Any

from .bilagsprint import _is_bilagsprint_segment, _segment_is_bilagsprint
from .models import FieldEvidence, TextSegment
from .patterns import _NUMBER_FRAGMENT  # noqa: F401  (imported for symmetry / use in tests)


# Canonical set of amount field names. Used by scoring logic to apply
# the special rules above (percent rejection, label-only-boost=0, etc.).
_AMOUNT_FIELDS = frozenset({"subtotal_amount", "vat_amount", "total_amount"})


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

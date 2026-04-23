"""Tripletex bilagsprint (accounting cover page) detection.

A Tripletex-sourced PDF typically has one or more "bilagsprint" cover
pages at the top: accounting-entry summaries that are NOT the real
vendor invoice. Field extraction and hint learning must both ignore
these pages or they will learn garbage (``bilag nummer`` as an invoice
label, ``sum debet`` as a total_amount label, accounting-line amounts
as invoice amounts).

Two entry points, both used by the engine:

``_tag_bilagsprint_pages(segments)``
    Classifies pages by their *combined* segment text, then flips
    ``is_bilagsprint_page`` on every segment from a flagged page. This
    is the canonical check: it works correctly on word-level
    extractors (``pdf_text_fitz_words``), where no single segment
    carries both signals at once.

``_segment_is_bilagsprint(segment)``
    Primary per-segment check. Reads the page-level flag set above,
    falling back to text-only detection for segments that never went
    through the full extraction pipeline (synthetic test fixtures).

``_is_bilagsprint_segment(text)``
    Text-only fallback for callers that don't have a ``TextSegment``
    handy. Less reliable than the flag-based path on word-level
    segments, but kept for legacy call-sites.
"""
from __future__ import annotations

from .models import TextSegment
from .patterns import _BILAGSPRINT_NR_RE, _BILAGSPRINT_SIGNAL_RE


def _tag_bilagsprint_pages(segments: list[TextSegment]) -> None:
    """Set ``is_bilagsprint_page=True`` on every segment from a Tripletex
    accounting cover page.

    The classification operates at *page granularity*: all segments on a
    page are combined, and the page is declared a bilagsprint when the
    combined text carries both a ``bilag nummer <digits>`` marker and a
    kontering-summary signal (``konteringssammendrag``, ``sum debet``,
    ``sum kredit``, ``kontostrengen``). This is the only way to correctly
    classify word-level extractors: a single word-line almost never
    contains both signals, so per-segment classification would leak
    cover-page values into amount-extraction and hint-learning.
    """
    if not segments:
        return
    pages: dict[int | None, list[TextSegment]] = {}
    for s in segments:
        pages.setdefault(s.page, []).append(s)
    flagged_pages: set[int | None] = set()
    for page, segs in pages.items():
        if page is None:
            continue
        combined = "\n".join(s.text for s in segs).lower()
        if _BILAGSPRINT_NR_RE.search(combined) and _BILAGSPRINT_SIGNAL_RE.search(combined):
            flagged_pages.add(page)
    if not flagged_pages:
        return
    for s in segments:
        if s.page in flagged_pages:
            s.is_bilagsprint_page = True


def _is_bilagsprint_segment(text: str) -> bool:
    """Return True when *text* itself carries both bilagsprint signals.

    This is the fallback check used when only the text of a segment is
    available. Single word-level lines rarely satisfy both conditions at
    once, so callers that have a :class:`TextSegment` should prefer
    :func:`_segment_is_bilagsprint` — it consults the segment's
    ``is_bilagsprint_page`` flag first, which is set per-page during
    extraction and correctly covers word-level segments too.
    """
    lowered = text.lower()
    has_bilag_nr = bool(_BILAGSPRINT_NR_RE.search(lowered))
    has_kontering = bool(_BILAGSPRINT_SIGNAL_RE.search(lowered))
    return has_bilag_nr and has_kontering


def _segment_is_bilagsprint(segment: TextSegment) -> bool:
    """Return True if *segment* belongs to a Tripletex bilagsprint page.

    Checks the per-page flag set by :func:`_tag_bilagsprint_pages`
    first; falls back to text-level detection for segments produced
    without a full extraction pipeline (e.g. synthetic test fixtures
    or the rare case where ``_tag_bilagsprint_pages`` was skipped).
    """
    if getattr(segment, "is_bilagsprint_page", False):
        return True
    return _is_bilagsprint_segment(segment.text)

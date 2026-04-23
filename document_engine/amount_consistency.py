"""Amount self-consistency and redo-OCR decision logic.

Three concerns live here, all related to the ``subtotal + vat ≈ total``
invariant on invoices:

1. **Self-consistency check** — does the extracted trio add up? Used by
   ``analyze_document`` to annotate evidence and by the redo-OCR
   decision logic.

2. **Redo-OCR triggers** — when the trio doesn't add up, should we
   trust the existing text layer or retry OCR? Controlled by score
   gates and deviation thresholds so we don't re-OCR every PDF with
   a noisy amount.

3. **Joint amount selection** — when the individually-picked top
   candidates are inconsistent, can we find a better combination by
   exploring the top-K candidates per field and selecting a consistent
   triple? This is the safety net for invoices where pattern-matching
   alone lands on the wrong row.
"""
from __future__ import annotations

from typing import Any

from .format_utils import (
    normalize_amount_text as _normalize_amount_text,
    parse_amount_flexible as _parse_amount,
)
from .models import ExtractedTextResult, FieldEvidence, TextSegment
from .patterns import _AMOUNT_PATTERNS, _SUBTOTAL_PATTERNS, _VAT_PATTERNS


_AMOUNT_SELF_CONSISTENCY_TOLERANCE = 1.0

# Guard rails for the amount-driven redo-OCR fallback:
#  - don't bother re-OCR'ing a PDF whose text layer is already strong enough
#    that the mismatch is more likely a parsing issue than an OCR issue,
#  - unless the deviation is so large (absolute or relative) that the
#    correct value must have been mis-read.
_OCR_REDO_AMOUNT_SCORE_GATE = 60.0
_OCR_REDO_AMOUNT_ABS_THRESHOLD = 100.0
_OCR_REDO_AMOUNT_REL_THRESHOLD = 0.10  # 10 % of total


def _ev_value(evidence: FieldEvidence | None) -> str:
    if evidence is None:
        return ""
    return evidence.normalized_value or evidence.raw_value or ""


def _amounts_self_consistent(
    evidence_map: dict[str, FieldEvidence],
    *,
    tolerance: float = _AMOUNT_SELF_CONSISTENCY_TOLERANCE,
) -> bool | None:
    """Pure predicate mirror of :func:`_validate_amount_self_consistency`.

    Returns True/False when all three amounts are present and parseable,
    None when the check cannot be run. Does NOT mutate evidences.
    """
    st = _parse_amount(_ev_value(evidence_map.get("subtotal_amount")))
    vt = _parse_amount(_ev_value(evidence_map.get("vat_amount")))
    tt = _parse_amount(_ev_value(evidence_map.get("total_amount")))
    if st is None or vt is None or tt is None:
        return None
    return abs((st + vt) - tt) <= tolerance


def _should_redo_ocr_for_amounts(
    evidence_map: dict[str, FieldEvidence],
    extracted: ExtractedTextResult,
) -> bool:
    """Decide whether amount-inconsistency is worth a redo-OCR round."""
    # Already retried in the low-score fallback → don't loop.
    cand_sources = extracted.metadata.get("candidate_sources") or []
    for cand in cand_sources:
        if isinstance(cand, dict) and cand.get("source") == "pdf_ocrmypdf_redo":
            return False
    st = _parse_amount(_ev_value(evidence_map.get("subtotal_amount")))
    vt = _parse_amount(_ev_value(evidence_map.get("vat_amount")))
    tt = _parse_amount(_ev_value(evidence_map.get("total_amount")))
    if st is None or vt is None or tt is None:
        return False
    deviation = abs((st + vt) - tt)
    if deviation <= _AMOUNT_SELF_CONSISTENCY_TOLERANCE:
        return False
    selected_score = float(extracted.metadata.get("selected_score", 0.0) or 0.0)
    if selected_score < _OCR_REDO_AMOUNT_SCORE_GATE:
        return True
    # Score looks healthy but numbers don't add up — only trust OCR as the
    # culprit when the gap is materially large.
    if deviation >= _OCR_REDO_AMOUNT_ABS_THRESHOLD:
        return True
    if abs(tt) > 0 and deviation / abs(tt) >= _OCR_REDO_AMOUNT_REL_THRESHOLD:
        return True
    return False


def _is_redo_extraction_better(
    new_evidence: dict[str, FieldEvidence],
    old_evidence: dict[str, FieldEvidence],
) -> bool:
    """Prefer redo-OCR only when it genuinely improves the amounts.

    Rules:
      * redo consistent, old inconsistent → use redo
      * redo consistent, old unknown      → use redo (redo filled a missing
        field and stayed consistent)
      * redo inconsistent                 → never promote over old
    """
    new_verdict = _amounts_self_consistent(new_evidence)
    old_verdict = _amounts_self_consistent(old_evidence)
    if new_verdict is True and old_verdict is False:
        return True
    if new_verdict is True and old_verdict is None:
        return True
    return False


def _validate_amount_self_consistency(
    evidence_map: dict[str, FieldEvidence],
    *,
    tolerance: float = _AMOUNT_SELF_CONSISTENCY_TOLERANCE,
) -> bool | None:
    """Cross-check ``subtotal + vat ≈ total`` inside the invoice itself.

    Sets ``metadata["self_consistent"]`` (True|False) on all three amount
    evidences when all three are present. Does NOT mutate the values — we
    only flag so downstream logic (and the UI) can decide whether to demote
    confidence or warn the user. Returns the verdict, or None if the check
    could not run (a field was missing / unparseable).
    """
    st = _parse_amount(_ev_value(evidence_map.get("subtotal_amount")))
    vt = _parse_amount(_ev_value(evidence_map.get("vat_amount")))
    tt = _parse_amount(_ev_value(evidence_map.get("total_amount")))
    if st is None or vt is None or tt is None:
        return None
    consistent = abs((st + vt) - tt) <= tolerance
    note_snippet = f"Intern kontroll: {st:.2f} + {vt:.2f} = {st + vt:.2f} vs total {tt:.2f}"
    for fname in ("subtotal_amount", "vat_amount", "total_amount"):
        ev = evidence_map.get(fname)
        if ev is None:
            continue
        ev.metadata["self_consistent"] = consistent
        if not consistent:
            existing = (ev.validation_note or "").strip()
            suffix = f"[Avvik — {note_snippet}]"
            ev.validation_note = f"{existing} {suffix}".strip() if existing else suffix
    return consistent


def _select_self_consistent_amounts(
    sub_cands: list[tuple[float, FieldEvidence]],
    vat_cands: list[tuple[float, FieldEvidence]],
    tot_cands: list[tuple[float, FieldEvidence]],
    *,
    top_k: int = 6,
    tolerance: float = _AMOUNT_SELF_CONSISTENCY_TOLERANCE,
) -> tuple[FieldEvidence, FieldEvidence, FieldEvidence] | None:
    """Pick a ``(subtotal, vat, total)`` triple where ``s + v ≈ t`` holds.

    Takes the top-K ranked candidates per field (deduplicated by parsed
    numeric value — same amount at different bboxes collapses to one entry),
    enumerates all combinations, and returns the consistent combination with
    the lowest rank-position sum. Lower position = higher-ranked individual
    candidate, so hint-boosted values still win when a consistent combo
    exists. Returns ``None`` when no consistent triple can be formed.
    """
    def _dedupe(cands: list[tuple[float, FieldEvidence]]) -> list[tuple[int, float, FieldEvidence]]:
        seen: set[str] = set()
        out: list[tuple[int, float, FieldEvidence]] = []
        for rank, ev in cands:
            parsed = _parse_amount(ev.normalized_value)
            if parsed is None:
                continue
            key = f"{parsed:.4f}"
            if key in seen:
                continue
            seen.add(key)
            out.append((len(out), rank, ev))
            if len(out) >= top_k:
                break
        return out

    sub_top = _dedupe(sub_cands)
    vat_top = _dedupe(vat_cands)
    tot_top = _dedupe(tot_cands)
    if not (sub_top and vat_top and tot_top):
        return None

    best_key: tuple[int, float] | None = None
    best: tuple[FieldEvidence, FieldEvidence, FieldEvidence] | None = None
    for si, s_rank, s_ev in sub_top:
        s_val = _parse_amount(s_ev.normalized_value)
        if s_val is None:
            continue
        for vi, v_rank, v_ev in vat_top:
            v_val = _parse_amount(v_ev.normalized_value)
            if v_val is None:
                continue
            for ti, t_rank, t_ev in tot_top:
                t_val = _parse_amount(t_ev.normalized_value)
                if t_val is None:
                    continue
                if abs((s_val + v_val) - t_val) > tolerance:
                    continue
                idx_sum = si + vi + ti
                rank_sum = s_rank + v_rank + t_rank
                key = (idx_sum, -rank_sum)
                if best_key is None or key < best_key:
                    best_key = key
                    best = (s_ev, v_ev, t_ev)
    return best


def _apply_joint_amount_selection(
    evidence_map: dict[str, FieldEvidence],
    text: str,
    segments: list[TextSegment],
    source_hint: str,
    *,
    profile_hints: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    """Override independently-picked amounts with a self-consistent triple.

    Runs after per-field selection. Exits early when any of the three fields
    is missing or when the picked amounts already satisfy ``s + v ≈ t``.
    Otherwise it gathers top-K candidates per field and picks the consistent
    combination (see :func:`_select_self_consistent_amounts`). Each swapped
    evidence is tagged with ``metadata["selected_by"] = "joint_amount_ranking"``.
    """
    if not all(k in evidence_map for k in ("subtotal_amount", "vat_amount", "total_amount")):
        return
    if _amounts_self_consistent(evidence_map) is True:
        return

    # Lazy import to avoid module-level circular dependency with engine.
    # Engine imports this module at the top, so we can't import engine
    # symbols at the top of this file.
    from .engine import _collect_ranked_candidates

    hints = profile_hints or {}
    sub_cands = _collect_ranked_candidates(
        "subtotal_amount", _SUBTOTAL_PATTERNS, text, segments,
        _normalize_amount_text, 0.8, source_hint,
        profile_hints=hints.get("subtotal_amount"),
    )
    vat_cands = _collect_ranked_candidates(
        "vat_amount", _VAT_PATTERNS, text, segments,
        _normalize_amount_text, 0.8, source_hint,
        profile_hints=hints.get("vat_amount"),
    )
    tot_cands = _collect_ranked_candidates(
        "total_amount", _AMOUNT_PATTERNS, text, segments,
        _normalize_amount_text, 0.86, source_hint,
        profile_hints=hints.get("total_amount"),
    )
    selection = _select_self_consistent_amounts(sub_cands, vat_cands, tot_cands)
    if selection is None:
        return
    sub_ev, vat_ev, tot_ev = selection
    for fname, new_ev in (
        ("subtotal_amount", sub_ev),
        ("vat_amount", vat_ev),
        ("total_amount", tot_ev),
    ):
        old_ev = evidence_map.get(fname)
        if old_ev is None or old_ev.normalized_value != new_ev.normalized_value:
            new_ev.metadata = dict(new_ev.metadata or {})
            new_ev.metadata["selected_by"] = "joint_amount_ranking"
            evidence_map[fname] = new_ev

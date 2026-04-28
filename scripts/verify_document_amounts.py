"""Diagnostic runner for document amount extraction.

Runs ``analyze_document()`` against one or more PDF/XML files WITHOUT
writing to any store, and prints everything needed to decide whether the
current pipeline picks the right subtotal/MVA/total and whether
redo-OCR / self-consistency / bbox tightness behave as expected on real
bilag.

This is the Phase 3 verification gate: if Brage + a bad-OCR Tripletex
print both show correct, self-consistent amounts with tight per-value
bboxes, the planned joint amount-ranking refactor is not needed.

Usage
-----
    py scripts/verify_document_amounts.py path/to/brage.pdf
    py scripts/verify_document_amounts.py --with-profiles path/to/*.pdf
    py scripts/verify_document_amounts.py --json path/to/file.pdf

``--with-profiles`` loads the saved supplier profiles from the default
store so profile-hint boosting participates. Without it you get the
pre-learning behaviour — useful for reproducing what happens on a fresh
install.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from document_engine.engine import analyze_document
from document_engine.models import FieldEvidence, SupplierProfile

AMOUNT_FIELDS = ("subtotal_amount", "vat_amount", "total_amount")

# Sources we consider "risky to learn from": voucher covers / Tripletex
# bilagsprint, low-signal OCR, etc. A run containing these is not
# guaranteed wrong, but it is exactly the shape we saw drive bad hints
# into learned profiles — so --fail-on-risk rejects them.
_RISKY_SOURCES = {"pdf_voucher_print", "pdf_cover", "bilagsprint"}
# Bbox width (pt) above which we assume the extractor matched a full
# table row rather than a single amount cell.
_RISKY_BBOX_WIDTH_PT = 140.0


def _fmt_bbox(bbox: tuple[float, float, float, float] | None) -> str:
    if not bbox:
        return "—"
    x0, y0, x1, y1 = bbox
    return f"({x0:.1f},{y0:.1f})–({x1:.1f},{y1:.1f}) w={x1 - x0:.1f}"


def _load_profiles() -> dict[str, SupplierProfile] | None:
    try:
        from src.shared.document_control.store import load_supplier_profiles
    except Exception as exc:
        print(f"[warn] could not import src.shared.document_control.store as document_control_store: {exc}", file=sys.stderr)
        return None
    raw = load_supplier_profiles() or {}
    out: dict[str, SupplierProfile] = {}
    for key, payload in raw.items():
        profile = SupplierProfile.from_dict(payload)
        if profile is not None:
            out[key] = profile
    return out


def _evidence_summary(key: str, ev: FieldEvidence | None) -> dict[str, Any]:
    if ev is None:
        return {"field": key, "value": None}
    bbox = ev.bbox
    width = (bbox[2] - bbox[0]) if bbox else None
    return {
        "field": key,
        "value": ev.normalized_value or ev.raw_value,
        "source": ev.source,
        "confidence": round(ev.confidence, 3),
        "page": ev.page,
        "bbox": bbox,
        "bbox_width": round(width, 1) if width is not None else None,
        "inferred_from_profile": ev.inferred_from_profile,
        "self_consistent": ev.metadata.get("self_consistent"),
        "validation_note": ev.validation_note or "",
    }


def _candidate_summary(cands: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in cands or []:
        out.append({
            "source": c.get("source"),
            "score": c.get("score"),
            "ocr_used": c.get("ocr_used"),
            "char_count": c.get("char_count"),
            "segment_count": c.get("segment_count"),
        })
    return out


def _analyze(path: Path, profiles: dict[str, SupplierProfile] | None) -> dict[str, Any]:
    result = analyze_document(path, profiles=profiles)
    md = result.metadata or {}
    report = {
        "file": str(path),
        "file_type": result.file_type,
        "source": result.source,
        "selected_score": md.get("selected_score"),
        "ocr_used": md.get("ocr_used"),
        "ocr_engine": md.get("ocr_engine"),
        "profile_status": result.profile_status,
        "redo": {
            "triggered_by": md.get("ocr_redo_triggered_by"),
            "attempted": md.get("ocr_redo_attempted"),
            "chosen": md.get("ocr_redo_chosen"),
            "requested_but_missing": md.get("ocr_redo_requested_but_missing"),
        },
        "amount_self_consistent": md.get("amount_self_consistent"),
        "amounts": [
            _evidence_summary(f, result.field_evidence.get(f)) for f in AMOUNT_FIELDS
        ],
        "candidates": _candidate_summary(md.get("candidate_sources")),
        "validation_messages": list(result.validation_messages or []),
    }
    return report


def _risk_reasons(report: dict[str, Any]) -> list[str]:
    """Return the list of "unsafe to learn from" reasons for *report*.

    A report is "at risk" iff any of the following holds:
      - ``amount_self_consistent`` is False (or None because a field is
        missing — a learn based on missing data is worse than a skip).
      - Any of subtotal/vat/total amount fields has no ``page`` or no
        ``bbox`` — downstream hint inference needs both.
      - Any amount field's ``bbox_width`` exceeds the risky threshold.
      - Redo-OCR was wanted but ``ocrmypdf`` was not available.
      - The selected extraction source is on the risky-source list (e.g.
        Tripletex voucher cover), which means the selected text is
        probably from the cover page rather than the actual invoice.
    """
    reasons: list[str] = []
    cons = report.get("amount_self_consistent")
    if cons is False:
        reasons.append("amounts not self-consistent (subtotal+vat != total)")
    elif cons is None:
        reasons.append("amounts not self-consistent (one of subtotal/vat/total missing)")

    amounts = report.get("amounts") or []
    for a in amounts:
        if a["value"] is None:
            reasons.append(f"{a['field']}: not extracted")
            continue
        if a.get("page") is None:
            reasons.append(f"{a['field']}: missing page")
        if a.get("bbox") is None:
            reasons.append(f"{a['field']}: missing bbox")
        width = a.get("bbox_width")
        if width is not None and width > _RISKY_BBOX_WIDTH_PT:
            reasons.append(f"{a['field']}: bbox too wide ({width} > {_RISKY_BBOX_WIDTH_PT})")

    redo = report.get("redo") or {}
    if redo.get("requested_but_missing"):
        reasons.append("redo-OCR wanted but ocrmypdf is missing")

    source = (report.get("source") or "").strip().lower()
    if source in _RISKY_SOURCES:
        reasons.append(f"risky source: {source!r}")
    return reasons


def _print_report(report: dict[str, Any]) -> None:
    print("=" * 78)
    print(f"  {report['file']}")
    print("-" * 78)
    print(f"  source:              {report['source']!r}  "
          f"(score={report['selected_score']}, ocr_used={report['ocr_used']}, "
          f"engine={report['ocr_engine']})")
    print(f"  profile_status:      {report['profile_status']!r}")
    print(f"  amount_self_cons:    {report['amount_self_consistent']!r}")
    redo = report["redo"]
    if any(v is not None for v in redo.values()):
        print(f"  redo:                triggered_by={redo['triggered_by']!r} "
              f"attempted={redo['attempted']!r} chosen={redo['chosen']!r} "
              f"missing={redo['requested_but_missing']!r}")
    print()
    print("  Candidates (ranked by score):")
    for c in report["candidates"]:
        print(f"    {c['source']:<26} score={c['score']:<7} "
              f"chars={c['char_count']:<6} segs={c['segment_count']:<4} "
              f"ocr_used={c['ocr_used']}")
    print()
    print("  Amount fields:")
    for a in report["amounts"]:
        if a["value"] is None:
            print(f"    {a['field']:<18} <not extracted>")
            continue
        print(f"    {a['field']:<18} {a['value']!r:<14} "
              f"page={a['page']} bbox={_fmt_bbox(a['bbox'])}")
        print(f"    {'':<18}   source={a['source']!r} "
              f"conf={a['confidence']} self_cons={a['self_consistent']!r} "
              f"from_profile={a['inferred_from_profile']}")
        if a["validation_note"]:
            print(f"    {'':<18}   note: {a['validation_note']}")
    if report["validation_messages"]:
        print()
        print("  Validation messages:")
        for m in report["validation_messages"]:
            print(f"    - {m}")
    if report.get("risk_reasons"):
        print()
        print("  Risk flags (would block --fail-on-risk):")
        for r in report["risk_reasons"]:
            print(f"    ! {r}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="PDF/XML files to analyse")
    parser.add_argument("--with-profiles", action="store_true",
                        help="Load saved supplier profiles from the default store")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON (one object per file) instead of the human-readable report")
    parser.add_argument("--fail-on-risk", action="store_true",
                        help=("Exit with non-zero status if any analysed file trips a risk flag "
                              "(missing page/bbox, wide bbox, amounts not self-consistent, "
                              "redo-OCR wanted but missing, cover/voucher-print source). "
                              "Use this in CI to block dataset sweeps against risky inputs."))
    args = parser.parse_args(argv)

    profiles = _load_profiles() if args.with_profiles else None
    if args.with_profiles:
        print(f"[info] loaded {len(profiles or {})} supplier profile(s)",
              file=sys.stderr)

    reports: list[dict[str, Any]] = []
    for raw_path in args.paths:
        path = Path(raw_path).expanduser()
        if not path.exists():
            print(f"[error] not found: {path}", file=sys.stderr)
            continue
        try:
            report = _analyze(path, profiles)
        except Exception as exc:
            print(f"[error] {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        report["risk_reasons"] = _risk_reasons(report)
        reports.append(report)
        if not args.json:
            _print_report(report)

    if args.json:
        print(json.dumps(reports, indent=2, ensure_ascii=False, default=str))

    if not reports:
        return 1

    if args.fail_on_risk:
        risky = [r for r in reports if r.get("risk_reasons")]
        if risky:
            print(
                f"[fail-on-risk] {len(risky)} of {len(reports)} file(s) tripped risk flags",
                file=sys.stderr,
            )
            for r in risky:
                print(f"  - {r['file']}: {len(r['risk_reasons'])} flag(s)", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

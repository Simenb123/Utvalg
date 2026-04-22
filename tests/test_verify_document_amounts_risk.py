"""Tests for the --fail-on-risk risk detector in verify_document_amounts.

The detector is the gate we run before mass dataset sweeps: if it
returns any reasons, the sweep must stop. The cases below are the
specific shapes the plan called out as "would have slipped through
before".
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from verify_document_amounts import _risk_reasons  # noqa: E402


def _amount(value: float | str, *, page: int | None = 1,
            bbox: tuple[float, float, float, float] | None = (100, 400, 180, 412),
            bbox_width: float | None = 80.0) -> dict:
    return {
        "field": "total_amount",
        "value": value,
        "source": "pdf_text_fitz",
        "confidence": 0.9,
        "page": page,
        "bbox": bbox,
        "bbox_width": bbox_width,
        "inferred_from_profile": False,
        "self_consistent": True,
        "validation_note": "",
    }


def _clean_report(**overrides) -> dict:
    report = {
        "file": "bilag.pdf",
        "source": "pdf_text_fitz",
        "amount_self_consistent": True,
        "amounts": [
            dict(_amount(1175.0), field="total_amount"),
            dict(_amount(235.0), field="vat_amount"),
            dict(_amount(940.0), field="subtotal_amount"),
        ],
        "redo": {"requested_but_missing": None},
    }
    report.update(overrides)
    return report


def test_clean_report_has_no_risk_reasons() -> None:
    assert _risk_reasons(_clean_report()) == []


def test_flags_amounts_not_self_consistent() -> None:
    reasons = _risk_reasons(_clean_report(amount_self_consistent=False))
    assert any("not self-consistent" in r for r in reasons)


def test_flags_missing_field() -> None:
    report = _clean_report()
    report["amount_self_consistent"] = None
    report["amounts"][0]["value"] = None  # total missing
    reasons = _risk_reasons(report)
    assert any("not self-consistent" in r for r in reasons)
    assert any("total_amount: not extracted" in r for r in reasons)


def test_flags_missing_bbox() -> None:
    report = _clean_report()
    report["amounts"][0]["bbox"] = None
    reasons = _risk_reasons(report)
    assert any("missing bbox" in r for r in reasons)


def test_flags_missing_page() -> None:
    report = _clean_report()
    report["amounts"][0]["page"] = None
    reasons = _risk_reasons(report)
    assert any("missing page" in r for r in reasons)


def test_flags_too_wide_bbox() -> None:
    report = _clean_report()
    report["amounts"][0]["bbox_width"] = 250.0
    reasons = _risk_reasons(report)
    assert any("bbox too wide" in r for r in reasons)


def test_flags_redo_requested_but_missing() -> None:
    report = _clean_report()
    report["redo"]["requested_but_missing"] = True
    reasons = _risk_reasons(report)
    assert any("ocrmypdf is missing" in r for r in reasons)


def test_flags_risky_source() -> None:
    report = _clean_report(source="pdf_voucher_print")
    reasons = _risk_reasons(report)
    assert any("risky source" in r for r in reasons)

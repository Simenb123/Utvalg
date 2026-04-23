"""Tests for ``scripts/clean_profile_labels.py``.

The cleanup script has two invariants that matter:
  1. ``sample_count`` is NEVER modified.
  2. The ``profiles_losing_all_hints_by_field`` signal must be correct,
     because that is what humans read to decide whether to proceed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import pytest

import clean_profile_labels  # noqa: E402
from clean_profile_labels import (  # noqa: E402
    build_report,
    clean_profile_field_hints,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _profile(key: str, sample_count: int, field_hints: dict) -> dict:
    return {
        "profile_key": key,
        "supplier_name": f"Name {key}",
        "supplier_orgnr": "",
        "aliases": [],
        "sample_count": sample_count,
        "field_hints": field_hints,
        "static_fields": {},
        "schema_version": 1,
    }


def _hint(label: str, page: int | None = 1, count: int = 1) -> dict:
    return {"label": label, "page": page, "bbox": None, "count": count}


# ---------------------------------------------------------------------------
# clean_profile_field_hints
# ---------------------------------------------------------------------------

def test_removes_cover_page_labels_from_total_amount() -> None:
    profile = _profile("orgnr:111111111", 10, {
        "total_amount": [
            _hint("sum debet", count=42),
            _hint("sum", count=7),
            _hint("bilag nummer 135-2", count=4),
        ],
    })
    new_hints, removed = clean_profile_field_hints(profile)

    labels = [h["label"] for h in new_hints.get("total_amount", [])]
    assert labels == ["sum"], labels
    removed_labels = {lbl for _, lbl, _ in removed}
    assert "sum debet" in removed_labels
    assert any("bilag nummer" in r for r in removed_labels)


def test_removes_address_label_from_subtotal() -> None:
    profile = _profile("orgnr:222222222", 5, {
        "subtotal_amount": [
            _hint("153 poulssons kvarter 1", count=7),
            _hint("netto", count=3),
        ],
    })
    new_hints, _ = clean_profile_field_hints(profile)
    labels = [h["label"] for h in new_hints["subtotal_amount"]]
    assert labels == ["netto"]


def test_removes_swift_header_from_currency() -> None:
    profile = _profile("orgnr:333333333", 5, {
        "currency": [
            _hint("swift/bic dnba", count=99),
            _hint("dnba", count=40),
            _hint("valuta", count=20),
            _hint("nok", count=5),
        ],
    })
    new_hints, _ = clean_profile_field_hints(profile)
    labels = {h["label"] for h in new_hints["currency"]}
    assert labels == {"valuta", "nok"}


def test_duplicate_entries_with_same_label_page_are_merged() -> None:
    """Legacy doubles where the same (label, page) tuple was stored twice
    should collapse — counts are summed."""
    profile = _profile("orgnr:444444444", 10, {
        "invoice_number": [
            _hint("fakturanr", page=1, count=3),
            _hint("FAKTURANR", page=1, count=5),   # same after normalize
        ],
    })
    new_hints, _ = clean_profile_field_hints(profile)
    assert len(new_hints["invoice_number"]) == 1
    assert new_hints["invoice_number"][0]["count"] == 8


def test_page_none_and_page_n_are_kept_separate() -> None:
    """Engangs-konsolidering (page=None vs page=N) is a separate step —
    the cleanup validator itself must NOT fold them, so count semantics
    stay predictable."""
    profile = _profile("orgnr:555555555", 10, {
        "invoice_number": [
            _hint("fakturanr", page=None, count=4),
            _hint("fakturanr", page=1, count=7),
        ],
    })
    new_hints, _ = clean_profile_field_hints(profile)
    assert len(new_hints["invoice_number"]) == 2
    pages = {h["page"] for h in new_hints["invoice_number"]}
    assert pages == {None, 1}


def test_preserves_hints_that_already_pass_policy() -> None:
    profile = _profile("orgnr:666666666", 5, {
        "invoice_date": [_hint("dato", count=10)],
        "due_date": [_hint("forfallsdato", count=8)],
    })
    new_hints, removed = clean_profile_field_hints(profile)
    assert removed == []
    assert new_hints["invoice_date"][0]["count"] == 10
    assert new_hints["due_date"][0]["count"] == 8


# ---------------------------------------------------------------------------
# build_report — end-to-end behaviour
# ---------------------------------------------------------------------------

def test_build_report_never_touches_sample_count() -> None:
    store = {
        "profiles": {
            "orgnr:111111111": _profile("A", 52, {
                "total_amount": [
                    _hint("sum debet", count=42),
                    _hint("sum", count=3),
                ],
            }),
        },
    }
    before_samples = store["profiles"]["orgnr:111111111"]["sample_count"]
    report, new_store = build_report(store, Path("/tmp/fake.json"), applied=False)

    after_samples = new_store["profiles"]["orgnr:111111111"]["sample_count"]
    assert after_samples == before_samples == 52
    # And on the report itself
    assert report.per_profile[0].sample_count == 52


def test_build_report_flags_profile_losing_all_total_amount_hints() -> None:
    """The critical signal: a profile whose every total_amount hint is
    noise must surface in ``profiles_losing_all_hints_by_field``."""
    store = {
        "profiles": {
            "orgnr:111111111": _profile("A", 20, {
                "total_amount": [
                    _hint("sum debet", count=10),
                    _hint("bilag nummer", count=2),
                ],
                # invoice_number is fine — must NOT be flagged
                "invoice_number": [_hint("fakturanr", count=5)],
            }),
            "orgnr:222222222": _profile("B", 10, {
                "total_amount": [_hint("sum", count=4)],   # keeps its hint
            }),
        },
    }
    report, new_store = build_report(store, Path("/tmp/fake.json"), applied=False)

    losers = report.profiles_losing_all_hints_by_field
    assert losers.get("total_amount") == ["orgnr:111111111"]
    assert "invoice_number" not in losers   # A still has fakturanr

    # The new store for A should have zero total_amount hints but still
    # hold its invoice_number hint.
    a_after = new_store["profiles"]["orgnr:111111111"]["field_hints"]
    assert "total_amount" not in a_after or a_after["total_amount"] == []
    assert a_after.get("invoice_number")


def test_build_report_top_removed_aggregates_across_profiles() -> None:
    store = {
        "profiles": {
            f"orgnr:{i * 111}": _profile(f"P{i}", 5, {
                "total_amount": [_hint("sum debet", count=10)],
            })
            for i in range(1, 4)  # three profiles, same noisy label
        },
    }
    report, _ = build_report(store, Path("/tmp/fake.json"), applied=False)

    # Aggregated across all profiles: sum debet removed 30 times total
    entries = [(f, l, c) for f, l, c in report.top_removed if l == "sum debet"]
    assert entries == [("total_amount", "sum debet", 30)]


def test_build_report_leaves_global_profile_untouched() -> None:
    store = {
        "profiles": {
            "__global__": {
                "profile_key": "__global__",
                "supplier_name": "",
                "supplier_orgnr": "",
                "aliases": [],
                "sample_count": 0,
                "field_hints": {
                    "total_amount": [_hint("sum debet", count=99)],
                },
                "static_fields": {},
                "schema_version": 1,
            },
            "orgnr:111111111": _profile("A", 10, {
                "total_amount": [_hint("sum", count=3)],
            }),
        },
    }
    report, new_store = build_report(store, Path("/tmp/fake.json"), applied=False)

    # Global is preserved verbatim — the repo regenerates it on next save.
    assert new_store["profiles"]["__global__"]["field_hints"]["total_amount"]
    # Global is NOT counted in profiles_scanned
    assert report.profiles_scanned == 1


def test_build_report_does_not_mutate_input_store() -> None:
    store = {
        "profiles": {
            "orgnr:111111111": _profile("A", 10, {
                "total_amount": [_hint("sum debet", count=42)],
            }),
        },
    }
    snapshot = json.loads(json.dumps(store))
    build_report(store, Path("/tmp/fake.json"), applied=False)
    assert store == snapshot, "build_report must not mutate input"


# ---------------------------------------------------------------------------
# --apply path
# ---------------------------------------------------------------------------

def test_apply_writes_backup_and_preserves_sample_count(
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "store.json"
    store_path.write_text(json.dumps({
        "records": {},
        "profiles": {
            "orgnr:111111111": _profile("A", 77, {
                "invoice_number": [_hint("fakturanr", count=10)],
                "total_amount": [
                    _hint("sum debet", count=42),  # noise
                    _hint("sum", count=5),
                ],
            }),
        },
    }), encoding="utf-8")

    rc = clean_profile_labels.main(["--store", str(store_path), "--apply"])
    assert rc == 0

    backups = list(tmp_path.glob("store.backup_*.json"))
    assert len(backups) == 1

    written = json.loads(store_path.read_text(encoding="utf-8"))
    profile = written["profiles"]["orgnr:111111111"]
    assert profile["sample_count"] == 77  # never touched

    totals = profile["field_hints"].get("total_amount", [])
    labels = {h["label"] for h in totals}
    assert labels == {"sum"}
    assert all("sum debet" not in h["label"] for h in totals)

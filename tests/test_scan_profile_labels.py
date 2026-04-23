"""Unit tests for ``scripts/scan_profile_labels.py``.

The scanner is strictly read-only, so the tests only exercise the pure
aggregation and noise-classification logic — no file IO required.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import pytest

import scan_profile_labels  # noqa: E402
from scan_profile_labels import (  # noqa: E402
    _classify_noise,
    render_json,
    render_text,
    scan_store,
)


# ---------------------------------------------------------------------------
# _classify_noise
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label, field, expected_flag",
    [
        ("bilag nummer", "total_amount", "bilagsprint:bilag nummer"),
        ("bilag nummer 292-20", "vat_amount", "bilagsprint:bilag nummer"),
        ("sum debet", "total_amount", "bilagsprint:sum debet"),
        ("153 poulssons kvarter 1", "subtotal_amount", "address_word:kvarter"),
        ("mva 25 00 av 940 00", "vat_amount", "percent_rate_context"),
        ("27", "total_amount", "no_real_word"),
        ("27", "total_amount", "too_short"),
        ("as 2", "vat_amount", "no_real_word"),
        ("fakturanr", "invoice_number", "matches_field_vocab"),
        ("forfallsdato", "due_date", "matches_field_vocab"),
        ("totalt mva beløp", "vat_amount", "matches_field_vocab"),
        ("netto", "subtotal_amount", "matches_field_vocab"),
    ],
)
def test_classify_noise_flags_expected(
    label: str, field: str, expected_flag: str
) -> None:
    flags = _classify_noise(label, field)
    assert expected_flag in flags, (label, field, flags)


def test_classify_noise_empty_label() -> None:
    assert _classify_noise("", "invoice_number") == ["empty"]


def test_classify_noise_legitimate_label_has_only_vocab_flag() -> None:
    # "fakturanr" should be clean: only matches_field_vocab, nothing else.
    flags = _classify_noise("fakturanr", "invoice_number")
    assert flags == ["matches_field_vocab"]


# ---------------------------------------------------------------------------
# scan_store aggregation
# ---------------------------------------------------------------------------

def _profile(key: str, field_hints: dict) -> dict:
    return {
        "profile_key": key,
        "supplier_name": key,
        "supplier_orgnr": "",
        "aliases": [],
        "sample_count": 1,
        "field_hints": field_hints,
        "static_fields": {},
        "schema_version": 1,
    }


def test_scan_store_aggregates_counts_across_profiles() -> None:
    store = {
        "records": {},
        "profiles": {
            "orgnr:111111111": _profile("A", {
                "invoice_number": [{"label": "Fakturanr", "page": 1, "count": 10}],
            }),
            "orgnr:222222222": _profile("B", {
                "invoice_number": [{"label": "fakturanr", "page": 2, "count": 5}],
            }),
        },
    }
    report = scan_store(store)

    assert report["profiles_total"] == 2
    fakt = next(
        s for s in report["per_field"]["invoice_number"]
        if s["label"] == "fakturanr"
    )
    assert fakt["total_count"] == 15, "counts must sum across profiles"
    assert fakt["profile_count"] == 2
    assert set(fakt["example_profiles"]) == {"orgnr:111111111", "orgnr:222222222"}
    # Both None and 2 are sorted; 1 and 2 should both appear:
    assert 1 in fakt["pages"] and 2 in fakt["pages"]


def test_scan_store_skips_global_profile_and_empty_labels() -> None:
    store = {
        "profiles": {
            "__global__": _profile("g", {
                "invoice_number": [{"label": "faktura", "count": 99}],
            }),
            "orgnr:999999999": _profile("real", {
                "invoice_number": [
                    {"label": "", "count": 1},
                    {"label": "faktura", "count": 2},
                ],
            }),
        },
    }
    report = scan_store(store)

    assert report["profiles_total"] == 1
    labels = [s["label"] for s in report["per_field"]["invoice_number"]]
    assert labels == ["faktura"]
    assert report["per_field"]["invoice_number"][0]["total_count"] == 2


def test_scan_store_sorts_by_count_descending() -> None:
    store = {
        "profiles": {
            "orgnr:111111111": _profile("A", {
                "total_amount": [
                    {"label": "netto", "count": 3},
                    {"label": "sum", "count": 10},
                    {"label": "total", "count": 7},
                ],
            }),
        },
    }
    report = scan_store(store)
    labels = [s["label"] for s in report["per_field"]["total_amount"]]
    assert labels == ["sum", "total", "netto"]


def test_scan_store_handles_missing_profiles_gracefully() -> None:
    assert scan_store({})["profiles_total"] == 0
    assert scan_store({"profiles": None})["profiles_total"] == 0
    assert scan_store({"profiles": {"bogus": "not-a-dict"}})["profiles_total"] == 0


# ---------------------------------------------------------------------------
# Rendering contracts
# ---------------------------------------------------------------------------

def test_render_json_round_trips_through_json_module() -> None:
    store = {
        "profiles": {
            "orgnr:111111111": _profile("A", {
                "invoice_number": [{"label": "fakturanr", "page": 1, "count": 3}],
            }),
        },
    }
    report = scan_store(store)
    doc = render_json(report)
    # Must round-trip; render_json's contract is that output is JSON-safe.
    json.loads(json.dumps(doc, ensure_ascii=False))


def test_render_text_mentions_each_learnable_field() -> None:
    store = {
        "profiles": {
            "orgnr:111111111": _profile("A", {
                "invoice_number": [{"label": "fakturanr", "count": 1}],
            }),
        },
    }
    report = scan_store(store)
    text = render_text(report, top=10)
    assert "invoice_number" in text
    assert "vat_amount" in text
    assert "Noise-candidate summary" in text


# ---------------------------------------------------------------------------
# The scanner must be strictly read-only
# ---------------------------------------------------------------------------

def test_scan_store_does_not_mutate_input_store() -> None:
    store = {
        "profiles": {
            "orgnr:111111111": _profile("A", {
                "invoice_number": [{"label": "fakturanr", "page": 1, "count": 3}],
            }),
        },
    }
    snapshot = json.loads(json.dumps(store))
    scan_store(store)
    assert store == snapshot, "scan_store must not mutate its input"

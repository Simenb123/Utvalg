"""Tests for ``scripts/relearn_document_profiles.py``.

The strict re-learning runner is what we expect to run in bulk after a
parser or NBSP fix, so the accept/skip gate must be predictable and
side-effect-free in dry-run. The tests here do NOT need real PDFs —
they exercise the gate via ``_evaluate_record`` and the wiring around
``_needs_force_ocr_redo`` directly, which keeps them fast and
deterministic on CI boxes without ``ocrmypdf`` / ``fitz``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

import relearn_document_profiles  # noqa: E402
from relearn_document_profiles import (  # noqa: E402
    _amounts_self_consistent,
    _bbox_width,
    _evaluate_record,
    _needs_force_ocr_redo,
    _result_for_json,
    process_store,
)


# ----------------------------------------------------------------------
# Helpers producing fixture records / profiles
# ----------------------------------------------------------------------

def _good_evidence(field: str, page: int = 1) -> dict:
    return {
        "page": page,
        "bbox": [100.0, 400.0, 180.0, 412.0],  # width = 80 pt, well under 140
        "source": "pdf_fitz",
    }


def _make_record(pdf_path: Path, **overrides) -> dict:
    rec = {
        "supplier_profile_key": "orgnr:965004211",
        "file_path": str(pdf_path),
        "raw_text_excerpt": "Faktura nr 123\nBeløp 940,00\nMVA 235,00\nTotal 1 175,00",
        "validation_messages": [],
        "fields": {
            "invoice_number": "123",
            "invoice_date": "01.04.2026",
            "due_date": "15.04.2026",
            "subtotal_amount": "940,00",
            "vat_amount": "235,00",
            "total_amount": "1175,00",
            "currency": "NOK",
            "supplier_orgnr": "965004211",
            "supplier_name": "Test AS",
        },
        "field_evidence": {
            f: _good_evidence(f) for f in
            ("invoice_number", "invoice_date", "due_date",
             "subtotal_amount", "vat_amount", "total_amount")
        },
        "metadata": {"ocr_redo_chosen": False},
        "source": "pdf_fitz",
    }
    rec.update(overrides)
    return rec


_PROFILES = {
    "orgnr:965004211": {
        "profile_key": "orgnr:965004211",
        "supplier_orgnr": "965004211",
        "supplier_name": "Test AS",
        "aliases": ["965004211", "test as"],
        "schema_version": 1,
        "field_hints": {},
        "static_fields": {"supplier_name": "Test AS", "supplier_orgnr": "965004211"},
        "sample_count": 3,
    }
}


# ----------------------------------------------------------------------
# _amounts_self_consistent
# ----------------------------------------------------------------------

def test_amounts_self_consistent_norwegian_vs_international() -> None:
    ok, reason = _amounts_self_consistent(
        {"subtotal_amount": "940,00", "vat_amount": "235,00", "total_amount": "1 175,00"}
    )
    assert ok is True and reason == ""


def test_amounts_self_consistent_accepts_mixed_locale() -> None:
    ok, _ = _amounts_self_consistent(
        {"subtotal_amount": "940,00", "vat_amount": "235.00", "total_amount": "1,175.00"}
    )
    assert ok is True


def test_amounts_self_consistent_detects_mismatch() -> None:
    ok, reason = _amounts_self_consistent(
        {"subtotal_amount": "940,00", "vat_amount": "235,00", "total_amount": "5000,00"}
    )
    assert ok is False and "subtotal+vat" in reason


def test_amounts_self_consistent_returns_none_when_missing() -> None:
    ok, reason = _amounts_self_consistent(
        {"subtotal_amount": "940,00", "total_amount": "1175,00"}
    )
    assert ok is None and "missing" in reason


# ----------------------------------------------------------------------
# _bbox_width
# ----------------------------------------------------------------------

def test_bbox_width_computes_x_range() -> None:
    assert _bbox_width((100.0, 400.0, 180.0, 420.0)) == pytest.approx(80.0)


def test_bbox_width_handles_none_and_bad_input() -> None:
    assert _bbox_width(None) is None
    assert _bbox_width([]) is None
    assert _bbox_width("invalid") is None


# ----------------------------------------------------------------------
# _evaluate_record — accept path
# ----------------------------------------------------------------------

def test_evaluate_record_accepts_clean_record(tmp_path: Path) -> None:
    pdf = tmp_path / "bilag.pdf"
    pdf.write_bytes(b"%PDF-1.4\n% fake\n")
    rec = _make_record(pdf)
    verdict = _evaluate_record("rec1", rec, _PROFILES, max_bbox_width=140.0)
    assert verdict.decision == "accept", verdict.reasons


# ----------------------------------------------------------------------
# _evaluate_record — skip paths
# ----------------------------------------------------------------------

def test_evaluate_record_skips_missing_profile_key(tmp_path: Path) -> None:
    pdf = tmp_path / "bilag.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf, supplier_profile_key="")
    verdict = _evaluate_record("rec1", rec, _PROFILES, max_bbox_width=140.0)
    assert verdict.decision == "skip"
    assert any("supplier_profile_key" in r for r in verdict.reasons)


def test_evaluate_record_skips_profile_not_in_store(tmp_path: Path) -> None:
    pdf = tmp_path / "bilag.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf, supplier_profile_key="orgnr:111111111")
    verdict = _evaluate_record("rec1", rec, _PROFILES, max_bbox_width=140.0)
    assert verdict.decision == "skip"


def test_evaluate_record_skips_non_pdf_file(tmp_path: Path) -> None:
    f = tmp_path / "bilag.xml"
    f.write_text("<xml/>", encoding="utf-8")
    rec = _make_record(f)
    verdict = _evaluate_record("rec1", rec, _PROFILES, max_bbox_width=140.0)
    assert verdict.decision == "skip"


def test_evaluate_record_skips_empty_raw_text(tmp_path: Path) -> None:
    pdf = tmp_path / "bilag.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf, raw_text_excerpt="")
    verdict = _evaluate_record("rec1", rec, _PROFILES, max_bbox_width=140.0)
    assert verdict.decision == "skip"
    assert any("raw_text_excerpt" in r for r in verdict.reasons)


def test_evaluate_record_skips_records_with_validation_messages(tmp_path: Path) -> None:
    pdf = tmp_path / "bilag.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf, validation_messages=["MVA avviker"])
    verdict = _evaluate_record("rec1", rec, _PROFILES, max_bbox_width=140.0)
    assert verdict.decision == "skip"
    assert any("validation message" in r for r in verdict.reasons)


def test_evaluate_record_skips_when_amounts_not_self_consistent(tmp_path: Path) -> None:
    pdf = tmp_path / "bilag.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf)
    rec["fields"]["total_amount"] = "5000,00"  # 940 + 235 != 5000
    verdict = _evaluate_record("rec1", rec, _PROFILES, max_bbox_width=140.0)
    assert verdict.decision == "skip"
    assert any("subtotal+vat" in r for r in verdict.reasons)


def test_evaluate_record_skips_when_bbox_too_wide(tmp_path: Path) -> None:
    pdf = tmp_path / "bilag.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf)
    # Widen the total_amount bbox to 500 pt — exceeds default 140 pt.
    rec["field_evidence"]["total_amount"]["bbox"] = [10.0, 400.0, 510.0, 420.0]
    verdict = _evaluate_record("rec1", rec, _PROFILES, max_bbox_width=140.0)
    assert verdict.decision == "skip"
    assert any("total_amount" in r and "bbox" in r for r in verdict.reasons)


def test_evaluate_record_skips_when_evidence_missing_page(tmp_path: Path) -> None:
    pdf = tmp_path / "bilag.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf)
    rec["field_evidence"]["subtotal_amount"]["page"] = None
    verdict = _evaluate_record("rec1", rec, _PROFILES, max_bbox_width=140.0)
    assert verdict.decision == "skip"


# ----------------------------------------------------------------------
# _needs_force_ocr_redo
# ----------------------------------------------------------------------

def test_needs_force_ocr_redo_triggers_on_metadata_flag() -> None:
    assert _needs_force_ocr_redo({"metadata": {"ocr_redo_chosen": True}}) is True


def test_needs_force_ocr_redo_triggers_on_source() -> None:
    assert _needs_force_ocr_redo({"source": "pdf_ocrmypdf_redo"}) is True


def test_needs_force_ocr_redo_false_for_normal_records() -> None:
    assert _needs_force_ocr_redo({"source": "pdf_fitz"}) is False
    assert _needs_force_ocr_redo({}) is False


# ----------------------------------------------------------------------
# process_store — dry-run writes nothing; --apply creates backup
# ----------------------------------------------------------------------

def test_process_store_dry_run_writes_nothing(tmp_path: Path) -> None:
    store = tmp_path / "store.json"
    data = {"records": {}, "profiles": dict(_PROFILES)}
    store.write_text(json.dumps(data), encoding="utf-8")
    mtime_before = store.stat().st_mtime_ns
    process_store(store, apply=False)
    # No backup siblings should appear, content unchanged.
    siblings = [p for p in tmp_path.iterdir() if p.name != "store.json"]
    assert siblings == [], siblings
    assert store.stat().st_mtime_ns == mtime_before


def test_process_store_apply_without_accepted_still_writes_no_backup(tmp_path: Path) -> None:
    # Everything gets skipped -> profiles dict is unchanged -> no need to
    # write anything. The script should still exit cleanly.
    store = tmp_path / "store.json"
    data = {
        "records": {
            "c::2026::b1": {
                "supplier_profile_key": "orgnr:965004211",
                # file_path missing -> skip
                "file_path": "",
                "raw_text_excerpt": "",
                "validation_messages": [],
                "fields": {},
                "field_evidence": {},
            },
        },
        "profiles": dict(_PROFILES),
    }
    store.write_text(json.dumps(data), encoding="utf-8")
    result = process_store(store, apply=True)
    assert result["stats"]["records_accepted_final"] == 0
    assert result["stats"]["records_accepted_initial"] == 0
    # No backup should have been produced because nothing was accepted.
    backups = list(tmp_path.glob("store.backup_*.json"))
    assert backups == [], backups
    assert "backup_path" not in result


def test_process_store_limits_to_profile(tmp_path: Path) -> None:
    store = tmp_path / "store.json"
    data = {
        "records": {
            "c::2026::b1": {"supplier_profile_key": "orgnr:965004211", "file_path": ""},
            "c::2026::b2": {"supplier_profile_key": "orgnr:888888888", "file_path": ""},
        },
        "profiles": dict(_PROFILES),
    }
    store.write_text(json.dumps(data), encoding="utf-8")
    result = process_store(store, apply=False, only_profile="orgnr:965004211")
    # Filter keeps just the one record matching the profile key.
    assert result["stats"]["records_considered"] == 1


# ----------------------------------------------------------------------
# process_store — aggregation across accepted records per profile
#
# The gate has already accepted these records; these tests cover what
# happens AFTER — segment re-extraction (stubbed) and hint aggregation
# with _merge_hint_entries. Multiple accepted records on the same
# profile must roll up into a single profile rebuild with hint counts
# reflecting how many records reinforced each (label, page) — NOT
# whichever record happened to be processed last.
# ----------------------------------------------------------------------


_DEFAULT_LABELS = {
    "invoice_number": "Fakturanummer",
    "invoice_date": "Dato",
    "due_date": "Forfall",
    "subtotal_amount": "Subtotal",
    "vat_amount": "MVA",
    "total_amount": "Total",
}


class _FakeSegment:
    def __init__(self, text: str, page: int, bbox: tuple[float, float, float, float]):
        self.text = text
        self.page = page
        self.bbox = bbox


class _FakeExtractResult:
    def __init__(self, text: str, segments: list[_FakeSegment]):
        self.text = text
        self.segments = segments
        self.source = "fake"
        self.ocr_used = False
        self.metadata: dict = {}


def _segments_from_fields(
    fields: dict, *, labels: dict | None = None, page: int = 1
) -> list[_FakeSegment]:
    chosen = dict(_DEFAULT_LABELS)
    if labels:
        chosen.update(labels)
    segs: list[_FakeSegment] = []
    for i, fname in enumerate(
        ("invoice_number", "invoice_date", "due_date",
         "subtotal_amount", "vat_amount", "total_amount")
    ):
        value = fields.get(fname)
        if not value or fname not in chosen:
            continue
        y0 = 100.0 + i * 20
        segs.append(_FakeSegment(
            text=f"{chosen[fname]}: {value}",
            page=page,
            bbox=(100.0, y0, 280.0, y0 + 12.0),
        ))
    return segs


def _stub_extract(result_by_path: dict[str, _FakeExtractResult | Exception]):
    """Build a stub for extract_text_from_file keyed by file path."""
    def _fake(pdf_path, *, force_ocr_redo: bool = False):  # noqa: ARG001
        key = str(pdf_path)
        payload = result_by_path.get(key)
        if isinstance(payload, Exception):
            raise payload
        if payload is None:
            return _FakeExtractResult("", [])
        return payload
    return _fake


def _make_store(records: dict, profiles: dict, path: Path) -> Path:
    path.write_text(
        json.dumps({"records": records, "profiles": profiles}),
        encoding="utf-8",
    )
    return path


def test_aggregates_hints_across_records_for_same_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    pdf_a.write_bytes(b"%PDF-1.4\n")
    pdf_b.write_bytes(b"%PDF-1.4\n")
    rec_a = _make_record(pdf_a)
    rec_b = _make_record(pdf_b)

    monkeypatch.setattr(
        relearn_document_profiles, "extract_text_from_file",
        _stub_extract({
            str(pdf_a): _FakeExtractResult(
                "", _segments_from_fields(rec_a["fields"]),
            ),
            str(pdf_b): _FakeExtractResult(
                "", _segments_from_fields(rec_b["fields"]),
            ),
        }),
    )

    store = _make_store(
        {"c::2026::b1": rec_a, "c::2026::b2": rec_b},
        dict(_PROFILES),
        tmp_path / "store.json",
    )
    result = process_store(store, apply=False)

    assert result["stats"]["records_accepted_initial"] == 2
    assert result["stats"]["records_accepted_final"] == 2
    assert "orgnr:965004211" in result["stats"]["profiles_touched"]

    # Apply and inspect the merged hints on the written profile.
    result = process_store(store, apply=True)
    assert "backup_path" in result
    written = json.loads(store.read_text(encoding="utf-8"))
    profile = written["profiles"]["orgnr:965004211"]
    total_hints = profile["field_hints"].get("total_amount", [])
    # Both records produced the SAME label on the same page → one hint entry
    # with count incremented twice.
    assert total_hints, profile["field_hints"]
    counts = [int(h.get("count", 0)) for h in total_hints]
    assert max(counts) == 2, total_hints
    assert profile["sample_count"] >= _PROFILES["orgnr:965004211"]["sample_count"] + 2


def test_aggregates_distinct_labels_for_same_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    pdf_a.write_bytes(b"%PDF-1.4\n")
    pdf_b.write_bytes(b"%PDF-1.4\n")
    rec_a = _make_record(pdf_a)
    rec_b = _make_record(pdf_b)

    # Record A labels the total as "Total"; record B labels it "Beløp".
    segs_a = _segments_from_fields(rec_a["fields"], labels={"total_amount": "Total"})
    segs_b = _segments_from_fields(rec_b["fields"], labels={"total_amount": "Beløp"})
    monkeypatch.setattr(
        relearn_document_profiles, "extract_text_from_file",
        _stub_extract({
            str(pdf_a): _FakeExtractResult("", segs_a),
            str(pdf_b): _FakeExtractResult("", segs_b),
        }),
    )

    store = _make_store(
        {"c::2026::b1": rec_a, "c::2026::b2": rec_b},
        dict(_PROFILES),
        tmp_path / "store.json",
    )
    result = process_store(store, apply=True)
    written = json.loads(store.read_text(encoding="utf-8"))
    profile = written["profiles"]["orgnr:965004211"]
    total_hints = profile["field_hints"].get("total_amount", [])
    labels = {h["label"] for h in total_hints}
    assert {"total", "beløp"}.issubset(labels), total_hints
    assert result["stats"]["hints_written"] > 0
    assert result["stats"]["hints_written_by_profile"]["orgnr:965004211"] >= 2


def test_updates_multiple_profiles_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    pdf_a.write_bytes(b"%PDF-1.4\n")
    pdf_b.write_bytes(b"%PDF-1.4\n")
    rec_a = _make_record(pdf_a)
    rec_b = _make_record(pdf_b, supplier_profile_key="orgnr:111111118")
    rec_b["fields"]["supplier_orgnr"] = "111111118"

    profiles = dict(_PROFILES)
    profiles["orgnr:111111118"] = {
        "profile_key": "orgnr:111111118",
        "supplier_orgnr": "111111118",
        "supplier_name": "Annen AS",
        "aliases": ["111111118", "annen as"],
        "schema_version": 1,
        "field_hints": {},
        "static_fields": {},
        "sample_count": 1,
    }

    monkeypatch.setattr(
        relearn_document_profiles, "extract_text_from_file",
        _stub_extract({
            str(pdf_a): _FakeExtractResult("", _segments_from_fields(rec_a["fields"])),
            str(pdf_b): _FakeExtractResult("", _segments_from_fields(rec_b["fields"])),
        }),
    )

    store = _make_store(
        {"c::2026::b1": rec_a, "c::2026::b2": rec_b},
        profiles,
        tmp_path / "store.json",
    )
    result = process_store(store, apply=True)

    assert set(result["stats"]["profiles_touched"]) == {
        "orgnr:965004211", "orgnr:111111118",
    }
    written = json.loads(store.read_text(encoding="utf-8"))
    assert written["profiles"]["orgnr:965004211"]["field_hints"].get("total_amount")
    assert written["profiles"]["orgnr:111111118"]["field_hints"].get("total_amount")


def test_keeps_successful_record_when_other_record_fails_extract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_ok = tmp_path / "ok.pdf"
    pdf_bad = tmp_path / "bad.pdf"
    pdf_ok.write_bytes(b"%PDF-1.4\n")
    pdf_bad.write_bytes(b"%PDF-1.4\n")
    rec_ok = _make_record(pdf_ok)
    rec_bad = _make_record(pdf_bad)

    monkeypatch.setattr(
        relearn_document_profiles, "extract_text_from_file",
        _stub_extract({
            str(pdf_ok): _FakeExtractResult("", _segments_from_fields(rec_ok["fields"])),
            str(pdf_bad): RuntimeError("fitz blew up"),
        }),
    )

    store = _make_store(
        {"c::2026::ok": rec_ok, "c::2026::bad": rec_bad},
        dict(_PROFILES),
        tmp_path / "store.json",
    )
    result = process_store(store, apply=True)

    assert result["stats"]["records_accepted_initial"] == 2
    assert result["stats"]["records_accepted_final"] == 1
    assert result["stats"]["records_skipped_after_extract"] == 1
    assert "orgnr:965004211" in result["stats"]["profiles_touched"]

    written = json.loads(store.read_text(encoding="utf-8"))
    profile = written["profiles"]["orgnr:965004211"]
    assert profile["field_hints"].get("total_amount"), profile["field_hints"]


def test_preserves_existing_profile_when_all_records_fail_extract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf)

    monkeypatch.setattr(
        relearn_document_profiles, "extract_text_from_file",
        _stub_extract({str(pdf): RuntimeError("fitz blew up")}),
    )

    # Seed an existing profile with a known hint so we can assert it is
    # NOT overwritten when re-extract fails.
    profiles = dict(_PROFILES)
    profiles["orgnr:965004211"] = dict(profiles["orgnr:965004211"])
    profiles["orgnr:965004211"]["field_hints"] = {
        "total_amount": [{"label": "total", "page": 1, "bbox": None, "count": 5}]
    }
    store = _make_store(
        {"c::2026::b1": rec}, profiles, tmp_path / "store.json",
    )

    result = process_store(store, apply=True)
    assert result["stats"]["records_accepted_initial"] == 1
    assert result["stats"]["records_accepted_final"] == 0
    assert result["stats"]["profiles_touched"] == set()
    assert "backup_path" not in result  # nothing written → no backup

    written = json.loads(store.read_text(encoding="utf-8"))
    preserved = written["profiles"]["orgnr:965004211"]["field_hints"]
    assert preserved == {
        "total_amount": [{"label": "total", "page": 1, "bbox": None, "count": 5}]
    }


def test_preserves_existing_profile_when_segments_yield_no_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf)

    # Extract succeeds but the segments have no lines matching any marker,
    # so infer_field_hints will return an empty dict.
    useless_segments = [_FakeSegment(
        text="Unrelated header text", page=1, bbox=(100.0, 100.0, 280.0, 112.0),
    )]
    monkeypatch.setattr(
        relearn_document_profiles, "extract_text_from_file",
        _stub_extract({str(pdf): _FakeExtractResult("", useless_segments)}),
    )

    profiles = dict(_PROFILES)
    profiles["orgnr:965004211"] = dict(profiles["orgnr:965004211"])
    profiles["orgnr:965004211"]["field_hints"] = {
        "total_amount": [{"label": "total", "page": 1, "bbox": None, "count": 7}]
    }
    store = _make_store(
        {"c::2026::b1": rec}, profiles, tmp_path / "store.json",
    )

    result = process_store(store, apply=True)
    assert "orgnr:965004211" in result["stats"]["profiles_with_no_hints"]
    assert result["stats"]["profiles_touched"] == set()
    assert "backup_path" not in result

    written = json.loads(store.read_text(encoding="utf-8"))
    preserved = written["profiles"]["orgnr:965004211"]["field_hints"]
    assert preserved == {
        "total_amount": [{"label": "total", "page": 1, "bbox": None, "count": 7}]
    }


def test_result_is_json_serializable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf)
    monkeypatch.setattr(
        relearn_document_profiles, "extract_text_from_file",
        _stub_extract({str(pdf): _FakeExtractResult("", _segments_from_fields(rec["fields"]))}),
    )

    store = _make_store(
        {"c::2026::b1": rec}, dict(_PROFILES), tmp_path / "store.json",
    )
    result = process_store(store, apply=False)
    doc = _result_for_json(result)

    # Must round-trip through json.dumps / json.loads without TypeError.
    roundtrip = json.loads(json.dumps(doc))
    assert set(roundtrip.keys()) >= {"stats", "verdicts", "profiles_touched", "store_path"}
    assert roundtrip["store_path"] == str(store)
    assert isinstance(roundtrip["profiles_touched"], list)
    assert isinstance(roundtrip["verdicts"], list)
    assert isinstance(roundtrip["stats"]["profiles_touched"], list)
    assert isinstance(roundtrip["stats"]["profiles_with_no_hints"], list)


def test_apply_creates_backup_only_when_profile_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf)
    monkeypatch.setattr(
        relearn_document_profiles, "extract_text_from_file",
        _stub_extract({str(pdf): _FakeExtractResult("", _segments_from_fields(rec["fields"]))}),
    )

    store = _make_store(
        {"c::2026::b1": rec}, dict(_PROFILES), tmp_path / "store.json",
    )
    result = process_store(store, apply=True)
    assert "backup_path" in result
    backups = list(tmp_path.glob("store.backup_*.json"))
    assert len(backups) == 1, backups


def test_apply_regenerates_global_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf)
    monkeypatch.setattr(
        relearn_document_profiles, "extract_text_from_file",
        _stub_extract({str(pdf): _FakeExtractResult("", _segments_from_fields(rec["fields"]))}),
    )

    # Seed a stale __global__ so we can observe regeneration.
    profiles = dict(_PROFILES)
    profiles["__global__"] = {
        "profile_key": "__global__",
        "field_hints": {"total_amount": [{"label": "STALE", "page": 1, "count": 99}]},
        "aliases": [],
        "static_fields": {},
        "supplier_name": "",
        "supplier_orgnr": "",
        "schema_version": 1,
        "sample_count": 0,
    }

    store = _make_store(
        {"c::2026::b1": rec}, profiles, tmp_path / "store.json",
    )
    process_store(store, apply=True)

    written = json.loads(store.read_text(encoding="utf-8"))
    # Either __global__ is rebuilt (common case with few profiles → absent)
    # OR it has been regenerated from live data (no "STALE" label in hints).
    if "__global__" in written["profiles"]:
        global_hints = written["profiles"]["__global__"].get("field_hints", {}) or {}
        all_labels = {
            h.get("label")
            for entries in global_hints.values()
            for h in (entries or [])
        }
        assert "STALE" not in all_labels, written["profiles"]["__global__"]


def test_relearn_preserves_pre_existing_hint_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Relearn must add to existing hint counts, never reset them.

    Simulates the BRAGE case observed in prod: a profile had
    ``fakturanr`` count=52 from historical saves. After a relearn round
    where only 1 new record is re-processed, the count for the stable
    label must be **at least 52** (52 preserved + 1 newly confirmed = 53),
    never dropped to 1. Without this guard, re-runs of relearn
    progressively forget what the store already knows.
    """
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rec = _make_record(pdf)
    monkeypatch.setattr(
        relearn_document_profiles, "extract_text_from_file",
        _stub_extract({str(pdf): _FakeExtractResult("", _segments_from_fields(rec["fields"]))}),
    )

    # Seed the profile with pre-existing high-count hints (the historical
    # 52-count state).
    profiles = dict(_PROFILES)
    profiles["orgnr:965004211"] = {
        **_PROFILES["orgnr:965004211"],
        "sample_count": 52,
        "field_hints": {
            "invoice_number": [{"label": "fakturanr", "page": 1, "bbox": None, "count": 52}],
            "invoice_date": [{"label": "fakturadato", "page": 1, "bbox": None, "count": 34}],
        },
    }

    store = _make_store(
        {"c::2026::b1": rec}, profiles, tmp_path / "store.json",
    )
    process_store(store, apply=True)

    written = json.loads(store.read_text(encoding="utf-8"))
    updated = written["profiles"]["orgnr:965004211"]
    hints = updated.get("field_hints", {}) or {}

    def _count(field: str, label: str, page) -> int:
        for h in hints.get(field, []) or []:
            if str(h.get("label", "")).lower() == label and h.get("page") == page:
                return int(h.get("count", 0) or 0)
        return 0

    # Pre-existing count=52 must have been carried through. The new record
    # can add to it, but never reset it.
    assert _count("invoice_number", "fakturanr", 1) >= 52, (
        f"fakturanr count reset — got {_count('invoice_number', 'fakturanr', 1)}, "
        f"expected ≥52. Full hints: {hints!r}"
    )
    # Label not re-confirmed in this run should also be preserved as-is.
    assert _count("invoice_date", "fakturadato", 1) == 34, hints

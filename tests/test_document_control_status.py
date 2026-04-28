"""Tests for document status helpers in document_control_app_service."""
from __future__ import annotations

from src.shared.document_control.app_service import (
    DOK_STATUS_AVVIK,
    DOK_STATUS_LINKED,
    DOK_STATUS_NOT_LINKED,
    DOK_STATUS_OK,
    compute_document_status,
    load_document_statuses,
)


# ---------------------------------------------------------------------------
# compute_document_status
# ---------------------------------------------------------------------------


def test_status_not_linked_when_no_record() -> None:
    assert compute_document_status(None) == DOK_STATUS_NOT_LINKED


def test_status_not_linked_when_empty_file_path() -> None:
    assert compute_document_status({"file_path": "", "fields": {}}) == DOK_STATUS_NOT_LINKED


def test_status_koblet_when_file_linked_but_no_fields() -> None:
    record = {"file_path": "/tmp/faktura.pdf", "fields": {}}
    assert compute_document_status(record) == DOK_STATUS_LINKED


def test_status_koblet_when_file_linked_all_empty_fields() -> None:
    record = {
        "file_path": "/tmp/faktura.pdf",
        "fields": {"supplier_name": "", "invoice_number": ""},
    }
    assert compute_document_status(record) == DOK_STATUS_LINKED


def test_status_ok_when_fields_present_no_messages() -> None:
    record = {
        "file_path": "/tmp/faktura.pdf",
        "fields": {"supplier_name": "Partner AS", "total_amount": "1250.00"},
        "validation_messages": [],
    }
    assert compute_document_status(record) == DOK_STATUS_OK


def test_status_avvik_when_validation_messages_present() -> None:
    record = {
        "file_path": "/tmp/faktura.pdf",
        "fields": {"supplier_name": "Partner AS", "total_amount": "1250.00"},
        "validation_messages": ["Beløp stemmer ikke"],
    }
    assert compute_document_status(record) == DOK_STATUS_AVVIK


# ---------------------------------------------------------------------------
# load_document_statuses
# ---------------------------------------------------------------------------


def test_load_document_statuses_empty_list_returns_empty() -> None:
    result = load_document_statuses("DemoAS", "2025", [])
    assert result == {}


def test_load_document_statuses_missing_bilag_returns_not_linked(tmp_path, monkeypatch) -> None:
    import src.shared.document_control.store as store

    monkeypatch.setattr(store, "_store_path", lambda: tmp_path / "store.json")

    result = load_document_statuses("DemoAS", "2025", ["1001", "1002"])
    assert result == {"1001": DOK_STATUS_NOT_LINKED, "1002": DOK_STATUS_NOT_LINKED}


def test_load_document_statuses_reflects_saved_record(tmp_path, monkeypatch) -> None:
    import src.shared.document_control.store as store

    monkeypatch.setattr(store, "_store_path", lambda: tmp_path / "store.json")

    # Save a reviewed record
    store.save_document_record(
        "DemoAS",
        "2025",
        "1001",
        {
            "file_path": "/tmp/faktura.pdf",
            "fields": {"supplier_name": "Test AS"},
            "validation_messages": [],
        },
    )

    result = load_document_statuses("DemoAS", "2025", ["1001", "1002"])
    assert result["1001"] == DOK_STATUS_OK
    assert result["1002"] == DOK_STATUS_NOT_LINKED


def test_load_document_statuses_avvik_when_messages(tmp_path, monkeypatch) -> None:
    import src.shared.document_control.store as store

    monkeypatch.setattr(store, "_store_path", lambda: tmp_path / "store.json")

    store.save_document_record(
        "DemoAS",
        "2025",
        "2001",
        {
            "file_path": "/tmp/faktura2.pdf",
            "fields": {"supplier_name": "Test AS"},
            "validation_messages": ["Beløp stemmer ikke"],
        },
    )

    result = load_document_statuses("DemoAS", "2025", ["2001"])
    assert result["2001"] == DOK_STATUS_AVVIK

from __future__ import annotations

import pandas as pd
import pytest

from account_profile import (
    AccountClassificationCatalog,
    AccountClassificationCatalogEntry,
    AccountProfile,
    AccountProfileDocument,
)
from a07_feature import control_statement_source


def _catalog_with_loenn() -> AccountClassificationCatalog:
    return AccountClassificationCatalog(
        groups=(
            AccountClassificationCatalogEntry(
                id="Loenn",
                label="Lønn",
                active=True,
                sort_order=10,
                applies_to=("kontrolloppstilling",),
            ),
        ),
        tags=(),
    )


def _document_with_loenn() -> AccountProfileDocument:
    return AccountProfileDocument(
        client="Air Management AS",
        year=2025,
        profiles={
            "5000": AccountProfile(
                account_no="5000",
                account_name="Loenn fast",
                a07_code="fastloenn",
                control_group="Loenn",
                source="manual",
            ),
        },
    )


def _gl_df_5000() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Loenn fast", "IB": 0.0, "Endring": 100.0, "UB": 100.0},
        ]
    )


def test_build_current_returns_empty_for_blank_client(monkeypatch):
    def _fail_load(*_args, **_kwargs):
        raise AssertionError("should not load document when client is blank")

    monkeypatch.setattr(
        control_statement_source.mapping_source, "load_current_document", _fail_load
    )

    out = control_statement_source.build_current_control_statement_rows(
        "", 2025, _gl_df_5000()
    )

    assert out == []


def test_build_current_returns_empty_for_none_gl_df(monkeypatch):
    monkeypatch.setattr(
        control_statement_source.mapping_source,
        "load_current_document",
        lambda *_a, **_k: _document_with_loenn(),
    )

    out = control_statement_source.build_current_control_statement_rows(
        "Air Management AS", 2025, None
    )

    assert out == []


def test_build_current_returns_empty_for_empty_gl_df(monkeypatch):
    monkeypatch.setattr(
        control_statement_source.mapping_source,
        "load_current_document",
        lambda *_a, **_k: _document_with_loenn(),
    )

    out = control_statement_source.build_current_control_statement_rows(
        "Air Management AS", 2025, pd.DataFrame()
    )

    assert out == []


def test_build_current_returns_empty_when_document_load_fails(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("document load failed")

    monkeypatch.setattr(
        control_statement_source.mapping_source, "load_current_document", _raise
    )

    out = control_statement_source.build_current_control_statement_rows(
        "Air Management AS", 2025, _gl_df_5000()
    )

    assert out == []


def test_build_current_builds_rows_with_catalog(monkeypatch):
    monkeypatch.setattr(
        control_statement_source.mapping_source,
        "load_current_document",
        lambda *_a, **_k: _document_with_loenn(),
    )
    monkeypatch.setattr(
        control_statement_source,
        "load_current_catalog",
        lambda: _catalog_with_loenn(),
    )

    rows = control_statement_source.build_current_control_statement_rows(
        "Air Management AS", 2025, _gl_df_5000()
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.group_id == "Loenn"
    assert row.label == "Lønn"
    assert row.ub == pytest.approx(100.0)
    assert row.accounts == ("5000",)
    assert "manual" in row.source_breakdown


def test_build_current_falls_back_to_no_catalog_when_catalog_load_raises(monkeypatch):
    monkeypatch.setattr(
        control_statement_source.mapping_source,
        "load_current_document",
        lambda *_a, **_k: _document_with_loenn(),
    )
    monkeypatch.setattr(
        control_statement_source.classification_config,
        "resolve_catalog_path",
        lambda: (_ for _ in ()).throw(RuntimeError("no catalog path")),
    )

    rows = control_statement_source.build_current_control_statement_rows(
        "Air Management AS", 2025, _gl_df_5000()
    )

    assert len(rows) == 1
    assert rows[0].group_id == "Loenn"
    assert rows[0].ub == pytest.approx(100.0)


def test_build_current_include_unclassified_adds_placeholder_group(monkeypatch):
    document = AccountProfileDocument(
        client="Air Management AS",
        year=2025,
        profiles={
            "5000": AccountProfile(
                account_no="5000",
                account_name="Loenn fast",
                a07_code="fastloenn",
                control_group="Loenn",
                source="manual",
            ),
        },
    )
    monkeypatch.setattr(
        control_statement_source.mapping_source,
        "load_current_document",
        lambda *_a, **_k: document,
    )
    monkeypatch.setattr(
        control_statement_source, "load_current_catalog", lambda: _catalog_with_loenn()
    )

    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Loenn", "IB": 0.0, "Endring": 100.0, "UB": 100.0},
            {"Konto": "6300", "Navn": "Leie lokale", "IB": 0.0, "Endring": 50.0, "UB": 50.0},
        ]
    )

    rows = control_statement_source.build_current_control_statement_rows(
        "Air Management AS", 2025, gl_df, include_unclassified=True
    )

    group_ids = {row.group_id for row in rows}
    assert "Loenn" in group_ids
    assert "__unclassified__" in group_ids


def test_build_current_infers_payroll_control_group_from_known_a07_code(monkeypatch):
    document = AccountProfileDocument(
        client="Air Management AS",
        year=2025,
        profiles={
            "5930": AccountProfile(
                account_no="5930",
                account_name="Pensjonsforsikring OTP",
                a07_code="tilskuddOgPremieTilPensjon",
                control_group=None,
                source="manual",
            ),
        },
    )
    monkeypatch.setattr(
        control_statement_source.mapping_source,
        "load_current_document",
        lambda *_a, **_k: document,
    )
    monkeypatch.setattr(
        control_statement_source, "load_current_catalog", lambda: None
    )

    gl_df = pd.DataFrame(
        [
            {
                "Konto": "5930",
                "Navn": "Pensjonsforsikring OTP",
                "IB": 0.0,
                "Endring": 100.0,
                "UB": 100.0,
            },
        ]
    )

    rows = control_statement_source.build_current_control_statement_rows(
        "Air Management AS", 2025, gl_df
    )

    assert len(rows) == 1
    assert rows[0].group_id == "112_pensjon"
    assert rows[0].label == "Post 112 Pensjon"
    assert rows[0].accounts == ("5930",)


def test_load_current_catalog_returns_none_on_resolve_failure(monkeypatch):
    monkeypatch.setattr(
        control_statement_source.classification_config,
        "resolve_catalog_path",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert control_statement_source.load_current_catalog() is None


def test_load_current_catalog_returns_none_on_load_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        control_statement_source.classification_config,
        "resolve_catalog_path",
        lambda: tmp_path / "nonexistent" / "catalog.json",
    )

    def _raise(_path):
        raise RuntimeError("parse failed")

    monkeypatch.setattr(
        control_statement_source, "load_account_classification_catalog", _raise
    )

    assert control_statement_source.load_current_catalog() is None


def test_load_current_catalog_returns_catalog_on_success(monkeypatch, tmp_path):
    catalog = _catalog_with_loenn()
    catalog_path = tmp_path / "catalog.json"
    monkeypatch.setattr(
        control_statement_source.classification_config,
        "resolve_catalog_path",
        lambda: catalog_path,
    )
    monkeypatch.setattr(
        control_statement_source,
        "load_account_classification_catalog",
        lambda path: catalog if path == catalog_path else None,
    )

    assert control_statement_source.load_current_catalog() is catalog


def test_build_current_filters_groups_outside_control_statement_scope(monkeypatch):
    document = AccountProfileDocument(
        client="Air Management AS",
        year=2025,
        profiles={
            "5000": AccountProfile(
                account_no="5000",
                account_name="Loenn fast",
                a07_code="fastloenn",
                control_group="AnalyseOnly",
                source="manual",
            ),
        },
    )
    catalog = AccountClassificationCatalog(
        groups=(
            AccountClassificationCatalogEntry(
                id="AnalyseOnly",
                label="Analyse only",
                active=True,
                applies_to=("analyse",),
            ),
        ),
        tags=(),
    )
    monkeypatch.setattr(
        control_statement_source.mapping_source,
        "load_current_document",
        lambda *_a, **_k: document,
    )
    monkeypatch.setattr(control_statement_source, "load_current_catalog", lambda: catalog)

    rows = control_statement_source.build_current_control_statement_rows(
        "Air Management AS", 2025, _gl_df_5000()
    )

    assert rows == []

from __future__ import annotations

import sqlite3
from pathlib import Path

import crmsystem_materiality as mod


def _prepare_db(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute(
            """
            CREATE TABLE client_audit_info (
                client_number TEXT PRIMARY KEY,
                engagement_year INTEGER,
                materiality REAL,
                pmateriality REAL,
                clearly_triv REAL,
                source_updated_at TEXT,
                last_synced_at_utc TEXT,
                last_changed_at_utc TEXT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE clients (
                client_number TEXT PRIMARY KEY,
                client_name TEXT NOT NULL
            )
            """
        )
        con.execute("INSERT INTO clients(client_number, client_name) VALUES (?, ?)", ("7429", "Demo AS"))
        con.execute(
            """
            INSERT INTO client_audit_info(
                client_number, engagement_year, materiality, pmateriality, clearly_triv,
                source_updated_at, last_synced_at_utc, last_changed_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("7429", 2025, 1200000, 600000, 30000, "2025-01-15T12:00:00Z", "2025-01-16T08:00:00Z", "2025-01-16T08:00:00Z"),
        )
        con.commit()
    finally:
        con.close()


def test_load_materiality_from_crm_prefers_first_matching_candidate(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "crm.sqlite"
    _prepare_db(db_path)
    monkeypatch.setenv("CRMSYSTEM_DB_PATH", str(db_path))

    result = mod.load_materiality_from_crm(["147429", "7429"])

    assert result.error == ""
    assert result.record is not None
    assert result.record.client_number == "7429"
    assert result.record.materiality == 1200000.0
    assert result.record.pmateriality == 600000.0


def test_load_materiality_from_crm_returns_helpful_error_when_db_missing(monkeypatch) -> None:
    monkeypatch.setenv("CRMSYSTEM_DB_PATH", str(Path("C:/missing/crm.sqlite")))
    result = mod.load_materiality_from_crm(["7429"])
    assert result.record is None
    assert "finnes ikke" in result.error.lower()


def test_suggest_client_numbers_from_name_matches_normalized_client_name(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "crm.sqlite"
    _prepare_db(db_path)
    monkeypatch.setenv("CRMSYSTEM_DB_PATH", str(db_path))

    result = mod.suggest_client_numbers_from_name("Demo AS")

    assert result == ["7429"]


def test_suggest_client_numbers_from_name_uses_high_confidence_fuzzy_match(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "crm.sqlite"
    _prepare_db(db_path)
    con = sqlite3.connect(db_path)
    try:
        con.execute("INSERT INTO clients(client_number, client_name) VALUES (?, ?)", ("7162", "Spor Arkitekter AS"))
        con.commit()
    finally:
        con.close()
    monkeypatch.setenv("CRMSYSTEM_DB_PATH", str(db_path))

    result = mod.suggest_client_numbers_from_name("Spor Arkitektur AS")

    assert result == ["7162"]

"""Tester for selection_studio/haphazard_store.py.

Lag 1 av haphazard-bilag-testing-planen. Bekrefter:
- save_haphazard_test skriver én ny linje i haphazard.jsonl
- load_haphazard_tests leser tilbake samme data
- has_haphazard_test_for_bilag finner riktig bilag-nr
- save_pdf=True kopierer PDF til documents/bilag/<nr>.pdf
- Append-only: andre kontroll for samme bilag legger til ny linje
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _setup_app_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isoler client_store under tmp_path."""
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))


def test_save_and_load_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_app_paths(tmp_path, monkeypatch)
    from selection_studio.haphazard_store import (
        save_haphazard_test,
        load_haphazard_tests,
    )

    test = save_haphazard_test(
        client="Demo AS",
        year="2025",
        bilag_nr="11148",
        konto="6903",
        kontonavn="Mobiltelefon",
        beløp=2908.00,
        dato="2025-05-05",
        konklusjon="ok",
        notat="Faktura fra Telenor stemmer.",
        granskede_av="snb",
    )

    assert test.test_method == "haphazard"
    assert test.bilag_nr == "11148"
    assert test.konklusjon == "ok"
    assert test.pdf_attached is False
    assert test.test_id.startswith("ha-")

    loaded = load_haphazard_tests("Demo AS", "2025")
    assert len(loaded) == 1
    assert loaded[0].test_id == test.test_id
    assert loaded[0].notat == "Faktura fra Telenor stemmer."


def test_has_haphazard_test_for_bilag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_app_paths(tmp_path, monkeypatch)
    from selection_studio.haphazard_store import (
        save_haphazard_test,
        has_haphazard_test_for_bilag,
    )

    assert has_haphazard_test_for_bilag("Demo AS", "2025", "11148") is False

    save_haphazard_test(
        client="Demo AS",
        year="2025",
        bilag_nr="11148",
        konklusjon="ok",
    )

    assert has_haphazard_test_for_bilag("Demo AS", "2025", "11148") is True
    assert has_haphazard_test_for_bilag("Demo AS", "2025", "99999") is False


def test_append_only_multiple_tests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_app_paths(tmp_path, monkeypatch)
    from selection_studio.haphazard_store import (
        save_haphazard_test,
        load_haphazard_tests,
    )

    save_haphazard_test(client="Demo AS", year="2025", bilag_nr="11148", konklusjon="ok", notat="første")
    save_haphazard_test(client="Demo AS", year="2025", bilag_nr="11148", konklusjon="avvik", notat="andre")

    loaded = load_haphazard_tests("Demo AS", "2025")
    assert len(loaded) == 2
    assert {t.notat for t in loaded} == {"første", "andre"}
    assert {t.konklusjon for t in loaded} == {"ok", "avvik"}


def test_save_pdf_copies_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_app_paths(tmp_path, monkeypatch)
    from selection_studio.haphazard_store import save_haphazard_test
    import src.shared.client_store.store as client_store

    # Lag en dummy "PDF" å arkivere
    pdf_src = tmp_path / "fake_bilag.pdf"
    pdf_src.write_bytes(b"%PDF-1.4 dummy")

    test = save_haphazard_test(
        client="Demo AS",
        year="2025",
        bilag_nr="11148",
        konklusjon="ok",
        pdf_source_path=pdf_src,
        save_pdf=True,
    )

    assert test.pdf_attached is True
    expected = client_store.years_dir("Demo AS", year="2025") / "documents" / "bilag" / "11148.pdf"
    assert expected.exists()
    assert expected.read_bytes() == b"%PDF-1.4 dummy"


def test_invalid_konklusjon_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_app_paths(tmp_path, monkeypatch)
    from selection_studio.haphazard_store import save_haphazard_test

    with pytest.raises(ValueError, match="Ugyldig konklusjon"):
        save_haphazard_test(client="Demo AS", year="2025", bilag_nr="x", konklusjon="ukjent")

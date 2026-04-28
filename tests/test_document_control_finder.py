from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import src.shared.document_control.finder as finder


def test_suggest_documents_for_bilag_prefers_pdf_with_bilag_and_reference_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    year_root = tmp_path / "client_store" / "years" / "2025"
    bilag_dir = year_root / "Bilag"
    bilag_dir.mkdir(parents=True, exist_ok=True)

    best = bilag_dir / "1001_INV-2025-001_eksempel-partner.pdf"
    best.write_text("pdf", encoding="utf-8")

    weaker = bilag_dir / "notat_1001.txt"
    weaker.write_text("txt", encoding="utf-8")

    versions_dir = year_root / "versions" / "hb"
    versions_dir.mkdir(parents=True, exist_ok=True)
    stored_version = versions_dir / "hb.xlsx"
    stored_version.write_text("hb", encoding="utf-8")

    source_dir = tmp_path / "kilde"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_file = source_dir / "grunnlag.xlsx"
    source_file.write_text("src", encoding="utf-8")

    monkeypatch.setattr(finder.client_store, "years_dir", lambda _client, *, year: year_root)
    monkeypatch.setattr(
        finder.client_store,
        "get_active_version",
        lambda _client, *, year, dtype: SimpleNamespace(
            path=str(stored_version),
            meta={"source_path": str(source_file)},
        ),
    )

    df_bilag = pd.DataFrame(
        {
            "Bilag": [1001],
            "Tekst": ["INV-2025-001 Eksempel Partner AS kjøp"],
            "Dato": ["15.02.2025"],
            "Beløp": [1250.0],
        }
    )

    suggestions = finder.suggest_documents_for_bilag(
        client="Demo AS",
        year="2025",
        bilag="1001",
        df_bilag=df_bilag,
    )

    assert suggestions
    assert Path(suggestions[0].path) == best
    assert suggestions[0].score > suggestions[-1].score


def test_suggest_documents_for_bilag_can_find_files_near_original_source_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    year_root = tmp_path / "client_store" / "years" / "2025"
    year_root.mkdir(parents=True, exist_ok=True)

    source_parent = tmp_path / "kunde" / "2025"
    docs_dir = source_parent / "Vedlegg"
    docs_dir.mkdir(parents=True, exist_ok=True)

    source_file = source_parent / "hovedbok.xlsx"
    source_file.write_text("hb", encoding="utf-8")

    candidate = docs_dir / "faktura_INV-999.pdf"
    candidate.write_text("pdf", encoding="utf-8")

    stored_version = year_root / "versions" / "hb" / "hb.xlsx"
    stored_version.parent.mkdir(parents=True, exist_ok=True)
    stored_version.write_text("stored", encoding="utf-8")

    monkeypatch.setattr(finder.client_store, "years_dir", lambda _client, *, year: year_root)
    monkeypatch.setattr(
        finder.client_store,
        "get_active_version",
        lambda _client, *, year, dtype: SimpleNamespace(
            path=str(stored_version),
            meta={"source_path": str(source_file)},
        ),
    )

    df_bilag = pd.DataFrame(
        {
            "Bilag": [999],
            "Tekst": ["INV-999 Leverandør Demo"],
            "Dato": ["01.03.2025"],
            "Beløp": [995.0],
        }
    )

    suggestions = finder.suggest_documents_for_bilag(
        client="Demo AS",
        year="2025",
        bilag="999",
        df_bilag=df_bilag,
    )

    assert suggestions
    assert any(Path(suggestion.path) == candidate for suggestion in suggestions)

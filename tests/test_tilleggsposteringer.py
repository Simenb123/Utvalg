from __future__ import annotations

from pathlib import Path

import pytest

from tilleggsposteringer import import_entries_from_excel


def _write_excel(path: Path, rows: list[list[object]]) -> None:
    import pandas as pd

    pd.DataFrame(rows).to_excel(path, index=False, header=False)


def test_import_entries_from_excel_handles_ao_layout_with_preamble(tmp_path: Path) -> None:
    path = tmp_path / "ao_import.xlsx"
    rows = [
        [None] * 10,
        ["Posteringer"] + [None] * 9,
        ["Glitre AS"] + [None] * 9,
        ["Kilde", " ", "Bilagsnr", "Dato", "Tekst", "Kontonr", "Kontonavn", "Debet", "Kredit", "Netto"],
        ["Disponeringer", "D", 6, "2025-12-31", "Overfort til annen egenkapital", "2050", "Annen egenkapital", None, "2 754 414,39", "-2 754 414,39"],
        ["Disponeringer", "D", 6, "2025-12-31", "Overfort til annen egenkapital", "8960", "Overfort annen egenkapital", "2 754 414,39", None, "2 754 414,39"],
        ["Disponeringer", "D", 6, "2025-12-31", "Nullinje", "2100", "Utsatt skatt", 0, None, 0],
    ]
    _write_excel(path, rows)

    result = import_entries_from_excel(path)

    assert result.total_rows == 3
    assert result.imported_rows == 2
    assert result.skipped_rows == 1
    assert [entry["bilag"] for entry in result.entries] == ["D 6", "D 6"]
    assert [entry["konto"] for entry in result.entries] == ["2050", "8960"]
    assert result.entries[0]["belop"] == pytest.approx(-2754414.39)
    assert result.entries[1]["belop"] == pytest.approx(2754414.39)
    assert result.entries[0]["beskrivelse"] == "Overfort til annen egenkapital"


def test_import_entries_from_excel_falls_back_to_debet_minus_kredit(tmp_path: Path) -> None:
    path = tmp_path / "ao_import_no_netto.xlsx"
    rows = [
        ["Kilde", "Bilagsnr", "Kontonummer", "Beskrivelse", "Debet", "Kredit"],
        ["Tillegg", 11, "1574", "Reversering", None, "17 073 548,00"],
        ["Tillegg", 11, "7827", "Reversering", "17 073 548,00", None],
    ]
    _write_excel(path, rows)

    result = import_entries_from_excel(path)

    assert result.total_rows == 2
    assert result.imported_rows == 2
    assert result.skipped_rows == 0
    assert [entry["bilag"] for entry in result.entries] == ["11", "11"]
    assert [entry["belop"] for entry in result.entries] == [
        pytest.approx(-17073548.0),
        pytest.approx(17073548.0),
    ]

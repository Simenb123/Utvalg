from __future__ import annotations

import openpyxl
import pytest

from src.pages.dataset.backend.build_fast import build_from_file


def test_build_from_file_excel_allows_mapping_blank_header_column(tmp_path):
    xlsx = tmp_path / "hb.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "HB"

    # Blank header i kolonne 2 (skal bli 'kol2')
    ws.append(["Konto", "", "Beløp"])
    ws.append([3000, 1001, 10])
    ws.append([3001, 1002, 20])

    wb.save(xlsx)

    mapping = {
        "Konto": "Konto",
        "Bilag": "kol2",
        "Beløp": "Beløp",
    }

    df = build_from_file(xlsx, mapping=mapping, sheet_name="HB", header_row=1)

    assert len(df) == 2
    assert set(df["Bilag"].astype(str)) == {"1001", "1002"}
    assert df["Beløp"].sum() == 30


def test_build_from_file_csv_allows_mapping_blank_header_column(tmp_path):
    csv = tmp_path / "hb.csv"

    # Blank header i kolonne 2 (skal bli 'kol2')
    csv.write_text(
        "Konto,,Beløp\n"
        "3000,1001,10\n"
        "3001,1002,20\n",
        encoding="utf-8",
    )

    mapping = {
        "Konto": "Konto",
        "Bilag": "kol2",
        "Beløp": "Beløp",
    }

    df = build_from_file(csv, mapping=mapping, header_row=1)

    assert len(df) == 2
    assert set(df["Bilag"].astype(str)) == {"1001", "1002"}
    assert df["Beløp"].sum() == 30


def test_build_from_file_raises_nice_error_when_mapped_source_column_missing(tmp_path):
    csv = tmp_path / "hb.csv"
    csv.write_text(
        "Konto,,Beløp\n"
        "3000,1001,10\n",
        encoding="utf-8",
    )

    mapping = {
        "Konto": "Konto",
        "Bilag": "kol99",  # finnes ikke
        "Beløp": "Beløp",
    }

    with pytest.raises(ValueError) as exc:
        _ = build_from_file(csv, mapping=mapping, header_row=1)

    assert "finnes ikke" in str(exc.value).lower() or "mangler" in str(exc.value).lower()

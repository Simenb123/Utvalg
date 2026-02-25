from __future__ import annotations

from pathlib import Path

import openpyxl

from dataset_pane_io import read_csv_rows, read_excel_rows


def test_read_csv_rows_accepts_max_rows_and_start_row(tmp_path: Path) -> None:
    p = tmp_path / "sample.csv"
    p.write_text(
        "h1,h2,h3\n"
        "r1c1,r1c2,r1c3\n"
        "r2c1,r2c2,r2c3\n"
        "r3c1,r3c2,r3c3\n",
        encoding="utf-8",
    )

    # Skip header (start_row=2) and read 2 rows
    rows = read_csv_rows(p, start_row=2, max_rows=2, max_cols=10)
    assert rows == [
        ["r1c1", "r1c2", "r1c3"],
        ["r2c1", "r2c2", "r2c3"],
    ]


def test_read_csv_rows_raises_if_nrows_and_max_rows_conflict(tmp_path: Path) -> None:
    p = tmp_path / "sample.csv"
    p.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    try:
        read_csv_rows(p, start_row=1, nrows=3, max_rows=2, max_cols=10)
    except ValueError as e:
        assert "nrows" in str(e).lower() and "max_rows" in str(e).lower()
    else:
        raise AssertionError("Expected ValueError when nrows and max_rows conflict")


def test_read_excel_rows_accepts_max_rows_and_start_row(tmp_path: Path) -> None:
    p = tmp_path / "sample.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet"

    ws.append(["h1", "h2", "h3"])
    ws.append(["r1c1", "r1c2", "r1c3"])
    ws.append(["r2c1", "r2c2", "r2c3"])
    ws.append(["r3c1", "r3c2", "r3c3"])

    wb.save(p)

    rows = read_excel_rows(p, sheet_name="Sheet", start_row=2, max_rows=2, max_cols=10)
    assert rows == [
        ["r1c1", "r1c2", "r1c3"],
        ["r2c1", "r2c2", "r2c3"],
    ]


def test_read_excel_rows_raises_if_nrows_and_max_rows_conflict(tmp_path: Path) -> None:
    p = tmp_path / "sample.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet"
    ws.append(["a", "b"])
    ws.append(["1", "2"])
    ws.append(["3", "4"])
    wb.save(p)

    try:
        read_excel_rows(p, sheet_name="Sheet", start_row=1, nrows=3, max_rows=2, max_cols=10)
    except ValueError as e:
        assert "nrows" in str(e).lower() and "max_rows" in str(e).lower()
    else:
        raise AssertionError("Expected ValueError when nrows and max_rows conflict")

# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path

import src.pages.dataset.backend.pane_io as dio


def test_read_data_sample_excel(tmp_path: Path):
    import openpyxl

    p = tmp_path / "hb.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "HB"
    ws.append(["Konto", "", "Beløp"])
    ws.append([3000, 1001, -10.5])
    ws.append([3001, 1002, 20])
    wb.save(p)

    headers = dio.read_excel_header(p, "HB", header_row=1, max_cols=10)
    assert headers == ["Konto", "kol2", "Beløp"]

    sample = dio.read_data_sample(p, "HB", header_row=1, nrows=2, expected_width=len(headers), max_cols=10)
    assert len(sample) == 2
    assert sample[0] == [3000, 1001, -10.5]
    assert sample[1] == [3001, 1002, 20]


def test_read_data_sample_csv_with_preamble(tmp_path: Path):
    p = tmp_path / "hb.csv"
    p.write_text(
        "Rapport;dummy\n"
        "Mer info;dummy\n"
        "Konto;;Beløp\n"
        "3000;1001;-10,50\n"
        "3001;1002;20\n",
        encoding="utf-8",
    )

    headers = dio.read_csv_header(p, header_row=3)
    assert headers == ["Konto", "kol2", "Beløp"]

    sample = dio.read_data_sample(p, None, header_row=3, nrows=2, expected_width=len(headers), max_cols=10)
    assert sample == [["3000", "1001", "-10,50"], ["3001", "1002", "20"]]

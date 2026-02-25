from __future__ import annotations

import datetime as dt

import openpyxl

from dataset_build_fast import build_from_file


def test_build_from_file_respects_sheet_name_and_header_row_excel(tmp_path):
    xlsx = tmp_path / "hb.xlsx"

    wb = openpyxl.Workbook()

    # First sheet: irrelevant/wrong structure (should NOT be used when sheet_name is set)
    ws_wrong = wb.active
    ws_wrong.title = "Feil"
    ws_wrong.append(["ikke", "riktig"])
    ws_wrong.append(["a", "b"])
    ws_wrong.append([1, 2])

    # Second sheet: actual data, but header is on row 2 (row 1 is a title)
    ws_ok = wb.create_sheet("Riktig")
    ws_ok.append(["Hovedbokrapport"])  # row 1 (title)
    ws_ok.append(["Kontonr", "Kontonavn", "Bilagsnummer", "Bilagsdato", "Beløp"])  # row 2 (header)
    ws_ok.append([3000, "Salg", 1001, dt.date(2026, 1, 1), -100.0])
    ws_ok.append([3001, "Salg2", 1002, dt.date(2026, 1, 2), -200.0])

    wb.save(xlsx)

    mapping = {
        "Konto": "Kontonr",
        "Kontonavn": "Kontonavn",
        "Bilag": "Bilagsnummer",
        "Dato": "Bilagsdato",
        "Beløp": "Beløp",
    }

    df = build_from_file(xlsx, mapping=mapping, sheet_name="Riktig", header_row=2)

    assert df.shape[0] == 2
    assert {"konto", "kontonavn", "bilag", "dato", "beløp"}.issubset(df.columns)
    assert int(df["konto"].iloc[0]) == 3000


def test_build_from_file_respects_header_row_csv(tmp_path):
    csv = tmp_path / "hb.csv"

    csv.write_text(
        "Rapport: Hovedbok\n"
        "Generert: 2026-02-06\n"
        "Kontonr,Bilagsnummer,Bilagsdato,Beløp\n"
        "3000,1001,2026-01-01,-100.00\n"
        "3001,1002,2026-01-02,-200.00\n",
        encoding="utf-8",
    )

    mapping = {
        "Konto": "Kontonr",
        "Bilag": "Bilagsnummer",
        "Dato": "Bilagsdato",
        "Beløp": "Beløp",
    }

    df = build_from_file(csv, mapping=mapping, header_row=3)

    assert df.shape[0] == 2
    assert {"konto", "bilag", "dato", "beløp"}.issubset(df.columns)
    assert int(df["bilag"].iloc[1]) == 1002

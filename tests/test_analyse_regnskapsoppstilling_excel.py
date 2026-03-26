from __future__ import annotations

import openpyxl
import pandas as pd


def test_build_regnskapsoppstilling_workbook_creates_main_and_tx_sheet() -> None:
    from analyse_regnskapsoppstilling_excel import build_regnskapsoppstilling_workbook

    rl_df = pd.DataFrame(
        {
            "regnr": [10, 99],
            "regnskapslinje": ["Eiendeler", "SUM"],
            "IB": [100.0, 100.0],
            "Endring": [50.0, 50.0],
            "UB": [150.0, 150.0],
            "Antall": [3, 3],
        }
    )
    regn = pd.DataFrame(
        {
            "nr": [10, 99],
            "regnskapslinje": ["Eiendeler", "SUM"],
            "sumpost": ["nei", "ja"],
            "Formel": ["", "=10"],
        }
    )
    tx_df = pd.DataFrame({"Konto": ["1000"], "Beløp": [150.0], "Tekst": ["Test"]})

    wb = build_regnskapsoppstilling_workbook(
        rl_df,
        regnskapslinjer=regn,
        transactions_df=tx_df,
        client="Nbs Regnskap AS",
        year="2025",
    )

    assert wb.sheetnames == ["Regnskapsoppstilling", "Transaksjoner"]
    ws = wb["Regnskapsoppstilling"]
    assert "Regnskapsoppstilling - Nbs Regnskap AS - 2025" == ws["A1"].value
    assert [ws["A4"].value, ws["B4"].value, ws["C4"].value, ws["D4"].value, ws["E4"].value, ws["F4"].value] == [
        "Nr",
        "Regnskapslinje",
        "IB",
        "Endring",
        "UB",
        "Antall",
    ]
    assert ws["B6"].font.bold is True


def test_save_regnskapsoppstilling_workbook_writes_file(tmp_path) -> None:
    from analyse_regnskapsoppstilling_excel import save_regnskapsoppstilling_workbook

    rl_df = pd.DataFrame(
        {
            "regnr": [10],
            "regnskapslinje": ["Eiendeler"],
            "IB": [100.0],
            "Endring": [25.0],
            "UB": [125.0],
            "Antall": [2],
        }
    )

    out = save_regnskapsoppstilling_workbook(tmp_path / "rl_export", rl_df=rl_df, client="Test", year="2025")

    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Regnskapsoppstilling"]
    assert wb["Regnskapsoppstilling"]["A5"].value == 10

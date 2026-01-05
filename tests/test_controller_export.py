import os

import pandas as pd

from controller_export import export_to_excel


def test_export_to_excel_single_dataframe(tmp_path):
    df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
    out = tmp_path / "one.xlsx"

    result = export_to_excel(out, df)

    assert result == str(out)
    assert os.path.exists(out)

    xf = pd.ExcelFile(out)
    assert "Data" in xf.sheet_names

    read_back = pd.read_excel(out, sheet_name="Data")
    assert list(read_back.columns) == ["A", "B"]
    assert read_back.shape == (2, 2)


def test_export_to_excel_multiple_sheets(tmp_path):
    sheets = {
        "Ark 1": pd.DataFrame({"x": [1]}),
        "Ark/2": pd.DataFrame({"y": [2]}),  # / skal bli sanitert
    }
    out = tmp_path / "multi.xlsx"

    export_to_excel(out, sheets)

    assert os.path.exists(out)
    xf = pd.ExcelFile(out)

    # "Ark/2" -> "Ark_2" pga Excel-regler
    assert "Ark 1" in xf.sheet_names
    assert "Ark_2" in xf.sheet_names

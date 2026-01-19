import pandas as pd


def _sample_df() -> pd.DataFrame:
    # Bilag 1: typical sales invoice (net sales + VAT + receivable)
    # Bilag 2: simple posting (sales + receivable)
    return pd.DataFrame(
        [
            {"Bilag": 1, "Konto": 3000, "Kontonavn": "Salgsinntekter", "Dato": "2025-01-01", "Tekst": "Invoice A", "Beløp": -100.0},
            {"Bilag": 1, "Konto": 2700, "Kontonavn": "Utgående mva", "Dato": "2025-01-01", "Tekst": "Invoice A", "Beløp": -25.0},
            {"Bilag": 1, "Konto": 1500, "Kontonavn": "Kundefordringer", "Dato": "2025-01-01", "Tekst": "Invoice A", "Beløp": 125.0},
            {"Bilag": 2, "Konto": 3000, "Kontonavn": "Salgsinntekter", "Dato": "2025-01-02", "Tekst": "Invoice B", "Beløp": -200.0},
            {"Bilag": 2, "Konto": 1500, "Kontonavn": "Kundefordringer", "Dato": "2025-01-02", "Tekst": "Invoice B", "Beløp": 200.0},
        ]
    )


def test_build_motpost_data_basic():
    from views_motpost_konto import build_motpost_data

    df_all = _sample_df()
    data = build_motpost_data(df_all, {"3000"})

    assert set(data.selected_accounts) == {"3000"}
    assert data.bilag_count == 2
    assert data.selected_sum == -300.0

    # Motkonto should include both VAT and receivables
    motkonto_set = set(data.df_summary["Motkonto"].astype(str).tolist())
    assert motkonto_set == {"2700", "1500"}

    # Control (selected + mot) should be 0 for balanced bilag
    assert round(data.control_sum, 6) == 0.0

    # Details should contain one row per (bilag, motkonto)
    # Bilag 1 has two motkontoer (2700 + 1500), bilag 2 has one (1500)
    assert len(data.df_details) == 3
    assert (data.df_details["Bilag_key"] == "1").sum() == 2
    assert (data.df_details["Bilag_key"] == "2").sum() == 1


def test_excel_workbook_contains_outlier_sheets():
    from views_motpost_konto import build_motpost_data, build_motpost_excel_workbook

    df_all = _sample_df()
    data = build_motpost_data(df_all, {"3000"})

    wb = build_motpost_excel_workbook(
        data,
        df_details_view=data.df_details,
        outlier_accounts={"2700"},
    )

    assert set(wb.sheetnames) >= {"Motkonto", "Bilag", "Outliers", "OutlierBilag"}

    ws_out = wb["Outliers"]
    # Find motkonto column values in Outliers sheet (skip header rows)
    motkonto_values = []
    for r in range(1, ws_out.max_row + 1):
        v = ws_out.cell(row=r, column=1).value
        if v in (None, "Motkonto"):
            continue
        # The exporter writes a short summary line in A1; ignore any non-konto values.
        if not str(v).strip().isdigit():
            continue
        motkonto_values.append(v)
    # Should only contain 2700
    assert any(str(v) == "2700" for v in motkonto_values)
    assert all(str(v) == "2700" for v in motkonto_values)

import pandas as pd

from motpost.combinations import build_bilag_to_motkonto_combo
from motpost.combinations import build_motkonto_combinations_per_selected_account
from motpost.combo_workflow import apply_combo_status
from motpost_konto_core import build_motpost_excel_workbook
from views_motpost_konto import build_motpost_data


def _sample_df() -> pd.DataFrame:
    # A tiny dataset with two bilag. Selected account is 3000.
    #
    # Bilag 1: 3000 kredit -1000, motposter 2700 debet 250, 1500 debet 750
    # Bilag 2: 3000 kredit -500,  motposter 1500 debet 500
    return pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 2, 2],
            "Dato": [
                "2025-01-01",
                "2025-01-01",
                "2025-01-01",
                "2025-01-02",
                "2025-01-02",
            ],
            "Konto": ["3000", "2700", "1500", "3000", "1500"],
            "Kontonavn": [
                "Salg",
                "Utgående mva",
                "Kundefordringer",
                "Salg",
                "Kundefordringer",
            ],
            "Tekst": ["Salg A", "MVA", "Kunde A", "Salg B", "Kunde B"],
            "Beløp": [-1000.0, 250.0, 750.0, -500.0, 500.0],
        }
    )


def test_build_motpost_data_credit_only_sums():
    df = _sample_df()
    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")
    assert data.bilag_count == 2
    # Selected sum is only the credit lines on 3000: -1000 + -500 = -1500
    assert data.selected_sum == -1500.0
    # Control sum on scope should be 0.0
    assert abs(data.control_sum) < 1e-9


def test_bilag_to_motkonto_combo_and_drilldown_symmetry():
    df = _sample_df()
    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")

    bilag_to_combo = build_bilag_to_motkonto_combo(data.df_scope, ["3000"])
    assert bilag_to_combo["1"] == "1500, 2700"
    assert bilag_to_combo["2"] == "1500"

    # For bilag 1, selected sum is -1000 and mot sum is +1000 (250+750)
    df_b1 = data.df_scope[data.df_scope["Bilag_str"] == "1"].copy()
    sel_mask = (df_b1["Konto_str"] == "3000") & (df_b1["Beløp"] < 0)
    sum_sel = float(df_b1.loc[sel_mask, "Beløp"].sum())
    sum_mot = float(df_b1.loc[~sel_mask, "Beløp"].sum())
    assert sum_sel == -1000.0
    assert sum_mot == 1000.0
    assert abs(sum_sel + sum_mot) < 1e-9


def _find_header_row(ws, must_contain: set[str]) -> int:
    for r in range(1, ws.max_row + 1):
        row_vals = []
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row=r, column=c).value
            if v not in (None, ""):
                row_vals.append(str(v).strip())
        if must_contain.issubset(set(row_vals)):
            return r
    raise AssertionError(f"Could not find table header row containing {must_contain}")


def _read_sheet_table(ws, must_contain: set[str]) -> tuple[list[str], list[dict[str, object]]]:
    """Helper: reads a sheet written by _write_df_table (title row + blank + header)."""
    header_row = _find_header_row(ws, must_contain)

    headers: list[str] = []
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=header_row, column=c).value
        if v in (None, ""):
            break
        headers.append(str(v))

    rows: list[dict[str, object]] = []
    for r in range(header_row + 1, ws.max_row + 1):
        row_values = [ws.cell(row=r, column=c).value for c in range(1, len(headers) + 1)]
        if all(v in (None, "") for v in row_values):
            continue
        row: dict[str, object] = {}
        for c, h in enumerate(headers, start=1):
            row[h] = ws.cell(row=r, column=c).value
        rows.append(row)
    return headers, rows


def test_excel_workbook_combo_status_and_outlier_bilag_extract_happy_path():
    df = _sample_df()
    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")

    # Mark combo "1500, 2700" as outlier and combo "1500" as expected
    status_map = {"1500, 2700": "outlier", "1500": "expected"}

    wb = build_motpost_excel_workbook(data, combo_status_map=status_map)

    assert set(wb.sheetnames) == {
        "Oversikt",
        "Valgte kontoer",
        "Kombinasjoner",
        "Oppsummering status",
        "Outlier – Full bilagsutskrift",
    }

    # Kombinasjoner sheet should contain Status + Kombinasjon (navn)
    ws_combo = wb["Kombinasjoner"]
    headers, rows = _read_sheet_table(ws_combo, {"Kombinasjon", "Status"})
    assert "Status" in headers
    assert "Kombinasjon (navn)" in headers

    by_combo = {str(r["Kombinasjon"]): r for r in rows}
    assert by_combo["1500, 2700"]["Status"] == "Outlier"
    assert by_combo["1500"]["Status"] == "Forventet"

    combo_name = str(by_combo["1500, 2700"]["Kombinasjon (navn)"])
    assert "1500" in combo_name and "Kundefordringer" in combo_name
    assert "2700" in combo_name and "Utgående mva" in combo_name

    # Valgte kontoer sheet should show which kontoer er valgt og sum
    ws_sel = wb["Valgte kontoer"]
    h_sel, r_sel = _read_sheet_table(ws_sel, {"Konto", "Sum valgte kontoer"})
    assert "Andel av valgt" in h_sel
    by_konto = {str(r["Konto"]): r for r in r_sel if r.get("Konto") not in (None, "")}
    assert float(by_konto["3000"]["Sum valgte kontoer"]) == -1500.0
    assert abs(float(by_konto["3000"]["Andel av valgt"]) - 1.0) < 1e-9

    # Outlier sheet should contain only bilag 1 (all lines)
    ws_out = wb["Outlier – Full bilagsutskrift"]
    h_out, r_out = _read_sheet_table(ws_out, {"Bilag", "Konto"})
    assert "Kombinasjon (navn)" in h_out

    bilag_values = {str(r["Bilag"]) for r in r_out if r.get("Bilag") not in (None, "")}
    assert bilag_values == {"1"}

    konto_values = {str(r["Konto"]) for r in r_out if r.get("Konto") not in (None, "")}
    assert {"3000", "2700", "1500"}.issubset(konto_values)

    # Three lines in bilag 1
    assert len([r for r in r_out if r.get("Bilag") not in (None, "")]) == 3


def test_excel_workbook_excludes_blank_bilag_and_documents_note():
    # Typical SAF-T edge case: missing bilagsnummer (None/NaN).
    df = pd.DataFrame(
        {
            "Bilag": [None, None, None],
            "Dato": ["2025-01-01", "2025-01-01", "2025-01-01"],
            "Konto": ["3000", "2700", "1500"],
            "Kontonavn": ["Salg", "Utgående mva", "Kundefordringer"],
            "Tekst": ["Salg A", "MVA", "Kunde A"],
            "Beløp": [-1000.0, 250.0, 750.0],
        }
    )
    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")

    # Combo will be "1500, 2700" but bilag-id is blank -> excluded from full bilag extract.
    wb = build_motpost_excel_workbook(data, combo_status_map={"1500, 2700": "outlier"})
    ws_out = wb["Outlier – Full bilagsutskrift"]

    # The note about excluded blank bilag must be present (documented).
    found = False
    for r in range(1, ws_out.max_row + 1):
        for c in range(1, ws_out.max_column + 1):
            v = ws_out.cell(row=r, column=c).value
            if isinstance(v, str) and "uten bilagsnummer" in v:
                found = True
                break
        if found:
            break
    assert found, "Expected note about excluded blank bilag groups in outlier sheet"


def test_build_motkonto_combinations_per_selected_account():
    df = _sample_df()
    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")
    konto_name_map = {"3000": "Salg", "2700": "Utgående mva"}

    df_per = build_motkonto_combinations_per_selected_account(
        df_scope=data.df_scope,
        selected_accounts=list(data.selected_accounts),
        outlier_motkonto=set(),
        konto_navn_map=konto_name_map,
        selected_direction=data.selected_direction,
    )
    assert "Valgt konto" in df_per.columns
    assert "Kombinasjon" in df_per.columns

    df_3000 = df_per[df_per["Valgt konto"].astype(str) == "3000"]
    combos_3000 = set(df_3000["Kombinasjon"].astype(str).tolist())
    assert combos_3000 == {"1500, 2700", "1500"}

    # Kun 3000 er valgt-konto i dette testsettet
    assert set(df_per["Valgt konto"].astype(str).tolist()) == {"3000"}


def test_apply_combo_status_updates_multiple_keys_and_resets():
    status_map: dict[str, str] = {"1500": "expected"}

    # Happy path: multiselect set to outlier
    apply_combo_status(status_map, ["1500", "1500, 2700"], "outlier")
    assert status_map["1500"] == "outlier"
    assert status_map["1500, 2700"] == "outlier"

    # Reset one key
    apply_combo_status(status_map, ["1500"], "")
    assert "1500" not in status_map
    assert status_map["1500, 2700"] == "outlier"

    # Typical "error" case: unknown status -> treated as neutral (removed)
    apply_combo_status(status_map, ["1500, 2700"], "not-a-valid-status")
    assert status_map == {}

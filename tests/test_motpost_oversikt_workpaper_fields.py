import pandas as pd

from src.audit_actions.motpost.konto_core import build_motpost_excel_workbook
from views_motpost_konto import build_motpost_data


def _find_cell(ws, needle: str):
    for row in ws.iter_rows():
        for cell in row:
            if cell.value == needle:
                return cell
    return None


def test_oversikt_has_workpaper_inputs_and_no_duplicate_navlist():
    # Minimal datasett som gir minst én outlier-fane
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 2, 2],
            "Dato": ["2025-01-01", "2025-01-01", "2025-01-02", "2025-01-02"],
            "Konto": ["3000", "1500", "3000", "1500"],
            "Kontonavn": ["Salg", "Kundefordringer", "Salg", "Kundefordringer"],
            "Tekst": ["Salg A", "Mot", "Salg B", "Mot"],
            "Beløp": [-100.0, 100.0, -50.0, 50.0],
        }
    )

    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")
    wb = build_motpost_excel_workbook(data, combo_status_map={"1500": "outlier"})
    ws = wb["Oversikt"]

    # (1) Ikke ha topp-oppsummering for "Netto kredit (valgte kontoer)" (C12 i tidligere versjoner)
    assert _find_cell(ws, "Netto kredit (valgte kontoer)") is None

    # (2) Innholdslisten skal ikke ligge i arket (ble opplevd som dobbelt opp)
    assert _find_cell(ws, "Innhold") is None

    # (3) Skal ha enkel handlingsbeskrivelse synlig på oversikt (ref. eksempelmal)
    assert ws["E6"].value == "Handling"

    # (4) Skal ha inputfelt/arbeidspapir-felter som i eksempelmal
    c_thr_lbl = _find_cell(ws, "Arbeidsvesentlighetsgrense")
    assert c_thr_lbl is not None

    # Verdicelle (kolonnen til høyre) skal være tom ved eksport (input)
    thr_val = ws.cell(row=c_thr_lbl.row, column=c_thr_lbl.column + 1)
    assert thr_val.value in (None, "")

    c_rest_lbl = _find_cell(ws, "Restpopulasjon")
    assert c_rest_lbl is not None
    assert c_rest_lbl.row == c_thr_lbl.row + 1

    c_diff_lbl = _find_cell(ws, "differanse")
    assert c_diff_lbl is not None
    assert c_diff_lbl.row == c_thr_lbl.row + 2

    # Differanse er beregnet med formel
    diff_val = ws.cell(row=c_diff_lbl.row, column=c_diff_lbl.column + 1)
    assert isinstance(diff_val.value, str)
    assert diff_val.value.startswith("=IF(")

    # Konklusjonsfeltet skal finnes og være tydelig (stor skriveflate)
    c_conc_lbl = _find_cell(ws, "Konklusjon")
    assert c_conc_lbl is not None
    placeholder = ws.cell(row=c_conc_lbl.row + 1, column=c_conc_lbl.column)
    assert isinstance(placeholder.value, str)
    assert placeholder.value.strip() != ""

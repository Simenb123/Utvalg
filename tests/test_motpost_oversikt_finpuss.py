import pandas as pd

from motpost.excel_sheets.common import DEFAULT_INT_FORMAT
from motpost.konto_core import build_motpost_data
from motpost_konto_core import build_motpost_excel_workbook


def _find_cell(ws, value: str):
    for row in ws.iter_rows():
        for cell in row:
            if cell.value == value:
                return cell
    return None


def test_oversikt_finpuss_compact_layout_and_formats():
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 2, 2],
            "Dato": ["2025-01-01", "2025-01-01", "2025-01-02", "2025-01-02"],
            "Tekst": ["Salg", "Mot", "Salg", "Mot"],
            "Konto": ["3000", "1500", "3000", "1500"],
            "Kontonavn": ["Salg", "Kundefordringer", "Salg", "Kundefordringer"],
            "Beløp": [-1000.0, 1000.0, -500.0, 500.0],
        }
    )

    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")
    wb = build_motpost_excel_workbook(data, combo_status_map={"1500": "outlier"})
    ws = wb["Oversikt"]

    # (1) "Parametre" er fjernet, og "Generert" starter på rad 3
    assert _find_cell(ws, "Parametre") is None

    c_gen = _find_cell(ws, "Generert")
    assert c_gen is not None
    assert (c_gen.row, c_gen.column) == (3, 2)  # B3

    # (2) Parameterblokk har linjemarkeringer (tynne border-linjer)
    assert c_gen.border.bottom.style == "thin"
    assert ws.cell(row=3, column=3).border.bottom.style == "thin"  # C3

    # (3) Populasjon-raden finnes i parameterblokken og har int-format (tusenskille, ingen desimaler)
    c_pop = _find_cell(ws, "Populasjon (valgte kontoer - Kredit)")
    assert c_pop is not None
    assert c_pop.row == 8

    pop_val = ws.cell(row=c_pop.row, column=c_pop.column + 1)
    assert pop_val.number_format == DEFAULT_INT_FORMAT

    # (4) Handling-boks stopper i kolonne H (E6:H6 er merged)
    merged = {str(rng) for rng in ws.merged_cells.ranges}
    assert "E6:H6" in merged

    # Nye handlingstekster (radene E7-E9)
    assert ws["E7"].value == (
        "1. Opparbeid en forståelse av uforventede kombinasjoner og dokumenter vurderingen i fanene #x."
    )
    assert ws["E8"].value == "2. Vurder om det er relevant å detaljteste på bilagsnivå"
    assert ws["E9"].value == "3. Oppsummer og konkluder"

    # (5) Outlier-indeks starter i kolonne A
    c_out_title = _find_cell(ws, "Outliers (ikke forventet) – dokumenter i egne faner")
    assert c_out_title is not None
    assert c_out_title.column == 1

    # Wrap på headeren "Sum valgte kontoer (Kredit)" i outlier-indeksen
    c_sum_hdr = _find_cell(ws, "Sum valgte kontoer (Kredit)")
    assert c_sum_hdr is not None
    assert c_sum_hdr.column == 4  # D
    assert bool(c_sum_hdr.alignment.wrap_text) is True

    # (6) Kolonnebredder: B og H litt bredere, og D litt smalere
    assert float(ws.column_dimensions["B"].width) >= 34
    assert float(ws.column_dimensions["H"].width) >= 38
    assert float(ws.column_dimensions["D"].width) <= 20

    # (7) Finn header-raden i status-tabellen og sjekk at beløpskolonner er int-format
    c_status_title = _find_cell(ws, "Oversikt forventet / ikke forventet")
    assert c_status_title is not None
    header_row = c_status_title.row + 2

    headers = [ws.cell(row=header_row, column=c).value for c in range(1, 30)]
    assert "Sum valgte kontoer" in headers
    assert "Netto kredit" in headers

    col_sum = headers.index("Sum valgte kontoer") + 1
    col_net = headers.index("Netto kredit") + 1

    first_data_row = header_row + 1
    assert ws.cell(row=first_data_row, column=col_sum).number_format == DEFAULT_INT_FORMAT
    assert ws.cell(row=first_data_row, column=col_net).number_format == DEFAULT_INT_FORMAT

    # (8) Konklusjonsfeltet stopper i kolonne H (ikke J)
    c_conc = _find_cell(ws, "Konklusjon")
    assert c_conc is not None

    box_top_row = c_conc.row + 1
    box_left_col = c_conc.column  # B

    # Plassholder-/starttekst skal finnes (ikke blank)
    placeholder = ws.cell(row=box_top_row, column=box_left_col).value
    assert isinstance(placeholder, str)
    assert placeholder.strip() != ""

    found = None
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= box_top_row <= rng.max_row and rng.min_col <= box_left_col <= rng.max_col:
            found = rng
            break
    assert found is not None
    assert found.min_col == 2  # B
    assert found.max_col == 8  # H

    # (9) Standard frys etter rad 1
    assert ws.freeze_panes == "A2"

import pandas as pd
from openpyxl import Workbook

from src.audit_actions.motpost.excel_sheets.common import _write_df_table


def test_autowidth_ignores_hyperlink_formula_text() -> None:
    """Regresjon: HYPERLINK-formler skal ikke gjøre kolonnen enorm pga formeltekst."""

    wb = Workbook()
    ws = wb.active

    df = pd.DataFrame(
        {
            "Dokumentasjon": [
                '=HYPERLINK("#\'Oversikt\'!A1","Gå til")',
            ],
        }
    )

    _write_df_table(ws, df, "Tabell", start_row=1, start_col=1)

    width_a = ws.column_dimensions["A"].width
    assert width_a is not None

    # Skal være moderat (basert på visningsteksten "Gå til"),
    # ikke lengden på selve formelen.
    assert float(width_a) <= 18


def test_autowidth_caps_long_headers() -> None:
    """Regresjon: lange overskrifter skal ikke alene tvinge enorme kolonnebredder."""

    wb = Workbook()
    ws = wb.active

    df = pd.DataFrame(
        {
            "Netto kredit (valgte kontoer)": [123.45],
        }
    )

    _write_df_table(ws, df, "Tabell", start_row=1, start_col=1)

    width_a = ws.column_dimensions["A"].width
    assert width_a is not None

    # Header er lang, men dataverdien er kort. Vi capper overskrift-lengde, så
    # kolonnen ikke blir unødvendig bred.
    assert float(width_a) <= 22

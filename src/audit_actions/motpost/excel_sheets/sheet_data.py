"""Bygger "Data"-arket i motpostanalyse-eksporten.

Prinsipp:
- Oversikt-arket skal være kort og arbeidspapir-aktig.
- Data-arket kan være mer "utfyllende" med tabeller.

Denne modulen skriver tre tabeller:
1) Valgte kontoer (populasjon)
2) Kombinasjoner
3) Oversikt forventet / ikke forventet
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from openpyxl.worksheet.worksheet import Worksheet

from .common import (
    FILL_EXPECTED,
    FILL_OUTLIER,
    hide_gridlines,
    set_column_widths,
    _write_df_table,
)


def _apply_status_row_fills(
    ws: Worksheet,
    *,
    table_start_row: int,
    first_data_row: int,
    last_data_row: int,
    start_col: int,
    last_col: int,
    status_col_index: int,
) -> None:
    """Fargelegg kombinasjonsrader basert på status."""

    for r in range(first_data_row, last_data_row + 1):
        v = ws.cell(row=r, column=status_col_index).value
        status = str(v or "").strip().lower()
        if status in {"ikke forventet", "outlier"}:
            fill = FILL_OUTLIER
        elif status in {"forventet"}:
            fill = FILL_EXPECTED
        else:
            fill = None

        if fill is None:
            continue
        for c in range(start_col, last_col + 1):
            ws.cell(row=r, column=c).fill = fill


def write_data_sheet(
    ws: Worksheet,
    *,
    df_valgte_kontoer: pd.DataFrame,
    df_kombinasjoner: pd.DataFrame,
    df_status: pd.DataFrame,
) -> None:
    """Skriv Data-arket."""

    hide_gridlines(ws)

    # --- Valgte kontoer (populasjon) ---
    res_sel = _write_df_table(
        ws,
        df_valgte_kontoer,
        "Valgte kontoer (populasjon)",
        start_row=1,
        start_col=1,
        add_summary_row=True,
    )

    # --- Kombinasjoner ---
    next_row = res_sel.last_row + 3
    res_combo = _write_df_table(
        ws,
        df_kombinasjoner,
        "Kombinasjoner",
        start_row=next_row,
        start_col=1,
        add_summary_row=True,
    )

    # Farg rader etter status
    if df_kombinasjoner is not None and not df_kombinasjoner.empty and "Status" in df_kombinasjoner.columns:
        status_offset = list(df_kombinasjoner.columns).index("Status")
        status_col = res_combo.start_col + status_offset
        _apply_status_row_fills(
            ws,
            table_start_row=res_combo.start_row,
            first_data_row=res_combo.first_data_row,
            last_data_row=res_combo.last_data_row,
            start_col=res_combo.start_col,
            last_col=res_combo.last_col,
            status_col_index=status_col,
        )

    # --- Oversikt forventet / ikke forventet ---
    next_row = res_combo.last_row + 3
    _write_df_table(
        ws,
        df_status,
        "Oversikt forventet / ikke forventet",
        start_row=next_row,
        start_col=1,
        add_summary_row=True,
    )

    # --- Kolonnebredder (kompakt og "mal"-aktig) ---
    # NB: Setter faste bredder for å unngå at lange kommentarer/formler gjør arket enormt.
    set_column_widths(
        ws,
        {
            "A": 8,
            "B": 44,
            "C": 49,
            "D": 24,
            "E": 24,
            "F": 16,
            "G": 16,
            "H": 16,
            "I": 16,
            "J": 35,
        },
    )

    # Frys toppdelen (tittel + overskrifter for første tabell)
    # _write_df_table bruker: tittelrad, tom rad, header-rad, data...
    ws.freeze_panes = "A4"

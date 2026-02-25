from __future__ import annotations

"""Fane: "Outlier-kombinasjoner" i motpost-arbeidspapiret.

Denne fanen er en ren "arbeidsliste":
- Kun kombinasjoner som er markert som Outlier
- Lenker til bilagslinjer (full bilagsutskrift)
- (Valgfritt) lenke til dokumentasjonsfane per kombinasjon

Hvorfor egen fane?
- Oversikt skal være kompakt.
- Outlier-listen kan bli bred (kombinasjonsnavn, kommentarer, lenker).
"""

from typing import Optional

import pandas as pd
from openpyxl import Workbook

from .common import _set_cell, _write_df_table, _write_kv_sheet


def write_outlier_index_sheet(
    wb: Workbook,
    *,
    df_out_idx: Optional[pd.DataFrame],
) -> None:
    """Opprett og skriv fanen "Outlier-kombinasjoner".

    Arket opprettes alltid (for stabil navigasjon), men kan inneholde en "ingen rader"-melding.
    """

    if "Outlier-kombinasjoner" in wb.sheetnames:
        ws = wb["Outlier-kombinasjoner"]
    else:
        ws = wb.create_sheet("Outlier-kombinasjoner")

    cnt = 0
    try:
        cnt = int(len(df_out_idx)) if df_out_idx is not None else 0
    except Exception:
        cnt = 0

    kv = [
        ("Til oversikt", "=HYPERLINK(\"#'Oversikt'!A1\",\"Oversikt\")"),
        ("Antall outlier-kombinasjoner", cnt),
        ("Arbeidsflyt", "Merk kombinasjoner i 'Kombinasjoner'. Outliers listes her automatisk."),
    ]

    next_row = _write_kv_sheet(
        ws,
        "Outlier-kombinasjoner",
        kv,
        key_col_width=26,
        value_col_width=48,
        apply_column_widths=True,
    )

    if df_out_idx is None or df_out_idx.empty:
        _set_cell(ws, next_row, 1, "(ingen outlier-kombinasjoner)")
        return

    _write_df_table(
        ws,
        df_out_idx,
        "Outlier-kombinasjoner",
        start_row=next_row,
        start_col=1,
        add_summary_row=True,
        max_col_width=34,
    )


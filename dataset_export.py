from __future__ import annotations

"""dataset_export.py

Eksport av innlastet hovedbok (transactions) til Excel.

Hvorfor egen modul?
- GUI (DatasetPane) skal holde seg tynn og UI-fokusert.
- Eksportlogikk skal være testbar uten Tkinter.

Funksjonalitet:
- Eksporter en DataFrame til Excel via `controller_export.export_to_excel` slik at vi får
  konsistent formatering (header, autofilter, datoformat dd.mm.yyyy, beløpformat osv.)
- Dersom datasettet overstiger Excel sin radgrense per ark, deles det automatisk i flere ark.

Excel-begrensninger (per ark):
- Maks 1 048 576 rader totalt (inkludert header-raden).
- Det betyr maks 1 048 575 datarader når vi skriver header.
"""

from pathlib import Path
from typing import Dict

import pandas as pd

from controller_export import export_to_excel

EXCEL_MAX_ROWS: int = 1_048_576
EXCEL_MAX_DATA_ROWS: int = EXCEL_MAX_ROWS - 1


def build_hovedbok_excel_sheets(
    df: pd.DataFrame,
    *,
    sheet_name: str = "Hovedbok",
    max_rows_per_sheet: int = EXCEL_MAX_DATA_ROWS,
) -> Dict[str, pd.DataFrame]:
    """Bygg et sheet->DataFrame mapping for hovedbok-eksport.

    Args:
        df: DataFrame med transaksjoner/hovedbok.
        sheet_name: Base-arknavn.
        max_rows_per_sheet: Maks antall *datarader* per ark (header kommer i tillegg).

    Returns:
        Dict med {arknavn -> DataFrame}.

    Raises:
        ValueError: hvis df er tom/None, eller max_rows_per_sheet <= 0.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        raise ValueError("Ingen data å eksportere.")

    if max_rows_per_sheet <= 0:
        raise ValueError("max_rows_per_sheet må være > 0")

    n = int(len(df))
    if n <= max_rows_per_sheet:
        return {sheet_name: df}

    sheets: Dict[str, pd.DataFrame] = {}
    i = 1
    for start in range(0, n, max_rows_per_sheet):
        end = min(start + max_rows_per_sheet, n)
        # Del opp i flere ark: Hovedbok_1, Hovedbok_2, ...
        sheets[f"{sheet_name}_{i}"] = df.iloc[start:end]
        i += 1
    return sheets


def export_hovedbok_to_excel(
    path: str | Path,
    df: pd.DataFrame,
    *,
    sheet_name: str = "Hovedbok",
    max_rows_per_sheet: int = EXCEL_MAX_DATA_ROWS,
) -> str:
    """Eksporter hovedbok (DataFrame) til Excel.

    Denne funksjonen åpner ikke Excel automatisk. Det håndteres av GUI (best effort).

    Args:
        path: Filsti (eller Path) som brukeren har valgt.
        df: DataFrame som skal eksporteres.
        sheet_name: Base-arknavn.
        max_rows_per_sheet: Maks antall datarader per ark (for splitting).

    Returns:
        Faktisk filsti (string) som ble skrevet.

    Raises:
        ValueError: hvis df er tom/None, eller max_rows_per_sheet <= 0.
    """
    sheets = build_hovedbok_excel_sheets(
        df,
        sheet_name=sheet_name,
        max_rows_per_sheet=max_rows_per_sheet,
    )
    # Viktig: aldri åpne filutforsker automatisk her (testvennlig).
    return export_to_excel(
        str(path),
        sheets=sheets,
        auto_filename=False,
        open_folder=False,
        filename_prefix="Hovedbok",
    )

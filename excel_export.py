
from __future__ import annotations
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

def export_strata_and_sample(xlsx_path: str, strata_df: pd.DataFrame, sample_df: pd.DataFrame) -> None:
    """Eksporter to ark: 'Strata' og 'Trekk' med norsk formateringsvennlig data.
    Lar Excel gjøre visningen; vi holder oss enkle for kompatibilitet.
    """
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Strata"
    for r in dataframe_to_rows(strata_df, index=False, header=True):
        ws1.append(r)

    ws2 = wb.create_sheet("Trekk")
    for r in dataframe_to_rows(sample_df, index=False, header=True):
        ws2.append(r)

    wb.save(xlsx_path)

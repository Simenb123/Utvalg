# excel_export.py
from __future__ import annotations
from typing import Dict, Iterable
import os, tempfile
import pandas as pd

def export_and_open(sheets: Dict[str, pd.DataFrame], prefer_date_cols: Iterable[str] = (),
                    prefer_amount_cols: Iterable[str] = ()) -> str:
    tmp = tempfile.NamedTemporaryFile(prefix="Analyser_", suffix=".xlsx", delete=False)
    tmp.close()
    path = tmp.name
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in sheets.items():
            safe = name[:31] if name else "Ark"
            (df if df is not None else pd.DataFrame()).to_excel(xw, sheet_name=safe, index=False)
        wb = xw.book
        for name, df in sheets.items():
            if df is None or df.empty:
                continue
            ws = wb[name[:31]]
            cols = list(df.columns)
            for cand in prefer_date_cols:
                if cand in df.columns:
                    idx = cols.index(cand) + 1
                    for col in ws.iter_cols(min_col=idx, max_col=idx, min_row=2, max_row=ws.max_row):
                        for cell in col: cell.number_format = "DD.MM.YYYY"
            for cand in prefer_amount_cols:
                if cand in df.columns:
                    idx = cols.index(cand) + 1
                    for col in ws.iter_cols(min_col=idx, max_col=idx, min_row=2, max_row=ws.max_row):
                        for cell in col: cell.number_format = "# ##0,00"
    try:
        os.startfile(path)  # Windows
    except Exception:
        pass
    return path

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd


def list_xls_sheets(path: Path) -> list[str]:
    try:
        xf = pd.ExcelFile(path)
        return list(xf.sheet_names)
    except Exception:
        return []


def read_xls_header(path: Path, *, header_row: int, sheet_name: Optional[str]) -> list[str]:
    try:
        df = pd.read_excel(path, sheet_name=sheet_name or 0, header=header_row - 1, nrows=0)
    except Exception as e:
        raise RuntimeError(
            "Kunne ikke lese .xls (mangler ofte 'xlrd'). Konverter til .xlsx eller installer xlrd."
        ) from e
    return [str(c).strip() for c in df.columns.tolist() if str(c).strip()]


def read_xls_sample(path: Path, *, nrows: int = 200) -> pd.DataFrame:
    try:
        return pd.read_excel(path, header=None, nrows=nrows)
    except Exception as e:
        raise RuntimeError(
            "Kunne ikke forhåndsvise .xls (mangler ofte 'xlrd'). Konverter til .xlsx eller installer xlrd."
        ) from e

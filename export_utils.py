from __future__ import annotations
from typing import Iterable, Set
from pathlib import Path
import pandas as pd
import os, sys, tempfile

from models import Columns

def export_selection_to_excel(df: pd.DataFrame, c: Columns, sample_ids: Iterable[str] | Set[str]) -> Path:
    sample_ids = {str(x) for x in sample_ids}
    fullt = df[df[c.bilag].astype(str).isin(sample_ids)].copy()
    inter = fullt  # (her kunne man filtrert på valgte kontoer hvis ønskelig)
    summer = (
        inter.groupby(c.bilag)[c.belop]
        .agg(Sum="sum", Linjer="count")
        .reset_index()
    )
    tmpdir = Path(tempfile.gettempdir())
    path = tmpdir / f"Bilag_uttrekk_{len(sample_ids)}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        fullt.to_excel(xw, "Fullt_bilagsutvalg", index=False)
        inter.to_excel(xw, "Utvalg", index=False)
        summer.to_excel(xw, "Bilag_summer", index=False)

    # Åpne filen direkte (Windows/Mac/Linux)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            os.system(f"open '{path}'")
        else:
            os.system(f"xdg-open '{path}' >/dev/null 2>&1 &")
    except Exception:
        pass
    return path

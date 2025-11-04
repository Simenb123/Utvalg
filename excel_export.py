from __future__ import annotations
from typing import Dict
import os, sys, tempfile, subprocess
import pandas as pd

def _san(name: str) -> str:
    bad = '[]:*?/\\'
    for ch in bad: name = name.replace(ch, "_")
    return name[:31] if len(name) > 31 else name

def _open_path(path: str) -> None:
    try:
        if sys.platform.startswith("win"): os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin": subprocess.Popen(["open", path])
        else: subprocess.Popen(["xdg-open", path])
    except Exception: pass

def export_temp_excel(sheets: Dict[str, pd.DataFrame], prefix: str = "Utvalg_") -> str:
    import warnings
    warnings.simplefilter("ignore", category=FutureWarning)
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".xlsx"); os.close(fd)
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, df in sheets.items():
            if df is None: continue
            try: df.to_excel(xw, sheet_name=_san(str(name)), index=False)
            except Exception: pd.DataFrame(df).to_excel(xw, sheet_name=_san(str(name)), index=False)
    _open_path(path); return path

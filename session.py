from __future__ import annotations
from typing import Optional, Tuple
import pandas as pd
from models import Columns

_DF: Optional[pd.DataFrame] = None
_COLS: Optional[Columns] = None

def set_dataset(df: pd.DataFrame, cols: Columns) -> None:
    global _DF, _COLS
    _DF, _COLS = df.copy(), cols

def get_dataset() -> Tuple[Optional[pd.DataFrame], Optional[Columns]]:
    return _DF, _COLS

def has_dataset() -> bool:
    return _DF is not None and _COLS is not None

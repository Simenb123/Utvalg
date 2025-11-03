# session.py
from __future__ import annotations
from typing import Optional, Tuple
import pandas as pd
from models import Columns

_df: Optional[pd.DataFrame] = None
_cols: Optional[Columns] = None

def set_dataset(df: pd.DataFrame, cols: Columns) -> None:
    global _df, _cols
    _df, _cols = df, cols

def get_dataset() -> Tuple[Optional[pd.DataFrame], Optional[Columns]]:
    return _df, _cols

def has_dataset() -> bool:
    return _df is not None and _cols is not None

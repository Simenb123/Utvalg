from __future__ import annotations
from typing import Tuple, Optional
import pandas as pd
from models import Columns

_df: Optional[pd.DataFrame] = None
_cols: Optional[Columns] = None

#
# Global dataset and selection storage
# -----------------------------------
#
# Besides the internal ``_df``/``_cols`` used by early versions of the code, we also
# expose two module-level attributes: ``dataset`` and ``SELECTION``.  These
# attributes are used by the GUI to share the currently loaded transactions
# DataFrame and the set of selected accounts between different pages
# (DatasetPane, AnalysePage and UtvalgPage).  Modules that import
# ``session`` can set or get these attributes directly.  The ``set_dataset``
# function also updates ``dataset`` so callers that use the older API still
# update the shared DataFrame.

# The currently loaded transactions DataFrame.  None until a dataset is
# constructed.
dataset: Optional[pd.DataFrame] = None

# A mutable structure holding information about the current account selection.
# Expected keys:
#     ``accounts`` – a list of account identifiers (as strings)
#     ``version`` – an integer that increments each time the selection changes
SELECTION: dict = {}

def set_dataset(df: pd.DataFrame, cols: Columns) -> None:
    global _df, _cols, dataset
    _df, _cols = df, cols
    # Also update the global dataset attribute so other modules can retrieve
    # the current DataFrame via session.dataset. Without this assignment
    # modules that import session will not see the loaded data.
    dataset = df

def get_dataset() -> Tuple[Optional[pd.DataFrame], Optional[Columns]]:
    return _df, _cols

def has_dataset() -> bool:
    return _df is not None and _cols is not None
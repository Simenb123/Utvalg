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

# Active client and year – set by ui_main when a dataset is loaded.
# Used by RL-pivot and other modules that need to know current context.
client: Optional[str] = None
year: Optional[str] = None

# Active version type – "hb", "sb", or None.
# Set by set_dataset() / set_tb() so downstream consumers know whether
# the session is running in full transaction mode or TB-only.
version_type: Optional[str] = None

# Active trial-balance DataFrame (saldobalanse).
# Populated when the user selects an SB version; None otherwise.
# Columns: konto, kontonavn, ib, ub, netto.
tb_df: Optional[pd.DataFrame] = None

# Feature-specific state containers used by newer workspaces.
# These are intentionally loose and can be replaced by richer dataclasses
# later without breaking the basic session contract.
consolidation_project = None
reskontro_state: dict = {}

# A mutable structure holding information about the current account selection.
# Expected keys:
#     ``accounts`` – a list of account identifiers (as strings)
#     ``version`` – an integer that increments each time the selection changes
SELECTION: dict = {}

def set_dataset(df: pd.DataFrame, cols: Columns) -> None:
    global _df, _cols, dataset, version_type
    _df, _cols = df, cols
    # Also update the global dataset attribute so other modules can retrieve
    # the current DataFrame via session.dataset. Without this assignment
    # modules that import session will not see the loaded data.
    dataset = df
    version_type = "hb"


def set_tb(df: pd.DataFrame) -> None:
    """Set the active trial-balance (saldobalanse) DataFrame.

    This marks the session as TB-only mode.  The main ``dataset`` is NOT
    cleared — consumers that need transaction data can still check it,
    but ``version_type`` will be ``"sb"`` signalling that TB is the
    primary data source.
    """
    global tb_df, version_type
    tb_df = df
    version_type = "sb"

def get_dataset() -> Tuple[Optional[pd.DataFrame], Optional[Columns]]:
    return _df, _cols

def has_dataset() -> bool:
    return _df is not None and _cols is not None

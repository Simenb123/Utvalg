from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .groups import A07Group


@dataclass
class A07WorkspaceData:
    a07_df: pd.DataFrame
    gl_df: pd.DataFrame
    source_a07_df: pd.DataFrame | None = None
    mapping: dict[str, str] = field(default_factory=dict)
    suggestions: pd.DataFrame | None = None
    groups: dict[str, A07Group] = field(default_factory=dict)
    locks: set[str] = field(default_factory=set)
    membership: dict[str, str] = field(default_factory=dict)
    basis_col: str = "Endring"
    selected_code: str | None = None
    selected_group: str | None = None
    project_meta: dict[str, object] = field(default_factory=dict)

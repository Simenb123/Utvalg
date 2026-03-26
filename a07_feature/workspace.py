from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class A07WorkspaceData:
    a07_df: pd.DataFrame
    gl_df: pd.DataFrame
    mapping: dict[str, str] = field(default_factory=dict)
    suggestions: pd.DataFrame | None = None

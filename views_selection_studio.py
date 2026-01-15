# -*- coding: utf-8 -*-
from __future__ import annotations

# UI ligger her
from views_selection_studio_ui import *  # noqa: F401,F403

# Logikk overstyres her (samme som i UI-fila, men nyttig for fremtidig importstruktur)
from selection_studio_bilag import build_bilag_dataframe, stratify_bilag_sums  # noqa: F401,E402

try:
    __all__  # type: ignore[name-defined]
except NameError:
    __all__ = [n for n in globals().keys() if not n.startswith("_")]

for _n in ("build_bilag_dataframe", "stratify_bilag_sums"):
    if _n not in __all__:
        __all__.append(_n)

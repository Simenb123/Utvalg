"""Bakoverkompat-shim — saldobalanse_columns har flyttet.

Modulen lever nå i ``src.pages.saldobalanse.frontend.columns``.
``sys.modules``-alias bevarer eksisterende imports og monkeypatch.
"""

from __future__ import annotations

import sys as _sys

from src.pages.saldobalanse.frontend import columns as _columns

_sys.modules[__name__] = _columns

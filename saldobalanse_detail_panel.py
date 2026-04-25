"""Bakoverkompat-shim — saldobalanse_detail_panel har flyttet.

Modulen lever nå i ``src.pages.saldobalanse.frontend.detail_panel``.
``sys.modules``-alias bevarer eksisterende imports og monkeypatch.
"""

from __future__ import annotations

import sys as _sys

from src.pages.saldobalanse.frontend import detail_panel as _detail_panel

_sys.modules[__name__] = _detail_panel

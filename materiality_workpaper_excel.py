"""Bakoverkompat-shim — materiality_workpaper_excel har flyttet til
``src.pages.materiality.backend.workpaper_excel``. ``sys.modules``-alias
bevarer eksisterende imports og monkeypatch.
"""

from __future__ import annotations

import sys as _sys

from src.pages.materiality.backend import workpaper_excel as _workpaper_excel

_sys.modules[__name__] = _workpaper_excel

"""Bakoverkompat-shim — page_ar_chart har flyttet til
``src.pages.ar.frontend.chart``. ``sys.modules``-alias bevarer eksisterende imports
og monkeypatch i tester.
"""

from __future__ import annotations

import sys as _sys

from src.pages.ar.frontend import chart as _mod

_sys.modules[__name__] = _mod

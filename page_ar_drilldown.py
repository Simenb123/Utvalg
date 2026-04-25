"""Bakoverkompat-shim — page_ar_drilldown har flyttet til
``src.pages.ar.frontend.drilldown``. ``sys.modules``-alias bevarer eksisterende imports
og monkeypatch i tester.
"""

from __future__ import annotations

import sys as _sys

from src.pages.ar.frontend import drilldown as _mod

_sys.modules[__name__] = _mod

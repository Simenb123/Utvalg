"""Bakoverkompat-shim — page_ar_compare har flyttet til
``src.pages.ar.frontend.compare``. ``sys.modules``-alias bevarer eksisterende imports
og monkeypatch i tester.
"""

from __future__ import annotations

import sys as _sys

from src.pages.ar.frontend import compare as _mod

_sys.modules[__name__] = _mod

"""Bakoverkompat-shim — page_ar_formatters har flyttet til
``src.pages.ar.backend.formatters``. ``sys.modules``-alias bevarer eksisterende imports
og monkeypatch i tester.
"""

from __future__ import annotations

import sys as _sys

from src.pages.ar.backend import formatters as _mod

_sys.modules[__name__] = _mod

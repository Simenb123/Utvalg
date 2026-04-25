"""Bakoverkompat-shim — ar_store har flyttet til
``src.pages.ar.backend.store``. ``sys.modules``-alias bevarer eksisterende imports
og monkeypatch i tester.
"""

from __future__ import annotations

import sys as _sys

from src.pages.ar.backend import store as _mod

_sys.modules[__name__] = _mod

"""Bakoverkompat-shim — materiality_store har flyttet til
``src.pages.materiality.backend.store``. ``sys.modules``-alias bevarer
eksisterende imports og monkeypatch.
"""

from __future__ import annotations

import sys as _sys

from src.pages.materiality.backend import store as _store

_sys.modules[__name__] = _store

"""Bakoverkompat-shim — materiality_engine har flyttet til
``src.pages.materiality.backend.engine``. ``sys.modules``-alias bevarer
eksisterende imports og monkeypatch.
"""

from __future__ import annotations

import sys as _sys

from src.pages.materiality.backend import engine as _engine

_sys.modules[__name__] = _engine

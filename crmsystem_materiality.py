"""Bakoverkompat-shim — crmsystem_materiality har flyttet til
``src.pages.materiality.backend.crmsystem``. ``sys.modules``-alias bevarer
eksisterende imports og monkeypatch.
"""

from __future__ import annotations

import sys as _sys

from src.pages.materiality.backend import crmsystem as _crmsystem

_sys.modules[__name__] = _crmsystem

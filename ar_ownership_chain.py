"""Bakoverkompat-shim — ar_ownership_chain har flyttet til
``src.pages.ar.backend.ownership_chain``. ``sys.modules``-alias bevarer eksisterende imports
og monkeypatch i tester.
"""

from __future__ import annotations

import sys as _sys

from src.pages.ar.backend import ownership_chain as _mod

_sys.modules[__name__] = _mod

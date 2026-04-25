"""Bakoverkompat-shim — saldobalanse_actions har flyttet.

Modulen lever nå i ``src.pages.saldobalanse.frontend.actions``.
``sys.modules``-alias bevarer eksisterende imports og monkeypatch.
"""

from __future__ import annotations

import sys as _sys

from src.pages.saldobalanse.frontend import actions as _actions

_sys.modules[__name__] = _actions

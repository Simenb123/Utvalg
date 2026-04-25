"""Bakoverkompat-shim — page_saldobalanse har flyttet.

Modulen lever nå i ``src.pages.saldobalanse.frontend.page`` (pilot 5 av
frontend/backend-mappestrukturen). Denne shim-en aliasserer modulen via
``sys.modules`` slik at eksisterende ``import page_saldobalanse``-kall
og monkeypatch i tester treffer samme modul-objekt.
"""

from __future__ import annotations

import sys as _sys

from src.pages.saldobalanse.frontend import page as _page

_sys.modules[__name__] = _page

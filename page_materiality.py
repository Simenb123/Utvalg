"""Bakoverkompat-shim — page_materiality har flyttet til
``src.pages.materiality.frontend.page``. ``sys.modules``-alias bevarer
eksisterende imports og monkeypatch.
"""

from __future__ import annotations

import sys as _sys

from src.pages.materiality.frontend import page as _page

_sys.modules[__name__] = _page

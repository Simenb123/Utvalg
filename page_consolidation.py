"""Bakoverkompat-shim — page_consolidation har flyttet til
``src.pages.consolidation.frontend.page``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import page as _mod

_sys.modules[__name__] = _mod

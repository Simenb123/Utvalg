"""Bakoverkompat-shim — page_consolidation_view har flyttet til
``src.pages.consolidation.frontend.view``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import view as _mod

_sys.modules[__name__] = _mod

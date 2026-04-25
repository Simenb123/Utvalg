"""Bakoverkompat-shim — page_consolidation_result har flyttet til
``src.pages.consolidation.frontend.result``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import result as _mod

_sys.modules[__name__] = _mod

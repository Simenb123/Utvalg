"""Bakoverkompat-shim — page_consolidation_detail har flyttet til
``src.pages.consolidation.frontend.detail``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import detail as _mod

_sys.modules[__name__] = _mod

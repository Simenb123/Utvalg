"""Bakoverkompat-shim — page_consolidation_fx har flyttet til
``src.pages.consolidation.frontend.fx``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import fx as _mod

_sys.modules[__name__] = _mod

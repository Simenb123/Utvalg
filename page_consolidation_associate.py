"""Bakoverkompat-shim — page_consolidation_associate har flyttet til
``src.pages.consolidation.frontend.associate``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import associate as _mod

_sys.modules[__name__] = _mod

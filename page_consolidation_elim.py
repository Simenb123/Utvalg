"""Bakoverkompat-shim — page_consolidation_elim har flyttet til
``src.pages.consolidation.frontend.elim``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import elim as _mod

_sys.modules[__name__] = _mod

"""Bakoverkompat-shim — page_consolidation_common har flyttet til
``src.pages.consolidation.frontend.common``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import common as _mod

_sys.modules[__name__] = _mod

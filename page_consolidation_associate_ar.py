"""Bakoverkompat-shim — page_consolidation_associate_ar har flyttet til
``src.pages.consolidation.frontend.associate_ar``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import associate_ar as _mod

_sys.modules[__name__] = _mod

"""Bakoverkompat-shim — page_consolidation_readiness_ui har flyttet til
``src.pages.consolidation.frontend.readiness_ui``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import readiness_ui as _mod

_sys.modules[__name__] = _mod

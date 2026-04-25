"""Bakoverkompat-shim — page_consolidation_elim_ui har flyttet til
``src.pages.consolidation.frontend.elim_ui``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import elim_ui as _mod

_sys.modules[__name__] = _mod

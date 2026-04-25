"""Bakoverkompat-shim — page_consolidation_elim_suggestions har flyttet til
``src.pages.consolidation.frontend.elim_suggestions``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import elim_suggestions as _mod

_sys.modules[__name__] = _mod

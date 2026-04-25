"""Bakoverkompat-shim — page_consolidation_elim_draft har flyttet til
``src.pages.consolidation.frontend.elim_draft``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import elim_draft as _mod

_sys.modules[__name__] = _mod

"""Bakoverkompat-shim — consolidation_mapping_tab har flyttet til
``src.pages.consolidation.frontend.mapping_tab``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import mapping_tab as _mod

_sys.modules[__name__] = _mod

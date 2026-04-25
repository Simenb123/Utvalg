"""Bakoverkompat-shim — page_consolidation_mapping_state har flyttet til
``src.pages.consolidation.frontend.mapping_state``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import mapping_state as _mod

_sys.modules[__name__] = _mod

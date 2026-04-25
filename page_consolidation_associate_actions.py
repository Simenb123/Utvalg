"""Bakoverkompat-shim — page_consolidation_associate_actions har flyttet til
``src.pages.consolidation.frontend.associate_actions``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import associate_actions as _mod

_sys.modules[__name__] = _mod

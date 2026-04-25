"""Bakoverkompat-shim — page_consolidation_import har flyttet til
``src.pages.consolidation.frontend.imports``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import imports as _mod

_sys.modules[__name__] = _mod

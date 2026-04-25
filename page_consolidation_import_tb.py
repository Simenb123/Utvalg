"""Bakoverkompat-shim — page_consolidation_import_tb har flyttet til
``src.pages.consolidation.frontend.import_tb``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import import_tb as _mod

_sys.modules[__name__] = _mod

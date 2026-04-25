"""Bakoverkompat-shim — page_consolidation_import_line_basis har flyttet til
``src.pages.consolidation.frontend.import_line_basis``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import import_line_basis as _mod

_sys.modules[__name__] = _mod

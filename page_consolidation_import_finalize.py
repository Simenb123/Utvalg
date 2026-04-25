"""Bakoverkompat-shim — page_consolidation_import_finalize har flyttet til
``src.pages.consolidation.frontend.import_finalize``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import import_finalize as _mod

_sys.modules[__name__] = _mod

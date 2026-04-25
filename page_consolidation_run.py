"""Bakoverkompat-shim — page_consolidation_run har flyttet til
``src.pages.consolidation.frontend.run``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import run as _mod

_sys.modules[__name__] = _mod

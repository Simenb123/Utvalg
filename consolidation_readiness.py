"""Bakoverkompat-shim — consolidation_readiness har flyttet til
``src.pages.consolidation.backend.readiness``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.backend import readiness as _mod

_sys.modules[__name__] = _mod

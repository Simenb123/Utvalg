"""Bakoverkompat-shim — consolidation_readiness_digest har flyttet til
``src.pages.consolidation.backend.readiness_digest``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.backend import readiness_digest as _mod

_sys.modules[__name__] = _mod

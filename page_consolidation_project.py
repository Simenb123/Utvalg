"""Bakoverkompat-shim — page_consolidation_project har flyttet til
``src.pages.consolidation.frontend.project``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import project as _mod

_sys.modules[__name__] = _mod

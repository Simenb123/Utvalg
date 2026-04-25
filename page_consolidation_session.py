"""Bakoverkompat-shim — page_consolidation_session har flyttet til
``src.pages.consolidation.frontend.session``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import session as _mod

_sys.modules[__name__] = _mod

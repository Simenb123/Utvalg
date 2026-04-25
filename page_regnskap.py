"""Bakoverkompat-shim — page_regnskap har flyttet til
``src.pages.regnskap.frontend.page``. ``sys.modules``-alias bevarer
eksisterende imports.
"""

from __future__ import annotations

import sys as _sys

from src.pages.regnskap.frontend import page as _page

_sys.modules[__name__] = _page

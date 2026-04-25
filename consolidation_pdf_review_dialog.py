"""Bakoverkompat-shim — consolidation_pdf_review_dialog har flyttet til
``src.pages.consolidation.frontend.pdf_review_dialog``. ``sys.modules``-alias.
"""

from __future__ import annotations

import sys as _sys

from src.pages.consolidation.frontend import pdf_review_dialog as _mod

_sys.modules[__name__] = _mod

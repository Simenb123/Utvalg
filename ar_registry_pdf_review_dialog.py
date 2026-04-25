"""Bakoverkompat-shim — ar_registry_pdf_review_dialog har flyttet til
``src.pages.ar.frontend.pdf_review_dialog``. ``sys.modules``-alias bevarer eksisterende imports
og monkeypatch i tester.
"""

from __future__ import annotations

import sys as _sys

from src.pages.ar.frontend import pdf_review_dialog as _mod

_sys.modules[__name__] = _mod

"""Bakoverkompat-shim — page_ar_import_detail_dialog har flyttet til
``src.pages.ar.frontend.import_detail_dialog``. ``sys.modules``-alias bevarer eksisterende imports
og monkeypatch i tester.
"""

from __future__ import annotations

import sys as _sys

from src.pages.ar.frontend import import_detail_dialog as _mod

_sys.modules[__name__] = _mod

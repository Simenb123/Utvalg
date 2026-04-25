"""Bakoverkompat-shim — ar_registry_pdf_parser har flyttet til
``src.pages.ar.backend.pdf_parser``. ``sys.modules``-alias bevarer eksisterende imports
og monkeypatch i tester.
"""

from __future__ import annotations

import sys as _sys

from src.pages.ar.backend import pdf_parser as _mod

_sys.modules[__name__] = _mod

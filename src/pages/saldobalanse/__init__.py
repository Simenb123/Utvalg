"""Saldobalanse-fanen.

Pilot 4 i frontend/backend-mappestrukturen. Foreløpig er kun
``backend/payload.py`` flyttet hit — frontend-filene
(``page_saldobalanse.py``, ``saldobalanse_actions.py``,
``saldobalanse_detail_panel.py``, ``saldobalanse_columns.py``) ligger
fortsatt på toppnivå og refaktoreres i en senere pilot.

Toppnivå-modulen ``saldobalanse_payload`` er en bakoverkompat-shim
som peker hit via ``sys.modules``-alias — eldre importer
(``import saldobalanse_payload``) og monkeypatch i tester treffer
samme modul-objekt som ``src.pages.saldobalanse.backend.payload``.
"""

from .backend import payload  # noqa: F401

__all__ = ["payload"]

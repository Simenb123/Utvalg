"""Bakoverkompat-shim — saldobalanse_payload har flyttet.

Modulen lever nå i ``src.pages.saldobalanse.backend.payload`` (pilot 4 av
frontend/backend-mappestrukturen). Denne shim-en aliasserer modulen via
``sys.modules`` slik at:

- Eksisterende importer (``import saldobalanse_payload``,
  ``from saldobalanse_payload import X``) virker uendret.
- ``monkeypatch.setattr(saldobalanse_payload, ...)`` i tester treffer
  samme modul-objekt som ``src.pages.saldobalanse.backend.payload``.

Aliasen kan fjernes når alle eksterne importerere er migrert til den
nye stien.
"""

from __future__ import annotations

import sys as _sys

from src.pages.saldobalanse.backend import payload as _payload

_sys.modules[__name__] = _payload

"""Driftsmidler-fanen.

Pilot for ``frontend/backend``-mappestruktur (innført 2026-04-25).

Skillet:

- ``backend/`` — ren Python-logikk (DataFrames inn, DataFrames/dicts ut).
  Ingen tkinter. Kan kjøres hodeløst og er klar til å eksponeres som
  REST-endepunkt senere.
- ``frontend/`` — Tk-widgets. Henter data fra Analyse-siden og delegerer
  all forretningslogikk til ``backend``.

Eksterne kallere bruker fortsatt ``DriftsmidlerPage`` direkte fra denne
pakken — re-eksporten under skjuler at klassen nå bor i ``frontend/page.py``.
"""

from .frontend import DriftsmidlerPage

__all__ = ["DriftsmidlerPage"]

"""Statistikk — revisjonshandling som åpnes som popup fra Analyse.

Lå tidligere i ``src/pages/statistikk/`` (pilot 2-3), men hører
egentlig hjemme i ``src/audit_actions/`` siden Statistikk ikke er
en fane i hovednotebook — den åpnes via ``_open_statistikk_popup()``
fra Analyse (høyreklikk → "Vis statistikk for ...").

Skillet:
- ``backend/`` — beregningskjerne + Excel-eksport (ren Python, ingen Tk)
- ``frontend/`` — Tk-widgets (StatistikkPage)

Eksterne kallere bruker fortsatt ``StatistikkPage`` direkte fra denne
pakken — re-eksporten under skjuler at klassen nå bor i ``frontend/page.py``.
"""

from .frontend import StatistikkPage

# Bakoverkompat-aliaser: eldre kode (særlig tester) importerer som
# ``from src.audit_actions.statistikk import page_statistikk`` osv. Vi peker
# disse navnene til de nye lokasjonene så ingen eksterne kall trenger
# oppdatering. Aliasene kan fjernes når alle importer er migrert.
from .frontend import page as page_statistikk  # noqa: F401
from .backend import compute as page_statistikk_compute  # noqa: F401
from .backend import excel as page_statistikk_excel  # noqa: F401

__all__ = [
    "StatistikkPage",
    "page_statistikk",
    "page_statistikk_compute",
    "page_statistikk_excel",
]

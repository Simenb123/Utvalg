"""Statistikk-fanen.

Følger ``frontend/backend``-mappestrukturen (pilot 2 i mønsteret som
ble etablert med driftsmidler 2026-04-25).

Skillet:
- ``backend/`` — beregningskjerne + Excel-eksport (ren Python, ingen Tk)
- ``frontend/`` — Tk-widgets (StatistikkPage)

Eksterne kallere bruker fortsatt ``StatistikkPage`` direkte fra denne
pakken — re-eksporten under skjuler at klassen nå bor i ``frontend/page.py``.
"""

from .frontend import StatistikkPage

# Bakoverkompat-aliaser: eldre kode (særlig tester) importerer som
# ``from src.pages.statistikk import page_statistikk`` osv. Vi peker
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

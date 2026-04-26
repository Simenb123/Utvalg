"""Regnskap — cross-cutting utility (brukt av flere faner).

Pilot 21 av frontend/backend-mappestrukturen. Her ligger ren Python-
logikk for regnskap-modellen som brukes av Analyse, Saldobalanse,
Konsolidering, Skatt osv.

Moduler:
- ``client_overrides.py`` — klient-spesifikke konto/RL-overstyringer
- ``config.py`` — konfig-loading (load_regnskapslinjer, load_kontoplan_mapping)
- ``data.py`` — dataoperasjoner på regnskapslinje-pivot
- ``intelligence.py`` — analyse av regnskap-mønstre
- ``mapping.py`` — normalisering og hierarki-utvidelse
- ``report.py`` — rapportbygging (Resultat, Balanse, Kontantstrøm)

VIKTIG: Denne pakken får ALDRI importere ``tkinter``. Verifiseres av
``tests/test_shared_regnskap_no_tk.py``.
"""

from . import client_overrides, config, data, intelligence, mapping, report  # noqa: F401

__all__ = ["client_overrides", "config", "data", "intelligence", "mapping", "report"]

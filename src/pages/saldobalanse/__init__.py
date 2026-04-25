"""Saldobalanse-fanen.

Pilot 4-5 av frontend/backend-mappestrukturen er fullført:
- ``backend/payload.py`` — ren datalogikk (1452 linjer, ingen Tk)
- ``frontend/page.py`` — SaldobalansePage (Tk-widgets)
- ``frontend/actions.py`` — knapp-handlinger
- ``frontend/columns.py`` — kolonnevalg/presets
- ``frontend/detail_panel.py`` — detalj-panel-widgets

Toppnivå-modulene ``page_saldobalanse``, ``saldobalanse_payload``,
``saldobalanse_actions``, ``saldobalanse_columns`` og
``saldobalanse_detail_panel`` er bevart som ``sys.modules``-aliaser
slik at eksisterende ``import``-er og ``monkeypatch.setattr(...)`` i
tester treffer samme modul-objekt som de nye lokasjonene.

``saldobalanse_payroll_mode`` ligger fortsatt på toppen — det er en
compat-shim for ``a07_feature.payroll.saldobalanse_bridge`` og hører
ikke hjemme i frontend eller backend.
"""

from .frontend import SaldobalansePage
from .backend import payload  # noqa: F401

__all__ = ["SaldobalansePage", "payload"]

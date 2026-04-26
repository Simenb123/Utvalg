"""Reskontro-fanen.

Pilot 20 av frontend/backend-mappestrukturen — reskontro-analyse for
kunder og leverandører (åpne poster, BRREG-risiko, rapporter).

Backend (ren Python, ingen Tk):
- ``backend/brreg_helpers.py`` — BRREG-risiko-helpers
- ``backend/open_items.py`` — beregning av åpne poster
- ``backend/report_engine.py`` — rapport-bygging
- ``backend/report_html.py`` — HTML-rapport-generering

Frontend (Tk-widgets):
- ``frontend/page.py`` — ReskontroPage hovedside
- ``frontend/brreg_actions.py`` — BRREG-actions
- ``frontend/brreg_panel.py`` — BRREG-panel-widget
- ``frontend/export.py`` — Excel-eksport-dialoger
- ``frontend/popups.py`` — diverse popups
- ``frontend/selection.py`` — seleksjonshåndtering
- ``frontend/tree_helpers.py`` — treeview-helpers
- ``frontend/ui_build.py`` — UI-bygging
"""

from .frontend.page import ReskontroPage

__all__ = ["ReskontroPage"]

"""Dataset-fanen.

Pilot 19 av frontend/backend-mappestrukturen. Stor pakke (14 filer)
fordi dataset-fanen blander to roller — datakilde-velger og klient-info
(jf. ``doc/architecture/dataset_klientoversikt_plan.md`` for senere
splitting i Klientoversikt + Datasett-popup).

Backend (ren Python, ingen Tk):
- ``backend/build_fast.py`` — vektorisert dataset-bygging
- ``backend/cache_sqlite.py`` — sqlite-cache for ferdige datasets
- ``backend/export.py`` — Excel-eksport av hovedbok
- ``backend/pane_build.py`` — datasett-bygge-pipeline
- ``backend/pane_io.py`` — fil-I/O (Excel, CSV, SAF-T)
- ``backend/pane_xls.py`` — XLS-spesifikk lesing

Frontend (Tk-widgets):
- ``frontend/page.py`` — DatasetPage (faneside)
- ``frontend/pane.py`` — DatasetPane (gjenbrukbar widget)
- ``frontend/pane_ui.py`` — UI-bygging
- ``frontend/pane_store.py`` — compat-wrapper for pane_store_section
- ``frontend/pane_store_section.py`` — klient/versjons-seksjon
- ``frontend/pane_store_ui.py`` — widget-bygging for klient-info
- ``frontend/pane_store_logic.py`` — page-koblet logikk (importerer messagebox lokalt)
- ``frontend/pane_store_import_ui.py`` — Visena-import-dialog
"""

from .frontend.page import DatasetPage

__all__ = ["DatasetPage"]

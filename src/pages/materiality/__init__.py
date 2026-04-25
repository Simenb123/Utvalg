"""Vesentlighet-fanen.

Pilot 6 av frontend/backend-mappestrukturen:
- ``backend/engine.py`` — beregning av vesentlighet
- ``backend/store.py`` — lagring/lasting av materialitets-tilstand
- ``backend/workpaper_excel.py`` — Excel-eksport av arbeidsdokument
- ``backend/crmsystem.py`` — integrasjon mot CRM-system
- ``frontend/page.py`` — MaterialityPage (Tk-widgets)

Toppnivå-modulene (``page_materiality``, ``materiality_engine``,
``materiality_store``, ``materiality_workpaper_excel``,
``crmsystem_materiality``) er bevart som ``sys.modules``-aliaser så
eksisterende importer og monkeypatch i tester treffer samme modul.
"""

from .frontend.page import MaterialityPage

__all__ = ["MaterialityPage"]

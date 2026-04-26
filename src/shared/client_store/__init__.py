"""Klient-store — cross-cutting utility (brukt av alle faner).

Pilot 22 av frontend/backend-mappestrukturen.

Moduler:
- ``store.py`` — klientmappen på disk (read_client_meta, update_client_meta,
  list_clients, add_client osv.)
- ``meta_index.py`` — rask oppslagstabell over alle klienter
  (orgnr, knr, responsible, manager, team_members)
- ``enrich.py`` — match Visena-rader mot eksisterende klienter
  (3-trinns matching: knr → eksakt navn → fuzzy)
- ``importer.py`` — import av klientliste fra XLSX/CSV/TXT
- ``versions.py`` — versjons-håndtering (HB/SB/KR/LR per klient/år)

VIKTIG: Denne pakken får ALDRI importere ``tkinter``. Verifiseres av
``tests/test_shared_client_store_no_tk.py``.

Frontend-dialoger som bruker disse modulene:
- ``client_picker_dialog.py`` (toppnivå) — klient-velger-popup
- ``client_store_enrich_ui.py`` (toppnivå) — Visena-berikelse-dialog
"""

from . import enrich, importer, meta_index, store, versions  # noqa: F401

__all__ = ["enrich", "importer", "meta_index", "store", "versions"]

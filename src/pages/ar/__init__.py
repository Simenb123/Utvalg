"""AR-fanen — Aksjonærer (eierskap, aksjonærregister, ownership chain).

Pilot 7 av frontend/backend-mappestrukturen. 11 filer flyttet hit.

Backend (ren Python, ingen Tk):
- ``backend/store.py`` — datalager (manuelle eier-endringer, BRREG-cache)
- ``backend/ownership_chain.py`` — eierskapskjede-logikk
- ``backend/pdf_parser.py`` — PDF-parser for aksjonærregister
- ``backend/formatters.py`` — formatterings-helpers (rene)

Frontend (Tk-widgets):
- ``frontend/page.py`` — ARPage hovedside
- ``frontend/brreg.py`` — BRREG-integrasjon
- ``frontend/chart.py`` — diagram-fane
- ``frontend/compare.py`` — sammenligning mellom år
- ``frontend/drilldown.py`` — drill-down-popup
- ``frontend/import_detail_dialog.py`` — import-detalj-dialog
- ``frontend/pdf_review_dialog.py`` — PDF-review-dialog

Toppnivå-modulene (``page_ar``, ``ar_store`` osv., 11 totalt) er
bevart som ``sys.modules``-aliaser.
"""

from .frontend.page import ARPage

__all__ = ["ARPage"]

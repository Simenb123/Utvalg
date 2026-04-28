"""Dokumentkontroll — felles arbeidsflyt for bilag-PDF-er.

Pilot 28 av frontend/backend-mappestrukturen — flyttet 13
document_control-filer fra rot til denne pakken.

Brukes av Utvalg, Analyse, AR og flere andre fans for å:
- Sammenstille bilag-numre med opplastede PDF-er
- Vurdere og lagre dokumentstatus (OK / Avvik / Ikke vurdert)
- Forhåndsvise PDF + transaksjonslinjer side-ved-side
- Kjøre batch-analyse over et utvalg

Moduler:
- service.py / app_service.py — backend-tjenester
- store.py — JSON-persistens
- finder.py / voucher_index.py — PDF-oppslag
- learning.py — historikk + læring
- dialog.py / review_dialog.py / batch_dialog.py / voucher_dialog.py — Tk-dialoger
- viewer.py — PDF-preview-widget
- batch_service.py — bulk-analyse
- export.py — Excel-eksport
"""

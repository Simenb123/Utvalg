"""SAF-T (Norsk Standard Audit File for Tax) — cross-cutting utility.

Pilot 24 av frontend/backend-mappestrukturen. Pakka samler all SAF-T-
relatert lese- og parsing-logikk som brukes på tvers av Utvalg-faner.

Moduler:
- ``reader.py`` — kanonisk SAF-T-Financial-parser → DataFrame.
  Brukes av Dataset-fanen, Reskontro-actions, og Series-control-tester.
- ``tax_table.py`` — ekstraherer master TaxTable (MVA-koder + satser).
  Brukes av MVA-fanens config-dialog og av reader.py som lookup-fallback.
- ``trial_balance.py`` — bygger trial balance fra SAF-T (xlsx-eksport
  + DataFrame-API). Brukes av Konsolidering, Analyse-RL og
  Versjons-oversikt-dialogen.
- ``importer.py`` — eldre SAF-T → CSV-importer. Beholdes som
  dead-code-katalog (ingen aktive call-sites pr 2026-04-27); kan
  brukes som referanse hvis noen trenger CSV-output fremover.

VIKTIG: Pakka får ALDRI importere ``tkinter``. Verifiseres av
``tests/test_shared_saft_no_tk.py``.
"""

from . import reader, tax_table, trial_balance  # noqa: F401

__all__ = ["reader", "tax_table", "trial_balance"]

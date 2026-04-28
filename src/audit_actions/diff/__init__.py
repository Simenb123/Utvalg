"""Diff og kontinuitets-kontroller for hovedbok og saldobalanse.

Pilot 33. Pakka samler de tre diff-handlingene som tidligere lå løst
i rot:

- HB versjonsdiff — sammenlign to importerte hovedbok-versjoner
- IB/UB-kontroll — SB/HB-avstemming og IB(i år) == UB(fjor)
- SB versjonsdiff — sammenlign to importerte saldobalanse-versjoner

Hver handling består av to lag:
- ``*_engine.py`` — Tk-fri beregningslogikk (Pandas/dataclasses)
- ``*_excel.py``  — Excel-bygging (openpyxl, ingen Tk)

UI-orkestreringen (file-dialog, session-data, kall til engine+excel) lever
i ``src/audit_actions/exports/{hb_diff,ib_ub}.py`` (pilot 30).

Moduler:
- ``hb_engine.py``    + ``hb_excel.py``
- ``ib_ub_engine.py`` + ``ib_ub_excel.py``
- ``sb_engine.py``    + ``sb_excel.py``
"""

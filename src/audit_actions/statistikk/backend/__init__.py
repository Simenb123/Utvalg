"""Statistikk — backend-pakke (ren Python, ingen tkinter).

Inneholder beregnings-kjernen og Excel-eksport for statistikk-fanen.
Kan kjøres hodeløst og er klar til å eksponeres som REST-endepunkt
senere.

VIKTIG: Denne pakken får ALDRI importere ``tkinter``. Brudd fanges av
``tests/test_statistikk_backend_no_tk.py``.

Status (pilot 3 — pure-data API ferdig):
- ``get_konto_ranges(intervals, regnskapslinjer, regnr)`` — ren
- ``get_konto_set_for_regnr(intervals, regnskapslinjer, regnr, ranges,
  df_all, sb_df, sb_prev_df, *, context=None)`` — ren
- ``compute_kontoer(df_rl, sb_df, sb_prev_df, *, ranges, konto_set)`` — ren
- ``write_workbook(... pivot_df_rl, sb_df, sb_prev_df, context, ...)`` — ren
- ``compute_motpost_rl(grp_mp, *, context)`` — ren

Underscore-prefiksede shims (``_get_konto_set_for_regnr(page, ...)`` osv.)
er bevart for bakoverkompat med eksisterende tester. De kan fjernes når
testene migreres til pure-data-API.
"""

from . import compute, excel  # noqa: F401

__all__ = ["compute", "excel"]

"""Driftsmidler — backend-pakke (ren Python, ingen tkinter).

Hele forretningslogikken for driftsmiddelavstemming. Kan kjøres
hodeløst og er klar til å eksponeres som REST-endepunkt senere.

VIKTIG: Denne pakken får ALDRI importere ``tkinter``. Brudd fanges av
``tests/test_driftsmidler_backend_no_tk.py``.
"""

from .compute import (
    build_dm_reconciliation,
    classify_dm_transactions,
    get_konto_ranges,
    safe_float,
)

__all__ = [
    "build_dm_reconciliation",
    "classify_dm_transactions",
    "get_konto_ranges",
    "safe_float",
]

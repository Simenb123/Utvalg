"""Vesentlighet — backend-pakke (ren Python, ingen tkinter).

VIKTIG: Denne pakken får ALDRI importere ``tkinter``. Brudd fanges av
``tests/test_materiality_backend_no_tk.py``.
"""

from . import crmsystem, engine, store, workpaper_excel  # noqa: F401

__all__ = ["crmsystem", "engine", "store", "workpaper_excel"]

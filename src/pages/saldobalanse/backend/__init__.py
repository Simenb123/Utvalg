"""Saldobalanse — backend-pakke (ren Python, ingen tkinter).

VIKTIG: Denne pakken får ALDRI importere ``tkinter``. Brudd fanges av
``tests/test_saldobalanse_backend_no_tk.py``.
"""

from . import payload  # noqa: F401

__all__ = ["payload"]

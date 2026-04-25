"""AR — backend-pakke (ren Python, ingen tkinter).

VIKTIG: Denne pakken får ALDRI importere ``tkinter``. Brudd fanges av
``tests/test_ar_backend_no_tk.py``.
"""

from . import formatters, ownership_chain, pdf_parser, store  # noqa: F401

__all__ = ["formatters", "ownership_chain", "pdf_parser", "store"]

"""MVA — backend-pakke (ren Python, ingen tkinter).

VIKTIG: Denne pakken får ALDRI importere ``tkinter``. Brudd fanges av
``tests/test_mva_backend_no_tk.py``.
"""

from . import (  # noqa: F401
    avstemming,
    avstemming_excel,
    codes,
    kontroller,
    melding_parser,
    system_defaults,
)

__all__ = [
    "avstemming",
    "avstemming_excel",
    "codes",
    "kontroller",
    "melding_parser",
    "system_defaults",
]

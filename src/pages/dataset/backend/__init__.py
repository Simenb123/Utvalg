"""Dataset — backend-pakke (ren Python, ingen tkinter).

VIKTIG: Denne pakken får ALDRI importere ``tkinter``. Brudd fanges av
``tests/test_dataset_backend_no_tk.py``.
"""

from . import (  # noqa: F401
    build_fast,
    cache_sqlite,
    export,
    pane_build,
    pane_io,
    pane_xls,
)

__all__ = ["build_fast", "cache_sqlite", "export", "pane_build", "pane_io", "pane_xls"]

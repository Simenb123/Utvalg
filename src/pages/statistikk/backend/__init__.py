"""Statistikk — backend-pakke (ren Python, ingen tkinter).

Inneholder beregnings-kjernen og Excel-eksport for statistikk-fanen.
Kan kjøres hodeløst og er klar til å eksponeres som REST-endepunkt
senere.

VIKTIG: Denne pakken får ALDRI importere ``tkinter``. Brudd fanges av
``tests/test_statistikk_backend_no_tk.py``.

Status (pilot 2 av frontend/backend-mønsteret):
- ``get_konto_ranges`` har ren signatur (rene DataFrames inn).
- ``_get_konto_set_for_regnr`` og ``_compute_kontoer`` tar fortsatt
  ``page``-objekt som argument — refaktoreres i pilot 3 sammen med
  ``regnskapslinje_mapping_service.context_from_page``.
"""

from . import compute, excel  # noqa: F401

__all__ = ["compute", "excel"]

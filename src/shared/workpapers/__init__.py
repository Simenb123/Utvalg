"""Workpaper-bibliotek — cross-cutting utility for revisjonsdokumentasjon.

Pilot 25 av frontend/backend-mappestrukturen. Pakka samler ren
backend-logikk for arbeidsdokumenter (workpapers).

Moduler:
- ``library.py`` — ``Workpaper``-dataklasse + ``DEFAULT_KATEGORIER``.
  Brukes av Admin-, Handlinger- og Settings-fanene.
- ``forside.py`` — Excel forside-ark-generator (klient/år/dato/teamhode).
  Brukes av analyse-rapporter, hb-diff, ib-ub-kontroll og
  workpaper-export-modulene.
- ``generators.py`` — Wrappers for å generere standard-arbeidsdokument
  fra mal. Brukes av Handlinger-fanen.
- ``klientinfo.py`` — Datamodell + builder for klient-info-ark.

VIKTIG: Pakka får ALDRI importere ``tkinter``. Verifiseres av
``tests/test_shared_workpapers_no_tk.py``.

NB: De 5 ``workpaper_export_*.py``-filene i roten er IKKE flyttet
hit — de orkestrerer file-dialog og messagebox (UI), så de hører
i ``src/audit_actions/`` (planlagt egen pilot).
"""

from . import forside, generators, klientinfo, library  # noqa: F401

__all__ = ["forside", "generators", "klientinfo", "library"]

"""page_analyse_ui.py

UI-bygging for Analyse-fanen.

Designmål
---------
* Lav risiko: kun layout/visuelle grep, og kobling mot eksisterende logikk i
  ``page_analyse.py``.
* Testbarhet: ``build_ui`` kan få injisert ``tk``/``ttk``-moduler og
  ``dir_options`` fra ``page_analyse``.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from page_analyse_ui_helpers import (  # noqa: F401
    _build_period_range_picker,
    _nk_auto_fetch_brreg,
    _nk_fetch_brreg,
    _safe_period_value,
)


def build_ui(
    page: Any,
    tk=None,
    ttk=None,
    dir_options: Optional[Sequence[Any]] = None,
) -> None:
    """Bygg UI for Analyse-fanen.

    Args:
        page: AnalysePage-instans (ttk.Frame)
        tk: tkinter-modul (valgfri, for injisering i tester)
        ttk: tkinter.ttk-modul (valgfri, for injisering i tester)
        dir_options: Liste med objekter som har ``label`` (valgfri)
    """

    # Lazy import (og støtte for injisering)
    if tk is None:
        import tkinter as tk  # type: ignore

    if ttk is None:
        from tkinter import ttk  # type: ignore

    # Retning-labels: bruk dir_options hvis tilgjengelig, ellers fallback
    dir_labels: list[str] = []
    if dir_options:
        try:
            dir_labels = [str(getattr(opt, "label")) for opt in dir_options if getattr(opt, "label", None)]
        except Exception:
            dir_labels = []
    if not dir_labels:
        dir_labels = ["Alle", "+", "-"]

    # PageHeader øverst — felles topptittel + refresh + eksport-meny.
    # Filterlinjen som build_toolbar bygger fortsetter under headeren som
    # egen rad (mange side-spesifikke kontroller, krever bredde).
    # NB: PageHeader krever et ekte Tk-widget som parent. I tester der
    # `page` er en DummyPage uten Tk hopper vi over headeren — UI-bygging
    # av filterlinje/paneler er hovedansvaret til denne funksjonen.
    try:
        from src.shared.ui.page_header import PageHeader

        header = PageHeader(page, title="Analyse", subtitle="Hovedbok og saldobalanse")
        header.pack(fill="x", padx=6, pady=(6, 0))
        header.set_refresh(command=lambda: page.refresh_from_session(), key="<F5>")

        # Rapport-eksporter samles i header-eksportmenyen.
        for label, attr in (
            ("Regnskapsoppstilling (Excel)", "_export_regnskapsoppstilling_excel"),
            ("Nøkkeltallsrapport (PDF)", "_export_nokkeltall_pdf"),
            ("SB/HB-avstemming (Excel)", "_export_ib_ub_control"),
            ("IB/UB-kontinuitet (Excel)", "_export_ib_ub_continuity"),
        ):
            cmd = getattr(page, attr, None)
            if callable(cmd):
                header.add_export(label, command=cmd)
        page._page_header = header
    except Exception:
        # Tk ikke tilgjengelig (typisk i tester med DummyPage) — skipp header.
        page._page_header = None

    from page_analyse_ui_toolbar import build_toolbar

    refs = build_toolbar(page, tk=tk, ttk=ttk, dir_labels=dir_labels)
    from page_analyse_ui_panels import build_panels

    build_panels(page, tk=tk, ttk=ttk, refs=refs)


# ---------------------------------------------------------------------------
# BRREG-henting for nøkkeltall — flyttet til page_analyse_ui_helpers (re-eksportert øverst).
# ---------------------------------------------------------------------------

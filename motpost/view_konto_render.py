"""Motpostanalyse (GUI) - rendering.

All kode som fyller Treeviews og oppdaterer visning ligger her.

Merk:
    - Funksjonene tar inn dependencies som argumenter der testene
      monkeypatcher navn i :mod:`views_motpost_konto`.
"""

from __future__ import annotations

from typing import Any, Callable

import tkinter as tk

from formatting import fmt_amount
from motpost_konto_core import _fmt_date_ddmmyyyy, _fmt_percent_points, _konto_str


def render_summary(view: Any) -> None:
    """Render pivot-tabellen (motkontoer)."""

    view._tree_summary.delete(*view._tree_summary.get_children())

    df = getattr(getattr(view, "_data", None), "df_motkonto", None)
    if df is None or getattr(df, "empty", False):
        return

    outliers = getattr(view, "_outliers", set()) or set()

    for _, row in df.iterrows():
        motkonto = _konto_str(row.get("Motkonto"))
        kontonavn = row.get("Kontonavn", "")
        s = float(row.get("Sum", 0.0))
        share = float(row.get("% andel", 0.0))
        cnt = int(row.get("Antall bilag", 0))
        out = "Ja" if motkonto in outliers else ""

        tags: list[str] = []
        if s < 0:
            tags.append("neg")
        if motkonto in outliers:
            tags.append("outlier")

        view._tree_summary.insert(
            "",
            tk.END,
            values=(motkonto, kontonavn, fmt_amount(s), _fmt_percent_points(share), cnt, out),
            tags=tuple(tags),
        )


def refresh_details(view: Any, *, build_bilag_details_fn: Callable[[Any, str], Any]) -> None:
    """Oppdater bilagslisten for valgt motkonto."""

    view._tree_details.delete(*view._tree_details.get_children())

    motkonto = getattr(view, "_selected_motkonto", None)
    if not motkonto:
        return

    df_b = build_bilag_details_fn(getattr(view, "_data", None), motkonto)
    if df_b is None or getattr(df_b, "empty", False):
        return

    limit = int(getattr(getattr(view, "_details_limit_var", None), "get", lambda: 200)() or 200)
    df_b = df_b.head(limit)

    for _, row in df_b.iterrows():
        bilag = row.get("Bilag", "")
        dato = _fmt_date_ddmmyyyy(row.get("Dato"))
        tekst = row.get("Tekst", "")
        bel_sel = float(row.get("Beløp (valgte kontoer)", 0.0))
        motb = float(row.get("Motbeløp", 0.0))
        kontoer = row.get("Kontoer i bilag", "")

        tags: list[str] = []
        if bel_sel < 0 or motb < 0:
            tags.append("neg")

        view._tree_details.insert(
            "",
            tk.END,
            values=(bilag, dato, tekst, fmt_amount(bel_sel), fmt_amount(motb), kontoer),
            tags=tuple(tags),
        )

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
from .view_konto_filters import available_mva_codes, filter_bilag_details_by_mva


def render_summary(view: Any) -> None:
    """Render pivot-tabellen (motkontoer)."""

    view._tree_summary.delete(*view._tree_summary.get_children())

    df = getattr(getattr(view, "_data", None), "df_motkonto", None)
    if df is None or getattr(df, "empty", False):
        return

    outliers = getattr(view, "_outliers", set()) or set()
    expected_motkontoer = {
        _konto_str(k)
        for k in (getattr(view, "_expected_motkontoer", set()) or set())
        if _konto_str(k)
    }

    for _, row in df.iterrows():
        motkonto = _konto_str(row.get("Motkonto"))
        kontonavn = str(row.get("Kontonavn", "") or "").strip()
        s = float(row.get("Sum", 0.0))
        share = float(row.get("% andel", 0.0))
        cnt = int(row.get("Antall bilag", 0))
        out = "Ja" if motkonto in outliers else ""
        is_expected = bool(
            motkonto not in outliers
            and motkonto in expected_motkontoer
        )

        tags: list[str] = []
        if s < 0:
            tags.append("neg")
        if is_expected:
            tags.append("expected")
        if motkonto in outliers:
            tags.append("outlier")

        if is_expected:
            kontonavn = f"{kontonavn} (forventet)" if kontonavn else "Forventet motpost"

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

    code_values = available_mva_codes(df_b)
    current_code = str(getattr(getattr(view, "_details_mva_code_var", None), "get", lambda: "Alle")() or "Alle")
    if current_code not in code_values:
        current_code = "Alle"
        try:
            view._details_mva_code_var.set(current_code)
        except Exception:
            pass

    try:
        view._details_mva_code_values = list(code_values)
    except Exception:
        pass
    try:
        view._details_mva_code_combo.configure(values=tuple(code_values))
    except Exception:
        pass

    mva_mode = str(getattr(getattr(view, "_details_mva_mode_var", None), "get", lambda: "Alle")() or "Alle")
    expected_rate = str(getattr(getattr(view, "_details_expected_mva_var", None), "get", lambda: "25")() or "25")
    df_b = filter_bilag_details_by_mva(
        df_b,
        mva_code=current_code,
        mode=mva_mode,
        expected_rate=expected_rate,
    )
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
        mva_code = row.get("MVA-kode", "")
        mva_percent = row.get("MVA-prosent", "")
        mva_amount = float(row.get("MVA-beløp", 0.0))
        kontoer = row.get("Kontoer i bilag", "")
        show_mva_amount = bool(str(mva_code).strip() or str(mva_percent).strip() or abs(mva_amount) > 1e-9)

        tags: list[str] = []
        if bel_sel < 0 or motb < 0:
            tags.append("neg")
        if bool(row.get("_mva_avvik", False)):
            tags.append("mva_avvik")

        view._tree_details.insert(
            "",
            tk.END,
            values=(
                bilag,
                dato,
                tekst,
                fmt_amount(bel_sel),
                fmt_amount(motb),
                mva_code,
                mva_percent,
                fmt_amount(mva_amount) if show_mva_amount else "",
                kontoer,
            ),
            tags=tuple(tags),
        )

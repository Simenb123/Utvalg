"""Selection Studio widget: actions (commit/export/drilldown/summary).

These functions implement user-triggered actions (buttons/menu) for the
SelectionStudio widget.

They are extracted from `views_selection_studio_ui.py` to keep the view module
small and easier to reason about.
"""

from __future__ import annotations

import inspect
import os
from datetime import datetime
from typing import Any

import pandas as pd

from tkinter import filedialog, messagebox, ttk
import tkinter as tk

import session
from document_control_dialog import DocumentControlDialog
from document_control_service import normalize_bilag_key
from controller_export import export_to_excel
from .helpers import fmt_amount_no, fmt_int_no


def commit_selection(studio: Any) -> None:
    """Send the current sample to the configured callback."""

    if studio._df_sample is None or studio._df_sample.empty:
        messagebox.showinfo("Utvalg", "Ingen utvalg å legge til.")
        return

    if studio._on_commit_selection is None:
        messagebox.showinfo("Utvalg", "Ingen mottaker for utvalg (on_commit).")
        return

    try:
        studio._on_commit_selection(studio._df_sample.copy())
    except Exception as e:
        messagebox.showerror("Utvalg", f"Kunne ikke legge utvalg til.\n\n{e}")


def export_excel(studio: Any) -> None:
    """Export current sample + drawing frame to an Excel workbook."""

    if studio._df_sample is None or studio._df_sample.empty:
        messagebox.showinfo("Eksporter", "Ingen utvalg å eksportere.")
        return

    # Suggest a default file name so the user doesn't need to type one.
    default_name = f"Utvalg_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx"
    initialdir = getattr(studio, "_last_export_dir", "") or ""

    path = filedialog.asksaveasfilename(
        title="Lagre Excel",
        defaultextension=".xlsx",
        filetypes=[("Excel", "*.xlsx")],
        initialfile=default_name,
        initialdir=initialdir,
    )
    if not path:
        return

    # Remember last used folder.
    try:
        studio._last_export_dir = os.path.dirname(path)
    except Exception:
        pass

    try:
        export_to_excel(
            path,
            Utvalg=studio._df_sample,
            Grunnlag=studio._df_filtered,
        )
        messagebox.showinfo("Eksporter", "Eksportert.")
    except Exception as e:
        messagebox.showerror("Eksporter", f"Kunne ikke eksportere.\n\n{e}")


def build_konto_summary_df(df: pd.DataFrame) -> pd.DataFrame:
    """Build a compact account summary for the current drawing frame.

    Returns a DataFrame with columns:
        Konto, (Kontonavn), Rader, Bilag, Sum

    Raises:
        KeyError: if 'Konto' missing.
    """

    if df is None or df.empty:
        cols = ["Konto", "Rader", "Bilag", "Sum"]
        return pd.DataFrame(columns=cols)

    if "Konto" not in df.columns:
        raise KeyError("Konto")

    konto_col = "Konto"
    navn_col = "Kontonavn" if "Kontonavn" in df.columns else None

    gcols = [konto_col] + ([navn_col] if navn_col else [])

    # Prefer robust groupby. Named aggregation works in modern pandas.
    agg_spec: dict[str, tuple[str, str]] = {
        "Rader": (konto_col, "size"),
        "Bilag": ("Bilag", "nunique") if "Bilag" in df.columns else (konto_col, "size"),
        "Sum": ("Beløp", "sum") if "Beløp" in df.columns else (konto_col, "size"),
    }

    try:
        summary = df.groupby(gcols, dropna=False).agg(**agg_spec).reset_index()
    except Exception:
        # Fallback for older pandas: plain dict aggregation.
        summary = df.groupby(gcols, dropna=False).agg(
            {
                konto_col: "size",
                "Bilag": "nunique" if "Bilag" in df.columns else "size",
                "Beløp": "sum" if "Beløp" in df.columns else "size",
            }
        ).reset_index()
        # Normalise column names
        if konto_col in summary.columns:
            summary = summary.rename(columns={konto_col: "Rader"})
        if "Bilag" in summary.columns:
            summary = summary.rename(columns={"Bilag": "Bilag"})
        if "Beløp" in summary.columns:
            summary = summary.rename(columns={"Beløp": "Sum"})

    # Sort by absolute sum descending (most significant accounts first)
    if "Sum" in summary.columns and not summary.empty:
        try:
            summary = summary.loc[summary["Sum"].abs().sort_values(ascending=False).index]
        except Exception:
            pass

    return summary


def show_accounts(studio: Any) -> None:
    """Open a small window showing account-level totals for current drawing frame."""

    df = studio._df_filtered
    if df is None or df.empty:
        messagebox.showinfo("Kontorer", "Ingen data å vise.")
        return

    try:
        summary = build_konto_summary_df(df)
    except KeyError:
        messagebox.showinfo("Kontorer", "Datasettet mangler kolonnen 'Konto'.")
        return
    except Exception as e:
        messagebox.showerror("Kontorer", f"Kunne ikke bygge kontosummering.\n\n{e}")
        return

    win = tk.Toplevel(studio)
    win.title("Kontosummering")
    win.geometry("700x400")

    cols = ["Konto"]
    if "Kontonavn" in summary.columns:
        cols.append("Kontonavn")
    cols += ["Rader", "Bilag", "Sum"]

    tree = ttk.Treeview(win, columns=cols, show="headings")
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=120, anchor=("w" if c in ("Konto", "Kontonavn") else "e"))
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    ys = ttk.Scrollbar(win, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=ys.set)
    ys.pack(side=tk.RIGHT, fill=tk.Y)

    for _, row in summary.iterrows():
        konto = row.get("Konto", "")
        navn = row.get("Kontonavn", "") if "Kontonavn" in summary.columns else ""
        rader = int(row.get("Rader", 0) or 0)
        bilag = int(row.get("Bilag", 0) or 0)
        s = float(row.get("Sum", 0.0) or 0.0)

        values: list[Any] = [konto]
        if "Kontonavn" in summary.columns:
            values.append(navn)
        values += [fmt_int_no(rader), fmt_int_no(bilag), fmt_amount_no(s, decimals=2)]
        tree.insert("", tk.END, values=values)


def open_drilldown(studio: Any, *, open_dialog: Any) -> None:
    """Open bilag drilldown dialog for selected bilag in the sample Treeview."""

    if open_dialog is None:
        messagebox.showinfo("Drilldown", "Drilldown er ikke tilgjengelig.")
        return

    selection = studio.tree.selection()
    if not selection:
        messagebox.showinfo("Drilldown", "Velg et bilag i tabellen først.")
        return

    values = studio.tree.item(selection[0], "values")
    if not values:
        return

    bilag = values[0]

    # Backwards compatible: try to pass a preset/selected bilag if the dialog supports it.
    try:
        kwargs: dict[str, Any] = {
            "df_all": studio._df_all,
            "bilag_col": "Bilag",
        }

        try:
            params = inspect.signature(open_dialog).parameters
            if "preset_bilag" in params:
                kwargs["preset_bilag"] = bilag
            elif "bilag" in params:
                kwargs["bilag"] = bilag
            elif "bilag_id" in params:
                kwargs["bilag_id"] = bilag
            elif "selected_bilag" in params:
                kwargs["selected_bilag"] = bilag
        except Exception:
            pass

        open_dialog(studio, **kwargs)
    except TypeError:
        # Typical: "unexpected keyword argument" – retry without preset
        try:
            open_dialog(studio, df_all=studio._df_all, bilag_col="Bilag")
        except Exception as e:
            messagebox.showerror("Drilldown", f"Kunne ikke åpne drilldown.\n\n{e}")
    except Exception as e:
        messagebox.showerror("Drilldown", f"Kunne ikke åpne drilldown.\n\n{e}")


def open_document_control(studio: Any) -> None:
    """Open document control dialog for the selected bilag."""

    selection = studio.tree.selection()
    if not selection:
        messagebox.showinfo("Dokumentkontroll", "Velg et bilag i tabellen fÃ¸rst.")
        return

    values = studio.tree.item(selection[0], "values")
    if not values:
        messagebox.showinfo("Dokumentkontroll", "Fant ikke valgt bilag.")
        return

    bilag = normalize_bilag_key(values[0])
    if not bilag:
        messagebox.showinfo("Dokumentkontroll", "Bilagsnummer mangler for valgt rad.")
        return

    df_source = getattr(studio, "_df_all", None)
    if df_source is None or getattr(df_source, "empty", True):
        df_source = getattr(studio, "_df_base", None)

    if df_source is None or getattr(df_source, "empty", True) or "Bilag" not in df_source.columns:
        messagebox.showinfo("Dokumentkontroll", "Fant ikke bilagslinjer i aktivt datasett.")
        return

    bilag_series = df_source["Bilag"].map(normalize_bilag_key)
    df_bilag = df_source.loc[bilag_series == bilag].copy()
    if df_bilag.empty:
        messagebox.showinfo("Dokumentkontroll", "Fant ingen regnskapslinjer for valgt bilag.")
        return

    dialog = DocumentControlDialog(
        studio,
        bilag=bilag,
        df_bilag=df_bilag,
        client=getattr(session, "client", None),
        year=getattr(session, "year", None),
    )
    dialog.wait_window()


def sample_size_touched(studio: Any) -> None:
    """Called when user manually edits the sample size.

    The current implementation keeps the old behaviour (no explicit state flag),
    but retains the hook so that the UI builder can call it.
    """

    try:
        current = int(studio.var_sample_n.get() or 0)
    except Exception:
        return

    last_suggested = getattr(studio, "_last_suggested_n", None)
    if last_suggested is not None and current != 0 and current != last_suggested:
        # Keep user's choice; do not overwrite on refresh.
        pass

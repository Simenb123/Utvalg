"""Helper functions for actions in AnalysisPage (page_analyse.py).

This module exists to keep page_analyse.py smaller and to isolate optional
dependencies like Motpostanalyse (views_motpost_konto) and bilagsdrill
(selection_studio_drill).

The functions are defensive: if the optional modules are not available, they
will show a messagebox (when possible) and return.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

import pandas as pd

try:  # pragma: no cover (headless tests)
    from tkinter import messagebox  # type: ignore
except Exception:  # pragma: no cover
    messagebox = None  # type: ignore


def _show_error(title: str, msg: str) -> None:
    if messagebox is None:
        return
    try:
        messagebox.showerror(title, msg)
    except Exception:
        # Fail silently in environments without a real Tk root.
        pass


# Optional dependency: bilagsdrill dialog
try:  # pragma: no cover
    from selection_studio_drill import open_bilag_drill_dialog as _open_bilag_drill_dialog
except Exception:  # pragma: no cover
    _open_bilag_drill_dialog = None  # type: ignore


# Optional dependency: Motpostanalyse view
try:  # pragma: no cover
    from views_motpost_konto import show_motpost_konto as _show_motpost_konto
except Exception:  # pragma: no cover
    _show_motpost_konto = None  # type: ignore


def open_bilag_drilldown(
    *,
    parent: Any,
    df_filtered: Optional[pd.DataFrame],
    df_all: Optional[pd.DataFrame],
    bilag_value: Optional[str] = None,
) -> None:
    """Open bilagsdrilldown dialog.

    Parameters
    ----------
    parent:
        Tk parent widget (e.g. AnalysisPage)
    df_filtered / df_all:
        DataFrames from the analysis page. The dialog needs both the current
        view (filtered) and the full data.
    bilag_value:
        Optional pre-selected bilag id.
    """
    df_base = df_filtered if df_filtered is not None else df_all
    if df_base is None or df_all is None:
        return

    if _open_bilag_drill_dialog is None:
        _show_error("Bilagsdrill", "Bilagsdrill-modul er ikke tilgjengelig.")
        return

    try:
        # New signature (kwargs)
        _open_bilag_drill_dialog(
            parent,
            df_base=df_base,
            df_all=df_all,
            preset_bilag=bilag_value,
            bilag_col="Bilag",
        )
        return
    except TypeError:
        pass
    except Exception as e:
        _show_error("Bilagsdrill", f"Kunne ikke åpne bilagsdrill.\n\n{e}")
        return

    # Older signature (positional)
    try:
        _open_bilag_drill_dialog(parent, df_base, df_all, bilag_value)
    except Exception as e:
        _show_error("Bilagsdrill", f"Kunne ikke åpne bilagsdrill.\n\n{e}")


def open_motpost(
    *,
    parent: Any,
    df_filtered: Optional[pd.DataFrame],
    df_all: Optional[pd.DataFrame],
    selected_accounts: Iterable[str],
    dataset: Any = None,
) -> None:
    """Open Motpostanalyse window for the selected accounts."""
    if _show_motpost_konto is None:
        _show_error("Motpost", "Motpostanalyse-modul er ikke tilgjengelig.")
        return

    accounts = [str(a) for a in (selected_accounts or []) if str(a).strip()]
    if not accounts:
        _show_error("Motpost", "Ingen kontoer valgt.")
        return

    df_base = df_filtered if df_filtered is not None else df_all
    if df_base is None:
        _show_error("Motpost", "Ingen datagrunnlag tilgjengelig.")
        return

    # Optional konto-navn mapping
    konto_name_map = None
    try:
        if dataset is not None and hasattr(dataset, "account_map"):
            konto_name_map = getattr(dataset, "account_map")
    except Exception:
        konto_name_map = None

    # Prefer the new signature (keyword args)
    try:
        _show_motpost_konto(
            parent,
            df_all=df_base,
            selected_accounts=accounts,
            konto_name_map=konto_name_map,
        )
        return
    except TypeError:
        pass

    # Backwards compatible fallbacks
    try:
        _show_motpost_konto(parent, df_base, accounts, konto_name_map=konto_name_map)
        return
    except TypeError:
        pass

    try:
        _show_motpost_konto(parent, df_base=df_base, accounts=accounts, konto_name_map=konto_name_map)
        return
    except TypeError:
        pass

    try:
        _show_motpost_konto(parent, df_base, accounts, konto_name_map)
        return
    except Exception as e:
        _show_error("Motpost", f"Kunne ikke åpne motpostanalyse.\n\n{e}")

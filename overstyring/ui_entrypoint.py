"""UI entrypoint for Overstyring (override checks).

Kept as a small, stable surface so the rest of the app can call into the feature
without importing heavier UI modules at import-time.

We accept a few legacy/compat kwargs (e.g. ``df_scope`` / ``master``) so older
call-sites can be migrated incrementally.
"""

from __future__ import annotations

from typing import Any

import tkinter as tk
from tkinter import ttk

import pandas as pd

from .ui_panel import OverrideChecksPanel


def open_override_checks_popup(
    parent: tk.Misc | None = None,
    *,
    # Compat: several call-sites use `master=` instead of `parent=`.
    master: tk.Misc | None = None,
    session: Any | None = None,
    # Full dataset (if available).
    df_all: pd.DataFrame | None = None,
    # Current filtered scope (optional). If provided and non-empty, this is used by default.
    df_scope: pd.DataFrame | None = None,
    cols: Any | None = None,
    title: str = "Overstyring av kontroller",
    **_: Any,
) -> tk.Toplevel | None:
    """Open the Overstyring checks popup.

    Parameters
    ----------
    parent / master:
        Parent Tk widget (root or a frame). Either name is accepted.
    session:
        Optional object/module exposing ``get_dataset() -> (df, cols)``.
        Used if ``df_all`` is not provided, and as a best-effort source of ``cols``.
    df_all:
        Full dataset.
    df_scope:
        Current filtered scope. If provided and non-empty, checks will run on this scope.
        If empty/None, we fall back to ``df_all``.
    cols:
        Optional column mapping object used by the app.
    title:
        Window title.
    **_:
        Ignored extra kwargs for forward/backward compatibility.

    Returns
    -------
    tk.Toplevel | None
        The created window, or None if no dataset was available.
    """

    if parent is None:
        parent = master

    # Load from session if needed.
    if df_all is None and session is not None and hasattr(session, "get_dataset"):
        try:
            df_from_sess, cols_from_sess = session.get_dataset()  # type: ignore[attr-defined]
        except Exception:
            df_from_sess, cols_from_sess = None, None

        df_all = df_from_sess
        if cols is None:
            cols = cols_from_sess

    # If df_all was supplied but cols wasn't, still try session for cols (best-effort).
    if cols is None and session is not None and hasattr(session, "get_dataset"):
        try:
            _, cols_from_sess = session.get_dataset()  # type: ignore[attr-defined]
            if cols_from_sess is not None:
                cols = cols_from_sess
        except Exception:
            pass

    # Prefer scope when provided.
    df_use: pd.DataFrame | None
    if df_scope is not None and len(df_scope) > 0:
        df_use = df_scope
    else:
        df_use = df_all

    if df_use is None or len(df_use) == 0:
        return None

    top = tk.Toplevel(parent)
    top.title(title)
    top.geometry("1100x650")

    main = ttk.Frame(top, padding=6)
    main.pack(fill="both", expand=True)

    panel = OverrideChecksPanel(main, df_all=df_use, cols=cols)
    panel.pack(fill="both", expand=True)

    return top

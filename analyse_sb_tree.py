"""analyse_sb_tree.py — konstanter og oppretting/toggling av SB-treeview.

Utskilt fra page_analyse_sb.py. Konstantene og funksjonene her brukes
som tidligere; page_analyse_sb.py re-eksporterer dem for bakoverkompat.
"""

from __future__ import annotations

from typing import Any


# Egne kolonner for SB-visning (ingen gjenbruk av TX-kolonner).
# "Endring_fjor" (UB - UB_fjor) og "Endring_pct" er beregnede kolonner som
# matcher samme labels som i venstre pivot ("Endring" og "Endring %"). Den
# opprinnelige "Endring"-kolonnen er fortsatt periode-bevegelsen (UB - IB)
# og vises som "Bevegelse i år" via den felles label-mapperen.
SB_COLS = (
    "Konto", "Kontonavn", "OK", "OK_av", "OK_dato", "Vedlegg", "Gruppe",
    "regnr", "regnskapslinje",
    "IB", "Endring", "UB", "UB_fjor", "Endring_fjor", "Endring_pct", "Antall",
)

# Kanonisk standardvisning — matcher venstre pivot:
# Konto | Kontonavn | UB <år> | UB <år-1> | Endring | Endring % | Antall
# regnr/regnskapslinje er valgfrie ekstrakolonner; ikke i default visible.
SB_DEFAULT_VISIBLE = (
    "Konto", "Kontonavn", "UB", "UB_fjor", "Endring_fjor", "Endring_pct", "Antall",
)

# Overskrifter hentes nå fra analysis_heading (page_analyse_columns). Kartet
# beholdes tomt av bakoverkomp — configure_sb_tree_columns bruker mapperen.
_SB_COL_HEADINGS: dict[str, str] = {}

_SB_COL_WIDTHS = {
    "Konto":          70,
    "Kontonavn":      220,
    "OK":             40,
    "OK_av":          70,
    "OK_dato":        90,
    "Vedlegg":        60,
    "Gruppe":         150,
    "regnr":          60,
    "regnskapslinje": 180,
    "IB":             110,
    "Endring":        110,
    "UB":             110,
    "UB_fjor":        110,
    "Endring_fjor":   110,
    "Endring_pct":    90,
    "Antall":         70,
}

_SB_NUMERIC_COLS = (
    "regnr",
    "IB", "Endring", "UB", "UB_fjor", "Endring_fjor", "Endring_pct", "Antall",
)
_SB_CENTER_COLS = ("OK", "OK_av", "OK_dato", "Vedlegg")


# =====================================================================
# Oppretting og toggling av SB-treeview
# =====================================================================

def create_sb_tree(parent_frame: Any) -> Any:
    """Opprett en SB-treeview i parent_frame, returnerer (frame, tree).

    Lager en egen Frame med tree + scrollbars, plassert i samme grid-celle
    som TX-treet. Skjult som standard.
    """
    try:
        from tkinter import ttk
        import tkinter as tk  # noqa: F401
    except Exception:
        return None

    frame = ttk.Frame(parent_frame)

    tree = ttk.Treeview(frame, columns=SB_COLS, show="headings", selectmode="extended")
    tree.grid(row=0, column=0, sticky="nsew")

    try:
        import page_analyse_columns as _cols
        year = _cols._active_year()
        _heading_fn = lambda c: _cols.analysis_heading(c, year=year)
    except Exception:
        _heading_fn = lambda c: _SB_COL_HEADINGS.get(c, c)

    for col in SB_COLS:
        tree.heading(col, text=_heading_fn(col))
        if col in _SB_NUMERIC_COLS:
            anchor = "e"
        elif col in _SB_CENTER_COLS:
            anchor = "center"
        else:
            anchor = "w"
        stretch = col == "Kontonavn"
        tree.column(col, width=_SB_COL_WIDTHS.get(col, 100), anchor=anchor, stretch=stretch)

    try:
        tree.tag_configure("gruppe", foreground="#1A56A0")
    except Exception:
        pass

    try:
        tree.tag_configure("neg", foreground="red")
    except Exception:
        pass

    # Lys grønn bakgrunn for konti markert som OK (ferdigrevidert)
    try:
        tree.tag_configure("ok_row", background="#E3F5E1")
    except Exception:
        pass

    # Lys gul bakgrunn for konti der suggesteren foreslår en annen RL enn
    # nåværende mapping (has_suggestion_conflict). Signaliserer at navnet
    # på kontoen peker mot en annen regnskapslinje enn den den havnet på
    # via intervall/override — en mulig feil-mapping å vurdere.
    try:
        tree.tag_configure("mapping_conflict", background="#FFF3CD")
    except Exception:
        pass

    v_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    v_scroll.grid(row=0, column=1, sticky="ns")
    h_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    h_scroll.grid(row=1, column=0, sticky="ew")
    tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)

    # Lagre tree-referanse på frame for enkel tilgang
    frame._sb_tree = tree  # type: ignore[attr-defined]

    return frame


def _hide_all_views(*, page: Any, except_frame: Any = None) -> None:
    """Skjul alle visningsrammer bortsett fra except_frame."""
    for attr in ("_tx_frame", "_sb_frame", "_nk_frame", "_mp_frame", "_mp_acct_frame"):
        f = getattr(page, attr, None)
        if f is not None and f is not except_frame:
            try:
                f.grid_remove()
            except Exception:
                pass


def show_sb_tree(*, page: Any) -> None:
    """Vis SB-treet og skjul andre visninger."""
    sb_frame = getattr(page, "_sb_frame", None)
    if sb_frame is None:
        return
    _hide_all_views(page=page, except_frame=sb_frame)
    try:
        sb_frame.grid()
    except Exception:
        pass
    try:
        import page_analyse_columns as _cols
        _cols.configure_sb_tree_columns(page=page)
    except Exception:
        pass


def show_tx_tree(*, page: Any) -> None:
    """Vis TX-treet og skjul andre visninger."""
    tx_frame = getattr(page, "_tx_frame", None)
    _hide_all_views(page=page, except_frame=tx_frame)
    try:
        if tx_frame is not None:
            tx_frame.grid()
    except Exception:
        pass


def show_nk_view(*, page: Any) -> None:
    """Vis nøkkeltall-rammen og skjul andre visninger."""
    nk_frame = getattr(page, "_nk_frame", None)
    if nk_frame is None:
        return
    _hide_all_views(page=page, except_frame=nk_frame)
    try:
        nk_frame.grid()
    except Exception:
        pass

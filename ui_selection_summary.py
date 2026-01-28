"""ui_selection_summary.py

Felles summering av markerte rader i GUI (Treeview/Listbox).

Mål:
- Når brukeren markerer rader: vis "Markert: N rader | Beløp: X | Sum: Y ..." et sted i GUI.
- Sentralisert: én install-funksjon som binder globalt med bind_all, så alle views får samme oppførsel.

Design:
- UI-uavhengig logikk for summering (duck typing) + best-effort parsing.
- For visning forsøker vi (i rekkefølge):
  1) status_setter callback (hvis gitt)
  2) eksisterende `set_status()` på toplevel
  3) auto-laget status label nederst i toplevel (pack/grid hvis mulig)
  4) fallback: oppdater vindu-tittel (title)

Merk:
- Vi gjør *ingen* antakelser om konkrete widget-klasser (ingen isinstance mot Tk-klasser),
  for å gjøre dette testbart uten Tk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

try:  # pragma: no cover
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore


# --------------------------------------------------------------------------------------
# Parsing / heuristikk
# --------------------------------------------------------------------------------------

def _parse_number_best_effort(value: Any) -> Optional[float]:
    """Robust parsing av tall (best effort).

    Støtter typiske GUI-strenger:
      - "1 234,50"
      - "-200,00"
      - "(34,50)"
      - "1234.56"
      - "1.234,56"
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s:
        return None

    low = s.lower()
    if low in {"nan", "none", "null", "na"}:
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()

    # remove spaces incl NBSP
    s = s.replace("\u00a0", " ").replace(" ", "")

    # remove currency suffixes
    for suf in ("kr", "nok"):
        if s.lower().endswith(suf):
            s = s[: -len(suf)].strip()

    # If both ',' and '.' present -> assume '.' thousands, ',' decimal (NO style)
    if "," in s and "." in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    elif "," in s and "." not in s:
        s = s.replace(",", ".")

    try:
        n = float(s)
    except Exception:
        return None

    if negative:
        n = -abs(n)
    return n


def _format_amount_no(value: float, decimals: int = 2) -> str:
    """Norsk format: tusenskiller mellomrom, desimal komma."""
    try:
        v = float(value)
    except Exception:
        v = 0.0

    sign = "-" if v < 0 else ""
    v = abs(v)

    s = f"{v:.{decimals}f}"
    whole, dec = s.split(".")
    parts = []
    while len(whole) > 3:
        parts.insert(0, whole[-3:])
        whole = whole[:-3]
    parts.insert(0, whole)
    whole_spaced = " ".join(parts)
    return f"{sign}{whole_spaced},{dec}"


def _score_column_for_sum(col_name: str) -> int:
    name = str(col_name).strip().lower()

    if "%" in name or "andel" in name:
        return 0
    if "antall" in name or "linjer" in name:
        return 10

    if "beløp" in name or "belop" in name or "amount" in name:
        return 100
    if "sum" in name:
        return 80
    if "netto" in name:
        return 70
    if "diff" in name:
        return 60
    if "saldo" in name:
        return 50

    return 0


def guess_sum_columns(columns: list[str], *, max_cols: int = 3) -> list[str]:
    """Velg relevante kolonner å summere basert på navn."""
    scored = [(c, _score_column_for_sum(c)) for c in columns]
    scored = [x for x in scored if x[1] >= 60]
    scored.sort(key=lambda x: (-x[1], str(x[0]).lower()))
    return [str(c) for c, _ in scored[:max_cols]]


# --------------------------------------------------------------------------------------
# Treeview summering (duck typing)
# --------------------------------------------------------------------------------------

def _tree_is_treeview(widget: Any) -> bool:
    return all(hasattr(widget, attr) for attr in ("selection", "set", "get_children"))


def _tree_get_columns(tree: Any) -> list[str]:
    try:
        return [str(c) for c in list(tree["columns"])]  # type: ignore[index]
    except Exception:
        return []


def _tree_get_heading_text(tree: Any, col_id: str) -> str:
    try:
        txt = tree.heading(col_id, option="text")
        return str(txt) if txt else str(col_id)
    except Exception:
        return str(col_id)


def treeview_selection_sums(tree: Any) -> tuple[int, dict[str, float]]:
    """Returnerer (antall markerte, {kolonne: sum})."""
    if not _tree_is_treeview(tree):
        return 0, {}

    try:
        selected = list(tree.selection())
    except Exception:
        selected = []

    if not selected:
        return 0, {}

    cols = _tree_get_columns(tree)
    sum_cols = guess_sum_columns(cols)
    if not sum_cols:
        return len(selected), {}

    sums: dict[str, float] = {c: 0.0 for c in sum_cols}
    parsed_counts: dict[str, int] = {c: 0 for c in sum_cols}

    for iid in selected:
        for c in sum_cols:
            try:
                raw = tree.set(iid, c)
            except Exception:
                raw = None
            n = _parse_number_best_effort(raw)
            if n is None:
                continue
            sums[c] += float(n)
            parsed_counts[c] += 1

    sums = {c: sums[c] for c in sum_cols if parsed_counts.get(c, 0) > 0}
    return len(selected), sums


def build_selection_summary_text(count: int, sums: dict[str, float]) -> str:
    rows_txt = "rad" if count == 1 else "rader"
    parts = [f"Markert: {count} {rows_txt}"]

    if sums:
        cols = list(sums.keys())
        cols.sort(key=lambda c: (-_score_column_for_sum(c), str(c).lower()))
        for c in cols:
            parts.append(f"{c}: {_format_amount_no(sums[c])}")

    return " | ".join(parts)


# --------------------------------------------------------------------------------------
# Status output (setter/label/title) + install
# --------------------------------------------------------------------------------------

def _safe_call(fn: Callable[[str], None], txt: str) -> None:
    try:
        fn(txt)
    except Exception:
        return


def _get_toplevel(widget: Any) -> Any:
    try:
        return widget.winfo_toplevel()
    except Exception:
        return None


def _toplevel_title_get(win: Any) -> str:
    try:
        return str(win.title())
    except Exception:
        return ""


def _toplevel_title_set(win: Any, txt: str) -> None:
    try:
        win.title(txt)
    except Exception:
        return


def _ensure_status_label(win: Any) -> Any:
    """Lag (eller hent) en label i bunnen av vinduet. Best effort."""
    existing = getattr(win, "_ui_selection_summary_status_label", None)
    if existing is not None:
        return existing

    if tk is None or ttk is None:
        return None

    # Prøv å se hvilket geometry manager vinduet allerede bruker
    uses_grid = False
    uses_pack = False
    try:
        uses_grid = bool(getattr(win, "grid_slaves")())  # type: ignore[misc]
    except Exception:
        uses_grid = False
    try:
        uses_pack = bool(getattr(win, "pack_slaves")())  # type: ignore[misc]
    except Exception:
        uses_pack = False

    try:
        lbl = ttk.Label(win, relief=tk.SUNKEN, anchor="w")
        if uses_grid and not uses_pack:
            # Grid fallback: legg langt nede
            try:
                lbl.grid(row=999, column=0, sticky="ew", columnspan=999)
                try:
                    win.grid_rowconfigure(999, weight=0)
                except Exception:
                    pass
            except Exception:
                return None
        else:
            # Pack default (eller hvis vi ikke vet)
            try:
                lbl.pack(side=tk.BOTTOM, fill=tk.X)
            except Exception:
                # Kan feile hvis root bruker grid; da har vi grid forsøkt over.
                return None
    except Exception:
        return None

    try:
        setattr(win, "_ui_selection_summary_status_label", lbl)
    except Exception:
        pass
    return lbl


def _default_status_setter_for_window(win: Any) -> Callable[[str], None]:
    """Finn et sted å skrive status for et gitt vindu."""
    if win is None:
        return lambda _txt: None

    # 1) win.set_status
    if callable(getattr(win, "set_status", None)):
        return getattr(win, "set_status")  # type: ignore[return-value]

    # 2) status label eksisterer / kan opprettes
    lbl = _ensure_status_label(win)
    if lbl is not None and callable(getattr(lbl, "config", None)):

        def _setter(txt: str) -> None:
            try:
                lbl.config(text=txt)
            except Exception:
                pass

        return _setter

    # 3) fallback: title
    base_title = getattr(win, "_ui_selection_summary_base_title", None)
    if base_title is None:
        base_title = _toplevel_title_get(win)
        try:
            setattr(win, "_ui_selection_summary_base_title", base_title)
        except Exception:
            pass

    def _setter(txt: str) -> None:
        if not txt:
            _toplevel_title_set(win, str(base_title))
            return
        _toplevel_title_set(win, f"{base_title} | {txt}")

    return _setter


@dataclass
class _Installed:
    installed: bool = False


def _get_install_state(root: Any) -> _Installed:
    st = getattr(root, "_ui_selection_summary_installed", None)
    if isinstance(st, _Installed):
        return st
    st = _Installed()
    try:
        setattr(root, "_ui_selection_summary_installed", st)
    except Exception:
        pass
    return st


def install_global_selection_summary(
    root: Any,
    *,
    status_setter: Optional[Callable[[str], None]] = None,
) -> None:
    """Installer global selection-summary (idempotent)."""
    if not callable(getattr(root, "bind_all", None)):
        return

    st = _get_install_state(root)
    if st.installed:
        return

    def on_tree_select(event: Any) -> None:
        tree = getattr(event, "widget", None)
        if tree is None or not _tree_is_treeview(tree):
            return

        n, sums = treeview_selection_sums(tree)
        # Vis heading-tekst i stedet for internal col-id
        pretty = {_tree_get_heading_text(tree, c): v for c, v in sums.items()}
        txt = build_selection_summary_text(n, pretty)

        if status_setter is not None:
            _safe_call(status_setter, txt)
            return

        win = _get_toplevel(tree)
        setter = _default_status_setter_for_window(win)
        _safe_call(setter, txt)

    def on_listbox_select(event: Any) -> None:
        lb = getattr(event, "widget", None)
        if lb is None:
            return
        # Duck typing listbox
        if not all(hasattr(lb, a) for a in ("curselection", "size")):
            return
        try:
            n = len(list(lb.curselection()))
        except Exception:
            n = 0
        txt = build_selection_summary_text(n, {})

        if status_setter is not None:
            _safe_call(status_setter, txt)
            return

        win = _get_toplevel(lb)
        setter = _default_status_setter_for_window(win)
        _safe_call(setter, txt)

    try:
        root.bind_all("<<TreeviewSelect>>", on_tree_select, add="+")
        root.bind_all("<<ListboxSelect>>", on_listbox_select, add="+")
    except Exception:
        return

    st.installed = True


__all__ = [
    "install_global_selection_summary",
    "guess_sum_columns",
    "treeview_selection_sums",
    "build_selection_summary_text",
]

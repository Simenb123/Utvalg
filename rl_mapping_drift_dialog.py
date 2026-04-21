"""Dialog som viser mapping-drift mellom inneværende år og fjoråret.

Brukes fra mapping-warning-banneret i Analyse-fanen.
Ren visningsmodul — all drift-deteksjon skjer i rl_mapping_drift.py.

Filter:
- Min beløp (materialitet): skjul småposter under terskel.
- Skjul kun-i-ett-år: kan man fokusere på `Endret mapping`-rader alene.

Høyreklikk på (multiselect) rader gir tre handlinger:
- Sett årets mapping til fjorårets mapping
- Sett fjorårets mapping til årets mapping
- Aksepter som reell endring (skjul fra listen)
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

import formatting
from rl_mapping_drift import (
    DRIFT_CHANGED,
    DRIFT_ONLY_CURRENT,
    DRIFT_ONLY_PRIOR,
    MappingDrift,
)

log = logging.getLogger(__name__)


_KIND_LABEL = {
    DRIFT_CHANGED: "Endret mapping",
    DRIFT_ONLY_CURRENT: "Kun i år",
    DRIFT_ONLY_PRIOR: "Kun i fjor",
}


def _fmt_regnr(regnr: int | None, navn: str) -> str:
    if regnr is None:
        return "(ikke mappet)"
    if navn:
        return f"{regnr} {navn}"
    return str(regnr)


def _get_session_info() -> tuple[str, str]:
    try:
        import session
        client = str(getattr(session, "client", None) or "").strip()
        year = str(getattr(session, "year", None) or "").strip()
        return client, year
    except Exception:
        return "", ""


def open_dialog(page: Any, drifts: Iterable[MappingDrift]) -> None:
    drifts_list = list(drifts)
    if not drifts_list or tk is None or ttk is None:
        return

    parent = getattr(page, "winfo_toplevel", None)
    try:
        master = parent() if callable(parent) else page
    except Exception:
        master = None

    try:
        top = tk.Toplevel(master) if master is not None else tk.Toplevel()
    except Exception:
        return
    try:
        top.title("Mapping-drift vs fjoråret")
        top.geometry("1080x560")
    except Exception:
        pass

    # Tilstand som overlever re-render
    state: dict[str, Any] = {
        "all": list(drifts_list),
        "min_amount": 0.0,
        "hide_one_year": False,
        "sort_col": None,
        "sort_desc": False,
    }

    container = ttk.Frame(top, padding=8)
    container.pack(fill="both", expand=True)

    header_text = (
        f"{len(drifts_list)} kontoer med ulik regnskapslinje-mapping i år vs fjor. "
        "Høyreklikk (evt. med flere valgt) for å endre mapping eller akseptere."
    )
    ttk.Label(container, text=header_text, wraplength=1040, justify="left").pack(
        anchor="w", pady=(0, 6)
    )

    # --- Filter-rad ---
    filter_row = ttk.Frame(container)
    filter_row.pack(fill="x", pady=(0, 6))
    ttk.Label(filter_row, text="Min beløp (|UB|):").pack(side="left")
    min_var = tk.StringVar(value="0")
    entry_min = ttk.Entry(filter_row, textvariable=min_var, width=12)
    entry_min.pack(side="left", padx=(4, 12))

    hide_var = tk.BooleanVar(value=False)
    chk_hide = ttk.Checkbutton(
        filter_row, text="Skjul kun-i-ett-år (vis bare endret mapping)",
        variable=hide_var,
    )
    chk_hide.pack(side="left")

    lbl_count = ttk.Label(filter_row, text="")
    lbl_count.pack(side="right")

    # --- Treeview ---
    cols = (
        "konto", "kontonavn", "kind",
        "rl_aar", "rl_fjor",
        "ub_aar", "ub_fjor", "endring",
    )
    headings = {
        "konto": "Konto", "kontonavn": "Kontonavn", "kind": "Type",
        "rl_aar": "RL i år", "rl_fjor": "RL i fjor",
        "ub_aar": "UB i år", "ub_fjor": "UB i fjor", "endring": "Endring",
    }
    widths = {
        "konto": 70, "kontonavn": 190, "kind": 120,
        "rl_aar": 180, "rl_fjor": 180,
        "ub_aar": 110, "ub_fjor": 110, "endring": 110,
    }

    tree_frame = ttk.Frame(container)
    tree_frame.pack(fill="both", expand=True)
    tree = ttk.Treeview(
        tree_frame, columns=cols, show="headings", height=18,
        selectmode="extended",
    )
    def _sort_key(col: str):
        def key_for(d: MappingDrift):
            if col == "konto":
                return (len(d.konto), d.konto)
            if col == "kontonavn":
                return (d.kontonavn or "").lower()
            if col == "kind":
                return _KIND_LABEL.get(d.kind, d.kind)
            if col == "rl_aar":
                return (d.regnr_aar if d.regnr_aar is not None else 10**9, d.rl_navn_aar or "")
            if col == "rl_fjor":
                return (d.regnr_fjor if d.regnr_fjor is not None else 10**9, d.rl_navn_fjor or "")
            if col == "ub_aar":
                return d.ub_aar
            if col == "ub_fjor":
                return d.ub_fjor
            if col == "endring":
                return d.ub_aar - d.ub_fjor
            return 0
        return key_for

    def _on_sort(col: str) -> None:
        if state["sort_col"] == col:
            state["sort_desc"] = not state["sort_desc"]
        else:
            state["sort_col"] = col
            state["sort_desc"] = col in ("ub_aar", "ub_fjor", "endring")
        _update_heading_arrows()
        _render()

    def _update_heading_arrows() -> None:
        for c in cols:
            arrow = ""
            if state["sort_col"] == c:
                arrow = " ▼" if state["sort_desc"] else " ▲"
            tree.heading(c, text=headings[c] + arrow)

    for c in cols:
        tree.heading(c, text=headings[c], command=lambda _c=c: _on_sort(_c))
        tree.column(
            c, width=widths[c],
            anchor=("e" if c in ("ub_aar", "ub_fjor", "endring") else "w"),
        )
    vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    # Mapping item → MappingDrift for høyreklikk-handlinger
    item_to_drift: dict[str, MappingDrift] = {}

    def _apply_filter() -> list[MappingDrift]:
        try:
            min_amount = float(str(min_var.get()).replace(" ", "").replace(",", "."))
        except (TypeError, ValueError):
            min_amount = 0.0
        state["min_amount"] = min_amount
        state["hide_one_year"] = bool(hide_var.get())
        out: list[MappingDrift] = []
        for d in state["all"]:
            if d.materialitet < min_amount:
                continue
            if state["hide_one_year"] and d.kind != DRIFT_CHANGED:
                continue
            out.append(d)
        return out

    def _render() -> None:
        for item in tree.get_children(""):
            tree.delete(item)
        item_to_drift.clear()
        filtered = _apply_filter()
        sort_col = state.get("sort_col")
        if sort_col:
            try:
                filtered = sorted(filtered, key=_sort_key(sort_col),
                                  reverse=bool(state.get("sort_desc")))
            except Exception:
                pass
        for d in filtered:
            delta = d.ub_aar - d.ub_fjor
            item = tree.insert("", "end", values=(
                d.konto, d.kontonavn, _KIND_LABEL.get(d.kind, d.kind),
                _fmt_regnr(d.regnr_aar, d.rl_navn_aar),
                _fmt_regnr(d.regnr_fjor, d.rl_navn_fjor),
                formatting.fmt_amount(d.ub_aar),
                formatting.fmt_amount(d.ub_fjor),
                formatting.fmt_amount(delta),
            ))
            item_to_drift[item] = d
        try:
            lbl_count.configure(text=f"Viser {len(filtered)} av {len(state['all'])}")
        except Exception:
            pass

    min_var.trace_add("write", lambda *_: _render())
    hide_var.trace_add("write", lambda *_: _render())

    # --- Høyreklikk-meny ---
    menu = tk.Menu(top, tearoff=0)

    def _selected_drifts() -> list[MappingDrift]:
        items = tree.selection()
        return [item_to_drift[i] for i in items if i in item_to_drift]

    def _confirm_if_many(n: int, verb: str) -> bool:
        if n <= 3 or messagebox is None:
            return True
        try:
            return bool(messagebox.askyesno(
                "Bekreft", f"{verb} {n} kontoer?", parent=top,
            ))
        except Exception:
            return True

    def _do_use_prior() -> None:
        selected = _selected_drifts()
        if not selected:
            return
        client, year = _get_session_info()
        if not client or not year:
            return
        if not _confirm_if_many(len(selected), "Sette fjorårets mapping på"):
            return
        try:
            import rl_mapping_drift as _drift
            n = _drift.apply_use_prior_mapping(
                client=client, year=year, drifts=selected,
            )
        except Exception as exc:
            log.warning("apply_use_prior_mapping failed: %s", exc)
            n = 0
        _refresh_page_after_change(page)
        if messagebox is not None:
            try:
                messagebox.showinfo(
                    "Mapping oppdatert",
                    f"{n} kontoer fikk fjorårets regnr i år.",
                    parent=top,
                )
            except Exception:
                pass
        _reload_drifts()

    def _do_use_current() -> None:
        selected = _selected_drifts()
        if not selected:
            return
        client, year = _get_session_info()
        if not client or not year:
            return
        if not _confirm_if_many(len(selected), "Sette årets mapping på fjor for"):
            return
        try:
            import rl_mapping_drift as _drift
            n = _drift.apply_use_current_mapping(
                client=client, year=year, drifts=selected,
            )
        except Exception as exc:
            log.warning("apply_use_current_mapping failed: %s", exc)
            n = 0
        _refresh_page_after_change(page)
        if messagebox is not None:
            try:
                messagebox.showinfo(
                    "Mapping oppdatert",
                    f"{n} kontoer fikk årets regnr i fjor-oversikten.",
                    parent=top,
                )
            except Exception:
                pass
        _reload_drifts()

    def _do_accept() -> None:
        selected = _selected_drifts()
        if not selected:
            return
        client, year = _get_session_info()
        if not client or not year:
            return
        if not _confirm_if_many(len(selected), "Akseptere drift for"):
            return
        try:
            import rl_mapping_drift as _drift
            n = _drift.apply_accept_drift(
                client=client, year=year, drifts=selected,
            )
        except Exception as exc:
            log.warning("apply_accept_drift failed: %s", exc)
            n = 0
        _refresh_page_after_change(page)
        if messagebox is not None:
            try:
                messagebox.showinfo(
                    "Drift akseptert",
                    f"{n} kontoer er markert som legitim endring.",
                    parent=top,
                )
            except Exception:
                pass
        _reload_drifts()

    def _reload_drifts() -> None:
        """Etter en handling: be page bygge drift på nytt og synk dialogen."""
        try:
            import analyse_mapping_ui
            analyse_mapping_ui.refresh_mapping_issues(page)
        except Exception:
            pass
        new_drifts = list(getattr(page, "_mapping_drifts", None) or [])
        state["all"] = new_drifts
        _render()
        if not new_drifts:
            try:
                top.destroy()
            except Exception:
                pass

    menu.add_command(label="Sett årets mapping = fjorårets", command=_do_use_prior)
    menu.add_command(label="Sett fjorårets mapping = årets", command=_do_use_current)
    menu.add_separator()
    menu.add_command(label="Aksepter som reell endring", command=_do_accept)

    def _on_right_click(event: Any) -> None:
        row = tree.identify_row(event.y)
        if row and row not in tree.selection():
            tree.selection_set(row)
        if not tree.selection():
            return
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    tree.bind("<Button-3>", _on_right_click)

    footer = ttk.Frame(top, padding=(8, 4))
    footer.pack(fill="x")
    ttk.Label(
        footer,
        text="Tips: hold Ctrl/Shift for å velge flere kontoer, så høyreklikk.",
        foreground="#555",
    ).pack(side="left")
    ttk.Button(footer, text="Lukk", command=top.destroy).pack(side="right")

    _render()


def _refresh_page_after_change(page: Any) -> None:
    """Oppdater analysesidens pivot + mapping-issues etter en drift-handling."""
    for name in ("_refresh_pivot", "_refresh_transactions_view"):
        fn = getattr(page, name, None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

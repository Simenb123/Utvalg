from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Iterable, Optional

import pandas as pd

import analyse_treewidths
import formatting

try:
    from ui_treeview_sort import enable_treeview_sorting  # type: ignore
except Exception:  # pragma: no cover
    enable_treeview_sorting = None  # type: ignore


def build_leaf_regnskapslinje_choices(regnskapslinjer: Optional[pd.DataFrame]) -> list[tuple[int, str]]:
    if regnskapslinjer is None or regnskapslinjer.empty:
        return []

    try:
        from src.shared.regnskap.mapping import normalize_regnskapslinjer
        regn = normalize_regnskapslinjer(regnskapslinjer)
    except Exception:
        return []

    leaf = regn.loc[~regn["sumpost"], ["regnr", "regnskapslinje"]].copy()
    leaf["regnr"] = leaf["regnr"].astype(int)
    leaf["regnskapslinje"] = leaf["regnskapslinje"].fillna("").astype(str)
    return [(int(row.regnr), str(row.regnskapslinje)) for row in leaf.sort_values("regnr").itertuples(index=False)]


def format_regnskapslinje_choice(regnr: int, navn: str) -> str:
    label = str(navn or "").strip()
    return f"{int(regnr)} - {label}" if label else str(int(regnr))


def parse_regnskapslinje_choice(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    head = text.split("-", 1)[0].strip()
    try:
        return int(head)
    except Exception:
        return None


def _resolve_initial_choice(
    values: list[str],
    *,
    current_regnr: object,
    current_regnskapslinje: str,
    suggested_regnr: object = None,
    suggested_regnskapslinje: str = "",
) -> str:
    current_regnr_int = parse_regnskapslinje_choice(current_regnr)
    current_choice = (
        format_regnskapslinje_choice(current_regnr_int, str(current_regnskapslinje or ""))
        if current_regnr_int is not None
        else ""
    )
    suggested_regnr_int = parse_regnskapslinje_choice(suggested_regnr)
    suggested_choice = (
        format_regnskapslinje_choice(suggested_regnr_int, str(suggested_regnskapslinje or ""))
        if suggested_regnr_int is not None
        else ""
    )
    if suggested_choice and suggested_choice in values:
        return suggested_choice
    if current_choice and current_choice in values:
        return current_choice
    return values[0] if values else ""


def _mapping_info_text(konto: str, current_overrides: dict[str, int]) -> str:
    if konto in current_overrides:
        return f"Denne kontoen er overstyrt til regnskapslinje {current_overrides[konto]}."
    return "Denne kontoen bruker standard intervall-mapping."


def _suggestion_info_text(
    *,
    suggested_regnr: object = None,
    suggested_regnskapslinje: str = "",
    suggestion_reason: str = "",
    suggestion_source: str = "",
    confidence_bucket: str = "",
    sign_note: str = "",
) -> str:
    regnr = parse_regnskapslinje_choice(suggested_regnr)
    if regnr is None:
        return ""
    lines = [f"Forslag: {format_regnskapslinje_choice(regnr, suggested_regnskapslinje)}"]
    if confidence_bucket:
        lines.append(f"Tillit: {confidence_bucket}")
    if suggestion_source:
        lines.append(f"Kilde: {str(suggestion_source).replace('_', ' ')}")
    if suggestion_reason:
        lines.append(f"Hvorfor: {suggestion_reason}")
    if sign_note:
        lines.append(f"Fortegn: {sign_note}")
    return "\n".join(lines)


def open_account_mapping_dialog(
    master: tk.Misc,
    *,
    client: str,
    konto: str,
    kontonavn: str,
    current_regnr: object,
    current_regnskapslinje: str,
    suggested_regnr: object = None,
    suggested_regnskapslinje: str = "",
    suggestion_reason: str = "",
    suggestion_source: str = "",
    confidence_bucket: str = "",
    sign_note: str = "",
    regnskapslinjer: Optional[pd.DataFrame] = None,
    on_saved: Optional[Callable[[], None]] = None,
    on_removed: Optional[Callable[[], None]] = None,
) -> None:
    choice_pairs = build_leaf_regnskapslinje_choices(regnskapslinjer)
    if not client:
        messagebox.showerror("Endre mapping", "Ingen aktiv klient i sesjonen. Kan ikke lagre mapping.", parent=master)
        return
    if not choice_pairs:
        messagebox.showerror("Endre mapping", "Fant ingen regnskapslinjer å mappe mot.", parent=master)
        return

    try:
        import src.shared.regnskap.client_overrides as regnskap_client_overrides

        import session as _session
        _year = getattr(_session, "year", None) or ""
        current_overrides = regnskap_client_overrides.load_account_overrides(
            client, year=str(_year) if _year else None)
    except Exception:
        current_overrides = {}

    win = tk.Toplevel(master)
    win.title("Endre mapping")
    win.transient(master)
    win.grab_set()
    win.resizable(False, False)

    frm = ttk.Frame(win, padding=10)
    frm.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frm, text=f"Konto: {konto}").grid(row=0, column=0, columnspan=2, sticky="w")
    ttk.Label(frm, text=f"Kontonavn: {kontonavn}").grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))
    ttk.Label(frm, text="Ny regnskapslinje:").grid(row=2, column=0, sticky="w")

    values = [format_regnskapslinje_choice(regnr, navn) for regnr, navn in choice_pairs]
    initial_choice = _resolve_initial_choice(
        values,
        current_regnr=current_regnr,
        current_regnskapslinje=current_regnskapslinje,
        suggested_regnr=suggested_regnr,
        suggested_regnskapslinje=suggested_regnskapslinje,
    )
    var_choice = tk.StringVar(master=win, value=initial_choice)
    cmb = ttk.Combobox(frm, textvariable=var_choice, values=values, state="readonly", width=40)
    cmb.grid(row=2, column=1, sticky="ew", padx=(8, 0))
    frm.columnconfigure(1, weight=1)

    info_text = _mapping_info_text(konto, current_overrides)
    ttk.Label(frm, text=info_text).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
    suggestion_text = _suggestion_info_text(
        suggested_regnr=suggested_regnr,
        suggested_regnskapslinje=suggested_regnskapslinje,
        suggestion_reason=suggestion_reason,
        suggestion_source=suggestion_source,
        confidence_bucket=confidence_bucket,
        sign_note=sign_note,
    )
    if suggestion_text:
        ttk.Label(
            frm,
            text=suggestion_text,
            justify="left",
            wraplength=420,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

    btns = ttk.Frame(frm)
    btns.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))

    def _save() -> None:
        regnr = parse_regnskapslinje_choice(var_choice.get())
        if regnr is None:
            messagebox.showerror("Endre mapping", "Velg en gyldig regnskapslinje.", parent=win)
            return
        try:
            import src.shared.regnskap.client_overrides as regnskap_client_overrides

            import session as _session
            _yr = getattr(_session, "year", None) or ""
            regnskap_client_overrides.set_account_override(
                client, konto, regnr, year=str(_yr) if _yr else None)
        except Exception as exc:
            messagebox.showerror("Endre mapping", f"Kunne ikke lagre mapping.\n\n{exc}", parent=win)
            return
        win.destroy()
        if callable(on_saved):
            try:
                on_saved()
            except Exception:
                pass

    def _remove() -> None:
        try:
            import src.shared.regnskap.client_overrides as regnskap_client_overrides

            import session as _session
            _yr = getattr(_session, "year", None) or ""
            regnskap_client_overrides.remove_account_override(
                client, konto, year=str(_yr) if _yr else None)
        except Exception as exc:
            messagebox.showerror("Endre mapping", f"Kunne ikke fjerne override.\n\n{exc}", parent=win)
            return
        win.destroy()
        if callable(on_removed):
            try:
                on_removed()
            except Exception:
                pass

    ttk.Button(btns, text="Lagre", command=_save).pack(side=tk.RIGHT)
    ttk.Button(btns, text="Avbryt", command=win.destroy).pack(side=tk.RIGHT, padx=(0, 6))
    ttk.Button(btns, text="Fjern override", command=_remove).pack(side=tk.RIGHT, padx=(0, 6))


class RLAccountDrillDialog(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        df: pd.DataFrame,
        *,
        title: str,
        client: str | None = None,
        regnskapslinjer: Optional[pd.DataFrame] = None,
        reload_callback: Optional[Callable[[], pd.DataFrame]] = None,
    ) -> None:
        super().__init__(master)
        self.df = df.copy()
        self.client = str(client or "").strip()
        self.regnskapslinjer = regnskapslinjer.copy() if isinstance(regnskapslinjer, pd.DataFrame) else None
        self.reload_callback = reload_callback
        self._choice_pairs = build_leaf_regnskapslinje_choices(self.regnskapslinjer)

        self.title(title)
        self.geometry("1100x680")

        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=(8, 4))

        self._lbl_count = ttk.Label(top, text="")
        self._lbl_count.pack(side=tk.LEFT)
        ttk.Button(top, text="Endre mapping...", command=self._open_mapping_dialog).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(top, text="Fjern override", command=self._remove_selected_override).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(top, text="Lukk", command=self.destroy).pack(side=tk.RIGHT)

        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        cols = list(self.df.columns)
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="extended")
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree.tag_configure("neg", foreground="red")

        self._setup_columns()
        self._populate()

        if enable_treeview_sorting:
            try:
                enable_treeview_sorting(self.tree, columns=cols)
            except Exception:
                pass

        self.tree.bind("<<TreeviewSelect>>", lambda _e=None: self._update_count_label())
        self.tree.bind("<Return>", lambda _e=None: self._open_mapping_dialog())
        self.tree.bind("<KP_Enter>", lambda _e=None: self._open_mapping_dialog())

    def _update_count_label(self) -> None:
        count = len(self.df.index)
        selected = self._selected_row()
        if selected is None:
            self._lbl_count.configure(text=f"Kontoer i utvalg: {count}")
            return
        regnr = str(selected.get("Nr", "") or "")
        rl_name = str(selected.get("Regnskapslinje", "") or "")
        konto = str(selected.get("Konto", "") or "")
        self._lbl_count.configure(text=f"Kontoer i utvalg: {count} | Valgt: {konto} → {regnr} {rl_name}".strip())

    def _setup_columns(self) -> None:
        for col in self.df.columns:
            self.tree.heading(col, text=col)
            width = analyse_treewidths.suggest_column_width(col, self._iter_sample_values(col))
            self.tree.column(
                col,
                width=width,
                minwidth=max(40, min(width, 80)),
                anchor=analyse_treewidths.column_anchor(col),
                stretch=False,
            )

    def _iter_sample_values(self, col: str) -> Iterable[object]:
        try:
            return self.df[col].head(200).tolist()
        except Exception:
            return []

    def _format_cell(self, col: str, value: object) -> str:
        if value is None:
            return ""
        if col in {"IB", "Endring", "UB"}:
            return formatting.fmt_amount(value)
        if col == "Antall":
            return formatting.format_int_no(value)
        return str(value)

    def _populate(self) -> None:
        try:
            self.tree.delete(*self.tree.get_children(""))
        except Exception:
            pass

        cols = list(self.df.columns)
        idx_endring = cols.index("Endring") if "Endring" in cols else None

        for row in self.df.itertuples(index=False, name=None):
            tags = ()
            if idx_endring is not None:
                try:
                    if float(row[idx_endring]) < 0:
                        tags = ("neg",)
                except Exception:
                    pass

            try:
                values = tuple(self._format_cell(col, value) for col, value in zip(cols, row))
                self.tree.insert("", tk.END, values=values, tags=tags)
            except Exception:
                continue

        self._update_count_label()

    def _selected_item(self):
        try:
            selected = list(self.tree.selection())
        except Exception:
            selected = []
        if selected:
            return selected[0]
        try:
            focused = self.tree.focus()
        except Exception:
            focused = ""
        return focused or None

    def _selected_row(self) -> Optional[dict[str, object]]:
        item = self._selected_item()
        if not item:
            return None
        try:
            values = list(self.tree.item(item).get("values") or [])
        except Exception:
            return None
        cols = list(self.df.columns)
        if not values or not cols:
            return None
        values = values + [""] * max(0, len(cols) - len(values))
        return {col: value for col, value in zip(cols, values)}

    def _current_overrides(self) -> dict[str, int]:
        if not self.client:
            return {}
        try:
            import src.shared.regnskap.client_overrides as regnskap_client_overrides
            import session as _session
            _year = getattr(_session, "year", None) or ""
            return regnskap_client_overrides.load_account_overrides(
                self.client, year=str(_year) if _year else None)
        except Exception:
            return {}

    def _reload_data(self, *, konto_to_focus: str = "") -> None:
        if not callable(self.reload_callback):
            return
        try:
            fresh = self.reload_callback()
        except Exception as exc:
            messagebox.showerror("RL-drilldown", f"Kunne ikke oppdatere drilldown.\n\n{exc}", parent=self)
            return
        if not isinstance(fresh, pd.DataFrame):
            return

        self.df = fresh.copy()
        try:
            self.tree.configure(columns=list(self.df.columns))
        except Exception:
            pass
        self._setup_columns()
        self._populate()

        if not konto_to_focus:
            return
        for item in self.tree.get_children(""):
            try:
                konto = str(self.tree.set(item, "Konto") or "").strip()
            except Exception:
                continue
            if konto == konto_to_focus:
                try:
                    self.tree.selection_set(item)
                    self.tree.focus(item)
                    self.tree.see(item)
                except Exception:
                    pass
                break

    def _open_mapping_dialog(self) -> None:
        selected = self._selected_row()
        if selected is None:
            messagebox.showinfo("RL-drilldown", "Velg en konto i listen først.", parent=self)
            return
        konto = str(selected.get("Konto", "") or "").strip()
        open_account_mapping_dialog(
            self,
            client=self.client,
            konto=konto,
            kontonavn=str(selected.get("Kontonavn", "") or "").strip(),
            current_regnr=selected.get("Nr"),
            current_regnskapslinje=str(selected.get("Regnskapslinje", "") or "").strip(),
            suggested_regnr=selected.get("Forslag Nr"),
            suggested_regnskapslinje=str(selected.get("Forslag Regnskapslinje", "") or "").strip(),
            suggestion_reason=str(selected.get("Forslag Hvorfor", "") or "").strip(),
            suggestion_source=str(selected.get("Forslag Kilde", "") or "").strip(),
            confidence_bucket=str(selected.get("Forslag Tillit", "") or "").strip(),
            sign_note=str(selected.get("Fortegn-notat", "") or "").strip(),
            regnskapslinjer=self.regnskapslinjer,
            on_saved=lambda: self._reload_data(konto_to_focus=konto),
            on_removed=lambda: self._reload_data(konto_to_focus=konto),
        )

    def _remove_selected_override(self) -> None:
        selected = self._selected_row()
        if selected is None:
            messagebox.showinfo("RL-drilldown", "Velg en konto i listen først.", parent=self)
            return
        if not self.client:
            messagebox.showerror("RL-drilldown", "Ingen aktiv klient i sesjonen. Kan ikke lagre mapping.", parent=self)
            return

        konto = str(selected.get("Konto", "") or "").strip()
        try:
            import src.shared.regnskap.client_overrides as regnskap_client_overrides
            import session as _session
            _yr = getattr(_session, "year", None) or ""
            regnskap_client_overrides.remove_account_override(
                self.client, konto, year=str(_yr) if _yr else None)
        except Exception as exc:
            messagebox.showerror("RL-drilldown", f"Kunne ikke fjerne override.\n\n{exc}", parent=self)
            return
        self._reload_data(konto_to_focus=konto)


def open_rl_account_drilldown(
    master: tk.Misc,
    df: pd.DataFrame,
    *,
    title: str,
    client: str | None = None,
    regnskapslinjer: Optional[pd.DataFrame] = None,
    reload_callback: Optional[Callable[[], pd.DataFrame]] = None,
) -> RLAccountDrillDialog:
    return RLAccountDrillDialog(
        master,
        df,
        title=title,
        client=client,
        regnskapslinjer=regnskapslinjer,
        reload_callback=reload_callback,
    )

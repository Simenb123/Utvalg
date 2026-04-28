from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Iterable, Optional

import pandas as pd

import analyse_treewidths
import formatting

try:
    from src.shared.ui.treeview_sort import enable_treeview_sorting  # type: ignore
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


def _label_for_regnr(values: list[str], regnr: int) -> str | None:
    """Finn dropdown-label som starter med ``regnr``-nummeret.

    Robust mot små forskjeller i RL-navnet — vi parser regnr-prefikset
    fra hver verdi i listen og sammenligner som int. Returnerer None
    hvis ingen treff.
    """
    for v in values:
        if parse_regnskapslinje_choice(v) == regnr:
            return v
    return None


def _compute_top_suggestions(
    *,
    client: str,
    konto: str,
    kontonavn: str,
    regnskapslinjer: Optional[pd.DataFrame],
    n: int = 5,
) -> list:
    """Beregn topp-N forslag for kontoen ved å kalle suggester med alle
    tilgjengelige inputs (rulebook, AR-data, historikk)."""
    if regnskapslinjer is None:
        return []
    try:
        import regnskapslinje_suggest as _suggest
        import regnskapslinje_mapping_service as _svc
        import session as _session

        year = getattr(_session, "year", None) or ""
        try:
            year_int = int(str(year)) if year else None
        except Exception:
            year_int = None

        rulebook = _suggest.load_rulebook_document()
        owned = _svc._load_owned_companies_for_client(client or None, year_int)
        history = _svc._history_overrides_by_account(client or None, year_int)
        historical_regnr = history.get(konto)

        return _suggest.suggest_top_n_regnskapslinje(
            n=n,
            konto=konto,
            kontonavn=kontonavn,
            regnskapslinjer=regnskapslinjer,
            rulebook_document=rulebook,
            historical_regnr=historical_regnr,
            owned_companies=owned,
        )
    except Exception:
        return []


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

    # Hent topp-5 forslag (kan inkludere det som allerede er i suggested_regnr)
    top_suggestions = _compute_top_suggestions(
        client=client,
        konto=konto,
        kontonavn=kontonavn,
        regnskapslinjer=regnskapslinjer,
        n=5,
    )

    win = tk.Toplevel(master)
    win.title(f"Endre mapping — {konto} {kontonavn}")
    win.transient(master)
    win.grab_set()
    win.minsize(720, 520)
    win.geometry("860x640")

    outer = ttk.Frame(win, padding=14)
    outer.pack(fill=tk.BOTH, expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(3, weight=1)  # listbox-raden strekker seg

    # ----- Header: konto + kontonavn -----
    header = ttk.Frame(outer)
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(1, weight=1)
    ttk.Label(header, text=str(konto), font=("Segoe UI", 14, "bold")).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(header, text=str(kontonavn or ""), font=("Segoe UI", 11)).grid(
        row=0, column=1, sticky="w", padx=(10, 0)
    )
    ttk.Separator(outer, orient="horizontal").grid(row=1, column=0, sticky="ew", pady=(8, 10))

    # ----- Nåværende-info -----
    info_text = _mapping_info_text(konto, current_overrides)
    ttk.Label(outer, text=info_text, foreground="#444").grid(
        row=2, column=0, sticky="w", pady=(0, 6)
    )

    # ----- Konflikt-card (hvis aktuelt) -----
    suggested_regnr_int = parse_regnskapslinje_choice(suggested_regnr)
    current_regnr_int = parse_regnskapslinje_choice(current_regnr)
    is_conflict = (
        suggested_regnr_int is not None
        and current_regnr_int is not None
        and suggested_regnr_int != current_regnr_int
    )

    values = [format_regnskapslinje_choice(regnr, navn) for regnr, navn in choice_pairs]
    initial_choice = _resolve_initial_choice(
        values,
        current_regnr=current_regnr,
        current_regnskapslinje=current_regnskapslinje,
        suggested_regnr=suggested_regnr,
        suggested_regnskapslinje=suggested_regnskapslinje,
    )
    var_choice = tk.StringVar(master=win, value=initial_choice)

    suggestion_text = _suggestion_info_text(
        suggested_regnr=suggested_regnr,
        suggested_regnskapslinje=suggested_regnskapslinje,
        suggestion_reason=suggestion_reason,
        suggestion_source=suggestion_source,
        confidence_bucket=confidence_bucket,
        sign_note=sign_note,
    )

    if suggestion_text and is_conflict:
        card_bg = "#FFF3CD"
        card_fg = "#664d03"
        sugg_frame = tk.Frame(
            outer, bg=card_bg, padx=12, pady=8,
            highlightbackground=card_fg, highlightthickness=1,
        )
        sugg_frame.grid(row=2, column=0, sticky="ew", pady=(6, 8))
        sugg_frame.columnconfigure(0, weight=1)
        tk.Label(
            sugg_frame, text="⚠ Konflikt: navnet peker mot en annen regnskapslinje",
            bg=card_bg, fg=card_fg, font=("Segoe UI", 10, "bold"), justify="left",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            sugg_frame, text=suggestion_text, bg=card_bg, fg=card_fg,
            justify="left", wraplength=780, font=("Segoe UI", 9),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

    # ----- To listbokser side om side -----
    body = ttk.Frame(outer)
    body.grid(row=3, column=0, sticky="nsew", pady=(4, 8))
    body.columnconfigure(0, weight=1)
    body.columnconfigure(1, weight=2)
    body.rowconfigure(1, weight=1)

    # ----- Venstre listbox: Topp 5 forslag -----
    left = ttk.LabelFrame(body, text=f"Topp {len(top_suggestions) or 5} forslag", padding=4)
    left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
    left.columnconfigure(0, weight=1)
    left.rowconfigure(0, weight=1)

    lb_top = tk.Listbox(left, font=("Segoe UI", 9), exportselection=False)
    lb_top_sb = ttk.Scrollbar(left, orient="vertical", command=lb_top.yview)
    lb_top.configure(yscrollcommand=lb_top_sb.set)
    lb_top.grid(row=0, column=0, sticky="nsew")
    lb_top_sb.grid(row=0, column=1, sticky="ns")

    # Map listbox-index → label-string i values
    top_index_to_label: dict[int, str] = {}
    for idx, sugg in enumerate(top_suggestions):
        try:
            regnr = int(getattr(sugg, "regnr", 0))
            navn = str(getattr(sugg, "regnskapslinje", "") or "")
            conf = float(getattr(sugg, "confidence", 0.0))
            bucket = str(getattr(sugg, "confidence_bucket", "") or "")
        except Exception:
            continue
        label = _label_for_regnr(values, regnr) or format_regnskapslinje_choice(regnr, navn)
        top_index_to_label[idx] = label
        display = f"{regnr}  {navn}    [{int(conf * 100)} % · {bucket}]"
        lb_top.insert(tk.END, display)
    if not top_suggestions:
        lb_top.insert(tk.END, "(ingen forslag)")
        lb_top.itemconfigure(0, foreground="#888")

    # ----- Høyre listbox: Alle regnskapslinjer + søk -----
    right = ttk.LabelFrame(body, text="Alle regnskapslinjer", padding=4)
    right.grid(row=0, column=1, rowspan=2, sticky="nsew")
    right.columnconfigure(1, weight=1)
    right.rowconfigure(1, weight=1)

    ttk.Label(right, text="Søk:").grid(row=0, column=0, sticky="w", padx=(0, 4), pady=(0, 4))
    var_search = tk.StringVar(master=win)
    ent_search = ttk.Entry(right, textvariable=var_search)
    ent_search.grid(row=0, column=1, sticky="ew", pady=(0, 4))

    lb_all = tk.Listbox(right, font=("Segoe UI", 9), exportselection=False)
    lb_all_sb = ttk.Scrollbar(right, orient="vertical", command=lb_all.yview)
    lb_all.configure(yscrollcommand=lb_all_sb.set)
    lb_all.grid(row=1, column=0, columnspan=2, sticky="nsew")
    lb_all_sb.grid(row=1, column=2, sticky="ns")

    # Map listbox-index → label
    all_index_to_label: list[str] = []

    def _refill_all_listbox(filter_text: str = "") -> None:
        nonlocal all_index_to_label
        lb_all.delete(0, tk.END)
        all_index_to_label = []
        ft = filter_text.strip().lower()
        for label in values:
            if ft and ft not in label.lower():
                continue
            lb_all.insert(tk.END, label)
            all_index_to_label.append(label)
        # Marker eksisterende valg hvis synlig
        try:
            current = var_choice.get()
            if current in all_index_to_label:
                idx = all_index_to_label.index(current)
                lb_all.selection_set(idx)
                lb_all.see(idx)
        except Exception:
            pass

    _refill_all_listbox()

    def _on_search_changed(*_args: object) -> None:
        _refill_all_listbox(var_search.get())

    var_search.trace_add("write", _on_search_changed)

    # ----- Save / Remove / Cancel -----
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

    # ----- Listbox-bindings -----
    def _select_from_top(_event=None) -> None:
        sel = lb_top.curselection()
        if not sel:
            return
        idx = sel[0]
        label = top_index_to_label.get(idx)
        if label:
            var_choice.set(label)

    def _select_from_all(_event=None) -> None:
        sel = lb_all.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(all_index_to_label):
            var_choice.set(all_index_to_label[idx])

    def _accept_top(_event=None) -> None:
        _select_from_top()
        if parse_regnskapslinje_choice(var_choice.get()) is not None:
            _save()

    def _accept_all(_event=None) -> None:
        _select_from_all()
        if parse_regnskapslinje_choice(var_choice.get()) is not None:
            _save()

    lb_top.bind("<<ListboxSelect>>", _select_from_top)
    lb_top.bind("<Double-Button-1>", _accept_top)
    lb_top.bind("<Return>", _accept_top)
    lb_top.bind("<KP_Enter>", _accept_top)

    lb_all.bind("<<ListboxSelect>>", _select_from_all)
    lb_all.bind("<Double-Button-1>", _accept_all)
    lb_all.bind("<Return>", _accept_all)
    lb_all.bind("<KP_Enter>", _accept_all)

    # ----- Status-tekst (valgt RL) + hotkey-hint -----
    status = ttk.Frame(outer)
    status.grid(row=4, column=0, sticky="ew", pady=(2, 6))
    status.columnconfigure(0, weight=1)
    var_status = tk.StringVar(master=win, value=f"Valgt: {var_choice.get() or '(ingen)'}")

    def _on_choice_changed(*_args: object) -> None:
        var_status.set(f"Valgt: {var_choice.get() or '(ingen)'}")

    var_choice.trace_add("write", _on_choice_changed)
    ttk.Label(status, textvariable=var_status, font=("Segoe UI", 9, "bold")).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(
        status,
        text="Dobbeltklikk = bytt og lukk · Enter = bytt · Esc = avbryt",
        foreground="#666", font=("Segoe UI", 8),
    ).grid(row=1, column=0, sticky="w")

    # ----- Knappe-rad -----
    ttk.Separator(outer, orient="horizontal").grid(row=5, column=0, sticky="ew", pady=(0, 8))
    btns = ttk.Frame(outer)
    btns.grid(row=6, column=0, sticky="e")
    ttk.Button(btns, text="Lagre", command=_save).pack(side=tk.RIGHT)
    ttk.Button(btns, text="Avbryt", command=win.destroy).pack(side=tk.RIGHT, padx=(0, 8))
    ttk.Button(btns, text="Fjern override", command=_remove).pack(side=tk.RIGHT, padx=(0, 8))

    # Globale hotkeys på vinduet
    win.bind("<Escape>", lambda _e=None: win.destroy())

    # Fokus: hvis det er et top-forslag, start med fokus på top-listen,
    # ellers på søkefeltet (raskest å finne en linje fra full liste)
    if top_suggestions:
        lb_top.selection_set(0)
        lb_top.focus_set()
        _select_from_top()
    else:
        ent_search.focus_set()


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

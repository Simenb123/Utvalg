"""Admin-underfane: Lokalt handlingsbibliotek."""

from __future__ import annotations

from typing import Callable

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

import action_library
import workpaper_library
from action_library import LocalAction
from workpaper_library import Workpaper


_AUTOSAVE_DELAY_MS = 400


def _load_rl_options() -> list[tuple[str, str, str]]:
    """Returner [(regnr, navn, "PL"|"BS"), …] uten sumposter."""
    try:
        import src.shared.regnskap.config as regnskap_config

        df = regnskap_config.load_regnskapslinjer_json()
    except Exception:
        return []
    out: list[tuple[str, str, str]] = []
    for _, row in df.iterrows():
        sumpost = str(row.get("sumpost", "")).strip().lower()
        if sumpost == "ja":
            continue
        nr = str(row.get("nr", "")).strip()
        navn = str(row.get("regnskapslinje", "")).strip()
        if not nr or not navn:
            continue
        rb = str(row.get("resultat/balanse", "")).strip().lower()
        if rb.startswith("res"):
            line_type = "PL"
        elif rb.startswith("bal"):
            line_type = "BS"
        else:
            line_type = ""
        out.append((nr, navn, line_type))
    return out


def _scope_summary(scope: str, regnrs: list[str]) -> str:
    s = (scope or "").strip().lower()
    if s == "alle":
        return "Alle linjer"
    if s == "alle_pl":
        return "Alle PL-linjer"
    if s == "alle_bs":
        return "Alle BS-linjer"
    n = len([r for r in (regnrs or []) if str(r).strip()])
    if n == 0:
        return "Ingen valgt"
    return f"{n} spesifikk linje" if n == 1 else f"{n} spesifikke linjer"


class _ActionLibraryEditor(ttk.Frame):  # type: ignore[misc]
    def __init__(
        self,
        master,
        *,
        title: str = "Handlinger",
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._title = title
        self._on_saved = on_saved
        self._items: list[LocalAction] = []
        self._types: list[str] = []
        self._workpapers: list[Workpaper] = []
        self._current_workpaper_ids: list[str] = []
        self._selected_id: str = ""

        # Multi-RL-state for det aktuelle elementet (ikke i widget)
        self._scope_value: str = ""
        self._regnr_value: list[str] = []

        # Autosave
        self._suspend_dirty = False
        self._save_after_id: str | None = None

        # Filter
        self._filter_type_var = tk.StringVar(value="Alle")

        # Skjema
        self._status_var = tk.StringVar(value="")
        self._navn_var = tk.StringVar()
        self._type_var = tk.StringVar(value="")
        self._rl_summary_var = tk.StringVar(value="Ingen valgt")

        # RL-options for popup-dialog
        self._rl_options: list[tuple[str, str, str]] = []

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        self._build_ui()
        self._wire_autosave()
        self.after(0, self._reload)

    # ------------------------------------------------------------------
    # UI
    def _build_ui(self) -> None:
        # Topplinje
        top = ttk.Frame(self)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        top.columnconfigure(0, weight=1)
        ttk.Label(
            top,
            text="Lokalt handlingsbibliotek — endringer lagres automatisk.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(top, text="Filter fase:").grid(row=0, column=1, padx=(0, 4))
        self._cb_filter = ttk.Combobox(
            top,
            textvariable=self._filter_type_var,
            values=["Alle"],
            width=20,
            state="readonly",
        )
        self._cb_filter.grid(row=0, column=2, padx=(0, 8))
        self._cb_filter.bind("<<ComboboxSelected>>", lambda _e: self._refresh_tree())
        ttk.Button(top, text="Ny", command=self._on_new).grid(row=0, column=3, padx=(6, 0))
        ttk.Button(top, text="Slett", command=self._on_delete).grid(row=0, column=4, padx=(6, 0))

        # Venstre liste
        left = ttk.Frame(self)
        left.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=4)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        cols = ("navn", "type")
        self._tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("navn", text="Navn")
        self._tree.heading("type", text="Fase")
        self._tree.column("navn", width=240, minwidth=140)
        self._tree.column("type", width=140, minwidth=100)
        yscroll = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=yscroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # Høyre skjema
        right = ttk.LabelFrame(self, text="Detaljer", padding=8)
        right.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=4)
        right.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(right, text="Navn:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self._navn_var).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        ttk.Label(right, text="Fase:").grid(row=row, column=0, sticky="w", pady=2)
        type_row = ttk.Frame(right)
        type_row.grid(row=row, column=1, sticky="ew", pady=2)
        type_row.columnconfigure(0, weight=1)
        self._cb_type = ttk.Combobox(
            type_row, textvariable=self._type_var, values=[], width=22,
        )
        self._cb_type.grid(row=0, column=0, sticky="w")
        ttk.Button(type_row, text="Rediger faser…", command=self._open_types_dialog).grid(
            row=0, column=1, padx=(6, 0)
        )
        row += 1

        ttk.Label(right, text="Regnskapslinjer:").grid(row=row, column=0, sticky="w", pady=2)
        rl_row = ttk.Frame(right)
        rl_row.grid(row=row, column=1, sticky="ew", pady=2)
        rl_row.columnconfigure(0, weight=1)
        ttk.Label(rl_row, textvariable=self._rl_summary_var).grid(row=0, column=0, sticky="w")
        ttk.Button(rl_row, text="Velg…", command=self._open_rl_dialog).grid(row=0, column=1, padx=(6, 0))
        row += 1

        ttk.Label(right, text="Arbeidspapir:").grid(row=row, column=0, sticky="nw", pady=2)
        wp_frame = ttk.Frame(right)
        wp_frame.grid(row=row, column=1, sticky="nsew", pady=2)
        wp_frame.columnconfigure(0, weight=1)
        self._wp_listbox = tk.Listbox(wp_frame, height=4, exportselection=False)
        self._wp_listbox.grid(row=0, column=0, sticky="nsew")
        wp_btns = ttk.Frame(wp_frame)
        wp_btns.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        ttk.Button(wp_btns, text="Legg til…", command=self._on_add_workpaper).pack(fill="x")
        ttk.Button(wp_btns, text="Fjern", command=self._on_remove_workpaper).pack(fill="x", pady=(4, 0))
        row += 1

        ttk.Label(right, text="Beskrivelse:").grid(row=row, column=0, sticky="nw", pady=2)
        self._beskr_txt = tk.Text(right, height=8, wrap="word")
        self._beskr_txt.grid(row=row, column=1, sticky="nsew", pady=2)
        right.rowconfigure(row, weight=1)
        row += 1

        # Status
        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6)
        )

    def _wire_autosave(self) -> None:
        self._navn_var.trace_add("write", lambda *_: self._schedule_save())
        self._type_var.trace_add("write", lambda *_: self._schedule_save())
        self._beskr_txt.bind("<KeyRelease>", lambda _e: self._schedule_save(), add="+")

    # ------------------------------------------------------------------
    # Lagring + reload

    def _schedule_save(self) -> None:
        if self._suspend_dirty:
            return
        if self._save_after_id is not None:
            try:
                self.after_cancel(self._save_after_id)
            except Exception:
                pass
        self._save_after_id = self.after(_AUTOSAVE_DELAY_MS, self._autosave)

    def _autosave(self) -> None:
        self._save_after_id = None
        navn = self._navn_var.get().strip()
        if not navn:
            return
        beskrivelse = self._beskr_txt.get("1.0", "end").strip()
        if self._selected_id:
            item = next((a for a in self._items if a.id == self._selected_id), None)
        else:
            item = None
        is_new = item is None
        if is_new:
            item = LocalAction.new(navn)
        item.navn = navn
        item.type = self._type_var.get().strip()
        item.workpaper_ids = list(self._current_workpaper_ids)
        item.beskrivelse = beskrivelse
        item.applies_to_scope = self._scope_value
        item.applies_to_regnr = list(self._regnr_value)
        action_library.upsert_action(item)
        self._selected_id = item.id
        self._items = action_library.load_library()
        self._refresh_tree(preserve_selection=True)
        self._update_status_line(saved_now=True)
        if self._on_saved:
            self._on_saved()

    def _reload(self) -> None:
        self._items = action_library.load_library()
        self._types = action_library.load_types()
        self._workpapers = workpaper_library.list_all()
        self._cb_type.configure(values=self._types)
        if not self._rl_options:
            self._rl_options = _load_rl_options()
        # Filter-combobox: "Alle" + alle typer
        filter_values = ["Alle"] + list(self._types)
        self._cb_filter.configure(values=filter_values)
        if self._filter_type_var.get() not in filter_values:
            self._filter_type_var.set("Alle")
        self._refresh_tree()
        self._refresh_workpaper_list()
        self._update_status_line()

    def _update_status_line(self, *, saved_now: bool = False) -> None:
        msg = f"{len(self._items)} handling(er) lagret i {action_library.library_path()}"
        if saved_now:
            msg = "Lagret. " + msg
        self._status_var.set(msg)

    def _refresh_tree(self, *, preserve_selection: bool = False) -> None:
        self._tree.delete(*self._tree.get_children())
        flt = self._filter_type_var.get().strip()
        for a in sorted(self._items, key=lambda x: (x.type.lower(), x.navn.lower())):
            if flt and flt != "Alle" and (a.type or "").strip() != flt:
                continue
            self._tree.insert(
                "", "end", iid=a.id,
                values=(a.navn, a.type),
            )
        if preserve_selection and self._selected_id and self._tree.exists(self._selected_id):
            self._tree.selection_set(self._selected_id)

    # ------------------------------------------------------------------
    # Selection / nytt / slett

    def _on_select(self, _evt=None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        new_id = sel[0]
        if new_id == self._selected_id:
            return
        self._selected_id = new_id
        item = next((a for a in self._items if a.id == self._selected_id), None)
        if item is None:
            return
        self._suspend_dirty = True
        try:
            self._navn_var.set(item.navn)
            self._type_var.set(item.type)
            self._current_workpaper_ids = list(item.workpaper_ids)
            self._refresh_workpaper_list()
            self._beskr_txt.delete("1.0", "end")
            self._beskr_txt.insert("1.0", item.beskrivelse)
            self._scope_value = (item.applies_to_scope or "").strip().lower()
            self._regnr_value = [
                str(x).strip() for x in (item.applies_to_regnr or []) if str(x).strip()
            ]
            self._rl_summary_var.set(_scope_summary(self._scope_value, self._regnr_value))
        finally:
            self._suspend_dirty = False

    def _on_new(self) -> None:
        # Avbryt evt. ventende lagring så ny handling ikke skriver gammelt navn.
        if self._save_after_id is not None:
            try:
                self.after_cancel(self._save_after_id)
            except Exception:
                pass
            self._save_after_id = None
        self._selected_id = ""
        self._suspend_dirty = True
        try:
            self._navn_var.set("")
            self._type_var.set(self._types[0] if self._types else "")
            self._current_workpaper_ids = []
            self._refresh_workpaper_list()
            self._beskr_txt.delete("1.0", "end")
            self._scope_value = ""
            self._regnr_value = []
            self._rl_summary_var.set(_scope_summary("", []))
            try:
                self._tree.selection_remove(self._tree.selection())
            except Exception:
                pass
        finally:
            self._suspend_dirty = False

    def _on_delete(self) -> None:
        if not self._selected_id:
            return
        item = next((a for a in self._items if a.id == self._selected_id), None)
        if item is None:
            return
        if not messagebox.askyesno("Slett handling", f"Slette «{item.navn}»?"):
            return
        if self._save_after_id is not None:
            try:
                self.after_cancel(self._save_after_id)
            except Exception:
                pass
            self._save_after_id = None
        action_library.delete_action(self._selected_id)
        self._selected_id = ""
        self._on_new()
        self._reload()
        if self._on_saved:
            self._on_saved()

    # ------------------------------------------------------------------
    # Arbeidspapir

    def _refresh_workpaper_list(self) -> None:
        self._wp_listbox.delete(0, "end")
        by_id = {w.id: w for w in self._workpapers}
        for wp_id in self._current_workpaper_ids:
            wp = by_id.get(wp_id)
            label = wp.navn if wp else f"[mangler {wp_id[:8]}…]"
            self._wp_listbox.insert("end", label)

    def _on_add_workpaper(self) -> None:
        if not self._workpapers:
            messagebox.showinfo(
                "Ingen arbeidspapir",
                "Legg til arbeidspapir i Arbeidspapir-fanen først.",
                parent=self,
            )
            return
        available = [w for w in self._workpapers if w.id not in self._current_workpaper_ids]
        if not available:
            messagebox.showinfo("Ingenting å legge til", "Alle arbeidspapir er allerede koblet.", parent=self)
            return
        self._open_pick_workpaper_dialog(available)

    def _open_pick_workpaper_dialog(self, available: list[Workpaper]) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Velg arbeidspapir")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.columnconfigure(0, weight=1)
        dlg.rowconfigure(0, weight=1)

        frm = ttk.Frame(dlg, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(0, weight=1)

        lb = tk.Listbox(frm, height=10, selectmode="extended", exportselection=False)
        lb.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(frm, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")

        ordered = sorted(available, key=lambda x: (x.kategori != "generert", x.navn.lower()))
        for w in ordered:
            label = f"{w.navn}  ({w.kategori})" if w.kategori else w.navn
            lb.insert("end", label)

        actions = ttk.Frame(frm)
        actions.grid(row=1, column=0, columnspan=2, sticky="e", pady=(8, 0))

        def _apply() -> None:
            picks = [ordered[i].id for i in lb.curselection()]
            if picks:
                self._current_workpaper_ids.extend(
                    i for i in picks if i not in self._current_workpaper_ids
                )
                self._refresh_workpaper_list()
                self._schedule_save()
            dlg.destroy()

        ttk.Button(actions, text="Avbryt", command=dlg.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(actions, text="Legg til valgt", command=_apply).pack(side="right")

    def _on_remove_workpaper(self) -> None:
        sel = self._wp_listbox.curselection()
        if not sel:
            return
        for i in reversed(sel):
            if 0 <= i < len(self._current_workpaper_ids):
                del self._current_workpaper_ids[i]
        self._refresh_workpaper_list()
        self._schedule_save()

    # ------------------------------------------------------------------
    # Faser-dialog (gamle "typer")

    def _open_types_dialog(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Rediger faser")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.columnconfigure(0, weight=1)
        dlg.rowconfigure(0, weight=1)

        frm = ttk.Frame(dlg, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(0, weight=1)

        lb = tk.Listbox(frm, height=10, exportselection=False)
        lb.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(frm, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=yscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")

        for t in self._types:
            lb.insert("end", t)

        entry_var = tk.StringVar()
        bottom = ttk.Frame(frm)
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        bottom.columnconfigure(0, weight=1)
        ent = ttk.Entry(bottom, textvariable=entry_var)
        ent.grid(row=0, column=0, sticky="ew")

        def _add() -> None:
            v = entry_var.get().strip()
            if v and v not in lb.get(0, "end"):
                lb.insert("end", v)
                entry_var.set("")

        def _delete() -> None:
            for i in reversed(lb.curselection()):
                lb.delete(i)

        def _move(delta: int) -> None:
            sel = lb.curselection()
            if not sel:
                return
            i = sel[0]
            j = i + delta
            if j < 0 or j >= lb.size():
                return
            v = lb.get(i)
            lb.delete(i)
            lb.insert(j, v)
            lb.selection_set(j)

        ttk.Button(bottom, text="Legg til", command=_add).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(bottom, text="Slett", command=_delete).grid(row=0, column=2, padx=(6, 0))
        ttk.Button(bottom, text="▲", width=3, command=lambda: _move(-1)).grid(row=0, column=3, padx=(6, 0))
        ttk.Button(bottom, text="▼", width=3, command=lambda: _move(1)).grid(row=0, column=4, padx=(2, 0))
        ent.bind("<Return>", lambda _: _add())

        actions_row = ttk.Frame(frm)
        actions_row.grid(row=2, column=0, columnspan=2, sticky="e", pady=(10, 0))

        def _save_and_close() -> None:
            new_types = list(lb.get(0, "end"))
            action_library.save_types(new_types)
            self._reload()
            dlg.destroy()

        ttk.Button(actions_row, text="Avbryt", command=dlg.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(actions_row, text="Lagre", command=_save_and_close).pack(side="right")

        ent.focus_set()

    # ------------------------------------------------------------------
    # Regnskapslinje-popup

    def _open_rl_dialog(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Velg regnskapslinjer")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.columnconfigure(0, weight=1)
        dlg.rowconfigure(0, weight=1)
        dlg.geometry("520x560")

        frm = ttk.Frame(dlg, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(3, weight=1)

        scope_var = tk.StringVar(value=self._scope_value if self._scope_value in ("alle", "alle_pl", "alle_bs") else "spesifikke")
        check_vars: dict[str, tk.BooleanVar] = {}
        check_widgets: dict[str, ttk.Checkbutton] = {}

        # Radio-rad
        radio_row = ttk.Frame(frm)
        radio_row.grid(row=0, column=0, sticky="w")
        for value, label in (
            ("spesifikke", "Spesifikke linjer"),
            ("alle_pl", "Alle PL-linjer"),
            ("alle_bs", "Alle BS-linjer"),
            ("alle", "Alle linjer"),
        ):
            ttk.Radiobutton(
                radio_row,
                text=label,
                variable=scope_var,
                value=value,
                command=lambda: _update_state(),
            ).pack(side="left", padx=(0, 10))

        # Hurtig-knapper
        quick_row = ttk.Frame(frm)
        quick_row.grid(row=1, column=0, sticky="w", pady=(6, 4))
        ttk.Button(quick_row, text="Hak av alle PL", command=lambda: _bulk("PL")).pack(side="left")
        ttk.Button(quick_row, text="Hak av alle BS", command=lambda: _bulk("BS")).pack(side="left", padx=(6, 0))
        ttk.Button(quick_row, text="Fjern alle", command=lambda: _bulk("")).pack(side="left", padx=(6, 0))

        # Scrollbar liste
        list_holder = ttk.Frame(frm)
        list_holder.grid(row=3, column=0, sticky="nsew", pady=(4, 8))
        list_holder.columnconfigure(0, weight=1)
        list_holder.rowconfigure(0, weight=1)
        canvas = tk.Canvas(list_holder, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(list_holder, orient="vertical", command=canvas.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=yscroll.set)
        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(inner_id, width=e.width))
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))

        if not self._rl_options:
            ttk.Label(
                inner,
                text="Ingen regnskapslinjer funnet. Sjekk regnskap_config.",
                style="Muted.TLabel",
            ).pack(anchor="w", padx=4, pady=4)
        else:
            preselected = set(self._regnr_value or [])
            for nr, navn, line_type in self._rl_options:
                var = tk.BooleanVar(value=nr in preselected)
                check_vars[nr] = var
                label = f"{nr}  {navn}"
                if line_type:
                    label = f"{label}    [{line_type}]"
                cb = ttk.Checkbutton(inner, text=label, variable=var)
                cb.pack(anchor="w", padx=4, pady=1)
                check_widgets[nr] = cb

        def _update_state() -> None:
            enabled = scope_var.get() == "spesifikke"
            state = "normal" if enabled else "disabled"
            for cb in check_widgets.values():
                try:
                    cb.configure(state=state)
                except Exception:
                    pass

        def _bulk(line_type: str) -> None:
            if scope_var.get() != "spesifikke":
                scope_var.set("spesifikke")
                _update_state()
            if not line_type:
                for var in check_vars.values():
                    var.set(False)
                return
            for nr, _navn, lt in self._rl_options:
                if lt == line_type and nr in check_vars:
                    check_vars[nr].set(True)

        _update_state()

        # Knapper
        btn_row = ttk.Frame(frm)
        btn_row.grid(row=4, column=0, sticky="e")

        def _save_and_close() -> None:
            scope = scope_var.get().strip().lower()
            if scope in ("alle", "alle_pl", "alle_bs"):
                self._scope_value = scope
                self._regnr_value = []
            else:
                self._scope_value = ""
                self._regnr_value = [nr for nr, var in check_vars.items() if var.get()]
            self._rl_summary_var.set(_scope_summary(self._scope_value, self._regnr_value))
            dlg.destroy()
            self._schedule_save()

        ttk.Button(btn_row, text="Avbryt", command=dlg.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btn_row, text="OK", command=_save_and_close).pack(side="right")

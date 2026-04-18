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
        self._suspend_dirty = False

        self._status_var = tk.StringVar(value="")
        self._navn_var = tk.StringVar()
        self._type_var = tk.StringVar(value="substansiv")
        self._omraade_var = tk.StringVar()
        self._default_regnr_var = tk.StringVar()

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        self._build_ui()
        self.after(0, self._reload)

    def _build_ui(self) -> None:
        # Topplinje
        top = ttk.Frame(self)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        top.columnconfigure(0, weight=1)
        ttk.Label(
            top,
            text="Lokalt handlingsbibliotek — brukes senere til å lage arbeidspapirer og foreslå handlinger.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(top, text="Ny", command=self._on_new).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(top, text="Slett", command=self._on_delete).grid(row=0, column=2, padx=(6, 0))
        ttk.Button(top, text="Lagre", command=self._on_save).grid(row=0, column=3, padx=(6, 0))

        # Venstre liste
        left = ttk.Frame(self)
        left.grid(row=1, column=0, sticky="nsew", padx=(8, 4), pady=4)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        cols = ("navn", "type", "omraade")
        self._tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("navn", text="Navn")
        self._tree.heading("type", text="Type")
        self._tree.heading("omraade", text="Område")
        self._tree.column("navn", width=220, minwidth=120)
        self._tree.column("type", width=90, minwidth=70)
        self._tree.column("omraade", width=140, minwidth=80)
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
        ent_navn = ttk.Entry(right, textvariable=self._navn_var)
        ent_navn.grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        ttk.Label(right, text="Type:").grid(row=row, column=0, sticky="w", pady=2)
        type_row = ttk.Frame(right)
        type_row.grid(row=row, column=1, sticky="w", pady=2)
        self._cb_type = ttk.Combobox(
            type_row, textvariable=self._type_var, values=[], width=22,
        )
        self._cb_type.pack(side="left")
        ttk.Button(type_row, text="Rediger typer…", command=self._open_types_dialog).pack(side="left", padx=(6, 0))
        row += 1

        ttk.Label(right, text="Område:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self._omraade_var).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        ttk.Label(right, text="Default regnr:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self._default_regnr_var, width=10).grid(row=row, column=1, sticky="w", pady=2)
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

    # ------------------------------------------------------------------

    def _reload(self) -> None:
        self._items = action_library.load_library()
        self._types = action_library.load_types()
        self._workpapers = workpaper_library.list_all()
        self._cb_type.configure(values=self._types)
        if self._type_var.get() not in self._types and self._types:
            self._type_var.set(self._types[0])
        self._refresh_tree()
        self._refresh_workpaper_list()
        self._status_var.set(f"{len(self._items)} handling(er) lagret i {action_library.library_path()}")

    def _refresh_workpaper_list(self) -> None:
        self._wp_listbox.delete(0, "end")
        by_id = {w.id: w for w in self._workpapers}
        for wp_id in self._current_workpaper_ids:
            wp = by_id.get(wp_id)
            label = wp.navn if wp else f"[mangler {wp_id[:8]}\u2026]"
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

    def _open_types_dialog(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Rediger handlingstyper")
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

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for a in sorted(self._items, key=lambda x: (x.omraade.lower(), x.navn.lower())):
            self._tree.insert(
                "", "end", iid=a.id,
                values=(a.navn, a.type, a.omraade or "\u2013"),
            )
        if self._selected_id and self._tree.exists(self._selected_id):
            self._tree.selection_set(self._selected_id)

    def _on_select(self, _evt=None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        self._selected_id = sel[0]
        item = next((a for a in self._items if a.id == self._selected_id), None)
        if item is None:
            return
        self._navn_var.set(item.navn)
        self._type_var.set(item.type)
        self._omraade_var.set(item.omraade)
        self._default_regnr_var.set(item.default_regnr)
        self._current_workpaper_ids = list(item.workpaper_ids)
        self._refresh_workpaper_list()
        self._beskr_txt.delete("1.0", "end")
        self._beskr_txt.insert("1.0", item.beskrivelse)

    def _on_new(self) -> None:
        self._selected_id = ""
        self._navn_var.set("")
        self._type_var.set(self._types[0] if self._types else "")
        self._omraade_var.set("")
        self._default_regnr_var.set("")
        self._current_workpaper_ids = []
        self._refresh_workpaper_list()
        self._beskr_txt.delete("1.0", "end")
        try:
            self._tree.selection_remove(self._tree.selection())
        except Exception:
            pass

    def _on_delete(self) -> None:
        if not self._selected_id:
            return
        item = next((a for a in self._items if a.id == self._selected_id), None)
        if item is None:
            return
        if not messagebox.askyesno("Slett handling", f"Slette «{item.navn}»?"):
            return
        action_library.delete_action(self._selected_id)
        self._selected_id = ""
        self._on_new()
        self._reload()
        if self._on_saved:
            self._on_saved()

    def _on_save(self) -> None:
        navn = self._navn_var.get().strip()
        if not navn:
            messagebox.showwarning("Mangler navn", "Navn er påkrevd.")
            return
        beskrivelse = self._beskr_txt.get("1.0", "end").strip()
        if self._selected_id:
            item = next((a for a in self._items if a.id == self._selected_id), None)
        else:
            item = None
        if item is None:
            item = LocalAction.new(navn)
        item.navn = navn
        item.type = self._type_var.get().strip()
        item.omraade = self._omraade_var.get().strip()
        item.default_regnr = self._default_regnr_var.get().strip()
        item.workpaper_ids = list(self._current_workpaper_ids)
        item.beskrivelse = beskrivelse
        action_library.upsert_action(item)
        self._selected_id = item.id
        self._reload()
        if self._on_saved:
            self._on_saved()

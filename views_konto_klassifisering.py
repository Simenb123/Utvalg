"""views_konto_klassifisering.py — Editor-dialog for konto-subklassifisering.

Åpnes fra Analyse-fanen. Viser alle kontoer som finnes i gjeldende datasett,
lar brukeren tildele hver konto en gruppe via kombobox eller fritekst.
Lagrer automatisk per klient via konto_klassifisering.py.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import konto_klassifisering as _kk

# ---------------------------------------------------------------------------
# Offentlig API
# ---------------------------------------------------------------------------

def open_klassifisering_editor(
    master: Any,
    *,
    client: str,
    kontoer: list[tuple[str, str]],  # [(konto, kontonavn), ...]
    on_save: Any = None,             # callback() etter lagring
) -> None:
    """Åpne klassifiserings-editoren som en toplevl-dialog."""
    if tk is None:
        return

    mapping = _kk.load(client)
    dlg = _KlassifiseringsEditor(master, client=client, kontoer=kontoer,
                                  mapping=mapping, on_save=on_save)
    dlg.grab_set()
    master.wait_window(dlg)


# ---------------------------------------------------------------------------
# Dialog-klassen
# ---------------------------------------------------------------------------

class _KlassifiseringsEditor(tk.Toplevel):  # type: ignore[misc]

    def __init__(
        self,
        master: Any,
        *,
        client: str,
        kontoer: list[tuple[str, str]],
        mapping: dict[str, str],
        on_save: Any,
    ) -> None:
        super().__init__(master)
        self._client  = client
        self._kontoer = kontoer        # alle tilgjengelige kontoer
        self._mapping = dict(mapping)  # arbeidskopi
        self._on_save = on_save
        self._filter_var  = tk.StringVar()
        self._group_filter_var = tk.StringVar(value="(alle)")
        self._row_vars: dict[str, tk.StringVar] = {}  # konto → StringVar

        self.title(f"Kontoklassifisering — {client}")
        self.geometry("860x600")
        self.resizable(True, True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Toolbar
        tb = ttk.Frame(self, padding=(6, 4))
        tb.grid(row=0, column=0, sticky="ew")
        tb.columnconfigure(2, weight=1)

        ttk.Label(tb, text="Søk konto/navn:").grid(row=0, column=0, padx=(0, 4))
        search_entry = ttk.Entry(tb, textvariable=self._filter_var, width=22)
        search_entry.grid(row=0, column=1, padx=(0, 10))
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())

        ttk.Label(tb, text="Vis gruppe:").grid(row=0, column=2, sticky="e", padx=(0, 4))
        self._group_cb = ttk.Combobox(tb, textvariable=self._group_filter_var,
                                       state="readonly", width=28)
        self._group_cb.grid(row=0, column=3, padx=(0, 10))
        self._group_cb.bind("<<ComboboxSelected>>", lambda _e: self._apply_filter())

        ttk.Button(tb, text="Nullstill filter", width=14,
                   command=self._clear_filter).grid(row=0, column=4, padx=(0, 10))
        ttk.Button(tb, text="Fjern alle grupper",
                   command=self._clear_all_groups).grid(row=0, column=5, padx=(0, 4))

        # Main pane: left = konto-liste, right = gruppevalg-panel
        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        # Left: scrollable treeview with konto, kontonavn, gruppe
        left = ttk.Frame(pane)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        pane.add(left, weight=3)

        cols = ("konto", "kontonavn", "gruppe")
        self._tree = ttk.Treeview(left, columns=cols, show="headings",
                                   selectmode="extended")
        self._tree.heading("konto",     text="Konto",    anchor="w")
        self._tree.heading("kontonavn", text="Navn",      anchor="w")
        self._tree.heading("gruppe",    text="Gruppe",    anchor="w")
        self._tree.column("konto",     width=90,  anchor="w", stretch=False)
        self._tree.column("kontonavn", width=260, anchor="w", stretch=True)
        self._tree.column("gruppe",    width=200, anchor="w", stretch=False)
        self._tree.tag_configure("assigned", foreground="#1A56A0")
        self._tree.tag_configure("unassigned", foreground="#888888")

        vsb = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Right: gruppe-velger panel
        right = ttk.Frame(pane, padding=(8, 4))
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)
        pane.add(right, weight=1)

        ttk.Label(right, text="Tildel gruppe til valgte kontoer:",
                  font=("TkDefaultFont", 10, "bold")).grid(
                      row=0, column=0, sticky="w", pady=(0, 6))

        # Combo for existing + new group
        self._assign_var = tk.StringVar()
        self._assign_cb = ttk.Combobox(right, textvariable=self._assign_var,
                                        width=28)
        self._assign_cb.grid(row=1, column=0, sticky="ew", pady=(0, 4))

        ttk.Button(right, text="Tildel gruppe ▶",
                   command=self._assign_group).grid(
                       row=2, column=0, sticky="new", pady=(0, 6))

        ttk.Separator(right, orient="horizontal").grid(
            row=3, column=0, sticky="ew", pady=8)

        ttk.Button(right, text="Fjern gruppe (valgte)",
                   command=self._remove_group).grid(
                       row=4, column=0, sticky="new", pady=(0, 4))

        ttk.Separator(right, orient="horizontal").grid(
            row=5, column=0, sticky="ew", pady=8)

        # Summary: grupper i bruk
        ttk.Label(right, text="Grupper i bruk:",
                  font=("TkDefaultFont", 9, "bold")).grid(
                      row=6, column=0, sticky="w", pady=(0, 4))
        self._summary_text = tk.Text(right, width=30, height=14,
                                      state="disabled", relief="flat",
                                      bg="#F4F6F9", font=("TkDefaultFont", 9))
        self._summary_text.grid(row=7, column=0, sticky="nsew")
        right.rowconfigure(7, weight=1)

        # Bottom bar
        bot = ttk.Frame(self, padding=(6, 4))
        bot.grid(row=2, column=0, sticky="ew")

        self._status_lbl = ttk.Label(bot, text="", foreground="#555")
        self._status_lbl.pack(side="left")

        ttk.Button(bot, text="Lukk", command=self.destroy,
                   width=10).pack(side="right", padx=(4, 0))
        ttk.Button(bot, text="Lagre", command=self._save,
                   width=10).pack(side="right")

    # ------------------------------------------------------------------
    # Populate
    # ------------------------------------------------------------------

    def _populate(self) -> None:
        self._refresh_tree(self._kontoer)
        self._refresh_combos()
        self._refresh_summary()

    def _refresh_tree(self, kontoer: list[tuple[str, str]]) -> None:
        self._tree.delete(*self._tree.get_children())
        for konto, navn in kontoer:
            gruppe = self._mapping.get(konto, "")
            tag = "assigned" if gruppe else "unassigned"
            self._tree.insert("", "end", iid=konto,
                               values=(konto, navn, gruppe), tags=(tag,))

    def _refresh_combos(self) -> None:
        all_groups = sorted(set(_kk.DEFAULT_GROUPS) |
                             set(self._mapping.values()) - {""})
        self._assign_cb["values"] = all_groups
        self._group_cb["values"] = ["(alle)", "(uten gruppe)"] + all_groups

    def _refresh_summary(self) -> None:
        groups = _kk.all_groups_in_use(self._mapping)
        lines = []
        for g in groups:
            count = len(_kk.kontoer_for_group(self._mapping, g))
            lines.append(f"{g}  ({count})")
        txt = "\n".join(lines) if lines else "(ingen klassifisering)"
        try:
            self._summary_text.configure(state="normal")
            self._summary_text.delete("1.0", "end")
            self._summary_text.insert("end", txt)
            self._summary_text.configure(state="disabled")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Filter
    # ------------------------------------------------------------------

    def _apply_filter(self) -> None:
        q = self._filter_var.get().strip().lower()
        gf = self._group_filter_var.get()

        result = []
        for konto, navn in self._kontoer:
            if q and q not in konto.lower() and q not in navn.lower():
                continue
            gruppe = self._mapping.get(konto, "")
            if gf == "(uten gruppe)" and gruppe:
                continue
            if gf not in ("(alle)", "(uten gruppe)") and gruppe != gf:
                continue
            result.append((konto, navn))

        self._refresh_tree(result)

    def _clear_filter(self) -> None:
        self._filter_var.set("")
        self._group_filter_var.set("(alle)")
        self._apply_filter()

    # ------------------------------------------------------------------
    # Edit actions
    # ------------------------------------------------------------------

    def _on_tree_select(self, _event: Any = None) -> None:
        sel = self._tree.selection()
        count = len(sel)
        self._status_lbl.configure(
            text=f"{count} konto{'er' if count != 1 else ''} valgt"
        )

    def _assign_group(self) -> None:
        gruppe = self._assign_var.get().strip()
        if not gruppe:
            return
        sel = self._tree.selection()
        if not sel:
            return
        for konto in sel:
            self._mapping[konto] = gruppe
            try:
                self._tree.set(konto, "gruppe", gruppe)
                self._tree.item(konto, tags=("assigned",))
            except Exception:
                pass
        self._refresh_combos()
        self._refresh_summary()
        self._status_lbl.configure(
            text=f"Tildelte «{gruppe}» til {len(sel)} kontoer"
        )

    def _remove_group(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        for konto in sel:
            self._mapping.pop(konto, None)
            try:
                self._tree.set(konto, "gruppe", "")
                self._tree.item(konto, tags=("unassigned",))
            except Exception:
                pass
        self._refresh_summary()
        self._status_lbl.configure(
            text=f"Fjernet gruppe fra {len(sel)} kontoer"
        )

    def _clear_all_groups(self) -> None:
        self._mapping.clear()
        self._refresh_tree(self._kontoer)
        self._refresh_summary()
        self._status_lbl.configure(text="Alle grupper fjernet")

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save(self) -> None:
        _kk.save(self._client, self._mapping)
        self._status_lbl.configure(text="Lagret.")
        if callable(self._on_save):
            try:
                self._on_save()
            except Exception:
                pass

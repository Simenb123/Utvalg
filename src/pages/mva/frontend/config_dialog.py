"""MVA-oppsett-dialog: regnskapssystem og MVA-kode-mapping per klient.

Denne dialogen lar brukeren:
1. Velge regnskapssystem (Tripletex, PowerOffice, etc.)
2. Se/redigere MVA-kode-mapping (klientens kode → SAF-T standard)
3. Tilbakestille til systemets standard-mapping
4. Importere koder fra en SAF-T-fil (TaxTable)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore
    filedialog = None  # type: ignore

from ..backend import codes as mva_codes
from ..backend import system_defaults as mva_system_defaults
import regnskap_client_overrides


@dataclass
class _DialogState:
    saved: bool = False
    system: str = ""
    mapping: dict[str, str] = field(default_factory=dict)


def open_mva_config(
    parent: tk.Misc,
    client: str,
) -> bool:
    """Åpne MVA-oppsett-dialog for en klient.

    Returnerer True hvis brukeren lagret endringer.
    """
    if not client:
        if messagebox is not None:
            messagebox.showwarning("MVA-oppsett", "Ingen klient er valgt.")
        return False

    # Last eksisterende data
    current_system = regnskap_client_overrides.load_accounting_system(client)
    current_mapping = regnskap_client_overrides.load_mva_code_mapping(client)

    # Hvis ingen mapping finnes, last defaults for valgt system (eller identitet)
    if not current_mapping and current_system:
        current_mapping = mva_system_defaults.get_default_mapping(current_system)

    state = _DialogState(system=current_system, mapping=dict(current_mapping))

    win = tk.Toplevel(parent)
    win.title(f"MVA-oppsett: {client}")
    win.transient(parent)
    win.grab_set()
    win.resizable(True, True)
    win.geometry("780x520")

    outer = ttk.Frame(win, padding=10)
    outer.pack(fill="both", expand=True)

    # ---- Regnskapssystem ----
    sys_frame = ttk.LabelFrame(outer, text="Regnskapssystem", padding=8)
    sys_frame.pack(fill="x", pady=(0, 8))

    sys_var = tk.StringVar(value=current_system)
    ttk.Label(sys_frame, text="System:").grid(row=0, column=0, sticky="w", padx=(0, 8))
    cmb_system = ttk.Combobox(
        sys_frame,
        textvariable=sys_var,
        values=mva_codes.ACCOUNTING_SYSTEMS,
        width=28,
        state="readonly",
    )
    cmb_system.grid(row=0, column=1, sticky="w")

    # ---- MVA-kode-mapping ----
    map_frame = ttk.LabelFrame(outer, text="MVA-kode mapping", padding=8)
    map_frame.pack(fill="both", expand=True, pady=(0, 8))

    cols = ("client_code", "saft_code", "description", "rate")
    tree = ttk.Treeview(map_frame, columns=cols, show="headings", selectmode="browse", height=14)
    tree.heading("client_code", text="Klientens kode")
    tree.heading("saft_code", text="SAF-T standard")
    tree.heading("description", text="Beskrivelse")
    tree.heading("rate", text="Sats")

    tree.column("client_code", width=110, anchor="center")
    tree.column("saft_code", width=100, anchor="center")
    tree.column("description", width=340, anchor="w")
    tree.column("rate", width=70, anchor="center")

    vsb = ttk.Scrollbar(map_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    # ---- Hjelpefunksjoner ----

    def _populate_tree(mapping: dict[str, str]) -> None:
        for item in tree.get_children():
            tree.delete(item)

        for client_code in sorted(mapping.keys(), key=lambda c: (c.isdigit(), int(c) if c.isdigit() else 0, c)):
            saft_code = mapping[client_code]
            info = mva_codes.get_code_info(saft_code)
            desc = info["description"] if info else ""
            rate = f"{info['rate']:.0f} %" if info else ""
            tree.insert("", "end", values=(client_code, saft_code, desc, rate))

    def _read_tree_mapping() -> dict[str, str]:
        result: dict[str, str] = {}
        for item in tree.get_children():
            vals = tree.item(item, "values")
            if len(vals) >= 2:
                client_code = str(vals[0]).strip()
                saft_code = str(vals[1]).strip()
                if client_code and saft_code:
                    result[client_code] = saft_code
        return result

    _populate_tree(current_mapping)

    # ---- Inline-redigering: dobbeltklikk på SAF-T-kode ----

    _edit_widget: list = []  # holder referanse til aktiv editor

    def _on_double_click(event) -> None:
        # Fjern evt. eksisterende editor
        for w in _edit_widget:
            w.destroy()
        _edit_widget.clear()

        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        col = tree.identify_column(event.x)
        item = tree.identify_row(event.y)
        if not item:
            return

        col_idx = int(col.replace("#", "")) - 1

        if col_idx == 0:
            # Redigere klientens kode
            _edit_cell_entry(item, col_idx, col)
        elif col_idx == 1:
            # Redigere SAF-T standard-kode med combobox
            _edit_cell_combobox(item, col_idx, col)

    def _edit_cell_entry(item: str, col_idx: int, col: str) -> None:
        bbox = tree.bbox(item, col)
        if not bbox:
            return
        x, y, w, h = bbox

        current_val = str(tree.item(item, "values")[col_idx])
        var = tk.StringVar(value=current_val)
        entry = ttk.Entry(tree, textvariable=var, width=12)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()
        entry.select_range(0, "end")
        _edit_widget.append(entry)

        def _commit(_event=None):
            new_val = var.get().strip()
            if new_val:
                vals = list(tree.item(item, "values"))
                vals[col_idx] = new_val
                tree.item(item, values=vals)
            entry.destroy()
            _edit_widget.clear()

        entry.bind("<Return>", _commit)
        entry.bind("<FocusOut>", _commit)
        entry.bind("<Escape>", lambda _: (entry.destroy(), _edit_widget.clear()))

    def _edit_cell_combobox(item: str, col_idx: int, col: str) -> None:
        bbox = tree.bbox(item, col)
        if not bbox:
            return
        x, y, w, h = bbox

        current_val = str(tree.item(item, "values")[col_idx])
        var = tk.StringVar(value=current_val)

        choices = [c["code"] for c in mva_codes.STANDARD_MVA_CODES]
        cmb = ttk.Combobox(tree, textvariable=var, values=choices, state="readonly", width=8)
        cmb.place(x=x, y=y, width=w, height=h)
        cmb.focus_set()
        _edit_widget.append(cmb)

        def _commit(_event=None):
            new_code = var.get().strip()
            if new_code:
                info = mva_codes.get_code_info(new_code)
                desc = info["description"] if info else ""
                rate = f"{info['rate']:.0f} %" if info else ""
                vals = list(tree.item(item, "values"))
                vals[1] = new_code
                vals[2] = desc
                vals[3] = rate
                tree.item(item, values=vals)
            cmb.destroy()
            _edit_widget.clear()

        cmb.bind("<<ComboboxSelected>>", _commit)
        cmb.bind("<FocusOut>", _commit)
        cmb.bind("<Escape>", lambda _: (cmb.destroy(), _edit_widget.clear()))

    tree.bind("<Double-1>", _on_double_click)

    # ---- Knapper under tabell ----
    btn_frame = ttk.Frame(outer)
    btn_frame.pack(fill="x", pady=(0, 8))

    def _add_row():
        tree.insert("", "end", values=("", "", "", ""))
        children = tree.get_children()
        if children:
            tree.selection_set(children[-1])
            tree.focus(children[-1])

    def _remove_row():
        sel = tree.selection()
        if sel:
            tree.delete(sel[0])

    def _reset_defaults():
        system = sys_var.get().strip()
        if not system:
            if messagebox is not None:
                messagebox.showinfo("MVA-oppsett", "Velg et regnskapssystem først.")
            return
        defaults = mva_system_defaults.get_default_mapping(system)
        _populate_tree(defaults)

    def _import_saft():
        try:
            import saft_tax_table
        except ImportError:
            if messagebox is not None:
                messagebox.showerror("MVA-oppsett", "saft_tax_table-modulen er ikke tilgjengelig.")
            return

        path = filedialog.askopenfilename(
            parent=win,
            title="Velg SAF-T-fil",
            filetypes=[
                ("SAF-T-filer", "*.xml *.zip"),
                ("Alle filer", "*.*"),
            ],
        )
        if not path:
            return

        try:
            entries = saft_tax_table.extract_tax_table(path)
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror("MVA-oppsett", f"Kunne ikke lese TaxTable:\n{exc}")
            return

        if not entries:
            if messagebox is not None:
                messagebox.showinfo("MVA-oppsett", "Ingen TaxTable funnet i SAF-T-filen.")
            return

        # Bygg mapping fra importerte entries
        imported: dict[str, str] = {}
        for e in entries:
            if e.standard_code:
                imported[e.code] = e.standard_code
            else:
                imported[e.code] = e.code  # bruker koden som er, bruker kan justere

        # Merg med eksisterende mapping (import overskriver duplikater)
        existing = _read_tree_mapping()
        existing.update(imported)
        _populate_tree(existing)

        if messagebox is not None:
            n_mapped = sum(1 for e in entries if e.standard_code)
            n_total = len(entries)
            messagebox.showinfo(
                "MVA-oppsett",
                f"Importerte {n_total} MVA-koder fra SAF-T.\n"
                f"{n_mapped} hadde StandardTaxCode, {n_total - n_mapped} trenger manuell mapping.",
            )

    ttk.Button(btn_frame, text="Legg til", command=_add_row).pack(side="left", padx=(0, 4))
    ttk.Button(btn_frame, text="Fjern", command=_remove_row).pack(side="left", padx=(0, 4))
    ttk.Button(btn_frame, text="Tilbakestill til std.", command=_reset_defaults).pack(side="left", padx=(0, 4))
    ttk.Button(btn_frame, text="Importer fra SAF-T\u2026", command=_import_saft).pack(side="left")

    # ---- Bytte system → tilby tilbakestilling ----

    def _on_system_change(_event=None):
        system = sys_var.get().strip()
        if not system:
            return
        current = _read_tree_mapping()
        if current:
            if messagebox is not None:
                answer = messagebox.askyesno(
                    "MVA-oppsett",
                    f"Vil du tilbakestille MVA-kode-mapping til standard for {system}?",
                )
                if not answer:
                    return
        defaults = mva_system_defaults.get_default_mapping(system)
        _populate_tree(defaults)

    cmb_system.bind("<<ComboboxSelected>>", _on_system_change)

    # ---- Lagre / Avbryt ----
    bottom = ttk.Frame(outer)
    bottom.pack(fill="x")

    def _save():
        system = sys_var.get().strip()
        mapping = _read_tree_mapping()

        regnskap_client_overrides.save_accounting_system(client, system)
        regnskap_client_overrides.save_mva_code_mapping(client, mapping)

        state.saved = True
        win.destroy()

    def _cancel():
        win.destroy()

    ttk.Button(bottom, text="Lagre", command=_save, style="Primary.TButton").pack(side="right", padx=(4, 0))
    ttk.Button(bottom, text="Avbryt", command=_cancel).pack(side="right")

    win.wait_window()
    return state.saved

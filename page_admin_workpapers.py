"""Admin-underfane: Arbeidspapir-katalog."""

from __future__ import annotations

from typing import Callable

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

import src.shared.workpapers.library as workpaper_library
from src.shared.workpapers.library import DEFAULT_KATEGORIER, Workpaper


class _WorkpaperLibraryEditor(ttk.Frame):  # type: ignore[misc]
    def __init__(
        self,
        master,
        *,
        title: str = "Arbeidspapir",
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._title = title
        self._on_saved = on_saved
        self._items: list[Workpaper] = []
        self._builtins: list[Workpaper] = []
        self._selected_id: str = ""

        self._status_var = tk.StringVar(value="")
        self._navn_var = tk.StringVar()
        self._kategori_var = tk.StringVar(value="manuell")
        self._generator_var = tk.StringVar()
        self._mal_var = tk.StringVar()

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        self._build_ui()
        self.after(0, self._reload)

    def _build_ui(self) -> None:
        top = ttk.Frame(self)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        top.columnconfigure(0, weight=1)
        ttk.Label(
            top,
            text="Arbeidspapir-katalog — katalog over arbeidspapir som kan kobles til handlinger.",
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

        cols = ("navn", "kategori", "generator")
        self._tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("navn", text="Navn")
        self._tree.heading("kategori", text="Kategori")
        self._tree.heading("generator", text="Generator")
        self._tree.column("navn", width=220, minwidth=140)
        self._tree.column("kategori", width=80, minwidth=60)
        self._tree.column("generator", width=160, minwidth=100)
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

        ttk.Label(right, text="Kategori:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Combobox(
            right, textvariable=self._kategori_var, values=list(DEFAULT_KATEGORIER),
            state="readonly", width=18,
        ).grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        ttk.Label(right, text="Generator-id:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self._generator_var).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        ttk.Label(right, text="Mal/referanse:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(right, textvariable=self._mal_var).grid(row=row, column=1, sticky="ew", pady=2)
        row += 1

        ttk.Label(right, text="Beskrivelse:").grid(row=row, column=0, sticky="nw", pady=2)
        self._beskr_txt = tk.Text(right, height=8, wrap="word")
        self._beskr_txt.grid(row=row, column=1, sticky="nsew", pady=2)
        right.rowconfigure(row, weight=1)

        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6)
        )

    # ------------------------------------------------------------------

    def _reload(self) -> None:
        self._items = workpaper_library.load_library()
        self._builtins = workpaper_library.list_builtins()
        self._refresh_tree()
        self._status_var.set(
            f"{len(self._builtins)} innebygd + {len(self._items)} manuell i {workpaper_library.library_path()}"
        )

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())
        try:
            self._tree.tag_configure("builtin", foreground="#6b7280")
        except Exception:
            pass
        for w in sorted(self._builtins, key=lambda x: x.navn.lower()):
            self._tree.insert(
                "", "end", iid=w.id,
                values=(f"\U0001f512 {w.navn}", "innebygd", w.generator_id or "\u2013"),
                tags=("builtin",),
            )
        for w in sorted(self._items, key=lambda x: (x.kategori.lower(), x.navn.lower())):
            self._tree.insert(
                "", "end", iid=w.id,
                values=(w.navn, w.kategori, w.generator_id or "\u2013"),
            )
        if self._selected_id and self._tree.exists(self._selected_id):
            self._tree.selection_set(self._selected_id)

    def _on_select(self, _evt=None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        self._selected_id = sel[0]
        if workpaper_library.is_builtin(self._selected_id):
            item = next((w for w in self._builtins if w.id == self._selected_id), None)
        else:
            item = next((w for w in self._items if w.id == self._selected_id), None)
        if item is None:
            return
        self._navn_var.set(item.navn)
        self._kategori_var.set(item.kategori)
        self._generator_var.set(item.generator_id)
        self._mal_var.set(item.mal)
        self._beskr_txt.delete("1.0", "end")
        self._beskr_txt.insert("1.0", item.beskrivelse)

    def _on_new(self) -> None:
        self._selected_id = ""
        self._navn_var.set("")
        self._kategori_var.set("manuell")
        self._generator_var.set("")
        self._mal_var.set("")
        self._beskr_txt.delete("1.0", "end")
        try:
            self._tree.selection_remove(self._tree.selection())
        except Exception:
            pass

    def _on_delete(self) -> None:
        if not self._selected_id:
            return
        if workpaper_library.is_builtin(self._selected_id):
            messagebox.showinfo(
                "Innebygd arbeidspapir",
                "Innebygde arbeidspapir kan ikke slettes.",
                parent=self,
            )
            return
        item = next((w for w in self._items if w.id == self._selected_id), None)
        if item is None:
            return
        if not messagebox.askyesno("Slett arbeidspapir", f"Slette «{item.navn}»?"):
            return
        workpaper_library.delete_workpaper(self._selected_id)
        self._selected_id = ""
        self._on_new()
        self._reload()
        if self._on_saved:
            self._on_saved()

    def _on_save(self) -> None:
        if workpaper_library.is_builtin(self._selected_id):
            messagebox.showinfo(
                "Innebygd arbeidspapir",
                "Innebygde arbeidspapir kan ikke redigeres. Opprett et manuelt arbeidspapir i stedet.",
                parent=self,
            )
            return
        navn = self._navn_var.get().strip()
        if not navn:
            messagebox.showwarning("Mangler navn", "Navn er påkrevd.")
            return
        beskrivelse = self._beskr_txt.get("1.0", "end").strip()
        if self._selected_id:
            item = next((w for w in self._items if w.id == self._selected_id), None)
        else:
            item = None
        if item is None:
            item = Workpaper.new(navn)
        item.navn = navn
        item.kategori = self._kategori_var.get().strip() or "manuell"
        item.generator_id = self._generator_var.get().strip()
        item.mal = self._mal_var.get().strip()
        item.beskrivelse = beskrivelse
        workpaper_library.upsert_workpaper(item)
        self._selected_id = item.id
        self._reload()
        if self._on_saved:
            self._on_saved()

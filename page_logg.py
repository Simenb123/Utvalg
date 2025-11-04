from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog
from logger import get_buffer, clear_buffer

class LoggPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook):
        super().__init__(parent)
        bar = ttk.Frame(self, padding=6); bar.pack(fill=tk.X)
        ttk.Button(bar, text="Oppdater", command=self.refresh).pack(side=tk.RIGHT, padx=(4,0))
        ttk.Button(bar, text="Tøm logg", command=lambda: (clear_buffer(), self.refresh())).pack(side=tk.RIGHT, padx=(4,0))
        ttk.Button(bar, text="Lagre til fil…", command=self._save).pack(side=tk.RIGHT)
        self.var_auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Auto-oppdater", variable=self.var_auto, command=self._toggle_auto).pack(side=tk.LEFT)

        cols = ("tid","nivå","kilde","melding")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols: self.tree.heading(c, text=c.capitalize())
        self.tree.column("tid", width=160, anchor="w")
        self.tree.column("nivå", width=70, anchor="w")
        self.tree.column("kilde", width=160, anchor="w")
        self.tree.column("melding", width=780, anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0,6))

        self._auto_job = None
        self.refresh(); self._toggle_auto()

    def _toggle_auto(self):
        if self._auto_job is not None:
            self.after_cancel(self._auto_job); self._auto_job = None
        if self.var_auto.get():
            self._auto_job = self.after(1000, self._tick)

    def _tick(self):
        self.refresh(); self._auto_job = self.after(1000, self._tick)

    def refresh(self):
        for iid in self.tree.get_children(): self.tree.delete(iid)
        for entry in get_buffer():
            self.tree.insert("", tk.END, values=(entry["time"], entry["level"], entry["name"], entry["message"]))

    def _save(self):
        path = filedialog.asksaveasfilename(title="Lagre logg", defaultextension=".log", filetypes=[("Logg", "*.log"), ("Tekst", "*.txt")])
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            for e in get_buffer():
                f.write(f'{e["time"]} [{e["level"]}] {e["name"]}: {e["message"]}\n')

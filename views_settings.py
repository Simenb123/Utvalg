# views_settings.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from preferences import Preferences, load_preferences, save_preferences
import formatting  # for refresh_from_prefs()

class SettingsView:
    def __init__(self, parent: tk.Tk | tk.Toplevel):
        self.win = tk.Toplevel(parent)
        self.win.title("Innstillinger")
        self.win.geometry("620x340")

        self.p = load_preferences()

        frm = ttk.Frame(self.win, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        # --- Hovedvisning ---
        grp = ttk.LabelFrame(frm, text="Hovedvisning", padding=8)
        grp.pack(fill=tk.X)
        ttk.Label(grp, text="Standard retning:").grid(row=0, column=0, sticky="w")
        self.cbo_dir = ttk.Combobox(grp, state="readonly", values=["Alle","Debet","Kredit"], width=10)
        self.cbo_dir.set(self.p.default_direction or "Alle")
        self.cbo_dir.grid(row=0, column=1, sticky="w", padx=(6,0))

        # --- Eksport ---
        exp = ttk.LabelFrame(frm, text="Eksport", padding=8)
        exp.pack(fill=tk.X, pady=(12,0))
        self.var_export = tk.StringVar(value=self.p.export_mode or "open_now")
        ttk.Radiobutton(exp, text="Åpne i Excel nå (midlertidig fil)", value="open_now", variable=self.var_export).pack(anchor="w")
        ttk.Radiobutton(exp, text="Spør om lagringsmappe (Lagre som …)", value="save_dialog", variable=self.var_export).pack(anchor="w")

        # --- Formater ---
        fmt = ttk.LabelFrame(frm, text="Formater", padding=8)
        fmt.pack(fill=tk.X, pady=(12,0))

        ttk.Label(fmt, text="Tusen‑separator:").grid(row=0, column=0, sticky="w")
        self.cbo_th = ttk.Combobox(fmt, state="readonly", width=18, values=[
            "Mellomrom", "Punktum", "Tynt mellomrom", "Ingen",
        ])
        m = {" ": "Mellomrom", ".":"Punktum", "\u202f":"Tynt mellomrom", "":"Ingen"}
        rmap = {v:k for k,v in m.items()}
        self.cbo_th.set(m.get(self.p.thousands_sep, "Mellomrom"))

        ttk.Label(fmt, text="Desimal‑separator:").grid(row=0, column=2, sticky="w", padx=(16,0))
        self.cbo_dec = ttk.Combobox(fmt, state="readonly", width=8, values=[",", "."])
        self.cbo_dec.set(self.p.decimal_sep or ",")

        ttk.Label(fmt, text="Datoformat (strftime):").grid(row=1, column=0, sticky="w", pady=(8,0))
        self.ent_date = ttk.Entry(fmt, width=22)
        self.ent_date.insert(0, self.p.date_fmt or "%d.%m.%Y")
        self.ent_date.grid(row=1, column=1, sticky="w", pady=(8,0))

        btn = ttk.Frame(frm); btn.pack(fill=tk.X, pady=(16,0))
        ttk.Button(btn, text="Lagre", command=lambda: self._save(rmap)).pack(side=tk.RIGHT)
        ttk.Button(btn, text="Avbryt", command=self.win.destroy).pack(side=tk.RIGHT, padx=(0,8))

    def _save(self, rmap):
        p = self.p
        p.default_direction = self.cbo_dir.get()
        p.export_mode = self.var_export.get()
        p.thousands_sep = rmap.get(self.cbo_th.get(), " ")
        p.decimal_sep = self.cbo_dec.get()
        p.date_fmt = self.ent_date.get().strip() or "%d.%m.%Y"
        save_preferences(p)

        # Refresher format globalt
        formatting.refresh_from_prefs()

        messagebox.showinfo("Lagret", "Innstillinger er lagret.")
        try: self.win.destroy()
        except Exception: pass

def open_settings(parent: tk.Tk | tk.Toplevel):
    SettingsView(parent)

# views_settings.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import app_paths
import client_store
import formatting  # for refresh_from_prefs()

# preferences.py (eldre kode) eksponerer load()/save().
# I nyere endringer ønsket vi mer eksplisitte navn (load_preferences/save_preferences).
# For bakoverkompatibilitet støtter vi begge.
try:
    from preferences import load_preferences, save_preferences  # type: ignore
except Exception:  # pragma: no cover
    from preferences import load as load_preferences, save as save_preferences


def _pref_get(prefs, key: str, default=None):
    """Read preference value safely.

    preferences.py stores preferences as a plain dict. Some UI code previously
    used attribute access; this helper keeps the settings dialog compatible
    regardless of representation.
    """

    try:
        if isinstance(prefs, dict):
            return prefs.get(key, default)
        return getattr(prefs, key, default)
    except Exception:
        return default


def _pref_set(prefs, key: str, value) -> None:
    """Set preference value safely."""

    if isinstance(prefs, dict):
        prefs[key] = value
        return
    try:
        setattr(prefs, key, value)
    except Exception:
        pass


class SettingsView:
    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        *,
        on_data_dir_changed: Optional[Callable[[], None]] = None,
        on_clients_changed: Optional[Callable[[], None]] = None,
    ):
        self._on_data_dir_changed = on_data_dir_changed
        self._on_clients_changed = on_clients_changed

        self.win = tk.Toplevel(parent)
        self.win.title("Innstillinger")
        self.win.geometry("720x520")

        self.p = load_preferences() or {}

        frm = ttk.Frame(self.win, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)

        # --- Datamappe + klienter ---
        store = ttk.LabelFrame(frm, text="Datamappe og klienter", padding=8)
        store.pack(fill=tk.X)
        store.columnconfigure(1, weight=1)

        self.var_datadir = tk.StringVar(value=str(app_paths.data_dir()))

        ttk.Label(store, text="Datamappe:").grid(row=0, column=0, sticky="w")
        ent_dir = ttk.Entry(store, textvariable=self.var_datadir, state="readonly")
        ent_dir.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(store, text="Velg…", command=self._pick_data_dir).grid(row=0, column=2, sticky="e")

        self.lbl_clients = ttk.Label(store, text="")
        self.lbl_clients.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        btns = ttk.Frame(store)
        btns.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Opprett klient…", command=self._create_client).pack(side=tk.LEFT)
        ttk.Button(btns, text="Importer klientliste…", command=self._import_client_list).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(btns, text="Bygg indeks på nytt", command=self._rebuild_client_index).pack(side=tk.LEFT, padx=(8, 0))

        self._refresh_store_info()

        # --- Hovedvisning ---
        grp = ttk.LabelFrame(frm, text="Hovedvisning", padding=8)
        grp.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(grp, text="Standard retning:").grid(row=0, column=0, sticky="w")
        self.cbo_dir = ttk.Combobox(grp, state="readonly", values=["Alle", "Debet", "Kredit"], width=10)
        cur_dir = str(_pref_get(self.p, "default_direction", "Alle") or "Alle")
        if cur_dir not in ("Alle", "Debet", "Kredit"):
            cur_dir = "Alle"
        self.cbo_dir.set(cur_dir)
        self.cbo_dir.grid(row=0, column=1, sticky="w", padx=(6, 0))

        # --- Eksport ---
        exp = ttk.LabelFrame(frm, text="Eksport", padding=8)
        exp.pack(fill=tk.X, pady=(12, 0))
        self.var_export = tk.StringVar(value=str(_pref_get(self.p, "export_mode", "open_now") or "open_now"))
        ttk.Radiobutton(
            exp,
            text="Åpne i Excel nå (midlertidig fil)",
            value="open_now",
            variable=self.var_export,
        ).pack(anchor="w")
        ttk.Radiobutton(
            exp,
            text="Spør om lagringsmappe (Lagre som …)",
            value="save_dialog",
            variable=self.var_export,
        ).pack(anchor="w")

        # --- Formater ---
        fmt = ttk.LabelFrame(frm, text="Formater", padding=8)
        fmt.pack(fill=tk.X, pady=(12, 0))

        ttk.Label(fmt, text="Tusen‑separator:").grid(row=0, column=0, sticky="w")
        self.cbo_th = ttk.Combobox(
            fmt,
            state="readonly",
            width=18,
            values=[
                "Mellomrom",
                "Punktum",
                "Tynt mellomrom",
                "Ingen",
            ],
        )
        m = {" ": "Mellomrom", ".": "Punktum", "\u202f": "Tynt mellomrom", "": "Ingen"}
        rmap = {v: k for k, v in m.items()}
        self._thousands_revmap = rmap
        self.cbo_th.set(m.get(str(_pref_get(self.p, "thousands_sep", " ") or " "), "Mellomrom"))
        self.cbo_th.grid(row=0, column=1, sticky="w", padx=(6, 0))

        ttk.Label(fmt, text="Desimal‑separator:").grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.cbo_dec = ttk.Combobox(fmt, state="readonly", width=8, values=[",", "."])
        self.cbo_dec.set(str(_pref_get(self.p, "decimal_sep", ",") or ","))
        self.cbo_dec.grid(row=0, column=3, sticky="w", padx=(6, 0))

        ttk.Label(fmt, text="Datoformat (strftime):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.ent_date = ttk.Entry(fmt, width=22)
        self.ent_date.insert(0, str(_pref_get(self.p, "date_fmt", "%d.%m.%Y") or "%d.%m.%Y"))
        self.ent_date.grid(row=1, column=1, sticky="w", pady=(8, 0))

        btn = ttk.Frame(frm)
        btn.pack(fill=tk.X, pady=(16, 0))
        ttk.Button(btn, text="Lagre", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(btn, text="Avbryt", command=self.win.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    # ------------------ Datamappe / klienter ------------------

    def _refresh_store_info(self) -> None:
        try:
            self.var_datadir.set(str(app_paths.data_dir()))
        except Exception:
            self.var_datadir.set("(ukjent)")

        try:
            n = len(client_store.list_clients())
            self.lbl_clients.configure(text=f"Klienter: {n}")
        except Exception:
            self.lbl_clients.configure(text="Klienter: (ukjent)")

    def _pick_data_dir(self) -> None:
        cur = None
        try:
            cur = str(app_paths.data_dir())
        except Exception:
            cur = None

        chosen = filedialog.askdirectory(parent=self.win, initialdir=cur or os.getcwd(), title="Velg datamappe")
        if not chosen:
            return

        p = Path(chosen)
        try:
            app_paths.write_data_dir_hint(p)
        except Exception as e:
            messagebox.showerror("Datamappe", f"Kunne ikke lagre datamappe: {e}", parent=self.win)
            return

        # Bruk env i denne kjøringen for umiddelbar effekt.
        os.environ["UTVALG_DATA_DIR"] = str(p)

        try:
            client_store.refresh_client_cache()
        except Exception:
            pass

        self._refresh_store_info()
        if self._on_data_dir_changed:
            try:
                self._on_data_dir_changed()
            except Exception:
                pass

    def _create_client(self) -> None:
        name = simpledialog.askstring("Opprett klient", "Klientnavn:", parent=self.win)
        if not name:
            return

        name = name.strip()
        if not name:
            return

        try:
            client_store.ensure_client(name)
        except Exception as e:
            messagebox.showerror("Opprett klient", f"Kunne ikke opprette klient: {e}", parent=self.win)
            return

        self._refresh_store_info()
        if self._on_clients_changed:
            try:
                self._on_clients_changed()
            except Exception:
                pass

    def _import_client_list(self) -> None:
        fn = filedialog.askopenfilename(
            parent=self.win,
            title="Importer klientliste",
            filetypes=[
                ("Excel", "*.xlsx *.xls"),
                ("Alle filer", "*.*"),
            ],
        )
        if not fn:
            return

        try:
            from dataset_pane_store_import_ui import import_client_list_with_progress

            import_client_list_with_progress(self.win, Path(fn))
        except Exception as e:
            messagebox.showerror("Importer", f"Import feilet: {e}", parent=self.win)
            return

        self._refresh_store_info()
        if self._on_clients_changed:
            try:
                self._on_clients_changed()
            except Exception:
                pass

    def _rebuild_client_index(self) -> None:
        if not messagebox.askyesno(
            "Bygg indeks",
            "Dette vil bygge klientindeksen på nytt ved å skanne mappestrukturen.\n\nFortsette?",
            parent=self.win,
        ):
            return

        try:
            client_store.refresh_client_cache()
        except Exception as e:
            messagebox.showerror("Bygg indeks", f"Kunne ikke bygge indeks: {e}", parent=self.win)
            return

        self._refresh_store_info()
        if self._on_clients_changed:
            try:
                self._on_clients_changed()
            except Exception:
                pass

    # ------------------ Preferences ------------------

    def _save(self) -> None:
        p = self.p
        _pref_set(p, "default_direction", self.cbo_dir.get())
        _pref_set(p, "export_mode", self.var_export.get())
        _pref_set(p, "thousands_sep", self._thousands_revmap.get(self.cbo_th.get(), " "))
        _pref_set(p, "decimal_sep", self.cbo_dec.get())
        _pref_set(p, "date_fmt", self.ent_date.get().strip() or "%d.%m.%Y")
        save_preferences(p)

        # Refresher format globalt
        try:
            if hasattr(formatting, "refresh_from_prefs"):
                formatting.refresh_from_prefs()
        except Exception:
            pass

        messagebox.showinfo("Lagret", "Innstillinger er lagret.", parent=self.win)
        try:
            self.win.destroy()
        except Exception:
            pass


def open_settings(
    parent: tk.Tk | tk.Toplevel,
    *,
    on_data_dir_changed: Optional[Callable[[], None]] = None,
    on_clients_changed: Optional[Callable[[], None]] = None,
):
    SettingsView(parent, on_data_dir_changed=on_data_dir_changed, on_clients_changed=on_clients_changed)

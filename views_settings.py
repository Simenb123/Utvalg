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


def _fmt_cfg_meta(meta: dict) -> str:
    """Kort statuslinje for importert config."""

    if not meta:
        return "(ikke importert)"

    fn = str(meta.get("filename") or "")
    ts = str(meta.get("imported_at") or "")
    sha = str(meta.get("sha256") or "")
    sha_short = (sha[:10] + "…") if sha else ""

    bits = [b for b in [fn, ts, sha_short] if b]
    return " | ".join(bits) if bits else "(importert)"


def _fmt_active_source(source: str) -> str:
    """Visningsnavn for aktiv baseline-source."""

    mapping = {
        "json": "JSON",
        "excel": "Excel",
        "missing": "mangler",
    }
    return mapping.get(str(source or ""), "ukjent")


def format_active_baseline_label(kind_label: str, source: str) -> str:
    """Bygg 'Aktiv <kind>-baseline: …'-label for settings-UI."""

    return f"Aktiv {kind_label}-baseline: {_fmt_active_source(source)}"


def build_replace_baseline_confirm_text(kind_label: str) -> str:
    """Bekreftelsestekst for 'Importer og erstatt' — brukes før Excel overskriver JSON."""

    return (
        f"Dette vil erstatte gjeldende global {kind_label}-baseline i JSON med innholdet "
        "fra Excel.\n\nFortsette?"
    )

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

        # --- Regnskap (mapping) ---
        reg = ttk.LabelFrame(frm, text="Regnskap (mapping)", padding=8)
        reg.pack(fill=tk.X, pady=(12, 0))
        reg.columnconfigure(1, weight=1)

        ttk.Label(reg, text="Regnskapslinjer:").grid(row=0, column=0, sticky="w")
        self.lbl_regn = ttk.Label(reg, text="")
        self.lbl_regn.grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Button(reg, text="Importer og erstatt…", command=self._import_regnskapslinjer).grid(row=0, column=2, sticky="e")

        self.lbl_regn_src = ttk.Label(reg, text="")
        self.lbl_regn_src.grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

        ttk.Label(reg, text="Kontoplan-mapping:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.lbl_map = ttk.Label(reg, text="")
        self.lbl_map.grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(6, 0))
        ttk.Button(reg, text="Importer og erstatt…", command=self._import_kontoplan_mapping).grid(
            row=2, column=2, sticky="e", pady=(6, 0)
        )

        self.lbl_map_src = ttk.Label(reg, text="")
        self.lbl_map_src.grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 0))

        self._refresh_regnskap_info()

        # --- Aksjonærregister (global CSV-import) ---
        ar = ttk.LabelFrame(frm, text="Aksjonærregister (AR)", padding=8)
        ar.pack(fill=tk.X, pady=(12, 0))
        ar.columnconfigure(1, weight=1)

        ttk.Label(ar, text="Register-CSV:").grid(row=0, column=0, sticky="w")
        self.lbl_ar = ttk.Label(ar, text="")
        self.lbl_ar.grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Button(ar, text="Importer…", command=self._import_ar_registry_csv).grid(row=0, column=2, sticky="e")

        self._refresh_ar_info()

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
        self._refresh_regnskap_info()
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

    # ------------------ Regnskap-config ------------------

    def _refresh_regnskap_info(self) -> None:
        """Oppdater labels for regnskapslinjer + mapping."""

        # Labels finnes først etter at __init__ har bygget UI.
        if not hasattr(self, "lbl_regn"):
            return

        try:
            import regnskap_config

            st = regnskap_config.get_status()
            self.lbl_regn.configure(text=_fmt_cfg_meta(st.regnskapslinjer_meta))
            self.lbl_map.configure(text=_fmt_cfg_meta(st.kontoplan_mapping_meta))
            if hasattr(self, "lbl_regn_src"):
                self.lbl_regn_src.configure(
                    text=format_active_baseline_label(
                        "regnskapslinje", st.regnskapslinjer_active_source
                    )
                )
            if hasattr(self, "lbl_map_src"):
                self.lbl_map_src.configure(
                    text=format_active_baseline_label(
                        "kontoplan", st.kontoplan_mapping_active_source
                    )
                )
        except Exception:
            self.lbl_regn.configure(text="(ukjent)")
            self.lbl_map.configure(text="(ukjent)")
            if hasattr(self, "lbl_regn_src"):
                self.lbl_regn_src.configure(text="")
            if hasattr(self, "lbl_map_src"):
                self.lbl_map_src.configure(text="")

    def _import_regnskapslinjer(self) -> None:
        fn = filedialog.askopenfilename(
            parent=self.win,
            title="Importer Regnskapslinjer.xlsx",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Alle filer", "*.*")],
        )
        if not fn:
            return

        if not messagebox.askyesno(
            "Importer og erstatt",
            build_replace_baseline_confirm_text("regnskapslinje"),
            parent=self.win,
        ):
            return

        try:
            import regnskap_config

            regnskap_config.import_regnskapslinjer(Path(fn))
        except Exception as e:
            messagebox.showerror("Regnskapslinjer", f"Kunne ikke importere: {e}", parent=self.win)
            return

        self._refresh_regnskap_info()

    def _import_kontoplan_mapping(self) -> None:
        fn = filedialog.askopenfilename(
            parent=self.win,
            title="Importer kontoplan-mapping.xlsx",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Alle filer", "*.*")],
        )
        if not fn:
            return

        if not messagebox.askyesno(
            "Importer og erstatt",
            build_replace_baseline_confirm_text("kontoplan"),
            parent=self.win,
        ):
            return

        try:
            import regnskap_config

            regnskap_config.import_kontoplan_mapping(Path(fn))
        except Exception as e:
            messagebox.showerror("Kontoplan-mapping", f"Kunne ikke importere: {e}", parent=self.win)
            return

        self._refresh_regnskap_info()

    # ------------------ Aksjonærregister ------------------

    def _refresh_ar_info(self) -> None:
        try:
            from ar_store import list_imported_years
            years = list_imported_years()
            if years:
                self.lbl_ar.config(text=f"Importert for: {', '.join(years)}")
            else:
                self.lbl_ar.config(text="(ikke importert)")
        except Exception:
            self.lbl_ar.config(text="(ikke tilgjengelig)")

    def _import_ar_registry_csv(self) -> None:
        fn = filedialog.askopenfilename(
            parent=self.win,
            title="Importer aksjonærregister (CSV)",
            filetypes=[("CSV", "*.csv"), ("Alle filer", "*.*")],
        )
        if not fn:
            return

        from ar_store import parse_year_from_filename
        default_year = parse_year_from_filename(fn)
        year = simpledialog.askstring(
            "Aksjonærregister",
            "År for aksjonærregisteret:",
            initialvalue=default_year,
            parent=self.win,
        )
        if not year:
            return

        try:
            from ar_store import import_registry_csv
            meta = import_registry_csv(Path(fn), year=str(year).strip())
            rows = meta.get("rows_read", 0)
            rels = meta.get("relations_count", 0)
            messagebox.showinfo(
                "Aksjonærregister",
                f"Importert: {rows} rader, {rels} relasjoner for {year}.",
                parent=self.win,
            )
        except Exception as e:
            messagebox.showerror("Aksjonærregister", f"Kunne ikke importere: {e}", parent=self.win)
            return

        self._refresh_ar_info()

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

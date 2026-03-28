# -*- coding: utf-8 -*-
"""dataset_pane_store_section.py

Klient- og versjonsseksjon som kan monteres i Dataset-panelet.

Mål:
 - Lagre hovedbok-filer per klient/år som versjoner (filbasert) slik at
   flere kan gjenbruke samme kildefil.
 - Minimalt inngrep i eksisterende flyt: brukeren kan fortsatt velge fil og
   bygge datasett som før.
 - UI skal være responsiv også ved store klientlister.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import logging
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import app_paths

from dataset_pane_store_import_ui import import_client_list_with_progress
from dataset_pane_store_ui import build_client_store_widgets
from dataset_pane_store_logic import (
    apply_active_version_to_path_if_needed as _apply_active_version_to_path_if_needed,
    auto_store_hb_from_path as _auto_store_hb_from_path,
)

log = logging.getLogger(__name__)


DEFAULT_YEAR = "2025"  # ønsket default


try:
    import client_store

    _HAS_CLIENT_STORE = True
except Exception:
    client_store = None
    _HAS_CLIENT_STORE = False


try:
    import preferences

    _HAS_PREFS = True
except Exception:
    preferences = None
    _HAS_PREFS = False


def get_active_version_path(display_name: str, year: str, dtype: str = "hb") -> Optional[str]:
    """Kompat-hjelper: returnerer aktiv versjon som *strengpath* (eller None).

    Viktig: returnerer None hvis filen ikke finnes på disk (f.eks. slettet/ikke synket).
    """

    if not _HAS_CLIENT_STORE or client_store is None:
        return None
    try:
        v = client_store.get_active_version(display_name, year=year, dtype=dtype)
        p = getattr(v, "path", None)
        if not p:
            return None
        pp = Path(str(p))
        return str(pp) if pp.exists() else None
    except Exception:
        return None


def get_version_path(display_name: str, year: str, dtype: str, version_id: str) -> Optional[str]:
    """Kompat-hjelper: returnerer versjonsfil som *strengpath* (eller None).

    Viktig: returnerer None hvis filen ikke finnes på disk (f.eks. slettet/ikke synket).
    """

    if not _HAS_CLIENT_STORE or client_store is None:
        return None
    try:
        versions = client_store.list_versions(display_name, year=year, dtype=dtype)
        v = next((x for x in versions if getattr(x, "id", None) == version_id), None)
        if v is None:
            return None
        p = getattr(v, "path", None)
        if not p:
            return None
        pp = Path(str(p))
        return str(pp) if pp.exists() else None
    except Exception:
        return None


def _safe_setenv(key: str, value: str) -> None:
    try:
        os.environ[key] = value
    except Exception:
        pass


@dataclass
class ClientStoreSection:
    frame: tk.Frame
    client_var: tk.StringVar
    year_var: tk.StringVar
    hb_var: tk.StringVar
    on_path_selected: Callable[[str], None]
    get_current_path: Callable[[], str]
    lbl_storage: ttk.Label
    cb_client: ttk.Combobox
    cb_hb: ttk.Combobox
    dtype: str = "hb"

    # Ikke en del av init-signaturen – brukes for søk/filtrering og prefs
    _all_clients: List[str] = field(default_factory=list, init=False, repr=False)
    _last_persisted_client: str = field(default="", init=False, repr=False)
    _last_persisted_year: str = field(default="", init=False, repr=False)
    # Brukes for å kunne tvinge oppdatering av filsti når bruker faktisk bytter
    # klient/år (uten å overskrive mens de bare skriver i søkefeltet).
    _last_applied_client: str = field(default="", init=False, repr=False)
    _last_applied_year: str = field(default="", init=False, repr=False)
    _refresh_after_id: str | None = field(default=None, init=False, repr=False)

    @staticmethod
    def create(parent: tk.Frame, *, on_path_selected: Callable[[str], None], get_current_path: Callable[[], str]) -> "ClientStoreSection":
        """Bygg UI-komponentene og returner en ClientStoreSection."""

        # Husk sist brukt klient/år når mulig
        init_client = ""
        init_year = DEFAULT_YEAR
        if _HAS_PREFS and preferences is not None:
            try:
                init_client = str(preferences.get_last_client() or "")
                init_year = str(preferences.get("client_store.last_year", DEFAULT_YEAR) or DEFAULT_YEAR)
            except Exception:
                pass

        w = build_client_store_widgets(parent, init_client=init_client, init_year=init_year)

        # NOTE: The DatasetPane uses `grid`. Ensure the client-store frame is
        # actually mounted; otherwise nothing will be visible.
        # We keep a pack() fallback in case the parent uses pack.
        try:
            parent.columnconfigure(0, weight=1)
            w.frame.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 0))
        except Exception:
            try:
                w.frame.pack(fill="x", padx=5, pady=5)
            except Exception:
                pass


        sec = ClientStoreSection(
            frame=w.frame,
            client_var=w.client_var,
            year_var=w.year_var,
            hb_var=w.hb_var,
            on_path_selected=on_path_selected,
            get_current_path=get_current_path,
            lbl_storage=w.lbl_storage,
            cb_client=w.cb_client,
            cb_hb=w.cb_hb,
        )

        # Bindings
        w.btn_pick_client.configure(command=sec._on_pick_client)
        w.btn_settings.configure(command=sec._on_open_settings)
        w.btn_versions.configure(command=sec._on_open_versions_dialog)

        # NB: Full refresh kan være tregt hvis man blar fort i comboboxen.
        # Vi debounce'er refresh for bedre UX.
        w.cb_client.bind("<<ComboboxSelected>>", lambda _e: sec._debounced_refresh())
        w.cb_client.bind("<KeyRelease>", sec._on_client_keyrelease)
        w.cb_client.bind("<Return>", lambda _e: sec._debounced_refresh())
        w.cb_client.bind("<FocusOut>", lambda _e: sec._debounced_refresh())
        w.cb_hb.bind("<<ComboboxSelected>>", lambda _e: sec._on_select_hb())
        w.cb_year.bind("<<ComboboxSelected>>", lambda _e: sec._debounced_refresh())
        w.cb_year.bind("<Return>", lambda _e: sec._debounced_refresh())

        sec.refresh()
        return sec

    def _persist_prefs(self) -> None:
        if not _HAS_PREFS or preferences is None:
            return
        c = (self._client() or "").strip()
        y = (self._year() or "").strip()
        if c and c != self._last_persisted_client:
            try:
                preferences.set_last_client(c)
                self._last_persisted_client = c
            except Exception:
                pass
        if y and y != self._last_persisted_year:
            try:
                preferences.set("client_store.last_year", y)
                self._last_persisted_year = y
            except Exception:
                pass

    def _client(self) -> str:
        return str(self.client_var.get() or "").strip()

    def _year(self) -> str:
        y = str(self.year_var.get() or "").strip()
        return y or DEFAULT_YEAR

    def get_current_version_id(self) -> str | None:
        """Returnerer valgt HB-versjon-id (hvis satt)."""

        v = str(self.hb_var.get() or "").strip()
        return v or None

    def _debounced_refresh(self, delay_ms: int = 150) -> None:
        """Kjør refresh() med debounce.

        Dette gjør at man kan bla raskt i klientdropdown uten at vi gjør en full
        refresh for hvert eneste mellomvalg.
        """

        if self._refresh_after_id is not None:
            try:
                self.frame.after_cancel(self._refresh_after_id)
            except Exception:
                pass
            self._refresh_after_id = None

        self._refresh_after_id = self.frame.after(delay_ms, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self) -> None:
        self._refresh_after_id = None
        self.refresh()

    def _on_client_keyrelease(self, event: tk.Event) -> None:  # type: ignore[name-defined]
        """Type-ahead søk: filtrer klientlisten på substring."""

        if not self._all_clients:
            return

        # Ikke trigge på navigasjonstaster
        if getattr(event, "keysym", "") in {"Up", "Down", "Left", "Right", "Escape", "Tab"}:
            return

        q = self._client().lower()
        if not q:
            vals = self._all_clients
        else:
            vals = [c for c in self._all_clients if q in c.lower()]

        # Begrens for å unngå ekstremt store lister i GUI
        self.cb_client["values"] = vals[:2000]

    def refresh(self) -> None:
        """Oppdater klient- og versjonsdropdowns."""

        # Hvis vi har en pending debounce, kanseller den – vi kjører refresh nå.
        if self._refresh_after_id is not None:
            try:
                self.frame.after_cancel(self._refresh_after_id)
            except Exception:
                pass
            self._refresh_after_id = None

        # Datamappe
        try:
            base = app_paths.data_dir()
        except Exception:
            base = None

        if not _HAS_CLIENT_STORE or client_store is None:
            self.cb_client["values"] = []
            self.cb_hb["values"] = []
            self.lbl_storage.configure(text=f"Datamappe: {base or '-'}")
            return

        # Klientliste
        try:
            clients = client_store.list_clients()
        except Exception as e:
            log.warning("Kunne ikke liste klienter: %s", e)
            clients = []

        extra = f" (klienter: {len(clients)})" if clients else ""
        self.lbl_storage.configure(text=f"Datamappe: {base or '-'}{extra}")

        self._all_clients = list(clients)

        # Bevar ev. søkestreng i inputfeltet, men vis alltid full liste når dropdown åpnes.
        try:
            if tuple(self.cb_client["values"]) != tuple(self._all_clients):
                self.cb_client["values"] = self._all_clients
        except Exception:
            self.cb_client["values"] = self._all_clients

        # Hvis lagret klient ikke finnes lenger (f.eks. slettet), nullstill.
        try:
            cur_client = str(self.client_var.get() or "").strip()
        except Exception:
            cur_client = ""
        if self._all_clients and cur_client and (cur_client not in self._all_clients):
            self.client_var.set("")

        # Versjoner
        c = self._client()
        y = self._year()
        versions: List[str] = []
        if c:
            try:
                versions = [v.id for v in client_store.list_versions(c, year=y, dtype=self.dtype)]
            except Exception as e:
                log.warning("Kunne ikke liste versjoner for %s/%s: %s", c, y, e)

        try:
            if tuple(self.cb_hb["values"]) != tuple(versions):
                self.cb_hb["values"] = versions
        except Exception:
            self.cb_hb["values"] = versions

        # Hvis valgt hb ikke finnes, sett aktiv
        if versions:
            cur = str(self.hb_var.get() or "").strip()
            if cur not in versions:
                try:
                    act = client_store.get_active_version_id(c, year=y, dtype=self.dtype)
                except Exception:
                    act = None
                if act in versions:
                    self.hb_var.set(act)
                else:
                    self.hb_var.set(versions[0])

        else:
            self.hb_var.set("")

        # Force apply when user has switched to a *valid* client/year.
        force_apply = False
        if c and (c in self._all_clients):
            if c != self._last_applied_client or y != self._last_applied_year:
                force_apply = True

        _apply_active_version_to_path_if_needed(self, force=force_apply)

        if force_apply:
            self._last_applied_client = c
            self._last_applied_year = y

        self._persist_prefs()

    def _on_create_client(self) -> None:
        if not _HAS_CLIENT_STORE or client_store is None:
            messagebox.showwarning("Klient", "Klientlager er ikke tilgjengelig.")
            return

        name = simpledialog.askstring("Klient", "Skriv inn klientnavn:", parent=self.frame)
        if not name:
            return

        try:
            client_store.ensure_client(name)
            self.client_var.set(name)
            self.refresh()
        except Exception as e:
            messagebox.showerror("Klient", f"Kunne ikke opprette klient: {e}")

    def _on_pick_client(self) -> None:
        """Åpne en søkbar popup for rask klientbytte."""

        if not _HAS_CLIENT_STORE or client_store is None:
            messagebox.showwarning("Klient", "Klientlager er ikke tilgjengelig.")
            return

        # Bruk cached liste om mulig
        try:
            clients = list(self._all_clients) if self._all_clients else list(client_store.list_clients())
        except Exception:
            clients = []

        if not clients:
            messagebox.showinfo(
                "Klient",
                "Fant ingen klienter. Importer klientliste først (Importer liste…).",
            )
            return

        try:
            from client_picker_dialog import open_client_picker
        except Exception as e:
            messagebox.showerror("Klient", f"Kunne ikke åpne klientvelger: {e}")
            return

        # Start alltid med tomt søkefelt, men forhåndsmarkér gjeldende klient i lista.
        current = str(self.client_var.get() or "")
        chosen = open_client_picker(
            self.frame,
            clients,
            initial_query="",
            initial_selection=current,
            title="Velg klient",
        )

        if chosen:
            self.client_var.set(chosen)
            # Direkte refresh: eksplisitt valgt av bruker.
            self.refresh()
            try:
                self.cb_client.focus_set()
            except Exception:
                pass

    def _on_select_hb(self) -> None:
        c = self._client()
        if not c:
            return
        vid = str(self.hb_var.get() or "").strip()
        if not vid:
            return
        y = self._year()
        p = get_version_path(c, y, self.dtype, vid)
        if not p:
            return
        pp = Path(p)
        try:
            client_store.set_active_version(c, year=y, dtype=self.dtype, version_id=vid)
        except Exception:
            pass
        try:
            self.on_path_selected(str(pp))
        except Exception:
            pass

    def _on_select_sb(self, version_id: str) -> None:
        """Handle selection of an SB (saldobalanse) version."""
        if not _HAS_CLIENT_STORE or client_store is None:
            return
        c = self._client()
        if not c:
            return
        y = self._year()
        try:
            v = client_store.get_version(c, year=y, dtype="sb", version_id=version_id)
        except Exception:
            log.debug("Could not look up SB version %s", version_id, exc_info=True)
            return
        if v is None:
            return

        # Show preview dialog for column confirmation
        try:
            from tb_preview_dialog import open_tb_preview
            parent = self._frm.winfo_toplevel()
            tb_df = open_tb_preview(parent, v.path)
            if tb_df is None:
                return  # User cancelled
        except ImportError:
            # Fallback: read without preview
            try:
                from trial_balance_reader import read_trial_balance
                tb_df = read_trial_balance(v.path)
            except Exception:
                log.exception("Failed to read SB file %s", v.path)
                messagebox.showerror("Saldobalanse", f"Kunne ikke lese saldobalanse:\n{v.path}")
                return
        except Exception:
            log.exception("Failed to read SB file %s", v.path)
            messagebox.showerror("Saldobalanse", f"Kunne ikke lese saldobalanse:\n{v.path}")
            return

        try:
            import session
            session.set_tb(tb_df)
            session.client = c
            session.year = y
        except Exception:
            log.exception("Failed to set TB in session")

        # Notify DatasetPane to switch to SB mode
        tb_cb = getattr(self, "_on_tb_selected_cb", None)
        if callable(tb_cb):
            try:
                tb_cb(str(v.path))
            except Exception:
                log.debug("_on_tb_selected_cb failed", exc_info=True)

        # Notify ui_main via bus event so downstream tabs refresh
        try:
            import bus
            bus.emit("TB_LOADED", tb_df)
        except Exception:
            log.debug("bus.emit TB_LOADED failed", exc_info=True)

    def _on_store_current_file(self) -> None:
        p = str(self.get_current_path() or "").strip()
        if not p:
            messagebox.showwarning("Fil", "Velg gyldig fil først.")
            return
        self.auto_store_hb_from_path(p, show_messages=True)

    def auto_store_hb_from_path(self, path: str, *, show_messages: bool = False) -> Optional[str]:
        return _auto_store_hb_from_path(self, path, show_messages=show_messages)

    def _on_delete_hb(self) -> None:
        if not _HAS_CLIENT_STORE or client_store is None:
            return
        c = self._client()
        if not c:
            return
        y = self._year()
        vid = str(self.hb_var.get() or "").strip()
        if not vid:
            return

        if not messagebox.askyesno("Slett", "Slette valgt versjon?", parent=self.frame):
            return
        try:
            client_store.delete_version(c, year=y, dtype=self.dtype, version_id=vid)
            self.hb_var.set("")
            self.refresh()
        except Exception as e:
            messagebox.showerror("Slett", f"Kunne ikke slette: {e}")


    def _on_open_versions_dialog(self) -> None:
        # Åpner dialog for å administrere versjoner for valgt klient/år.
        if not _HAS_CLIENT_STORE or client_store is None:
            messagebox.showinfo("Versjoner", "Klientlager er ikke tilgjengelig i denne installasjonen.")
            return

        client = (self._client() or "").strip()
        if not client:
            messagebox.showinfo("Versjoner", "Velg klient først.")
            return

        year = (self._year() or "").strip() or DEFAULT_YEAR

        try:
            from version_overview_dialog import open_versions_dialog
        except Exception as e:
            messagebox.showerror("Versjoner", f"Kunne ikke åpne versjonsdialog: {e}")
            return

        def _use_version(version_id: str) -> None:
            # Keep semantics identical to selecting from the combobox:
            # set hb_var then run the existing handler.
            self.hb_var.set(version_id)
            self._on_select_hb()

        def _use_sb_version(version_id: str) -> None:
            self._on_select_sb(version_id)

        open_versions_dialog(
            self.frame,
            client=client,
            year=year,
            dtype=self.dtype,
            current_path_getter=self.get_current_path,
            on_use_version=_use_version,
            on_use_sb_version=_use_sb_version,
            on_after_change=self.refresh,
        )

    def _on_open_settings(self) -> None:
        """Åpne innstillinger (datamappe, klientliste, eksportvalg)."""

        try:
            import settings_entry
        except Exception as e:
            messagebox.showerror("Innstillinger", f"Kunne ikke åpne innstillinger: {e}", parent=self.frame)
            return

        root = self.frame.winfo_toplevel()

        def _on_data_dir_changed() -> None:
            try:
                self.refresh()
            except Exception:
                pass

        def _on_clients_changed() -> None:
            try:
                self.refresh()
            except Exception:
                pass

        settings_entry.open_settings(root, on_data_dir_changed=_on_data_dir_changed, on_clients_changed=_on_clients_changed)

    def _on_pick_storage(self) -> None:
        """Velg datamappe (felles lagring)."""

        p = filedialog.askdirectory(title="Velg datamappe for klientlager", mustexist=False)
        if not p:
            return
        _safe_setenv("UTVALG_DATA_DIR", p)
        try:
            app_paths.set_data_dir_hint(p)
        except Exception:
            pass
        self.refresh()

    def _on_import_client_list(self) -> None:
        if not _HAS_CLIENT_STORE or client_store is None:
            messagebox.showwarning("Importer", "Klientlager er ikke tilgjengelig.")
            return

        p = filedialog.askopenfilename(
            title="Importer klientliste",
            filetypes=[("Excel/CSV", "*.xlsx;*.xls;*.xlsm;*.csv"), ("Alle", "*.*")],
        )
        if not p:
            return

        def _done(stats: dict) -> None:
            self.refresh()

            try:
                base = app_paths.data_dir()
            except Exception:
                base = None
            extra = f"\n\nDatamappe: {base}" if base is not None else ""

            found = (stats or {}).get("found", 0)
            created = (stats or {}).get("created", 0)
            skipped = (stats or {}).get("skipped_existing", 0)
            renamed = (stats or {}).get("renamed", 0)
            dups = (stats or {}).get("duplicates_in_file", 0)

            msg = f"Fant {found} klientnavn. Opprettet {created} nye."
            if skipped:
                msg += f" ({skipped} eksisterte allerede.)"
            if renamed:
                msg += f" Oppdatert navn på {renamed}."
            if dups:
                msg += f" {dups} duplikater i filen ble ignorert."
            msg += extra
            messagebox.showinfo("Importer", msg)

        import_client_list_with_progress(self.frame, p, on_done=_done)

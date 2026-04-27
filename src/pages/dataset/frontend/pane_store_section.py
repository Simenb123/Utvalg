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
import webbrowser
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import app_paths
from formatting import format_int_no

from .pane_store_import_ui import import_client_list_with_progress
from .pane_store_ui import build_client_store_widgets
from .pane_store_logic import (
    apply_active_version_to_path_if_needed as _apply_active_version_to_path_if_needed,
    auto_store_hb_from_path as _auto_store_hb_from_path,
)

log = logging.getLogger(__name__)


DEFAULT_YEAR = "2025"  # ønsket default


try:
    import src.shared.client_store.store as client_store

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


def _format_date_no(raw: object) -> str:
    if not raw:
        return ""
    s = str(raw).strip()
    parts = s[:10].split("-")
    if len(parts) == 3 and len(parts[0]) == 4 and all(p.isdigit() for p in parts):
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    return s


def _normalize_homepage_url(raw: object) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if "://" in s:
        return s
    return f"https://{s}"

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
    dtype: str = "hb"

    # Ikke en del av init-signaturen – brukes for prefs/status
    _status_pills: dict = field(default_factory=dict, init=False, repr=False)
    _brreg_cache: dict = field(default_factory=dict, init=False, repr=False)
    _brreg_request_id: int = field(default=0, init=False, repr=False)
    _brreg_current_orgnr: str = field(default="", init=False, repr=False)
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
        )

        sec._status_pills = w.status_pills
        sec._company_labels = w.company_labels
        sec._company_key_labels = w.company_key_labels
        sec._role_labels = w.role_labels
        sec._team_labels = w.team_labels
        # Skjul status-raden initielt (vises kun ved rødt flagg).
        sec._set_status_row_visible(False)

        # Bindings
        w.btn_switch_client.configure(command=sec._on_pick_client)
        w.btn_versions.configure(command=sec._on_open_versions_dialog)

        # Klikkhandler per status-pill — åpner Versjoner-dialogen for dtypen.
        for _dtype, _pill in w.status_pills.items():
            _pill.bind("<Button-1>", lambda _e, d=_dtype: sec._on_pill_clicked(d))

        w.cb_year.bind("<<ComboboxSelected>>", lambda _e: sec._debounced_refresh())
        w.cb_year.bind("<Return>", lambda _e: sec._debounced_refresh())

        # Defer den første refresh-en til etter at vinduet er rendret.
        # refresh() kaller client_store.list_clients() + list_versions()
        # for hver dtype og er hovedårsaken til ~3-5 s blokkering under
        # Dataset-fanens oppstart. Brukeren ser et tomt skall først, og
        # dropdowns + status-pills fylles inn etter at vinduet er synlig.
        try:
            w.frame.after(50, sec.refresh)
        except Exception:
            # Fallback: kjør synkront hvis after() ikke er tilgjengelig
            # (f.eks. headless test-miljø).
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
                preferences.add_recent_client(c)
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

    def _on_pill_clicked(self, dtype: str) -> None:
        """Åpne Versjoner-dialogen for valgt dtype (HB/SB) eller vis info for KR/LR."""
        if dtype in {"kr", "lr"}:
            label = "Kundereskontro" if dtype == "kr" else "Leverandørreskontro"
            messagebox.showinfo(
                "Kommer",
                f"{label} som egen datakilde kommer i en senere runde.",
                parent=self.frame,
            )
            return
        # HB/SB: åpne Versjoner-dialog fokusert på valgt dtype.
        prev_dtype = self.dtype
        self.dtype = dtype
        try:
            self._on_open_versions_dialog()
        finally:
            self.dtype = prev_dtype

    def _update_status_pills(self) -> None:
        """Fargelegg pill-knappene etter om aktiv versjon finnes for dtypen."""
        if not self._status_pills:
            return
        client = self._client()
        year = self._year()
        short_map = {"hb": "HB", "sb": "SB", "kr": "KR", "lr": "LR"}
        for dtype, pill in self._status_pills.items():
            short = short_map.get(dtype, dtype.upper())
            has_active = False
            if client and _HAS_CLIENT_STORE and client_store is not None and dtype in {"hb", "sb"}:
                try:
                    has_active = bool(
                        client_store.get_active_version_id(client, year=year, dtype=dtype)
                    )
                except Exception:
                    has_active = False
            if has_active:
                pill.configure(text=f"  ✓ {short}  ", bg="#2e7d32", fg="white")
            else:
                pill.configure(text=f"  {short}  ", bg="#e0e0e0", fg="#9e9e9e")

    def refresh(self) -> None:
        """Oppdater klient- og versjonsdropdowns."""

        # Hvis vi har en pending debounce, kanseller den – vi kjører refresh nå.
        if self._refresh_after_id is not None:
            try:
                self.frame.after_cancel(self._refresh_after_id)
            except Exception:
                pass
            self._refresh_after_id = None

        if not _HAS_CLIENT_STORE or client_store is None:
            return

        # Klientliste — brukes av "Bytt klient…"-dialogen og for å validere
        # at lagret klient fortsatt finnes.
        try:
            clients = client_store.list_clients()
        except Exception as e:
            log.warning("Kunne ikke liste klienter: %s", e)
            clients = []

        clients_set = set(clients)

        # Hvis lagret klient ikke finnes lenger (f.eks. slettet), nullstill.
        try:
            cur_client = str(self.client_var.get() or "").strip()
        except Exception:
            cur_client = ""
        if clients and cur_client and (cur_client not in clients_set):
            self.client_var.set("")

        # Versjoner for valgt klient/år
        c = self._client()
        y = self._year()
        versions: List[str] = []
        if c:
            try:
                versions = [v.id for v in client_store.list_versions(c, year=y, dtype=self.dtype)]
            except Exception as e:
                log.warning("Kunne ikke liste versjoner for %s/%s: %s", c, y, e)

        # Reset til aktiv versjon ved klient- eller år-bytte (selv om gammel
        # verdi tilfeldigvis finnes i ny liste). Ellers: kun sett aktiv hvis
        # nåværende valg er ugyldig.
        client_or_year_changed = bool(
            self._last_applied_client
            and (c != self._last_applied_client or y != self._last_applied_year)
        )
        if versions:
            cur = str(self.hb_var.get() or "").strip()
            if cur not in versions or client_or_year_changed:
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
        if c and (c in clients_set):
            if c != self._last_applied_client or y != self._last_applied_year:
                force_apply = True

        _apply_active_version_to_path_if_needed(self, force=force_apply)

        if force_apply:
            self._last_applied_client = c
            self._last_applied_year = y

        self._persist_prefs()
        self._update_client_info()
        self._update_status_pills()
        self._update_window_title()

    def _update_window_title(self) -> None:
        """Speile aktiv klient + år i hovedvinduets tittel."""
        try:
            root = self.frame.winfo_toplevel()
        except Exception:
            return
        klient = self._client()
        aar = self._year()
        parts = ["Utvalg"]
        if aar:
            parts.append(aar)
        parts.append(klient if klient else "revisjonsverktøy")
        try:
            root.title(" — ".join(parts))
        except Exception:
            pass

    def _update_client_info(self) -> None:
        """Oppdater klient-infopanelet med metadata fra lokal indeks.

        Fyller Selskap- (orgnr, knr), og Team-boksene (partner, manager,
        medarbeidere) synkront. Resten (selskaps-status, adresse, morselskap
        og selskapsroller) fylles asynkront via BRREG i `_update_brreg_fields`.
        """
        company = getattr(self, "_company_labels", None) or {}
        team = getattr(self, "_team_labels", None) or {}
        roles = getattr(self, "_role_labels", None) or {}

        client = self._client()
        if not client:
            for lbl in company.values():
                try: lbl.configure(text="\u2013", foreground="")
                except Exception: pass
            for lbl in team.values():
                try: lbl.configure(text="\u2013")
                except Exception: pass
            for lbl in roles.values():
                try: lbl.configure(text="\u2013")
                except Exception: pass
            self._update_brreg_fields({})
            return

        try:
            from src.shared.client_store.meta_index import get_index
            meta = get_index().get(client, {})
        except Exception:
            meta = {}

        # Selskap: orgnr + knr (resten fra BRREG)
        if "orgnr" in company:
            try: company["orgnr"].configure(text=meta.get("org_number") or "\u2013")
            except Exception: pass
        if "knr" in company:
            try: company["knr"].configure(text=meta.get("client_number") or "\u2013")
            except Exception: pass

        # Team: Partner (initialer → fullt navn hvis mulig), Manager, Medarbeidere
        self._update_team_labels(meta)

        self._update_brreg_fields(meta)

    def _update_team_labels(self, meta: dict) -> None:
        """Fyll Team-boksen fra lokal klient-meta."""
        team = getattr(self, "_team_labels", None) or {}
        if not team:
            return

        responsible = str((meta or {}).get("responsible") or "").strip()
        partner_text = "\u2013"
        if responsible:
            full = ""
            try:
                import team_config
                full = team_config.resolve_initials_to_name(responsible)
            except Exception:
                full = ""
            if full:
                partner_text = f"{full} ({responsible.upper()})"
            else:
                partner_text = responsible.upper()

        manager_text = str((meta or {}).get("manager") or "").strip() or "\u2013"

        members_raw = str((meta or {}).get("team_members") or "").strip()
        if members_raw:
            # Visena-feltet kan være newline- eller komma-separert. Normaliser.
            parts = [p.strip() for p in members_raw.replace("\n", ",").split(",")]
            members_text = ", ".join(p for p in parts if p) or "\u2013"
        else:
            members_text = "\u2013"

        for key, val in (("partner", partner_text), ("manager", manager_text),
                         ("medarbeidere", members_text)):
            lbl = team.get(key)
            if lbl is None:
                continue
            try: lbl.configure(text=val)
            except Exception: pass

    def _set_status_row_visible(self, visible: bool) -> None:
        """Vis/skjul Status-raden. Status vises kun ved rødt flagg."""
        company = getattr(self, "_company_labels", None) or {}
        keys = getattr(self, "_company_key_labels", None) or {}
        vlbl = company.get("status")
        klbl = keys.get("status")
        if vlbl is None or klbl is None:
            return
        try:
            if visible:
                klbl.grid()
                vlbl.grid()
            else:
                klbl.grid_remove()
                vlbl.grid_remove()
        except Exception:
            pass

    def _update_brreg_fields(self, meta: dict) -> None:
        """Hent BRREG-anriket info (org.form, MVA, næring, adresse, roller) lazy.

        Synkron render fra cache hvis tilgjengelig, ellers start bakgrunnstråd.
        Blokkerer aldri refresh().
        """
        company = getattr(self, "_company_labels", None) or {}
        role_labels = getattr(self, "_role_labels", None) or {}
        if not company or not role_labels:
            return

        orgnr = str((meta or {}).get("org_number") or "").strip()
        self._brreg_current_orgnr = orgnr

        if not orgnr:
            for key in ("orgform", "naering", "mva", "address", "stiftelsesdato", "ansatte", "hjemmeside", "kapital", "antall_aksjer"):
                lbl = company.get(key)
                if lbl is None:
                    continue
                try: lbl.configure(text="\u2013", foreground="")
                except Exception: pass
            # Tom status-rad + skjul
            status_lbl = company.get("status")
            if status_lbl is not None:
                try: status_lbl.configure(text="", foreground="")
                except Exception: pass
            self._set_status_row_visible(False)
            for lbl in role_labels.values():
                try: lbl.configure(text="\u2013")
                except Exception: pass
            return

        cached = self._brreg_cache.get(orgnr)
        if cached is not None:
            self._render_brreg_labels(cached.get("enhet") or {}, cached.get("roller") or [])
            return

        # "Laster…" i org.form mens vi venter på nettverk.
        orgform_lbl = company.get("orgform")
        if orgform_lbl is not None:
            try: orgform_lbl.configure(text="Laster\u2026", foreground="")
            except Exception: pass
        for key in ("naering", "mva", "address", "stiftelsesdato", "ansatte", "hjemmeside", "kapital", "antall_aksjer"):
            lbl = company.get(key)
            if lbl is None:
                continue
            try: lbl.configure(text="\u2013")
            except Exception: pass
        self._set_status_row_visible(False)
        for lbl in role_labels.values():
            try: lbl.configure(text="\u2013")
            except Exception: pass

        self._brreg_request_id += 1
        request_id = self._brreg_request_id
        try:
            threading.Thread(
                target=self._brreg_worker,
                args=(orgnr, request_id),
                daemon=True,
            ).start()
        except Exception:
            log.debug("Kunne ikke starte BRREG-tråd for %s", orgnr, exc_info=True)

    def _brreg_worker(self, orgnr: str, request_id: int) -> None:
        """Bakgrunnstråd: henter BRREG-data og planlegger apply på main-tråden."""
        enhet = None
        roller = None
        try:
            import src.shared.brreg.client as brreg_client
            enhet = brreg_client.fetch_enhet(orgnr)
            roller = brreg_client.fetch_roller(orgnr)
        except Exception:
            log.debug("BRREG-henting feilet for %s", orgnr, exc_info=True)
        try:
            self.frame.after(0, self._brreg_apply_result, request_id, orgnr, enhet, roller)
        except Exception:
            pass

    def _brreg_apply_result(self, request_id: int, orgnr: str, enhet, roller) -> None:
        """Main-tråd: cache resultatet, drop stale, render."""
        self._brreg_cache[orgnr] = {"enhet": enhet or {}, "roller": roller or []}
        if request_id != self._brreg_request_id:
            return
        if orgnr != self._brreg_current_orgnr:
            return
        self._render_brreg_labels(enhet or {}, roller or [])

    def _render_brreg_labels(self, enhet: dict, roller: list) -> None:
        """Fyll Selskap-boksen (org.form, næring, MVA, adresse + valgfritt
        status-flagg) + Roller-boksen."""
        company = getattr(self, "_company_labels", None) or {}
        role_labels = getattr(self, "_role_labels", None) or {}
        if not company or not role_labels:
            return

        RED = "#c62828"
        enhet = enhet or {}

        org_form = str(enhet.get("organisasjonsform") or "").strip() or "\u2013"
        naering = str(enhet.get("naeringsnavn") or "").strip() or "\u2013"
        mva_raw = enhet.get("registrertIMvaregisteret")
        if mva_raw is True:
            mva = "JA \u2713"
            mva_fg = "#2e7d32"
        elif mva_raw is False and "registrertIMvaregisteret" in enhet:
            mva = "NEI \u2715"
            mva_fg = "#ef6c00"
        else:
            mva = "\u2013"
            mva_fg = ""
        adresse = str(enhet.get("forretningsadresse") or "").strip() or "\u2013"
        stiftelsesdato = _format_date_no(enhet.get("stiftelsesdato")) or "\u2013"
        ansatte_raw = enhet.get("antallAnsatte")
        ansatte = "\u2013" if ansatte_raw in (None, "") else str(ansatte_raw)
        hjemmeside = str(enhet.get("hjemmeside") or "").strip() or "\u2013"
        kapital_belop_raw = enhet.get("kapital_belop")
        kapital_valuta = str(enhet.get("kapital_valuta") or "").strip()
        kapital_belop = format_int_no(kapital_belop_raw) if kapital_belop_raw not in (None, "") else ""
        kapital = (f"{kapital_belop} {kapital_valuta}".strip() if kapital_belop else "\u2013")
        antall_aksjer_raw = enhet.get("kapital_antall_aksjer")
        antall_aksjer = format_int_no(antall_aksjer_raw) if antall_aksjer_raw not in (None, "") else "\u2013"

        for key, text in (
            ("orgform", org_form),
            ("naering", naering),
            ("address", adresse),
            ("stiftelsesdato", stiftelsesdato),
            ("ansatte", ansatte),
            ("kapital", kapital),
            ("antall_aksjer", antall_aksjer),
        ):
            lbl = company.get(key)
            if lbl is None:
                continue
            try: lbl.configure(text=text, foreground="")
            except Exception: pass

        # Status-rad: kun når det er noe bekymringsverdig å varsle om.
        mva_lbl = company.get("mva")
        if mva_lbl is not None:
            try: mva_lbl.configure(text=mva, foreground=mva_fg)
            except Exception: pass

        hjemmeside_lbl = company.get("hjemmeside")
        if hjemmeside_lbl is not None:
            try: hjemmeside_lbl.configure(text=hjemmeside, foreground="", cursor="")
            except Exception: pass
            try: hjemmeside_lbl.unbind("<Button-1>")
            except Exception: pass
            if hjemmeside != "\u2013":
                homepage_url = _normalize_homepage_url(hjemmeside)
                try: hjemmeside_lbl.configure(foreground="#1565c0", cursor="hand2")
                except Exception: pass
                try: hjemmeside_lbl.bind("<Button-1>", lambda _e, u=homepage_url: webbrowser.open_new_tab(u))
                except Exception: pass

        slettedato = enhet.get("slettedato")
        if enhet.get("konkurs"):
            flag_text = "Konkurs"
        elif enhet.get("underTvangsavvikling"):
            flag_text = "Under tvangsavvikling"
        elif enhet.get("underAvvikling"):
            flag_text = "Under avvikling"
        elif slettedato:
            flag_text = f"Slettet {slettedato}"
        else:
            flag_text = ""

        status_lbl = company.get("status")
        if status_lbl is not None:
            if flag_text:
                try: status_lbl.configure(text=flag_text, foreground=RED)
                except Exception: pass
                self._set_status_row_visible(True)
            else:
                try: status_lbl.configure(text="", foreground="")
                except Exception: pass
                self._set_status_row_visible(False)

        # Roller: match på stabil rolle_kode (ikke beskrivelse — BRREG bruker
        # f.eks. "Styrets leder" for LEDE, som ikke matcher "Styreleder").
        single_code_map = {
            "DAGL": "daglig_leder",
            "LEDE": "styreleder",
            "NEST": "nestleder",
            "REVI": "revisor",
            "REGN": "regnskapsforer",
        }
        single_vals: dict[str, str] = {v: "\u2013" for v in single_code_map.values()}
        styremedlemmer: list[str] = []
        varamedlemmer: list[str] = []

        for r in roller or []:
            kode = str((r or {}).get("rolle_kode") or "").strip().upper()
            navn = str((r or {}).get("navn") or "").strip()
            if not navn:
                continue
            key = single_code_map.get(kode)
            if key and single_vals[key] == "\u2013":
                single_vals[key] = navn
            elif kode == "MEDL":
                styremedlemmer.append(navn)
            elif kode == "VARA":
                varamedlemmer.append(navn)

        all_vals = dict(single_vals)
        all_vals["styremedlemmer"] = ", ".join(styremedlemmer) if styremedlemmer else "\u2013"
        all_vals["varamedlemmer"] = ", ".join(varamedlemmer) if varamedlemmer else "\u2013"

        for key, val in all_vals.items():
            lbl = role_labels.get(key)
            if lbl is None:
                continue
            try: lbl.configure(text=val)
            except Exception: pass

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

        try:
            clients = list(client_store.list_clients())
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

        # Last metadata-indeks for rik visning
        try:
            from src.shared.client_store.meta_index import get_index
            meta = get_index()
        except Exception:
            meta = None

        # Start alltid med tomt søkefelt, men forhåndsmarkér gjeldende klient i lista.
        current = str(self.client_var.get() or "")
        chosen = open_client_picker(
            self.frame,
            clients,
            client_meta=meta,
            initial_query="",
            initial_selection=current,
            title="Velg klient",
            show_mine_filter=True,
            mine_by_default=True,
        )

        if chosen:
            self.client_var.set(chosen)
            # Direkte refresh: eksplisitt valgt av bruker.
            self.refresh()

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

        tb_df = None
        try:
            from trial_balance_reader import read_trial_balance
            tb_df = read_trial_balance(v.path)
        except Exception as read_exc:
            log.info("Auto-import av SB feilet, åpner preview-fallback: %s", read_exc)
            # Fallback: la brukeren mappe kolonner manuelt via TBPreviewDialog.
            parent_widget = getattr(self, "frame", None)
            try:
                from tb_preview_dialog import open_tb_preview
                preview = open_tb_preview(
                    parent_widget,
                    v.path,
                    initial_name=str(c or ""),
                )
            except Exception as preview_exc:
                log.exception("TBPreviewDialog feilet for %s", v.path)
                messagebox.showerror(
                    "Saldobalanse",
                    f"Kunne ikke lese saldobalanse:\n{v.path}\n\nÅrsak: {read_exc}\n"
                    f"Preview-dialog feilet: {preview_exc}",
                )
                return

            if preview is None:
                # Bruker avbrøt — ingen feilmelding, ingen session-endring.
                return
            tb_df, _name = preview

        if tb_df is None:
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

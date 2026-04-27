"""page_oversikt.py -- CRM-lignende oversiktsside (v1).

Viser:
- Hilsen med brukerens navn
- Aktiv klient (fra session)
- Sist brukte klienter som horisontale kort
- Klienttabell med mine/alle toggle og sok
- Frister-stub (v2)
"""

from __future__ import annotations

import logging
import time
import tkinter as tk
from tkinter import ttk

log = logging.getLogger(__name__)


def _safe_import(module_name: str):
    try:
        import importlib
        return importlib.import_module(module_name)
    except Exception:
        return None


class OversiktPage(ttk.Frame):
    """Oversikt-fane: landing page for appen."""

    def __init__(self, parent: tk.Widget, *, nb: ttk.Notebook, dataset_page):
        super().__init__(parent)
        self._nb = nb
        self._dataset_page = dataset_page

        # Lazy imports
        self._team_config = _safe_import("team_config")
        self._client_meta_index = _safe_import("src.shared.client_store.meta_index")
        self._client_store_enrich = _safe_import("src.shared.client_store.enrich")
        self._client_store_groups = _safe_import("src.shared.client_store.groups")
        self._preferences = _safe_import("preferences")

        # Brukerinfo
        self._user = None
        if self._team_config:
            try:
                self._user = self._team_config.current_user()
            except Exception:
                pass

        # State
        mine_only_default = False
        if self._preferences:
            try:
                mine_only_default = bool(self._preferences.get_bool("oversikt.mine_only", False))
            except Exception:
                pass
        self._mine_only_var = tk.BooleanVar(value=mine_only_default)
        self._search_var = tk.StringVar(value="")
        self._all_client_rows: list[tuple] = []  # (name, org, knr, ansvarlig, manager)
        self._initial_load_done = False

        # Build UI
        self._build_ui()

        # Klient-data leses asynkront etter at vinduet er rendret. På
        # Windows-disker med mange klienter tar load_accounting_system per
        # klient + meta-indeks ~9 sekunder synkront — det blokkerer hele
        # oppstart. Ved å scheduler det via after() får brukeren se
        # Oversikt-skallet umiddelbart, og listen fyller seg etterpå.
        self.after(50, self._deferred_initial_load)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)  # klienttabell tar resten av plassen

        self._build_header()
        self._build_recent_cards()
        self._build_client_table()
        # Frister-stub er ikke aktivert — _build_deadlines_stub kalles når
        # frister-funksjonen kommer (v2). Stubben tar bare plass uten innhold.

    def _build_header(self) -> None:
        hdr = ttk.Frame(self)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))
        hdr.columnconfigure(2, weight=1)

        # AarVaaken-logo til venstre — diskret merkevare-element på landing-fanen
        self._aarvaaken_photo = self._load_aarvaaken_for_header(target_height=56)
        if self._aarvaaken_photo is not None:
            logo_lbl = ttk.Label(hdr, image=self._aarvaaken_photo)
            logo_lbl.image = self._aarvaaken_photo  # GC-referanse
            logo_lbl.grid(row=0, column=0, sticky="w", padx=(0, 16))

        # Hilsen
        name = ""
        if self._user:
            name = self._user.full_name or self._user.windows_user or ""
        greeting = f"Hei, {name}" if name else "Oversikt"
        self._lbl_greeting = ttk.Label(hdr, text=greeting, font=("Segoe UI", 16, "bold"))
        self._lbl_greeting.grid(row=0, column=1, sticky="w")

        # Aktiv klient
        self._lbl_active = ttk.Label(hdr, text="", style="Muted.TLabel")
        self._lbl_active.grid(row=0, column=2, sticky="e", padx=(12, 0))

        # Ga til aktiv klient-knapp
        self._btn_goto_active = ttk.Button(
            hdr, text="Vis", width=6, style="Secondary.TButton",
            command=self._goto_active_client,
        )
        self._btn_goto_active.grid(row=0, column=3, sticky="e", padx=(6, 0))
        self._btn_goto_active.grid_remove()  # skjult til vi har aktiv klient

        # Sokefelt — plassert UNDER "Sist brukte klienter" (row=2) slik at
        # de mest brukte klientene ligger nærmest hilsen-overskriften og
        # søk er rett over selve klient-tabellen.
        search_frame = ttk.Frame(self)
        search_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 4))
        search_frame.columnconfigure(0, weight=1)

        self._entry_search = ttk.Entry(search_frame, textvariable=self._search_var)
        self._entry_search.grid(row=0, column=0, sticky="ew")
        self._entry_search.insert(0, "")
        self._search_var.trace_add("write", lambda *_: self._on_search())

        # Placeholder
        self._entry_search.insert(0, "")
        self._entry_search.bind("<FocusIn>", self._on_search_focus_in)
        self._entry_search.bind("<FocusOut>", self._on_search_focus_out)
        self._search_placeholder = True
        self._show_search_placeholder()

    def _show_search_placeholder(self) -> None:
        if not self._search_var.get():
            # _search_placeholder må settes FØR insert(): insert skriver til
            # _search_var som trigger trace → _on_search. Hvis flagget ikke er
            # satt enda, behandler _on_search "Sok klient..."-teksten som ekte
            # søk og filtrerer bort alle klienter.
            self._search_placeholder = True
            self._entry_search.insert(0, "Sok klient...")
            self._entry_search.config(foreground="gray")

    def _load_aarvaaken_for_header(self, *, target_height: int = 56):
        """Last AarVaaken.png skalert til ønsket høyde for header-bruk.

        Returnerer ImageTk.PhotoImage eller None ved feil. Caches på
        instansen via self._aarvaaken_photo (kall fra _build_header).
        Hvite marger croppes vekk på samme måte som splash.
        """
        try:
            from PIL import Image, ImageTk  # type: ignore[import-untyped]
            from pathlib import Path
            import sys

            candidates = []
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                candidates.append(Path(meipass) / "doc" / "pictures" / "AarVaaken.png")
            candidates.append(Path(__file__).resolve().parent / "doc" / "pictures" / "AarVaaken.png")

            pic_path = next((p for p in candidates if p.exists()), None)
            if pic_path is None:
                return None

            img = Image.open(str(pic_path))

            # Crop hvite kanter — samme terskel-tilnærming som splash
            try:
                gray = img.convert("L")
                bw = gray.point(lambda p: 255 if p < 250 else 0)
                bbox = bw.getbbox()
                if bbox:
                    img = img.crop(bbox)
            except Exception:
                pass

            # Skaler til target_height, behold aspekt-ratio
            w, h = img.size
            target_w = max(1, int(round(target_height * w / h)))
            img = img.resize((target_w, target_height), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            return None

    def _on_search_focus_in(self, _event=None) -> None:
        if self._search_placeholder:
            self._entry_search.delete(0, tk.END)
            self._entry_search.config(foreground="")
            self._search_placeholder = False

    def _on_search_focus_out(self, _event=None) -> None:
        if not self._search_var.get().strip():
            self._show_search_placeholder()

    def _build_recent_cards(self) -> None:
        self._recent_frame = ttk.LabelFrame(self, text="Sist brukte klienter", padding=8)
        self._recent_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 8))
        self._recent_cards_inner = ttk.Frame(self._recent_frame)
        self._recent_cards_inner.pack(fill="x")
        # Placeholder — fylles via _deferred_initial_load. Synkron lesing
        # av meta_index er treg på oppstart.
        ttk.Label(
            self._recent_cards_inner,
            text="Laster klienter…",
            style="Muted.TLabel",
        ).pack(padx=8, pady=8)

    def _populate_recent_cards(self) -> None:
        # Rydd opp
        for w in self._recent_cards_inner.winfo_children():
            w.destroy()

        recent = []
        if self._preferences:
            try:
                recent = self._preferences.get_recent_clients(max_count=8)
            except Exception:
                pass

        if not recent:
            ttk.Label(self._recent_cards_inner, text="Ingen nylige klienter.",
                      style="Muted.TLabel").pack(padx=8, pady=8)
            return

        # Hent metadata-indeks for org/knr/ansvarlig
        meta_index = {}
        if self._client_meta_index:
            try:
                meta_index = self._client_meta_index.get_index()
            except Exception:
                pass

        for i, entry in enumerate(recent):
            name = entry.get("name", "")
            ts = entry.get("timestamp", 0)
            if not name:
                continue

            meta = meta_index.get(name, {})
            org = meta.get("org_number", "")
            ansvarlig = meta.get("responsible", "")

            # Relativ tid
            elapsed = _relative_time(ts)

            card = ttk.Frame(self._recent_cards_inner, relief="solid", borderwidth=1, padding=8)
            card.pack(side="left", padx=(0 if i == 0 else 6, 0), pady=2)

            # Kort navn (maks 20 tegn)
            short_name = name if len(name) <= 22 else name[:20] + "..."
            ttk.Label(card, text=short_name, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            if org:
                ttk.Label(card, text=org, style="Muted.TLabel", font=("Segoe UI", 8)).pack(anchor="w")
            if ansvarlig:
                ttk.Label(card, text=ansvarlig, style="Muted.TLabel", font=("Segoe UI", 8)).pack(anchor="w")
            ttk.Label(card, text=elapsed, style="Muted.TLabel", font=("Segoe UI", 8)).pack(anchor="w")

            # Klikk -> navigasjon
            card.bind("<Button-1>", lambda _e, n=name: self._navigate_to_client(n))
            for child in card.winfo_children():
                child.bind("<Button-1>", lambda _e, n=name: self._navigate_to_client(n))

            # Hover-effekt
            card.bind("<Enter>", lambda _e, c=card: c.configure(relief="raised"))
            card.bind("<Leave>", lambda _e, c=card: c.configure(relief="solid"))

    def _build_client_table(self) -> None:
        from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview

        table_frame = ttk.Frame(self)
        table_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 8))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(1, weight=1)

        # Toolbar: mine klienter toggle
        toolbar = ttk.Frame(table_frame)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        cb_mine = ttk.Checkbutton(
            toolbar, text="Mine klienter", variable=self._mine_only_var,
            command=self._on_filter_changed,
        )
        cb_mine.pack(side="left")

        self._lbl_count = ttk.Label(toolbar, text="", style="Muted.TLabel")
        self._lbl_count.pack(side="right")

        # Treeview — kolonner og bredder via ColumnSpec, sortering/kolonnemeny/persist via ManagedTreeview
        column_specs = [
            ColumnSpec(id="klient",    heading="Klient",    width=320, minwidth=120),
            ColumnSpec(id="orgnr",     heading="Org.nr",    width=100, anchor="w"),
            ColumnSpec(id="knr",       heading="Knr",       width=80,  anchor="w"),
            ColumnSpec(id="ansvarlig", heading="Ansvarlig", width=90,  anchor="w"),
            ColumnSpec(id="manager",   heading="Manager",   width=180, anchor="w"),
            ColumnSpec(id="regnskapssystem", heading="Regnskapssystem", width=140, anchor="w"),
            ColumnSpec(id="team",      heading="Team",      width=220, anchor="w"),
            ColumnSpec(id="gruppe",    heading="Gruppe",    width=160, anchor="w", stretch=True),
        ]
        cols = [spec.id for spec in column_specs]

        # selectmode="extended" gir multi-select (Ctrl/Shift) — nødvendig for
        # å sette gruppe på flere klienter samtidig via høyreklikk.
        self._tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="extended")
        self._managed = ManagedTreeview(
            self._tree,
            view_id="oversikt_klienter",
            pref_prefix="ui",
            column_specs=column_specs,
        )

        self._tree.grid(row=1, column=0, sticky="nsew")

        # Scrollbar
        sb = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=sb.set)

        # Dobbeltklikk -> navigasjon
        self._tree.bind("<Double-1>", self._on_tree_double_click)
        # Høyreklikk -> kontekst-meny (sett/fjern gruppe)
        self._tree.bind("<Button-3>", self._on_tree_right_click)

        # Tabell fylles via _deferred_initial_load etter at vinduet er
        # rendret. _load_client_data() kaller load_accounting_system per
        # klient (disk-IO) og er hovedårsaken til ~9 s oppstartsforsinkelse.

    def _build_deadlines_stub(self) -> None:
        stub = ttk.LabelFrame(self, text="Frister (kommer)", padding=8)
        stub.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 16))
        ttk.Label(stub, text="Ingen frister registrert.", style="Muted.TLabel").pack(padx=8, pady=8)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _deferred_initial_load(self) -> None:
        """Fyll klient-tabellen og recent-cards etter at vinduet er rendret.

        Kalles via ``self.after(50, …)`` fra ``__init__``. Idempotent — hvis
        andre kodeveier har trigget en lasting allerede (f.eks. via
        ``refresh()``), skjer ingenting.
        """
        if self._initial_load_done:
            return
        self._initial_load_done = True
        try:
            self._load_client_data()
            self._populate_client_table()
            self._populate_recent_cards()
        except Exception:
            log.exception("Oversikt: deferred initial load feilet")

    def _load_client_data(self) -> None:
        """Les metadata-indeks og bygg _all_client_rows."""
        meta_index = {}
        if self._client_meta_index:
            try:
                meta_index = self._client_meta_index.get_index()
            except Exception:
                pass

        # Regnskapssystem auto-utfylles ved SAF-T-import (jf.
        # pane_build.py:65). Tom for klienter uten SAF-T eller med
        # manuell Excel-import. Lazy import + try/except slik at
        # Oversikt fortsatt virker hvis modulen mangler.
        try:
            from src.shared.regnskap.client_overrides import load_accounting_system
        except Exception:
            load_accounting_system = lambda _c: ""  # type: ignore[assignment]

        # Klient-grupper (manuelt satt via høyreklikk). Tom dict hvis
        # ingen klienter har gruppe-tilordning.
        client_groups: dict[str, str] = {}
        if self._client_store_groups:
            try:
                client_groups = self._client_store_groups.load_groups()
            except Exception:
                client_groups = {}

        rows = []
        for name, meta in sorted(meta_index.items()):
            org = meta.get("org_number", "")
            knr = meta.get("client_number", "")
            ansvarlig = meta.get("responsible", "")
            manager = meta.get("manager", "")
            team_raw = str(meta.get("team_members", "") or "")
            # Visena gir ofte fler navn separert med newline — vis kompakt.
            team = ", ".join(
                part.strip() for part in team_raw.replace("\r", "\n").split("\n") if part.strip()
            )
            try:
                regnskapssystem = load_accounting_system(name)
            except Exception:
                regnskapssystem = ""
            gruppe = client_groups.get(name, "")
            rows.append((name, org, knr, ansvarlig, manager, regnskapssystem, team, gruppe))

        self._all_client_rows = rows

    def _populate_client_table(self) -> None:
        """Fyll Treeview basert pa filter."""
        self._tree.delete(*self._tree.get_children())

        mine_only = self._mine_only_var.get()
        search_text = self._search_var.get().strip().lower()
        if self._search_placeholder:
            search_text = ""

        # Mine klienter-filtrering
        my_initials = ""
        my_name = ""
        if mine_only and self._user:
            my_initials = self._user.visena_initials or ""
            my_name = self._user.full_name or ""

        count = 0
        for name, org, knr, ansvarlig, manager, regnskapssystem, team, gruppe in self._all_client_rows:
            # Mine-filter
            if mine_only:
                if not self._client_store_enrich:
                    continue
                meta = {
                    "visena_responsible": ansvarlig,
                    "visena_manager": manager,
                    "visena_team_members": team,
                }
                if not self._client_store_enrich.is_my_client(meta, my_initials, my_name):
                    continue

            # Sok-filter — gruppe inngår også slik at man kan filtrere på
            # gruppe-navn direkte i søkefeltet.
            if search_text:
                haystack = f"{name} {org} {knr} {ansvarlig} {manager} {regnskapssystem} {team} {gruppe}".lower()
                if search_text not in haystack:
                    continue

            # Bruker klient-navn som iid → enklere oppslag i høyreklikk-handler.
            self._tree.insert(
                "", "end", iid=name,
                values=(name, org, knr, ansvarlig, manager, regnskapssystem, team, gruppe),
            )
            count += 1

        self._lbl_count.configure(text=f"{count} klienter")

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_filter_changed(self) -> None:
        if self._preferences:
            try:
                self._preferences.set("oversikt.mine_only", bool(self._mine_only_var.get()))
            except Exception:
                pass
        self._populate_client_table()

    def _on_search(self) -> None:
        if self._search_placeholder:
            return
        self._populate_client_table()

    def _on_tree_double_click(self, event) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        values = self._tree.item(sel[0], "values")
        if values:
            self._navigate_to_client(values[0])

    def _on_tree_right_click(self, event) -> None:
        """Vis kontekst-meny for å sette/fjerne gruppe på valgte klienter.

        Hvis raden under cursoren ikke er i utvalget, byttes utvalget til
        bare den raden — slik at høyreklikk virker som man forventer
        (uten å måtte venstreklikke først).
        """
        row_iid = self._tree.identify_row(event.y)
        sel = list(self._tree.selection())
        if row_iid and row_iid not in sel:
            self._tree.selection_set(row_iid)
            sel = [row_iid]

        if not sel:
            return

        menu = tk.Menu(self._tree, tearoff=0)
        n = len(sel)
        label_set = "Sett gruppe…" if n == 1 else f"Sett gruppe på {n} valgte…"
        label_clear = "Fjern gruppe" if n == 1 else f"Fjern gruppe på {n} valgte"
        menu.add_command(label=label_set, command=self._open_set_group_dialog)
        menu.add_separator()
        menu.add_command(label=label_clear, command=self._clear_group_for_selection)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _selected_client_names(self) -> list[str]:
        return [iid for iid in self._tree.selection() if iid]

    def _open_set_group_dialog(self) -> None:
        """Modal dialog for å sette gruppe-navn på valgte klienter.

        Combobox lister eksisterende grupper (man kan velge eller skrive
        ny). Hvis alle valgte klientene allerede har samme gruppe, brukes
        denne som default i feltet.
        """
        names = self._selected_client_names()
        if not names or self._client_store_groups is None:
            return

        try:
            from src.shared.ui.dialog import make_dialog
        except Exception:
            return

        existing = self._client_store_groups.list_groups()
        current_groups = {n: dict(self._all_row_lookup()).get(n, "") for n in names}
        # Default-tekst: felles gruppe hvis alle har samme, ellers tomt.
        common = {g for g in current_groups.values() if g}
        default_value = current_groups[names[0]] if len(common) == 1 else ""

        dlg = make_dialog(
            self.winfo_toplevel(),
            title="Sett gruppe",
            width=420,
            height=200,
            modal=True,
        )

        body = ttk.Frame(dlg, padding=14)
        body.pack(fill="both", expand=True)

        if len(names) == 1:
            ttk.Label(body, text=f"Klient: {names[0]}").pack(anchor="w", pady=(0, 8))
        else:
            ttk.Label(body, text=f"{len(names)} klienter valgt").pack(anchor="w", pady=(0, 8))

        ttk.Label(body, text="Gruppe:").pack(anchor="w")
        var_group = tk.StringVar(value=default_value)
        combo = ttk.Combobox(body, textvariable=var_group, values=existing, width=40)
        combo.pack(fill="x", pady=(2, 0))
        combo.focus_set()

        ttk.Label(
            body,
            text="Velg eksisterende eller skriv inn ny gruppe. Tom verdi fjerner gruppen.",
            foreground="#888",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(6, 0))

        btn_row = ttk.Frame(dlg, padding=(14, 0, 14, 14))
        btn_row.pack(fill="x")

        def _save() -> None:
            new_group = var_group.get().strip()
            try:
                self._client_store_groups.set_groups_bulk(
                    {n: new_group for n in names}
                )
            except Exception as exc:
                log.warning("Kunne ikke lagre gruppe: %s", exc)
                return
            dlg.destroy()
            self._load_client_data()
            self._populate_client_table()
            for n in names:
                if self._tree.exists(n):
                    self._tree.selection_add(n)

        ttk.Button(btn_row, text="Avbryt", command=dlg.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Lagre", command=_save).pack(side="right")
        combo.bind("<Return>", lambda _e: _save())

    def _clear_group_for_selection(self) -> None:
        names = self._selected_client_names()
        if not names or self._client_store_groups is None:
            return
        try:
            self._client_store_groups.set_groups_bulk({n: "" for n in names})
        except Exception as exc:
            log.warning("Kunne ikke fjerne gruppe: %s", exc)
            return
        self._load_client_data()
        self._populate_client_table()
        for n in names:
            if self._tree.exists(n):
                self._tree.selection_add(n)

    def _all_row_lookup(self):
        """Returner iterable av (klient-navn, gruppe) for raskt oppslag."""
        for row in self._all_client_rows:
            # Tuple-orden: (name, org, knr, ansvarlig, manager, regnskapssystem, team, gruppe)
            yield row[0], row[7] if len(row) >= 8 else ""

    def _goto_active_client(self) -> None:
        """Naviger til aktiv klient (vist i headeren)."""
        try:
            dp = getattr(self._dataset_page, "dp", None)
            sec = getattr(dp, "_store_section", None) if dp else None
            if sec:
                name = (getattr(sec, "client_var", None) and sec.client_var.get() or "").strip()
                if name:
                    self._navigate_to_client(name)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate_to_client(self, name: str) -> None:
        """Sett klient i Dataset og bytt tab."""
        if not name:
            return

        # Oppdater recent
        if self._preferences:
            try:
                self._preferences.add_recent_client(name)
            except Exception:
                pass

        # Sett klient i Dataset-fanen
        try:
            dp = getattr(self._dataset_page, "dp", None)
            sec = getattr(dp, "_store_section", None) if dp else None
            if sec is not None:
                sec.client_var.set(name)
                if hasattr(sec, "_debounced_refresh"):
                    sec._debounced_refresh()
        except Exception:
            log.debug("Kunne ikke navigere til klient %s", name, exc_info=True)

        # Bytt til Dataset-fanen
        try:
            self._nb.select(self._dataset_page)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Refresh (kalles fra ui_main nar session oppdateres)
    # ------------------------------------------------------------------

    def refresh_from_session(self, session=None, **kw) -> None:
        """Oppdater oversikt etter at dataset er lastet."""
        # Oppdater aktiv klient i header
        try:
            client_name = getattr(session, "client", None) if session else None
            year = getattr(session, "year", None) if session else None
            if client_name:
                text = f"Aktiv: {client_name}"
                if year:
                    text += f" ({year})"
                self._lbl_active.configure(text=text)
                self._btn_goto_active.grid()
            else:
                self._lbl_active.configure(text="")
                self._btn_goto_active.grid_remove()
        except Exception:
            pass

        # Oppdater recent cards
        try:
            self._populate_recent_cards()
        except Exception:
            pass

        # Oppdater klienttabell (metadata kan ha endret seg)
        try:
            self._load_client_data()
            self._populate_client_table()
        except Exception:
            pass


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _relative_time(timestamp: float) -> str:
    """Konverter timestamp til lesbar relativ tid."""
    if not timestamp:
        return ""
    try:
        diff = time.time() - timestamp
        if diff < 60:
            return "Akkurat na"
        if diff < 3600:
            m = int(diff // 60)
            return f"{m} min siden"
        if diff < 86400:
            h = int(diff // 3600)
            return f"{h} {'time' if h == 1 else 'timer'} siden"
        days = int(diff // 86400)
        if days == 1:
            return "I gar"
        if days < 7:
            return f"{days} dager siden"
        weeks = days // 7
        if weeks == 1:
            return "1 uke siden"
        if weeks < 5:
            return f"{weeks} uker siden"
        return f"{days} dager siden"
    except Exception:
        return ""

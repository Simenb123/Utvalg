"""Revisjonshandlinger tab — shows audit actions from CRMSystem.

Read-only view of substantive and control audit procedures for the
active client, loaded from the shared CRM database.  Each action is
matched to a regnskapslinje (financial statement line) when possible.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

import action_assignment_store as assignment_store
import action_library
import action_workpaper_store as workpaper_store
import workpaper_library
from action_library import LocalAction
from action_workpaper_store import ActionWorkpaper
from workpaper_library import Workpaper


# Revisjonsprosessens faser. Vises som sidebar på Handlinger-fanen
# og gir et grunnleggende rammeverk å strukturere handlingsbiblioteket
# rundt. Rekkefølgen brukes i sidebar-visningen.
PHASE_ORDER: tuple[str, ...] = (
    "Oppdragsvurdering",
    "Planlegging",
    "Utførelse",
    "Avslutning",
)

# Keyword-heuristikk for å avlede fase fra handlings-tekst. Bruker
# navn + område (og action_type for CRM-handlinger) som input. Senere
# kan vi legge til eksplisitt ``fase``-felt på LocalAction og CRM-
# metadata istedenfor gjetting — men for visuell prototype er dette
# godt nok til å fylle sidebar-en med rimelige tall.
_PHASE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Oppdragsvurdering": (
        "oppdragsvurdering",
        "uavhengighet",
        "integrity",
        "aksept",
        "engagement",
    ),
    "Planlegging": (
        "innledende",
        "ib ub",
        "ib-ub",
        "vesentlighet",
        "klientinfo",
        "roller",
        "eier",
        "nærstående",
        "narstaende",
        "estimat",
        "scoping",
        "risiko",
        "planlegging",
    ),
    "Avslutning": (
        "avslutning",
        "completion",
        "konklusjon",
        "rapport",
        "fullstendighetserklæring",
        "fullstendighetserklaering",
        "subsequent",
        "disclosure",
        "engasjementsbrev",
    ),
}


def infer_phase(
    *,
    navn: str = "",
    omraade: str = "",
    action_type: str = "",
    explicit: str = "",
) -> str:
    """Avled fase fra handlingens tekst-felter.

    Hvis ``explicit`` er satt (f.eks. ``LocalAction.fase``), respekteres
    den uten gjetting. Ellers brukes keyword-heuristikk på navn/område/
    type. Default er "Utførelse" (substansive/kontroll-handlinger er
    hoved-arbeidet).
    """
    if explicit and explicit in PHASE_ORDER:
        return explicit
    haystack = f"{navn} {omraade} {action_type}".lower()
    for phase, keywords in _PHASE_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            return phase
    return "Utførelse"


class RevisjonshandlingerPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent, padding=0)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self._client: str | None = None
        self._year: str | None = None
        self._actions: list[Any] = []
        self._local_lib: list[LocalAction] = []
        self._workpaper_index: dict[str, Workpaper] = {}
        self._engagement: Any = None
        self._match_by_action_id: dict[int, Any] = {}  # action_id → ActionMatch
        self._local_assignments: dict[int, str] = {}  # action_id → "SB" / "SB, TN"
        self._local_link_counts: dict[int, int] = {}  # action_id → antall lokale koblinger
        self._workpapers: dict[int, ActionWorkpaper] = {}  # action_id → bekreftelse
        self._assignments: dict[str, str] = {}  # action_key → ansvarlig (initialer)
        self._rl_list: list[Any] = []  # cache av RegnskapslinjeInfo for dropdown
        self._rl_amounts: dict[int, float] = {}  # regnr → UB for inneværende år
        self._rl_scope: dict[str, str] = {}  # regnr (str) → "inn"/"ut"/"" (manuell override)
        self._analyse_page: Any = None  # settes av ui_main via set_analyse_page

        self.var_status = tk.StringVar(value="Last inn klient for å se revisjonshandlinger.")
        self.var_filter_type = tk.StringVar(value="Alle")
        self.var_filter_status = tk.StringVar(value="Alle")
        self.var_filter_area = tk.StringVar(value="Alle")
        self.var_filter_regnr = tk.StringVar(value="Alle")
        self.var_filter_origin = tk.StringVar(value="Alle")
        self.var_filter_phase = tk.StringVar(value="Alle")  # sidebar
        self.var_search = tk.StringVar()
        # Alle scoped regnskapslinjer vises som utgangspunkt; handlinger
        # "kobles på" der de finnes. RL uten handling vises alltid — det
        # er selve poenget med Handlinger-fanen nå som regnskapslinjer
        # (og ikke CRM-handlinger) er sannheten.
        self.var_show_rl_gaps = tk.BooleanVar(value=True)
        self._phase_sidebar_labels: dict[str, ttk.Label] = {}
        self._phase_sidebar_counts: dict[str, tk.StringVar] = {}

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── Top bar ──
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top.columnconfigure(10, weight=1)

        ttk.Label(top, textvariable=self.var_status, foreground="#667085").grid(row=0, column=0, sticky="w")
        self._btn_confirm = ttk.Button(
            top, text="Bekreft RL",
            command=self._on_confirm_current, state="disabled",
        )
        self._btn_confirm.grid(row=0, column=8, sticky="e", padx=(6, 0))
        self._btn_override = ttk.Button(
            top, text="Velg RL…",
            command=self._on_override_regnr, state="disabled",
        )
        self._btn_override.grid(row=0, column=9, sticky="e", padx=(6, 0))
        self._btn_clear = ttk.Button(
            top, text="Fjern bekreftelse",
            command=self._on_clear_confirmation, state="disabled",
        )
        self._btn_clear.grid(row=0, column=10, sticky="e", padx=(6, 0))
        self._btn_run_wp = ttk.Button(
            top, text="Kjør arbeidspapir…",
            command=self._on_run_workpaper, state="disabled",
        )
        self._btn_run_wp.grid(row=0, column=11, sticky="e", padx=(6, 0))
        ttk.Button(top, text="Oppdater", command=self._refresh).grid(row=0, column=12, sticky="e", padx=(6, 0))

        # Filters
        filt = ttk.Frame(self)
        filt.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 0))

        # Opprinnelse, Type, Status og Område-filtrene er fjernet —
        # handlingssettet drives nå av regnskapslinjer (scoped inn) og
        # fase-sidebar-en. Internvariablene beholdes på "Alle" som
        # no-op slik at render-hjelperne fortsatt slipper gjennom alt.
        # _cb_status / _cb_area refereres i _refresh() for å fylle opp
        # verdier; de blir satt til None her og _refresh guards mot det.
        self._cb_status = None
        self._cb_area = None

        ttk.Label(filt, text="Regnskapslinje:").pack(side="left")
        self._cb_regnr = ttk.Combobox(filt, textvariable=self.var_filter_regnr, state="readonly",
                                      values=["Alle"], width=28)
        self._cb_regnr.pack(side="left", padx=(2, 12))
        self._cb_regnr.bind("<<ComboboxSelected>>", lambda _: self._apply_filter())

        ttk.Label(filt, text="Søk:").pack(side="left")
        ent_search = ttk.Entry(filt, textvariable=self.var_search, width=20)
        ent_search.pack(side="left", padx=(2, 0))
        ent_search.bind("<KeyRelease>", lambda _: self._apply_filter())

        # "Vis RL uten handling"-togglen er fjernet — alle scoped RL
        # vises nå som default (var_show_rl_gaps=True hardkodet).

        # ── Body: sidebar med faser + tree ──
        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 0))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Venstre sidebar — revisjonsprosessens faser som navigasjons-
        # knapper. Klikk setter var_filter_phase og re-filtrerer treet.
        self._build_phase_sidebar(body)

        tree_frame = ttk.Frame(body)
        tree_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        # Standard tabell-oppsett via ManagedTreeview (sortering, kolonne-
        # synlighet/rekkefølge/bredde, høyreklikk-meny på header — alt
        # persisteres mellom økter). Se doc/TREEVIEW_PLAYBOOK.md.
        from ui_managed_treeview import ColumnSpec, ManagedTreeview
        column_specs = [
            ColumnSpec("opprinnelse",    heading="Opprinnelse",    width=80,  minwidth=60,  anchor="center"),
            ColumnSpec("regnr",          heading="Regnr",          width=50,  minwidth=40),
            ColumnSpec("regnskapslinje", heading="Regnskapslinje", width=180, minwidth=100),
            ColumnSpec("belop",          heading="Beløp",          width=110, minwidth=80,  anchor="e"),
            ColumnSpec("scope",          heading="Scope",          width=55,  minwidth=40,  anchor="center"),
            ColumnSpec("kilde",          heading="Kilde",          width=90,  minwidth=70,  anchor="center"),
            ColumnSpec("omraade",        heading="Område",         width=150, minwidth=80),
            ColumnSpec("type",           heading="Type",           width=90,  minwidth=60),
            ColumnSpec("handling",       heading="Handling",       width=300, minwidth=150, stretch=True),
            ColumnSpec("timing",         heading="Timing",         width=80,  minwidth=50),
            ColumnSpec("eier",           heading="Eier (CRM)",     width=130, minwidth=80),
            ColumnSpec("ansvarlig",      heading="Ansvarlig",      width=80,  minwidth=60,  anchor="center"),
            ColumnSpec("tilordnet",      heading="Tilordnet",      width=80,  minwidth=60,  anchor="center"),
            ColumnSpec("status",         heading="Status",         width=100, minwidth=60),
            ColumnSpec("frist",          heading="Frist",          width=90,  minwidth=70),
        ]
        col_ids = tuple(spec.id for spec in column_specs)
        self._tree = ttk.Treeview(tree_frame, columns=col_ids, show="headings", selectmode="extended")
        self._managed_tree = ManagedTreeview(
            self._tree,
            view_id="revisjonshandlinger",
            column_specs=column_specs,
            on_body_right_click=self._on_tree_right_click,
        )

        self._tree.tag_configure("wp_confirmed", background="#E6F4EA")
        self._tree.tag_configure("wp_auto", background="#FFFFFF")
        self._tree.tag_configure("wp_unmatched", background="#FFF4DD")
        self._tree.tag_configure("wp_local", background="#EEF2FF")
        self._tree.tag_configure("rl_gap", background="#FAFAFA", foreground="#888888")

        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=yscroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", self._on_double_click)

        # ── Detail panel ──
        detail = ttk.LabelFrame(self, text="Detaljer", padding=6)
        detail.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 8))
        detail.columnconfigure(0, weight=1)

        self._detail_var = tk.StringVar(value="")
        self._detail_text = tk.Text(
            detail, height=6, wrap="word", relief="flat",
            background="#FFFFFF", borderwidth=0, highlightthickness=0,
        )
        self._detail_text.configure(state="disabled")
        detail_scroll = ttk.Scrollbar(detail, orient="vertical", command=self._detail_text.yview)
        self._detail_text.configure(yscrollcommand=detail_scroll.set)
        self._detail_text.grid(row=0, column=0, sticky="nsew")
        detail_scroll.grid(row=0, column=1, sticky="ns")

        def _sync_detail(*_args: object) -> None:
            self._detail_text.configure(state="normal")
            self._detail_text.delete("1.0", "end")
            self._detail_text.insert("1.0", self._detail_var.get())
            self._detail_text.configure(state="disabled")

        self._detail_var.trace_add("write", _sync_detail)

    # ------------------------------------------------------------------
    # Fase-sidebar
    # ------------------------------------------------------------------

    def _build_phase_sidebar(self, parent: ttk.Frame) -> None:
        """Bygg venstre sidebar med revisjonsfaser.

        Består av et "Alle"-punkt øverst, en skillelinje, og deretter
        de fire revisjonsfasene. Hver rad er en Label med tall-badge
        til høyre; klikk setter var_filter_phase og kjører filteret.
        """
        sidebar = ttk.Frame(parent, padding=(0, 0, 0, 0))
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.configure(width=200)

        # Toppheading
        ttk.Label(
            sidebar,
            text="Revisjonsprosess",
            font=("Segoe UI", 10, "bold"),
            foreground="#344054",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=(2, 6))

        # "Alle"-oppføring + faser
        entries: list[tuple[str, str]] = [("Alle", "Alle faser")]
        entries.extend((p, p) for p in PHASE_ORDER)

        for idx, (key, label) in enumerate(entries, start=1):
            row = ttk.Frame(sidebar, padding=(6, 4))
            row.grid(row=idx, column=0, columnspan=2, sticky="ew", pady=(0, 2))
            row.columnconfigure(0, weight=1)

            name_lbl = ttk.Label(row, text=label, anchor="w")
            name_lbl.grid(row=0, column=0, sticky="ew")

            count_var = tk.StringVar(value="")
            count_lbl = ttk.Label(
                row, textvariable=count_var, anchor="e",
                foreground="#667085",
            )
            count_lbl.grid(row=0, column=1, sticky="e", padx=(6, 0))

            # Holdt referanser slik at vi kan oppdatere highlight/tall
            # senere. Bruker key som identifikator.
            self._phase_sidebar_labels[key] = name_lbl
            self._phase_sidebar_counts[key] = count_var

            # Klikk-region: både raden, navn og badge er klikkbar.
            def _make_handler(k: str):
                return lambda _e=None: self._on_phase_selected(k)

            for w in (row, name_lbl, count_lbl):
                w.bind("<Button-1>", _make_handler(key))

            # Skillelinje etter "Alle"-raden
            if key == "Alle":
                sep = ttk.Separator(sidebar, orient="horizontal")
                sep.grid(row=idx * 10, column=0, columnspan=2, sticky="ew", pady=(2, 4))

        # Initial highlight
        self._update_phase_highlight()

    def _on_phase_selected(self, phase_key: str) -> None:
        self.var_filter_phase.set(phase_key)
        self._update_phase_highlight()
        self._apply_filter()

    def _update_phase_highlight(self) -> None:
        """Marker aktiv fase i sidebar-en ved å fete teksten."""
        active = self.var_filter_phase.get() or "Alle"
        for key, lbl in self._phase_sidebar_labels.items():
            try:
                if key == active:
                    lbl.configure(font=("Segoe UI", 10, "bold"), foreground="#1F6FEB")
                else:
                    lbl.configure(font=("Segoe UI", 10, "normal"), foreground="#1F2937")
            except Exception:
                pass

    def _update_phase_counts(self) -> None:
        """Oppdater tall-badgene i sidebar-en basert på tilgjengelige handlinger.

        CRM-handlinger telles ikke med — de vises ikke i listen lenger,
        så å inkludere dem i tellingen ville gitt forvirrende tall.
        Lokale handlinger fra appen og scopede regnskapslinjer er
        det som faktisk vises.
        """
        counts: dict[str, int] = {p: 0 for p in ("Alle", *PHASE_ORDER)}
        for item in self._local_lib:
            p = infer_phase(
                navn=getattr(item, "navn", "") or "",
                omraade=getattr(item, "omraade", "") or "",
                action_type=getattr(item, "type", "") or "",
                explicit=getattr(item, "fase", "") or "",
            )
            counts[p] = counts.get(p, 0) + 1
            counts["Alle"] += 1
        for key, var in self._phase_sidebar_counts.items():
            try:
                n = counts.get(key, 0)
                var.set(str(n) if n else "")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def on_client_changed(self, client: str | None, year: str | None) -> None:
        self._client = client
        self._year = year
        self._refresh()

    def set_analyse_page(self, page: Any) -> None:
        """Gjør AnalysePage tilgjengelig for innebygde arbeidspapir-generatorer."""
        self._analyse_page = page
        self._update_action_buttons()

    def filter_by_regnr(self, regnr: int | str | None) -> None:
        """Sett regnskapslinje-filteret til matchende verdi og kjør filter."""
        if regnr in (None, ""):
            self.var_filter_regnr.set("Alle")
            self._apply_filter()
            return
        target = str(regnr).strip()
        values = self._cb_regnr.cget("values") or []
        match = "Alle"
        for val in values:
            head = str(val).split()[0] if val else ""
            if head == target:
                match = str(val)
                break
        self.var_filter_regnr.set(match)
        self._apply_filter()

    def _refresh(self) -> None:
        # Lokalt bibliotek lastes alltid (uavhengig av klient)
        try:
            self._local_lib = action_library.load_library()
        except Exception:
            self._local_lib = []
        try:
            self._workpaper_index = workpaper_library.by_id(workpaper_library.list_all())
        except Exception:
            self._workpaper_index = {}

        if not self._client or not self._year:
            self._actions = []
            self._engagement = None
            self._match_by_action_id = {}
            self._workpapers = {}
            self._assignments = {}
            self._rl_list = []
            self._rl_amounts = {}
            self._rl_scope = {}
            self._detail_var.set("")
            if self._local_lib:
                if self._cb_area is not None:
                    self._cb_area.configure(values=["Alle"] + sorted({a.omraade for a in self._local_lib if a.omraade}))
                if self._cb_status is not None:
                    self._cb_status.configure(values=["Alle"])
                self._cb_regnr.configure(values=["Alle", "Uten match"])
                self._apply_filter()
                self.var_status.set(f"{len(self._local_lib)} lokale handling(er). Last inn klient for CRM-handlinger.")
            else:
                self._tree.delete(*self._tree.get_children())
                self.var_status.set("Last inn klient for å se revisjonshandlinger.")
            self._update_action_buttons()
            return

        self.var_status.set("Henter handlinger fra CRM ...")
        self.update_idletasks()

        try:
            from crmsystem_actions import load_audit_actions
            result = load_audit_actions(self._client, self._year)
        except Exception as exc:
            self.var_status.set(f"Feil: {exc}")
            return

        if result.error:
            self.var_status.set(result.error)
            self._actions = []
            self._engagement = None
            self._match_by_action_id = {}
            self._tree.delete(*self._tree.get_children())
            return

        self._engagement = result.engagement
        self._actions = result.actions

        # Run regnskapslinje matching
        self._match_by_action_id = {}
        self._run_matching()

        # Load workpaper confirmations (revisors overstyringer)
        try:
            self._workpapers = workpaper_store.load_workpapers(self._client, self._year)
        except Exception:
            self._workpapers = {}

        # Load local assignments (konto- og RL-koblinger per action_id)
        self._load_local_assignments()

        # Load direct handling-ansvar (per action_key)
        try:
            self._assignments = assignment_store.load_assignments(self._client, self._year)
        except Exception:
            self._assignments = {}

        # Beløp per regnr (fra aktiv SB) + scoping-overstyringer
        self._reload_rl_context()

        # Filter-dropdowns for Område og Status er fjernet; beholder
        # None-guarden slik at tidligere kall ikke krasjer om widgetene
        # gjeninnføres senere.
        if self._cb_area is not None:
            areas = sorted({a.area_name for a in self._actions if a.area_name} |
                           {a.omraade for a in self._local_lib if a.omraade})
            self._cb_area.configure(values=["Alle"] + areas)
        if self._cb_status is not None:
            statuses = sorted({a.status for a in self._actions if a.status})
            self._cb_status.configure(values=["Alle"] + statuses)

        # Build regnr filter values
        regnr_labels = sorted(
            {f"{m.regnr} {m.regnskapslinje}" for m in self._match_by_action_id.values() if m.regnr},
            key=lambda s: int(s.split()[0]) if s.split()[0].isdigit() else 0,
        )
        self._cb_regnr.configure(values=["Alle", "Uten match"] + regnr_labels)

        self._apply_filter()

        n = len(self._actions)
        matched = sum(1 for m in self._match_by_action_id.values() if m.regnr)
        eng = result.engagement
        label = f"{eng.client_name} ({eng.client_number}) — {eng.engagement_name} — {n} handlinger ({matched} matchet)"
        self.var_status.set(label)

    def _reload_rl_context(self) -> None:
        """Last beløp per regnskapslinje + scoping-overstyringer for året."""
        self._rl_amounts = {}
        self._rl_scope = {}
        if not self._client or not self._year:
            return
        try:
            import page_analyse_rl_data as _rl_data
            self._rl_amounts = _rl_data.load_rl_amounts() or {}
        except Exception:
            self._rl_amounts = {}
        try:
            import src.pages.scoping.backend.store as scoping_store
            overrides = scoping_store.load_overrides(self._client, self._year) or {}
        except Exception:
            overrides = {}
        for regnr_key, entry in overrides.items():
            try:
                scope = str((entry or {}).get("scoping") or "").strip().lower()
            except Exception:
                scope = ""
            if scope in ("inn", "ut"):
                self._rl_scope[str(regnr_key).strip()] = scope

    def _format_amount(self, regnr: str) -> str:
        if not regnr:
            return ""
        try:
            value = self._rl_amounts.get(int(regnr))
        except Exception:
            return ""
        if value is None:
            return ""
        try:
            return f"{value:,.0f}".replace(",", " ")
        except Exception:
            return str(value)

    def _format_scope(self, regnr: str) -> str:
        if not regnr:
            return ""
        scope = self._rl_scope.get(str(regnr).strip(), "")
        if scope == "inn":
            return "✓"
        if scope == "ut":
            return "–"
        return ""

    def _load_local_assignments(self) -> None:
        """Samle ``assigned_to`` per action_id fra konto- og RL-koblinger."""
        self._local_assignments = {}
        self._local_link_counts = {}
        if not self._client or not self._year:
            return
        try:
            import regnskap_client_overrides as _rco
        except Exception:
            return
        try:
            account_map = _rco.load_account_action_links(self._client, self._year)
        except Exception:
            account_map = {}
        try:
            rl_map = _rco.load_rl_action_links(self._client, self._year)
        except Exception:
            rl_map = {}

        per_action: dict[int, list[str]] = {}
        counts: dict[int, int] = {}
        for links in list(account_map.values()) + list(rl_map.values()):
            for lnk in links:
                try:
                    aid = int(lnk.get("action_id") or 0)
                except Exception:
                    continue
                if aid <= 0:
                    continue
                counts[aid] = counts.get(aid, 0) + 1
                assigned = str(lnk.get("assigned_to") or "").strip().upper()
                if assigned:
                    per_action.setdefault(aid, [])
                    if assigned not in per_action[aid]:
                        per_action[aid].append(assigned)
        self._local_assignments = {aid: ", ".join(vals) for aid, vals in per_action.items()}
        self._local_link_counts = counts

    def _run_matching(self) -> None:
        """Match actions to regnskapslinjer."""
        try:
            from crmsystem_action_matching import (
                RegnskapslinjeInfo,
                match_actions_to_regnskapslinjer,
            )
            from regnskap_config import load_regnskapslinjer

            df = load_regnskapslinjer()
            rl_list = []
            for _, row in df.iterrows():
                rb = str(row.get("resultat/balanse", "")).strip().lower()
                if rb.startswith("res"):
                    lt = "PL"
                elif rb.startswith("bal"):
                    lt = "BS"
                else:
                    lt = ""
                rl_list.append(RegnskapslinjeInfo(
                    nr=str(row["nr"]).strip(),
                    regnskapslinje=str(row["regnskapslinje"]).strip(),
                    line_type=lt,
                ))
            matches = match_actions_to_regnskapslinjer(self._actions, rl_list)
            self._match_by_action_id = {m.action.action_id: m for m in matches}
            self._rl_list = rl_list
        except Exception:
            # Matching is optional — don't block the tab if it fails
            self._match_by_action_id = {}
            self._rl_list = []

    def _apply_filter(self) -> None:
        self._tree.delete(*self._tree.get_children())

        # Oppdater tall-badgene i fase-sidebar-en så de speiler det
        # aktuelle datasettet (hendelsene telles før selve filtreringen).
        self._update_phase_counts()

        type_filter = self.var_filter_type.get()
        status_filter = self.var_filter_status.get()
        area_filter = self.var_filter_area.get()
        regnr_filter = self.var_filter_regnr.get()
        origin_filter = self.var_filter_origin.get()
        phase_filter = self.var_filter_phase.get() or "Alle"
        search = self.var_search.get().strip().lower()
        self._current_phase_filter = phase_filter  # leses av render-hjelperne

        shown = 0
        covered_regnr: set[str] = set()
        # CRM-handlinger skjules fra visningen — regnskapslinjer er
        # primær struktur, og handlinger fra det lokale biblioteket
        # (admin-fanen) skal ta over som sekundær info per RL.
        # Dataene lastes fortsatt slik at vi kan koble dem på igjen
        # senere uten ny implementasjon. Render-kallet er bevisst
        # utkommentert; _render_crm_rows-funksjonen er urørt.
        # Lokale handlinger vises som før (filtrert på fase).
        if origin_filter in ("Alle", "Lokal"):
            shown += self._render_local_rows(
                type_filter, status_filter, area_filter, regnr_filter, search,
                covered=covered_regnr,
            )

        # RL-rader (regnskapslinjer i scope) hører til Utførelse-fasen.
        # Siden CRM-handlinger ikke lenger renderes, er covered_regnr
        # bevisst tom her — alle scoped-IN RLs vises som rader (ikke
        # bare "gap"-rader).
        gap_rows = 0
        rl_phases = {"Alle", "Utførelse"}
        if self.var_show_rl_gaps.get() and phase_filter in rl_phases:
            gap_rows = self._render_rl_gap_rows(covered_regnr)

        # Update status — CRM-handlinger telles ikke i total siden de
        # ikke renderes lenger. shown teller bare lokale handlinger;
        # gap_rows er antall regnskapslinjer som vises som rader.
        total = len(self._local_lib)
        if self._engagement:
            extra = f"  +{gap_rows} regnskapslinjer" if gap_rows else ""
            self.var_status.set(
                f"{self._engagement.client_name} — viser {shown} av {total} handlinger{extra}"
            )

        # ManagedTreeview re-applikerer sortering automatisk på header-
        # klikk; den kalles etter at rader er populert via Treeview-events.

    def _render_crm_rows(self, type_filter, status_filter, area_filter, regnr_filter, search,
                         *, covered: set[str] | None = None) -> int:
        shown = 0
        phase_filter = getattr(self, "_current_phase_filter", "Alle")
        for a in self._actions:
            if type_filter != "Alle" and a.action_type != type_filter:
                continue
            if status_filter != "Alle" and a.status != status_filter:
                continue
            if area_filter != "Alle" and a.area_name != area_filter:
                continue
            if phase_filter != "Alle":
                p = infer_phase(
                    navn=getattr(a, "procedure_name", "") or "",
                    omraade=getattr(a, "area_name", "") or "",
                    action_type=getattr(a, "action_type", "") or "",
                )
                if p != phase_filter:
                    continue

            # Regnskapslinje (bekreftet > auto)
            match = self._match_by_action_id.get(a.action_id)
            auto_regnr = match.regnr if match else ""
            auto_rl = match.regnskapslinje if match else ""
            regnr, rl_name, source = workpaper_store.resolve_effective_regnr(
                a.action_id, auto_regnr, auto_rl, self._workpapers,
            )

            if regnr_filter == "Uten match" and regnr:
                continue
            if regnr_filter not in ("Alle", "Uten match"):
                filter_nr = regnr_filter.split()[0] if regnr_filter else ""
                if regnr != filter_nr:
                    continue

            if search and search not in a.procedure_name.lower() and search not in a.area_name.lower() and search not in (a.owner or "").lower():
                continue

            status_display = a.status or ""
            tilordnet = self._local_assignments.get(a.action_id, "")
            ansvarlig = self._assignments.get(str(a.action_id), "")
            kilde_label = {
                "confirmed": "bekreftet",
                "auto": "auto",
            }.get(source, "")
            tag = {
                "confirmed": "wp_confirmed",
                "auto": "wp_auto",
            }.get(source, "wp_unmatched")
            self._tree.insert("", "end", iid=str(a.action_id), values=(
                "CRM",
                regnr,
                rl_name,
                self._format_amount(regnr),
                self._format_scope(regnr),
                kilde_label,
                a.area_name,
                a.action_type,
                a.procedure_name,
                a.timing,
                a.owner,
                ansvarlig,
                tilordnet,
                status_display,
                a.due_date,
            ), tags=(tag,))
            if covered is not None and regnr:
                covered.add(str(regnr).strip())
            shown += 1
        return shown

    def _resolve_local_action_rls(self, item: LocalAction) -> list[tuple[str, str]]:
        """Returner [(regnr, regnskapslinje), …] som handlingen er relevant for.

        Bruker applies_to_scope/applies_to_regnr/default_regnr i nevnt
        rekkefølge. Returnerer tom liste hvis ingen RL er valgt og det
        ikke finnes default — handlingen vises da som én rad uten regnr.
        """
        scope = (getattr(item, "applies_to_scope", "") or "").strip().lower()
        applies_list = list(getattr(item, "applies_to_regnr", []) or [])
        if scope or applies_list:
            out: list[tuple[str, str]] = []
            seen: set[str] = set()
            for rl in self._rl_list:
                nr = str(getattr(rl, "nr", "") or "").strip()
                if not nr or nr in seen:
                    continue
                line_type = str(getattr(rl, "line_type", "") or "")
                if item.applies_to(nr, line_type):
                    out.append((nr, str(getattr(rl, "regnskapslinje", "") or "")))
                    seen.add(nr)
            return out
        if item.default_regnr:
            navn = ""
            for rl in self._rl_list:
                if str(getattr(rl, "nr", "") or "").strip() == str(item.default_regnr).strip():
                    navn = str(getattr(rl, "regnskapslinje", "") or "")
                    break
            return [(str(item.default_regnr).strip(), navn)]
        return []

    def _render_local_rows(self, type_filter, status_filter, area_filter, regnr_filter, search,
                           *, covered: set[str] | None = None) -> int:
        shown = 0
        phase_filter = getattr(self, "_current_phase_filter", "Alle")
        for item in self._local_lib:
            if type_filter != "Alle" and item.type != type_filter:
                continue
            if status_filter != "Alle":
                continue  # lokale har ingen CRM-status
            if area_filter != "Alle" and item.omraade != area_filter:
                continue
            if phase_filter != "Alle":
                p = infer_phase(
                    navn=getattr(item, "navn", "") or "",
                    omraade=getattr(item, "omraade", "") or "",
                    action_type=getattr(item, "type", "") or "",
                    explicit=getattr(item, "fase", "") or "",
                )
                if p != phase_filter:
                    continue
            if search and search not in item.navn.lower() and search not in item.omraade.lower():
                continue

            rl_targets = self._resolve_local_action_rls(item)
            filter_nr = ""
            if regnr_filter not in ("", "Alle", "Uten match"):
                filter_nr = regnr_filter.split()[0] if regnr_filter else ""

            if not rl_targets:
                if regnr_filter not in ("Alle", "Uten match"):
                    continue
                iid = f"L:{item.id}"
                ansvarlig = self._assignments.get(iid, "")
                self._tree.insert("", "end", iid=iid, values=(
                    "Lokal", "", "",
                    "", "",
                    "", item.omraade, item.type, item.navn,
                    "", "", ansvarlig, "", "", "",
                ), tags=("wp_local",))
                shown += 1
                continue

            if regnr_filter == "Uten match":
                continue

            for regnr, rl_name in rl_targets:
                if filter_nr and regnr != filter_nr:
                    continue
                iid = f"L:{item.id}:{regnr}" if len(rl_targets) > 1 else f"L:{item.id}"
                ansvarlig = self._assignments.get(iid, "")
                self._tree.insert("", "end", iid=iid, values=(
                    "Lokal",
                    regnr,
                    rl_name,
                    self._format_amount(regnr),
                    self._format_scope(regnr),
                    "",
                    item.omraade,
                    item.type,
                    item.navn,
                    "",
                    "",
                    ansvarlig,
                    "",
                    "",
                    "",
                ), tags=("wp_local",))
                if covered is not None and regnr:
                    covered.add(str(regnr).strip())
                shown += 1
        return shown

    def _render_rl_gap_rows(self, covered: set[str]) -> int:
        """Vis RL-er som ikke er truffet av noen filtrert handling."""
        if not self._rl_list:
            return 0
        regnr_filter = self.var_filter_regnr.get()
        search = self.var_search.get().strip().lower()

        # Hopp over rader som ikke matcher regnr-filteret hvis aktivt.
        filter_nr = ""
        if regnr_filter not in ("", "Alle", "Uten match"):
            filter_nr = regnr_filter.split()[0] if regnr_filter else ""

        added = 0
        seen: set[str] = set()
        for rl in self._rl_list:
            nr = str(getattr(rl, "nr", "") or "").strip()
            name = str(getattr(rl, "regnskapslinje", "") or "")
            if not nr or nr in covered or nr in seen:
                continue
            seen.add(nr)
            if filter_nr and nr != filter_nr:
                continue
            if search and search not in name.lower() and search not in nr.lower():
                continue
            try:
                amount = self._rl_amounts.get(int(nr))
            except (ValueError, TypeError):
                amount = None
            if not amount:
                continue
            iid = f"RL:{nr}"
            self._tree.insert("", "end", iid=iid, values=(
                "—",            # opprinnelse
                nr,
                name,
                self._format_amount(nr),
                self._format_scope(nr),
                "",             # kilde
                "",             # omraade
                "",             # type
                "(ingen handling — dobbeltklikk for å koble)",
                "",             # timing
                "",             # eier
                "",             # ansvarlig
                "",             # tilordnet
                "",             # status
                "",             # frist
            ), tags=("rl_gap",))
            added += 1
        return added

    @staticmethod
    def _local_action_id_from_iid(iid: str) -> str:
        """Pakk ut LocalAction.id fra iid på formen ``L:<id>`` eller
        ``L:<id>:<regnr>`` (multi-RL). UUID-id-er inneholder ikke ``:``
        så split på første kolon er trygt."""
        if not iid.startswith("L:"):
            return ""
        return iid[2:].split(":", 1)[0]

    def _on_select(self, _event: tk.Event | None = None) -> None:
        sel = self._tree.selection()
        if not sel:
            self._detail_var.set("")
            self._update_action_buttons()
            return

        if len(sel) > 1:
            self._detail_var.set(
                f"{len(sel)} handlinger valgt. Høyreklikk for å tilordne ansvarlig."
            )
            self._update_action_buttons()
            return

        iid = sel[0]
        if iid.startswith("RL:"):
            nr = iid[3:]
            name = next(
                (str(getattr(rl, "regnskapslinje", "") or "") for rl in self._rl_list
                 if str(getattr(rl, "nr", "") or "").strip() == nr),
                "",
            )
            beløp = self._format_amount(nr)
            scope = self._format_scope(nr) or "(ikke satt)"
            lines = [
                f"Regnskapslinje {nr} {name}",
                f"Beløp: {beløp}" if beløp else "Beløp: (ikke tilgjengelig)",
                f"Scope: {scope}",
                "",
                "Ingen handling koblet til denne regnskapslinjen.",
                "Dobbeltklikk for å åpne kobling-dialog.",
            ]
            self._detail_var.set("\n".join(lines))
            self._update_action_buttons()
            return

        if iid.startswith("L:"):
            item = next((x for x in self._local_lib if x.id == self._local_action_id_from_iid(iid)), None)
            if item is None:
                self._detail_var.set("")
            else:
                lines = [f"[Lokal] {item.omraade or '\u2013'}  /  {item.navn}"]
                lines.append(f"Type: {item.type}")
                if item.default_regnr:
                    lines.append(f"Default regnr: {item.default_regnr}")
                if item.workpaper_ids:
                    names = []
                    for wid in item.workpaper_ids:
                        wp = self._workpaper_index.get(wid)
                        names.append(wp.navn if wp else f"[mangler {wid[:8]}\u2026]")
                    lines.append(f"Arbeidspapir: {', '.join(names)}")
                if item.beskrivelse:
                    lines.append("")
                    lines.append(item.beskrivelse)
                self._detail_var.set("\n".join(lines))
            self._update_action_buttons()
            return

        action_id = int(iid)
        action = next((a for a in self._actions if a.action_id == action_id), None)
        if not action:
            self._detail_var.set("")
            self._update_action_buttons()
            return

        lines = [f"{action.area_name}  /  {action.procedure_name}"]

        # Show match info (auto)
        match = self._match_by_action_id.get(action.action_id)
        if match and match.regnr:
            method_labels = {"prefix": "nummerprefix", "alias": "nøkkelord", "fuzzy": "fuzzy-match"}
            method_label = method_labels.get(match.match_method, match.match_method)
            lines.append(
                f"Auto-match: {match.regnr} {match.regnskapslinje}  "
                f"({method_label}, {match.confidence:.0%})"
            )
        else:
            lines.append("Auto-match: (ingen)")

        # Show workpaper confirmation
        wp = self._workpapers.get(action.action_id)
        if wp:
            rl_part = f" {wp.confirmed_regnskapslinje}" if wp.confirmed_regnskapslinje else ""
            who = f" av {wp.confirmed_by}" if wp.confirmed_by else ""
            when = f" ({wp.confirmed_at})" if wp.confirmed_at else ""
            lines.append(f"Bekreftet: {wp.confirmed_regnr}{rl_part}{who}{when}")
            if wp.note:
                lines.append(f"Notat: {wp.note}")

        if action.owner:
            lines.append(f"Eier (CRM): {action.owner}")
        ansvarlig = self._assignments.get(str(action.action_id), "")
        if ansvarlig:
            lines.append(f"Ansvarlig: {ansvarlig}")
        tilordnet = self._local_assignments.get(action.action_id, "")
        if tilordnet:
            n_links = self._local_link_counts.get(action.action_id, 0)
            suffix = f" ({n_links} lokale koblinger)" if n_links else ""
            lines.append(f"Tilordnet lokalt: {tilordnet}{suffix}")
        if action.timing:
            lines.append(f"Timing: {action.timing}")
        if action.status:
            lines.append(f"Status: {action.status}")
        if action.due_date:
            lines.append(f"Frist: {action.due_date}")
        if action.comments:
            lines.append("")
            lines.append("Kommentarer:")
            for c in action.comments:
                by = f" ({c.created_by})" if c.created_by else ""
                lines.append(f"  {c.created_at}{by}: {c.comment}")

        self._detail_var.set("\n".join(lines))
        self._update_action_buttons()

    # ------------------------------------------------------------------
    # Workpaper actions
    # ------------------------------------------------------------------

    def _update_action_buttons(self) -> None:
        sel = self._tree.selection()
        iid = sel[0] if sel else ""

        def _state(enabled: bool) -> str:
            return "normal" if enabled else "disabled"

        # Multiselect: knappene jobber på én rad om gangen — deaktiver dem
        # når mer enn én er valgt. Tilordn-ansvarlig (høyreklikk) håndterer
        # bulk-handlinger separat.
        if len(sel) > 1:
            self._btn_confirm.configure(state="disabled")
            self._btn_override.configure(state="disabled")
            self._btn_clear.configure(state="disabled")
            self._btn_run_wp.configure(state="disabled")
            return

        if iid.startswith("RL:"):
            self._btn_confirm.configure(state="disabled")
            self._btn_override.configure(state="disabled")
            self._btn_clear.configure(state="disabled")
            self._btn_run_wp.configure(state="disabled")
            return

        if iid.startswith("L:"):
            # Lokale handlinger støtter ikke bekreftelse/overstyring mot CRM workpaper-store
            self._btn_confirm.configure(state="disabled")
            self._btn_override.configure(state="disabled")
            self._btn_clear.configure(state="disabled")
            item = next((x for x in self._local_lib if x.id == self._local_action_id_from_iid(iid)), None)
            has_builtin = bool(item) and any(
                workpaper_library.is_builtin(w) for w in (item.workpaper_ids if item else [])
            )
            self._btn_run_wp.configure(state=_state(has_builtin and self._analyse_page is not None))
            return
        action_id = int(iid) if iid else 0
        match = self._match_by_action_id.get(action_id) if action_id else None
        has_auto = bool(match and match.regnr)
        has_wp = action_id in self._workpapers
        client_ready = bool(self._client and self._year)

        self._btn_confirm.configure(state=_state(client_ready and action_id > 0 and has_auto))
        self._btn_override.configure(state=_state(client_ready and action_id > 0 and bool(self._rl_list)))
        self._btn_clear.configure(state=_state(client_ready and has_wp))
        self._btn_run_wp.configure(state="disabled")

    def _selected_action(self):
        sel = self._tree.selection()
        if not sel:
            return None
        iid = sel[0]
        if iid.startswith("L:"):
            return None
        action_id = int(iid)
        return next((a for a in self._actions if a.action_id == action_id), None)

    def _selected_local_action(self) -> LocalAction | None:
        sel = self._tree.selection()
        if not sel:
            return None
        iid = sel[0]
        if not iid.startswith("L:"):
            return None
        return next((x for x in self._local_lib if x.id == self._local_action_id_from_iid(iid)), None)

    def _on_run_workpaper(self) -> None:
        item = self._selected_local_action()
        if item is None or self._analyse_page is None:
            return
        import workpaper_generators

        builtins = [
            workpaper_generators.find_builtin(wid)
            for wid in item.workpaper_ids
            if workpaper_library.is_builtin(wid)
        ]
        builtins = [g for g in builtins if g is not None]
        if not builtins:
            messagebox.showinfo(
                "Ingen innebygde arbeidspapir",
                "Denne handlingen har ingen innebygde arbeidspapir koblet.",
                parent=self,
            )
            return
        if len(builtins) == 1:
            self._invoke_builtin(builtins[0])
            return
        self._open_run_picker(builtins)

    def _open_run_picker(self, builtins: list[Any]) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Kjør arbeidspapir")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.columnconfigure(0, weight=1)
        dlg.rowconfigure(0, weight=1)

        frm = ttk.Frame(dlg, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(0, weight=1)

        lb = tk.Listbox(frm, height=min(10, len(builtins)), exportselection=False)
        lb.grid(row=0, column=0, sticky="nsew")
        for g in builtins:
            lb.insert("end", g.navn)
        lb.selection_set(0)

        btns = ttk.Frame(frm)
        btns.grid(row=1, column=0, sticky="e", pady=(8, 0))

        def _run() -> None:
            sel = lb.curselection()
            if not sel:
                return
            g = builtins[sel[0]]
            dlg.destroy()
            self._invoke_builtin(g)

        ttk.Button(btns, text="Avbryt", command=dlg.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Kjør", command=_run).pack(side="right")

    def _invoke_builtin(self, generator: Any) -> None:
        if self._analyse_page is None:
            messagebox.showwarning(
                "Analyse ikke klar",
                "Analyse-fanen er ikke initialisert. Prøv igjen etter at Analyse er lastet.",
                parent=self,
            )
            return
        method = getattr(self._analyse_page, generator.method_name, None)
        if not callable(method):
            messagebox.showerror(
                "Generator mangler",
                f"Metoden {generator.method_name} finnes ikke på Analyse-siden.",
                parent=self,
            )
            return

        action_key = self._current_action_key()
        before = self._snapshot_exports_dir()
        ctx = self._build_action_context(action_key=action_key, generator=generator)
        try:
            if ctx is not None:
                import action_context as _ctx
                with _ctx.push(ctx):
                    method()
            else:
                method()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Feil ved kjøring",
                f"Kjøring av «{generator.navn}» feilet: {exc}",
                parent=self,
            )
            return
        if action_key and self._client and self._year:
            self._register_new_artifacts(
                action_key=action_key,
                generator=generator,
                before=before,
            )

    def _build_action_context(self, *, action_key: str, generator: Any) -> Any:
        if not action_key:
            return None
        import action_context as _ctx
        import getpass

        try:
            user = getpass.getuser()
        except Exception:
            user = ""

        handling_navn = ""
        handling_type = ""
        omraade = ""
        regnr = ""
        beskrivelse = ""

        if action_key.startswith("L:"):
            item = self._selected_local_action()
            if item is not None:
                handling_navn = item.navn
                handling_type = getattr(item, "type", "") or ""
                omraade = getattr(item, "omraade", "") or ""
                # Multi-RL: hent regnr fra iid-suffiks ("L:<id>:<regnr>");
                # ellers fall tilbake til default_regnr.
                rest = action_key[2:]
                if ":" in rest:
                    regnr = rest.split(":", 1)[1]
                else:
                    regnr = getattr(item, "default_regnr", "") or ""
                beskrivelse = getattr(item, "beskrivelse", "") or ""
        else:
            try:
                action_id = int(action_key)
            except ValueError:
                action_id = None
            if action_id is not None:
                act = self._find_action(action_id)
                if act is not None:
                    handling_navn = getattr(act, "navn", "") or getattr(act, "name", "")
                    handling_type = getattr(act, "type", "") or ""
                    omraade = getattr(act, "omraade", "") or ""
                    regnr = str(getattr(act, "regnr", "") or "")
                    beskrivelse = getattr(act, "beskrivelse", "") or ""

        if not beskrivelse:
            beskrivelse = self._lookup_workpaper_beskrivelse(generator)

        kommentar = ""
        if self._client and self._year:
            try:
                import action_artifact_store as _store
                kommentar = _store.get_comment(self._client, self._year, action_key).text
            except Exception:
                kommentar = ""

        return _ctx.ActionContext(
            action_key=action_key,
            handling_navn=handling_navn or "Handling",
            handling_type=handling_type,
            omraade=omraade,
            regnr=regnr,
            beskrivelse=beskrivelse,
            kommentar=kommentar,
            kjort_av=user,
            client=self._client or "",
            year=self._year or "",
            workpaper_navn=getattr(generator, "navn", "") or "",
        )

    def _lookup_workpaper_beskrivelse(self, generator: Any) -> str:
        gen_id = getattr(generator, "id", "") or ""
        if not gen_id:
            return ""
        try:
            for wp in workpaper_library.list_all():
                if wp.id == gen_id and (wp.beskrivelse or "").strip():
                    return wp.beskrivelse.strip()
        except Exception:
            pass
        return ""

    def _current_action_key(self) -> str:
        sel = self._tree.selection()
        if not sel:
            return ""
        iid = sel[0]
        return iid if iid.startswith("L:") else iid

    def _snapshot_exports_dir(self) -> dict[str, float]:
        """Returnerer {fil_sti: mtime} for alle filer i exports_dir."""
        if not (self._client and self._year):
            return {}
        try:
            import client_store
            exports = client_store.exports_dir(self._client, year=self._year)
        except Exception:
            return {}
        snap: dict[str, float] = {}
        try:
            for p in exports.iterdir():
                if p.is_file():
                    try:
                        snap[str(p)] = p.stat().st_mtime
                    except Exception:
                        continue
        except Exception:
            return {}
        return snap

    def _register_new_artifacts(
        self,
        *,
        action_key: str,
        generator: Any,
        before: dict[str, float],
    ) -> None:
        try:
            import client_store
            exports = client_store.exports_dir(self._client, year=self._year)  # type: ignore[arg-type]
        except Exception:
            return
        new_paths: list[Any] = []
        try:
            for p in exports.iterdir():
                if not p.is_file():
                    continue
                key = str(p)
                mtime = 0.0
                try:
                    mtime = p.stat().st_mtime
                except Exception:
                    continue
                if key not in before or mtime > before[key]:
                    new_paths.append(p)
        except Exception:
            return
        if not new_paths:
            return
        import getpass
        import action_artifact_store as _store
        try:
            user = getpass.getuser()
        except Exception:
            user = ""
        for p in new_paths:
            artifact = _store.Artifact.from_path(
                action_key=action_key,
                workpaper_id=generator.id,
                workpaper_navn=generator.navn,
                path=p,
                kjort_av=user,
            )
            _store.register_artifact(self._client, self._year, artifact)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Right-click → tilordne ansvarlig

    def _on_tree_right_click(self, event: tk.Event) -> None:
        if not self._client or not self._year:
            return
        row = self._tree.identify_row(event.y)
        if row and row not in self._tree.selection():
            self._tree.selection_set(row)

        # Regnr for aktiv rad (kan være både "RL:<nr>"-gap-rad eller vanlig
        # handlingsrad) — brukes til "Vis statistikk"-menyvalget.
        regnr_for_stat = ""
        rl_name_for_stat = ""
        if row:
            if row.startswith("RL:"):
                regnr_for_stat = row.split(":", 1)[1].strip()
            try:
                vals = self._tree.item(row, "values")
                if vals and len(vals) >= 3:
                    if not regnr_for_stat:
                        regnr_for_stat = str(vals[1] or "").strip()
                    rl_name_for_stat = str(vals[2] or "").strip()
            except Exception:
                pass

        menu = tk.Menu(self, tearoff=False)

        # Statistikk-valg (vises når rad har gyldig regnr).
        if regnr_for_stat.isdigit():
            label_parts = [regnr_for_stat]
            if rl_name_for_stat:
                label_parts.append(rl_name_for_stat)
            menu.add_command(
                label=f"Vis statistikk for {' '.join(label_parts)}",
                command=lambda r=regnr_for_stat: self._open_statistikk_for_regnr(r),
            )
            menu.add_separator()

        # RL-gap-rader (iid "RL:..." ) skal ikke tilordnes en ansvarlig.
        sel = tuple(s for s in self._tree.selection() if not s.startswith("RL:"))
        if not sel:
            # Kun statistikk-valget (hvis aktuelt) — vis menyen om den ikke er tom.
            try:
                if menu.index("end") is not None:
                    menu.tk_popup(event.x_root, event.y_root)
            except Exception:
                pass
            return

        try:
            import team_config as _tc
            members = _tc.list_team_members()
        except Exception:
            members = []

        n = len(sel)
        title = f"Tilordne ansvarlig ({n} valgt)" if n > 1 else "Tilordne ansvarlig"
        menu.add_command(label=title, state="disabled")
        menu.add_separator()
        if not members:
            menu.add_command(label="Ingen team-medlemmer i config/team.json", state="disabled")
        else:
            for m in members:
                initials = str(m.get("initials") or "").strip().upper()
                full = str(m.get("full_name") or "").strip()
                if not initials:
                    continue
                label = f"{initials} – {full}" if full else initials
                menu.add_command(
                    label=label,
                    command=lambda v=initials, keys=sel: self._assign_to(keys, v),
                )
        menu.add_separator()
        menu.add_command(
            label="Fjern ansvarlig",
            command=lambda keys=sel: self._assign_to(keys, ""),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_statistikk_for_regnr(self, regnr: str) -> None:
        """Åpne Statistikk-popup med oppgitt regnskapslinje.

        Statistikk er ikke lenger en egen fane — vises i Toplevel som
        håndteres av App._open_statistikk_popup.
        """
        try:
            import session as _session
            app = getattr(_session, "APP", None)
            opener = getattr(app, "_open_statistikk_popup", None) if app is not None else None
            if not callable(opener):
                return
            try:
                regnr_int = int(regnr)
            except (TypeError, ValueError):
                return
            opener(regnr=regnr_int)
        except Exception:
            pass

    def _assign_to(self, action_keys: tuple[str, ...], initials: str) -> None:
        if not self._client or not self._year or not action_keys:
            return
        try:
            self._assignments = assignment_store.set_many(
                self._client, self._year, list(action_keys), initials,
            )
        except Exception as exc:
            messagebox.showerror("Tilordne ansvarlig", str(exc), parent=self)
            return
        self._apply_filter()
        try:
            existing = [k for k in action_keys if self._tree.exists(k)]
            if existing:
                self._tree.selection_set(*existing)
                self._on_select()
        except Exception:
            self._update_action_buttons()

    # ------------------------------------------------------------------
    # Detalj-popup

    def _on_double_click(self, _evt: Any = None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid.startswith("RL:"):
            self._open_link_dialog_for_rl(iid[3:])
            return
        self._open_detail_dialog(iid)

    def _open_link_dialog_for_rl(self, regnr: str) -> None:
        regnr = (regnr or "").strip()
        if not regnr or not self._client or not self._year:
            return
        rl_name = ""
        for rl in self._rl_list:
            if str(getattr(rl, "nr", "") or "").strip() == regnr:
                rl_name = str(getattr(rl, "regnskapslinje", "") or "")
                break
        try:
            from action_link_dialog import open_action_link_dialog
        except Exception as exc:
            messagebox.showerror("Koble handling", str(exc), parent=self)
            return
        open_action_link_dialog(
            parent=self,
            client=self._client,
            year=self._year,
            kind="rl",
            entity_key=regnr,
            entity_label=f"{regnr} {rl_name}".strip(),
            on_saved=self._refresh,
        )

    def _open_detail_dialog(self, iid: str) -> None:
        from .detail import ActionDetailDialog

        if iid.startswith("L:"):
            item = next((x for x in self._local_lib if x.id == self._local_action_id_from_iid(iid)), None)
            if item is None:
                return
            header = [
                f"{item.navn}",
                f"[Lokal]  {item.omraade or '–'}  ·  Type: {item.type}",
            ]
            if item.default_regnr:
                header.append(f"Default regnr: {item.default_regnr}")
            workpaper_ids = list(item.workpaper_ids)
            description = item.beskrivelse
            action_key = iid
        else:
            try:
                action_id = int(iid)
            except ValueError:
                return
            action = next((a for a in self._actions if a.action_id == action_id), None)
            if action is None:
                return
            header = [
                f"{action.procedure_name}",
                f"[CRM]  {action.area_name}  ·  Type: {getattr(action, 'procedure_type', '–') or '–'}",
            ]
            workpaper_ids = []
            description = getattr(action, "description", "") or ""
            action_key = str(action_id)

        run_cb = None
        has_builtin = any(workpaper_library.is_builtin(w) for w in workpaper_ids)
        if has_builtin and self._analyse_page is not None:
            run_cb = self._on_run_workpaper

        import getpass
        try:
            user = getpass.getuser()
        except Exception:
            user = ""

        ActionDetailDialog(
            self,
            client=self._client or "",
            year=self._year or "",
            action_key=action_key,
            header_lines=header,
            description=description,
            workpaper_ids=workpaper_ids,
            workpaper_index=self._workpaper_index,
            on_run=run_cb,
            user_name=user,
        )

    def _persist_confirmation(self, action_id: int, regnr: str, regnskapslinje: str) -> None:
        if not self._client or not self._year:
            return
        try:
            workpaper_store.confirm_regnr(
                self._client, self._year, action_id,
                regnr=regnr, regnskapslinje=regnskapslinje,
            )
        except Exception as exc:
            messagebox.showerror("Bekreft RL", f"Kunne ikke lagre bekreftelse: {exc}", parent=self)
            return
        self._workpapers = workpaper_store.load_workpapers(self._client, self._year)
        self._apply_filter()
        try:
            self._tree.selection_set(str(action_id))
            self._on_select()
        except Exception:
            self._update_action_buttons()

    def _on_confirm_current(self) -> None:
        action = self._selected_action()
        if not action:
            return
        match = self._match_by_action_id.get(action.action_id)
        if not match or not match.regnr:
            messagebox.showinfo(
                "Bekreft RL",
                "Ingen auto-match å bekrefte. Bruk 'Velg RL…' for å sette regnskapslinje manuelt.",
                parent=self,
            )
            return
        self._persist_confirmation(action.action_id, match.regnr, match.regnskapslinje)

    def _on_override_regnr(self) -> None:
        action = self._selected_action()
        if not action or not self._rl_list:
            return
        picked = _RegnrPickerDialog.ask(self, self._rl_list)
        if not picked:
            return
        regnr, regnskapslinje = picked
        self._persist_confirmation(action.action_id, regnr, regnskapslinje)

    def _on_clear_confirmation(self) -> None:
        action = self._selected_action()
        if not action or not self._client or not self._year:
            return
        if action.action_id not in self._workpapers:
            return
        try:
            workpaper_store.clear_confirmation(self._client, self._year, action.action_id)
        except Exception as exc:
            messagebox.showerror("Fjern bekreftelse", str(exc), parent=self)
            return
        self._workpapers = workpaper_store.load_workpapers(self._client, self._year)
        self._apply_filter()
        try:
            self._tree.selection_set(str(action.action_id))
            self._on_select()
        except Exception:
            self._update_action_buttons()


class _RegnrPickerDialog(tk.Toplevel):
    """Enkel dialog for å velge en regnskapslinje fra en lukket liste."""

    def __init__(self, parent: tk.Misc, rl_list) -> None:
        super().__init__(parent)
        self.title("Velg regnskapslinje")
        self.transient(parent)
        self.resizable(False, False)
        self._result: tuple[str, str] | None = None
        self._rl_list = list(rl_list)

        labels = [f"{rl.nr} — {rl.regnskapslinje}" for rl in self._rl_list]
        self._label_to_rl = {lbl: rl for lbl, rl in zip(labels, self._rl_list)}

        ttk.Label(self, text="Regnskapslinje:").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))
        self._var = tk.StringVar(value=labels[0] if labels else "")
        self._cb = ttk.Combobox(self, textvariable=self._var, values=labels, state="readonly", width=42)
        self._cb.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=2)

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", padx=8, pady=8)
        ttk.Button(btns, text="Avbryt", command=self._on_cancel).pack(side="right")
        ttk.Button(btns, text="Bekreft", command=self._on_ok).pack(side="right", padx=(0, 6))

        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self._on_cancel())
        self._cb.focus_set()
        self.grab_set()

    def _on_ok(self) -> None:
        label = self._var.get().strip()
        rl = self._label_to_rl.get(label)
        if rl is None:
            self._on_cancel()
            return
        self._result = (str(rl.nr).strip(), str(rl.regnskapslinje).strip())
        self.destroy()

    def _on_cancel(self) -> None:
        self._result = None
        self.destroy()

    @classmethod
    def ask(cls, parent: tk.Misc, rl_list) -> tuple[str, str] | None:
        if not rl_list:
            return None
        dlg = cls(parent, rl_list)
        parent.wait_window(dlg)
        return dlg._result

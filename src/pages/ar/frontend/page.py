from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
import threading
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

import session
from ..backend.store import (
    MANUAL_OWNER_OP_REMOVE,
    MANUAL_OWNER_OP_UPSERT,
    ManualOwnedChange,
    ManualOwnerChange,
    accept_pending_ownership_changes,
    accept_pending_owner_changes,
    classify_relation_type,
    delete_manual_owned_change,
    delete_manual_owner_change,
    detect_circular_ownership,
    get_client_ownership_overview,
    import_registry_pdf,
    load_manual_owner_changes,
    normalize_orgnr,
    parse_year_from_filename,
    upsert_manual_owned_change,
    upsert_manual_owner_change,
)

from . import brreg as page_ar_brreg
from . import chart as page_ar_chart
from . import compare as page_ar_compare

from ..backend.formatters import (  # noqa: E402,F401
    _ar_sheet_respecting_displaycolumns,
    _build_owned_help_text,
    _change_type_label,
    _compare_change_label,
    _fmt_currency,
    _fmt_optional_pct,
    _fmt_pct,
    _fmt_signed_thousand,
    _fmt_thousand,
    _parse_float,
    _relation_accent,
    _relation_fill,
    _relation_label,
    _safe_text,
    _source_label,
)



class ARPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._session: object = session
        self._client = ""
        self._year = ""
        self._overview: dict[str, Any] = {}
        self._owned_rows_by_iid: dict[str, dict[str, Any]] = {}
        self._owners_rows_by_iid: dict[str, dict[str, Any]] = {}
        self._change_rows_by_iid: dict[str, dict[str, Any]] = {}
        self._current_manual_change_id: str | None = None
        self._current_manual_owner_change_id: str | None = None
        self._chart_node_actions: dict[str, dict[str, Any]] = {}
        self._chart_node_keys: dict[str, str] = {}  # action_key -> position_key
        self._chart_node_centers: dict[str, tuple[float, float]] = {}  # pos_key -> (x, y)
        self._chart_edges: list[tuple[str, str, str, str]] = []  # (from_key, to_key, line_tag, lbl_tag)
        self._chart_box_size: tuple[float, float] = (172, 56)
        self._chart_dragging = False
        self._chart_drag_node: str | None = None  # action_key of node being dragged
        self._chart_press_xy: tuple[int, int] = (0, 0)
        self._chart_pending_action: dict[str, Any] | None = None
        self._chart_zoom = 1.0
        self._chart_dirty = False
        self._overview_request_id = 0
        self._overview_loading = False
        # Lazy circular-ownership beregning — egen worker, egen request-id.
        # Blokkerer aldri AR-tabell-rendering; brukes kun av org-kart-varslet.
        self._circular_request_id = 0
        self._circular_in_flight = False
        self._current_source_pdf: str = ""
        self._compare_rows_by_iid: dict[str, dict[str, Any]] = {}
        self._history_rows_by_iid: dict[str, dict[str, Any]] = {}
        self.var_context = tk.StringVar(value="Ingen klient lastet")
        self.var_status = tk.StringVar(value="Last inn klient og Ã¥r for Ã¥ jobbe med aksjonÃ¦rregister.")
        self.var_orgnr = tk.StringVar(value="-")
        self.var_change_summary = tk.StringVar(value="Ingen ventende registerendringer.")
        self.var_owners_caption = tk.StringVar(value="Aksjonærer i aktiv klient basert på importert aksjonærregister.")
        self.var_chart_caption = tk.StringVar(value="Organisasjonskartet viser eiere og eide selskaper for aktiv klient.")
        self.var_import_meta = tk.StringVar(value="Ingen aksjonÃ¦rregister-fil importert for valgt Ã¥r.")
        self.var_self_ownership = tk.StringVar(value="Ingen egne aksjer registrert i gjeldende eierstatus.")
        self.var_owned_caption = tk.StringVar(
            value="Gjeldende eierstatus brukes videre i AR og konsolidering. Egne aksjer vises separat."
        )
        self.var_manual_help = tk.StringVar(
            value="Velg en rad for Ã¥ se hva eierskapet betyr, hvilken kilde som brukes, og hvordan raden kan brukes videre."
        )
        self.var_manual_mode = tk.StringVar(
            value="Ny manuell rad. Bruk dette når et eierskap mangler i registeret eller må overstyres."
        )
        self.var_chart_zoom = tk.StringVar(value="100 %")

        self.var_manual_company_name = tk.StringVar(value="")
        self.var_manual_company_orgnr = tk.StringVar(value="")
        self.var_manual_pct = tk.StringVar(value="")
        self.var_manual_relation = tk.StringVar(value="")
        self.var_manual_note = tk.StringVar(value="")
        self.var_manual_source = tk.StringVar(value="Ny manuell endring")

        self.var_owned_search = tk.StringVar(value="")
        self.var_brreg_header = tk.StringVar(value="— velg et eid selskap —")
        self.var_brreg_status = tk.StringVar(value="")

        self._brreg_data: dict[str, dict[str, Any]] = {}
        self._brreg_loading: set[str] = set()
        self._brreg_request_id = 0
        self._brreg_current_orgnr: str = ""
        self._master_df = None
        self._mode = "eide_selskaper"
        self._selected_nr = ""

        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=(12, 8, 12, 0))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, textvariable=self.var_context, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.var_status, foreground="#667085").grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Button(top, text="Importer RF-1086 (PDF)", command=self._on_import_pdf).grid(row=0, column=2, sticky="e")
        ttk.Button(top, text="Oppdater", command=self._refresh_current_overview).grid(row=0, column=3, sticky="e", padx=(6, 0))
        ttk.Button(top, text="Eksporter AR-data\u2026", command=self._export_excel).grid(row=0, column=4, sticky="e", padx=(6, 0))

        # ── Sporbarhetsstripe: sammenligning / grunnlag / RF-1086 ──
        self.var_trace_compare = tk.StringVar(value="Sammenligning: –")
        self.var_trace_basis = tk.StringVar(value="Grunnlag: –")
        self.var_trace_import = tk.StringVar(value="RF-1086: –")
        trace = ttk.Frame(self, padding=(12, 2, 12, 6))
        trace.grid(row=1, column=0, sticky="ew")
        trace.columnconfigure(5, weight=1)
        ttk.Label(trace, textvariable=self.var_trace_compare, foreground="#475467").grid(row=0, column=0, sticky="w")
        ttk.Separator(trace, orient="vertical").grid(row=0, column=1, sticky="ns", padx=8)
        ttk.Label(trace, textvariable=self.var_trace_basis, foreground="#475467").grid(row=0, column=2, sticky="w")
        ttk.Separator(trace, orient="vertical").grid(row=0, column=3, sticky="ns", padx=8)
        ttk.Label(trace, textvariable=self.var_trace_import, foreground="#475467").grid(row=0, column=4, sticky="w")
        self._btn_open_source_pdf = ttk.Button(
            trace, text="Åpne siste RF-1086", command=self._open_current_source_pdf, state="disabled",
        )
        self._btn_open_source_pdf.grid(row=0, column=6, sticky="e")

        nb = ttk.Notebook(self)
        nb.grid(row=2, column=0, sticky="nsew", padx=12, pady=(6, 12))
        self._nb = nb
        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_changed, add="+")

        frm_owned = ttk.Frame(nb)
        frm_owned.columnconfigure(0, weight=3)
        frm_owned.columnconfigure(1, weight=2)
        nb.add(frm_owned, text="Eide selskaper")
        self._build_owned_tab(frm_owned)

        frm_owners = ttk.Frame(nb)
        frm_owners.columnconfigure(0, weight=1)
        frm_owners.rowconfigure(0, weight=1)
        nb.add(frm_owners, text="Eiere i klienten")
        self._frm_owners = frm_owners
        self._build_owners_tab(frm_owners)

        frm_changes = ttk.Frame(nb)
        frm_changes.columnconfigure(0, weight=1)
        frm_changes.rowconfigure(0, weight=2)
        frm_changes.rowconfigure(1, weight=2)
        frm_changes.rowconfigure(2, weight=1)
        nb.add(frm_changes, text="Registerendringer")
        self._frm_changes = frm_changes
        self._build_changes_tab(frm_changes)

        frm_chart = ttk.Frame(nb)
        frm_chart.columnconfigure(0, weight=1)
        frm_chart.rowconfigure(1, weight=1)
        nb.add(frm_chart, text="Organisasjonskart")
        self._frm_chart = frm_chart
        self._build_chart_tab(frm_chart)

    def _build_owned_tab(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=0)
        parent.rowconfigure(2, weight=1)

        bar = ttk.Frame(parent)
        bar.grid(row=0, column=0, sticky="ew", pady=(4, 4))

        manual_group = ttk.LabelFrame(bar, text="Manuell overstyring", padding=(6, 2))
        manual_group.pack(side="left")
        ttk.Button(manual_group, text="Ny / nullstill", command=self._on_new_manual_change).pack(side="left")
        ttk.Button(manual_group, text="Lagre endring", command=self._on_save_manual_change).pack(side="left", padx=(4, 0))
        self._btn_delete_manual = ttk.Button(
            manual_group, text="Slett overstyring",
            command=self._on_delete_manual_change, state="disabled",
        )
        self._btn_delete_manual.pack(side="left", padx=(4, 0))

        consol_group = ttk.LabelFrame(bar, text="Konsolidering", padding=(6, 2))
        consol_group.pack(side="left", padx=(8, 0))
        self._btn_owned_daughter = ttk.Button(
            consol_group, text="Importer som datter",
            command=self._on_send_owned_to_consolidation_as_daughter,
            state="disabled",
        )
        self._btn_owned_daughter.pack(side="left")
        self._btn_owned_associate = ttk.Button(
            consol_group, text="Opprett som tilknyttet",
            command=self._on_send_owned_to_consolidation_as_associate,
            state="disabled",
        )
        self._btn_owned_associate.pack(side="left", padx=(4, 0))
        self._btn_batch_daughter = ttk.Button(
            consol_group, text="Importer valgte som datter",
            command=self._on_batch_import_as_daughter,
            state="disabled",
        )
        self._btn_batch_daughter.pack(side="left", padx=(8, 0))
        self._btn_batch_associate = ttk.Button(
            consol_group, text="Opprett valgte som tilknyttet",
            command=self._on_batch_import_as_associate,
            state="disabled",
        )
        self._btn_batch_associate.pack(side="left", padx=(4, 0))

        search_bar = ttk.Frame(parent)
        search_bar.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(search_bar, text="Søk:").pack(side="left")
        search_entry = ttk.Entry(search_bar, textvariable=self.var_owned_search, width=40)
        search_entry.pack(side="left", padx=(4, 0), fill="x", expand=True)
        ttk.Button(search_bar, text="Nullstill", command=lambda: self.var_owned_search.set("")).pack(side="left", padx=(4, 0))
        try:
            self.var_owned_search.trace_add("write", self._on_owned_search_changed)
        except Exception:
            pass
        self._entry_owned_search = search_entry

        tree = ttk.Treeview(
            parent,
            columns=("company", "orgnr", "pct", "relation", "matched_client", "sb", "source"),
            show="headings",
            selectmode="extended",
        )
        tree.heading("company", text="Selskap")
        tree.heading("orgnr", text="Org.nr")
        tree.heading("pct", text="Eierandel")
        tree.heading("relation", text="Klassifisering")
        tree.heading("matched_client", text="Klientmatch")
        tree.heading("sb", text="Aktiv SB")
        tree.heading("source", text="Status/kilde")
        tree.column("company", width=220, stretch=True)
        tree.column("orgnr", width=95)
        tree.column("pct", width=80, anchor="e")
        tree.column("relation", width=90)
        tree.column("matched_client", width=160, stretch=True)
        tree.column("sb", width=70, anchor="center")
        tree.column("source", width=105)
        tree.tag_configure("manual", background="#EAF7F0")
        tree.tag_configure("manual_override", background="#FFF4DD")
        tree.tag_configure("carry_forward", background="#EDF3FF")
        tree.grid(row=2, column=0, sticky="nsew")
        tree.bind("<<TreeviewSelect>>", self._on_owned_selected)
        self._tree_owned = tree

        right_nb = ttk.Notebook(parent)
        right_nb.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=(12, 0), pady=(4, 0))
        self._owned_right_nb = right_nb

        overstyring_tab = ttk.Frame(right_nb)
        overstyring_tab.columnconfigure(0, weight=1)
        overstyring_tab.rowconfigure(0, weight=1)
        right_nb.add(overstyring_tab, text="Overstyring")
        self._build_overstyring_subtab(overstyring_tab)

        brreg_tab = ttk.Frame(right_nb)
        brreg_tab.columnconfigure(0, weight=1)
        brreg_tab.rowconfigure(2, weight=1)
        right_nb.add(brreg_tab, text="BRREG og regnskap")
        self._build_brreg_subtab(brreg_tab)

    def _build_overstyring_subtab(self, parent: ttk.Frame) -> None:
        editor = ttk.LabelFrame(parent, text="Redigering og overstyring", padding=10)
        editor.grid(row=0, column=0, sticky="nsew")
        editor.columnconfigure(1, weight=1)

        ttk.Label(editor, text="Selskap").grid(row=0, column=0, sticky="w")
        ttk.Entry(editor, textvariable=self.var_manual_company_name).grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(editor, text="Org.nr").grid(row=1, column=0, sticky="w")
        ttk.Entry(editor, textvariable=self.var_manual_company_orgnr).grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Label(editor, text="Eierandel %").grid(row=2, column=0, sticky="w")
        ttk.Entry(editor, textvariable=self.var_manual_pct).grid(row=2, column=1, sticky="ew", pady=2)
        ttk.Label(editor, text="Relasjon").grid(row=3, column=0, sticky="w")
        relation_cb = ttk.Combobox(
            editor,
            textvariable=self.var_manual_relation,
            values=("", "datter", "tilknyttet", "investering", "vurder"),
            state="readonly",
        )
        relation_cb.grid(row=3, column=1, sticky="ew", pady=2)
        ttk.Label(editor, text="Notat").grid(row=4, column=0, sticky="w")
        ttk.Entry(editor, textvariable=self.var_manual_note).grid(row=4, column=1, sticky="ew", pady=2)
        ttk.Label(editor, text="Kilde").grid(row=5, column=0, sticky="w")
        ttk.Label(editor, textvariable=self.var_manual_source, foreground="#475467").grid(row=5, column=1, sticky="w", pady=2)

    def _build_brreg_subtab(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky="ew", pady=(4, 4))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, textvariable=self.var_brreg_header,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self._btn_brreg_refresh = ttk.Button(
            header, text="Oppdater BRREG",
            command=self._on_brreg_refresh_clicked,
            state="disabled",
        )
        self._btn_brreg_refresh.grid(row=0, column=1, sticky="e", padx=(6, 0))

        ttk.Label(
            parent, textvariable=self.var_brreg_status,
            foreground="#667085",
        ).grid(row=1, column=0, sticky="w")

        panel_frame = ttk.Frame(parent)
        panel_frame.grid(row=2, column=0, sticky="nsew")
        self._brreg_frame = panel_frame
        try:
            import reskontro_brreg_panel
            reskontro_brreg_panel.build_brreg_panel(self, parent=panel_frame)
        except Exception as exc:
            ttk.Label(
                panel_frame, text=f"Kunne ikke initialisere BRREG-panel: {exc}",
                foreground="#B42318",
            ).grid(row=0, column=0, sticky="w")

    def _build_changes_tab(self, parent: ttk.Frame) -> None:
        page_ar_compare.build_changes_tab(self, parent)

    def _on_changes_selection_changed(self, _event=None) -> None:
        page_ar_compare.on_changes_selection_changed(self, _event)

    def _on_shareholder_change_open(self, _event=None) -> None:
        page_ar_compare.on_shareholder_change_open(self, _event)

    def _on_history_open_detail(self, _event=None) -> None:
        page_ar_compare.on_history_open_detail(self, _event)

    def _build_chart_tab(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 0))
        ttk.Button(toolbar, text="+", width=3, command=lambda: self._chart_apply_zoom(1.15)).pack(side="left")
        ttk.Button(toolbar, text="\u2212", width=3, command=lambda: self._chart_apply_zoom(1 / 1.15)).pack(side="left", padx=(2, 0))
        ttk.Label(toolbar, textvariable=self.var_chart_zoom, foreground="#475467", width=6).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Tilpass", command=self._chart_fit_view).pack(side="left", padx=(4, 0))
        ttk.Button(toolbar, text="Nullstill", command=self._chart_reset_view).pack(side="left", padx=(2, 0))

        sep = ttk.Separator(toolbar, orient="vertical")
        sep.pack(side="left", padx=(10, 10), fill="y", pady=2)

        for label, color in (
            ("Klient", "#E6F0FF"),
            ("Datter", _relation_fill("datter")),
            ("Tilknyttet", _relation_fill("tilknyttet")),
            ("Investering", _relation_fill("investering")),
            ("Vurder", _relation_fill("vurder")),
        ):
            swatch = tk.Label(toolbar, width=2, background=color, relief="solid", bd=1)
            swatch.pack(side="left", padx=(0, 2))
            ttk.Label(toolbar, text=label, foreground="#475467").pack(side="left", padx=(0, 8))

        wrap = ttk.Frame(parent)
        wrap.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)

        canvas = tk.Canvas(
            wrap,
            background="#FFFFFF",
            highlightthickness=1,
            highlightbackground="#D0D5DD",
        )
        xscroll = ttk.Scrollbar(wrap, orient="horizontal", command=canvas.xview)
        yscroll = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        canvas.bind("<ButtonPress-1>", self._on_chart_press)
        canvas.bind("<B1-Motion>", self._on_chart_drag)
        canvas.bind("<ButtonRelease-1>", self._on_chart_release)
        canvas.bind("<MouseWheel>", self._on_chart_mousewheel)
        canvas.bind("<Double-Button-1>", self._on_chart_double_click)
        self._org_canvas = canvas

    def _update_owned_action_state(self, row: dict[str, Any] | None = None) -> None:
        daughter_state = "disabled"
        associate_state = "disabled"
        sel = self._tree_owned.selection()
        single = len(sel) == 1
        if row and single:
            associate_state = "normal"
            if _safe_text(row.get("matched_client")) and bool(row.get("has_active_sb")):
                daughter_state = "normal"
        try:
            self._btn_owned_daughter.configure(state=daughter_state)
            self._btn_owned_associate.configure(state=associate_state)
        except Exception:
            pass

        # Batch buttons: active when 2+ rows selected
        multi = len(sel) >= 2
        batch_daughter_state = "normal" if multi else "disabled"
        batch_associate_state = "normal" if multi else "disabled"
        try:
            self._btn_batch_daughter.configure(state=batch_daughter_state)
            self._btn_batch_associate.configure(state=batch_associate_state)
        except Exception:
            pass

        # Delete-overstyring: only when row has manual_change_id
        delete_state = "normal" if (row and _safe_text(row.get("manual_change_id"))) else "disabled"
        try:
            self._btn_delete_manual.configure(state=delete_state)
        except Exception:
            pass

    def _update_manual_help(self, row: dict[str, Any] | None = None) -> None:
        self.var_manual_help.set(
            _build_owned_help_text(
                row,
                year=self._year,
                accepted_meta=self._overview.get("accepted_meta") if isinstance(self._overview, dict) else {},
            )
        )

    def _selected_owned_row(self) -> dict[str, Any] | None:
        sel = self._tree_owned.selection()
        if not sel:
            return None
        return self._owned_rows_by_iid.get(sel[0])

    def _on_owned_selected(self, _event=None) -> None:
        row = self._selected_owned_row()
        if row is None:
            return
        self._current_manual_change_id = _safe_text(row.get("manual_change_id")) or None
        self.var_manual_company_name.set(_safe_text(row.get("company_name")))
        self.var_manual_company_orgnr.set(_safe_text(row.get("company_orgnr")))
        self.var_manual_pct.set(_fmt_pct(row.get("ownership_pct")))
        manual_relation = _safe_text(row.get("relation_type"))
        self.var_manual_relation.set(manual_relation if manual_relation in {"datter", "tilknyttet", "investering", "vurder"} else "")
        self.var_manual_note.set(_safe_text(row.get("note")))
        self.var_manual_source.set(
            "Manuell overstyring" if _safe_text(row.get("manual_change_id")) else f"Registerrad ({_source_label(row.get('source'))})"
        )
        if self._current_manual_change_id:
            self.var_manual_mode.set("Du redigerer en lagret manuell overstyring for denne raden.")
        else:
            self.var_manual_mode.set("Registerrad valgt. Endringer du lagrer her blir en manuell overstyring.")
        self._update_manual_help(row)
        self._update_owned_action_state(row)
        self._load_brreg_for_selected_row(row)

    def _on_owned_search_changed(self, *_args: object) -> None:
        if not self._overview:
            return
        self._refresh_trees()

    def _load_brreg_for_selected_row(self, row: dict[str, Any], *, force_refresh: bool = False) -> None:
        page_ar_brreg.load_brreg_for_selected_row(self, row, force_refresh=force_refresh)

    def _brreg_worker(self, orgnr: str, request_id: int, use_cache: bool) -> None:
        page_ar_brreg.brreg_worker(self, orgnr, request_id, use_cache)

    def _brreg_apply_result(
        self,
        request_id: int,
        orgnr: str,
        enhet: dict[str, Any] | None,
        regnskap: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        page_ar_brreg.brreg_apply_result(self, request_id, orgnr, enhet, regnskap, error)

    def _on_brreg_refresh_clicked(self) -> None:
        page_ar_brreg.on_brreg_refresh_clicked(self)

    def _update_brreg_header(self, orgnr: str, name: str) -> None:
        page_ar_brreg.update_brreg_header(self, orgnr, name)

    def _on_new_manual_change(self) -> None:
        self._current_manual_change_id = None
        self.var_manual_company_name.set("")
        self.var_manual_company_orgnr.set("")
        self.var_manual_pct.set("")
        self.var_manual_relation.set("")
        self.var_manual_note.set("")
        self.var_manual_source.set("Ny manuell endring")
        self.var_manual_mode.set(
            "Ny manuell rad. Bruk dette når et eierskap mangler i registeret eller må overstyres."
        )
        self._update_manual_help(None)
        self._update_owned_action_state(None)

    def _on_save_manual_change(self) -> None:
        if not self._client or not self._year:
            messagebox.showinfo("AR", "Velg klient og Ã¥r fÃ¸r du lagrer manuelle AR-endringer.")
            return

        company_name = _safe_text(self.var_manual_company_name.get())
        company_orgnr = _safe_text(self.var_manual_company_orgnr.get())
        if not company_name and not company_orgnr:
            messagebox.showwarning("AR", "Skriv inn minst selskapsnavn eller org.nr.")
            return
        client_orgnr = normalize_orgnr(self._overview.get("client_orgnr")) or normalize_orgnr(self.var_orgnr.get())
        if client_orgnr and normalize_orgnr(company_orgnr) == client_orgnr:
            messagebox.showinfo(
                "AR",
                "Klienten kan ikke legges inn som eget eid selskap her. Egne aksjer vises separat i AR-oversikten.",
            )
            return

        try:
            ownership_pct = _parse_float(self.var_manual_pct.get())
        except Exception as exc:
            messagebox.showerror("AR", f"Ugyldig eierandel:\n{exc}")
            return

        change = ManualOwnedChange(
            change_id=self._current_manual_change_id or ManualOwnedChange().change_id,
            company_name=company_name,
            company_orgnr=company_orgnr,
            ownership_pct=ownership_pct,
            relation_type=_safe_text(self.var_manual_relation.get()),
            note=_safe_text(self.var_manual_note.get()),
        )
        upsert_manual_owned_change(self._client, self._year, change)
        self.var_status.set("Manuell AR-endring lagret.")
        self._refresh_current_overview()

    def _on_delete_manual_change(self) -> None:
        change_id = self._current_manual_change_id
        if not change_id:
            messagebox.showinfo("AR", "Velg en manuell AR-endring for Ã¥ slette den.")
            return
        if not messagebox.askyesno("AR", "Slett valgt manuell AR-endring?"):
            return
        delete_manual_owned_change(self._client, self._year, change_id)
        self.var_status.set("Manuell AR-endring slettet.")
        self._refresh_current_overview()

    # ── Manuelle aksjonær-endringer (eier-siden) ──
    def _selected_owner_compare_row(self) -> dict[str, Any] | None:
        tree = getattr(self, "_tree_owners", None)
        if tree is None:
            return None
        sel = tree.selection()
        if not sel:
            return None
        return self._compare_rows_by_iid.get(sel[0])

    def _update_manual_owner_action_state(self, row: dict[str, Any] | None = None) -> None:
        row = row if row is not None else self._selected_owner_compare_row()
        has_row = row is not None
        has_manual = bool(row and _safe_text(row.get("manual_change_id")))
        is_hidden = _safe_text(row.get("source")) == "manual_hidden" if row else False
        edit_state = "normal" if has_row and not is_hidden else "disabled"
        remove_state = "normal" if has_row and not is_hidden else "disabled"
        delete_state = "normal" if has_manual else "disabled"
        for attr, state in (
            ("_btn_edit_owner", edit_state),
            ("_btn_remove_owner", remove_state),
            ("_btn_delete_manual_owner", delete_state),
        ):
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            try:
                btn.configure(state=state)
            except Exception:
                pass
        self._current_manual_owner_change_id = (
            _safe_text(row.get("manual_change_id")) or None if row else None
        )

    def _require_client_year(self) -> bool:
        if not self._client or not self._year:
            messagebox.showinfo(
                "AR",
                "Velg klient og år før du registrerer manuelle aksjonær-endringer.",
            )
            return False
        return True

    def _on_new_manual_owner_change(self) -> None:
        if not self._require_client_year():
            return
        self._open_manual_owner_dialog(prefill=None)

    def _on_edit_manual_owner_change(self) -> None:
        if not self._require_client_year():
            return
        row = self._selected_owner_compare_row()
        if row is None:
            messagebox.showinfo("AR", "Velg en aksjonær i listen først.")
            return
        prefill = {
            "change_id": _safe_text(row.get("manual_change_id")),
            "shareholder_name": _safe_text(row.get("shareholder_name")),
            "shareholder_orgnr": _safe_text(row.get("shareholder_orgnr")),
            "shareholder_kind": _safe_text(row.get("shareholder_kind")) or "unknown",
            "shares": int(row.get("shares_current") or 0),
            "total_shares": 0,
            "ownership_pct": float(row.get("ownership_pct_current") or 0.0),
            "note": _safe_text(row.get("manual_note")),
        }
        self._open_manual_owner_dialog(prefill=prefill)

    def _on_remove_owner_row(self) -> None:
        if not self._require_client_year():
            return
        row = self._selected_owner_compare_row()
        if row is None:
            messagebox.showinfo("AR", "Velg en aksjonær å skjule først.")
            return
        name = _safe_text(row.get("shareholder_name"))
        orgnr = _safe_text(row.get("shareholder_orgnr"))
        label = f"{name}" + (f" ({orgnr})" if orgnr else "")
        if not messagebox.askyesno(
            "AR",
            f"Skjul «{label}» fra aksjonærlisten?\n\n"
            "Dette overstyrer RF-1086 lokalt. Ved ny import må du godkjenne "
            "gjenoppretting eksplisitt i Registerendringer.",
        ):
            return
        existing_id = _safe_text(row.get("manual_change_id"))
        change = ManualOwnerChange(
            change_id=existing_id or ManualOwnerChange().change_id,
            op=MANUAL_OWNER_OP_REMOVE,
            shareholder_name=name,
            shareholder_orgnr=normalize_orgnr(orgnr),
            shareholder_kind=_safe_text(row.get("shareholder_kind")) or "unknown",
            note=f"Skjult manuelt {self._year}".strip(),
        )
        upsert_manual_owner_change(self._client, self._year, change)
        self.var_status.set("Aksjonær skjult (manuell overstyring).")
        self._refresh_current_overview()

    def _on_delete_manual_owner_change(self) -> None:
        if not self._require_client_year():
            return
        row = self._selected_owner_compare_row()
        change_id = _safe_text(row.get("manual_change_id")) if row else ""
        if not change_id:
            messagebox.showinfo("AR", "Valgt rad har ingen manuell overstyring.")
            return
        if not messagebox.askyesno(
            "AR",
            "Slett manuell overstyring for denne aksjonæren?\n\n"
            "Etter dette brukes RF-1086-registeret direkte.",
        ):
            return
        delete_manual_owner_change(self._client, self._year, change_id)
        self.var_status.set("Manuell aksjonær-overstyring slettet.")
        self._refresh_current_overview()

    def _open_manual_owner_dialog(self, *, prefill: dict[str, Any] | None) -> None:
        dlg = _ManualOwnerChangeDialog(self, prefill=prefill)
        self.wait_window(dlg)
        if not getattr(dlg, "saved", False):
            return
        change: ManualOwnerChange = dlg.result  # type: ignore[assignment]
        upsert_manual_owner_change(self._client, self._year, change)
        self.var_status.set("Manuell aksjonær-endring lagret.")
        self._refresh_current_overview()

    def _resolve_consolidation_page(self):
        app = getattr(session, "APP", None)
        if app is None:
            return None, None
        page = getattr(app, "src.pages.consolidation.frontend.page", None)
        notebook = getattr(app, "nb", None)
        return page, notebook

    def _on_send_owned_to_consolidation_as_daughter(self) -> None:
        row = self._selected_owned_row()
        if row is None:
            messagebox.showinfo("AR", "Velg et eid selskap fÃ¸rst.")
            return
        matched_client = _safe_text(row.get("matched_client"))
        if not matched_client:
            messagebox.showinfo("AR", "Fant ingen klientmatch pÃ¥ org.nr for valgt selskap.")
            return
        if not row.get("has_active_sb"):
            messagebox.showinfo(
                "AR",
                f"Klientmatch finnes for {matched_client}, men aktiv SB mangler for {self._year}.",
            )
            return

        page, notebook = self._resolve_consolidation_page()
        if page is None or not hasattr(page, "import_company_from_client_name"):
            messagebox.showerror("AR", "Konsolideringsmodulen er ikke tilgjengelig.")
            return
        company = page.import_company_from_client_name(
            matched_client,
            target_company_name=_safe_text(row.get("company_name")) or matched_client,
        )
        if company is not None and notebook is not None:
            try:
                notebook.select(page)
            except Exception:
                pass

    def _on_send_owned_to_consolidation_as_associate(self) -> None:
        row = self._selected_owned_row()
        if row is None:
            messagebox.showinfo("AR", "Velg et eid selskap fÃ¸rst.")
            return
        page, notebook = self._resolve_consolidation_page()
        if page is None or not hasattr(page, "create_or_update_associate_case_from_ar_relation"):
            messagebox.showerror("AR", "Konsolideringsmodulen er ikke tilgjengelig.")
            return
        case = page.create_or_update_associate_case_from_ar_relation(
            company_name=_safe_text(row.get("company_name")),
            company_orgnr=_safe_text(row.get("company_orgnr")),
            ownership_pct=float(row.get("ownership_pct") or 0.0),
            matched_client=_safe_text(row.get("matched_client")),
            relation_type=_safe_text(row.get("relation_type")) or classify_relation_type(float(row.get("ownership_pct") or 0.0)),
            source_ref=f"AR {self._year}",
            note=_safe_text(row.get("note")),
        )
        if case is not None and notebook is not None:
            try:
                notebook.select(page)
            except Exception:
                pass

    def _selected_owned_rows(self) -> list[dict[str, Any]]:
        """Return all selected rows in the owned tree."""
        return [
            self._owned_rows_by_iid[iid]
            for iid in self._tree_owned.selection()
            if iid in self._owned_rows_by_iid
        ]

    def _on_batch_import_as_daughter(self) -> None:
        rows = self._selected_owned_rows()
        if len(rows) < 2:
            messagebox.showinfo("AR", "Velg minst to selskaper for batch-import.")
            return
        page, notebook = self._resolve_consolidation_page()
        if page is None or not hasattr(page, "import_companies_from_ar_batch"):
            messagebox.showerror("AR", "Konsolideringsmodulen er ikke tilgjengelig.")
            return
        results = page.import_companies_from_ar_batch(rows)
        ok = sum(1 for r in results if r is not None)
        fail = len(results) - ok
        messagebox.showinfo(
            "AR batch-import",
            f"Importert {ok} av {len(rows)} selskaper som datter.\n"
            + (f"{fail} feilet (mangler klientmatch eller aktiv SB)." if fail else "Alle OK."),
        )
        if ok and notebook is not None:
            try:
                notebook.select(page)
            except Exception:
                pass

    def _on_batch_import_as_associate(self) -> None:
        rows = self._selected_owned_rows()
        if len(rows) < 2:
            messagebox.showinfo("AR", "Velg minst to selskaper for batch-opprettelse.")
            return
        page, notebook = self._resolve_consolidation_page()
        if page is None or not hasattr(page, "create_associate_cases_from_ar_batch"):
            messagebox.showerror("AR", "Konsolideringsmodulen er ikke tilgjengelig.")
            return
        results = page.create_associate_cases_from_ar_batch(rows, year=self._year)
        ok = sum(1 for r in results if r is not None)
        fail = len(results) - ok
        messagebox.showinfo(
            "AR batch-import",
            f"Opprettet {ok} av {len(rows)} selskaper som tilknyttet.\n"
            + (f"{fail} feilet." if fail else "Alle OK."),
        )
        if ok and notebook is not None:
            try:
                notebook.select(page)
            except Exception:
                pass

    def _build_owners_tab(self, parent: ttk.Frame) -> None:
        """Master-detail: upper = union-compare, lower = shareholder detail."""
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        # ── Toolbar: manuell overstyring av aksjonærer ──
        owner_tools = ttk.Frame(parent)
        owner_tools.grid(row=0, column=0, sticky="ew", pady=(4, 4))
        manual_group = ttk.LabelFrame(owner_tools, text="Manuell overstyring av eiere", padding=(6, 2))
        manual_group.pack(side="left")
        ttk.Button(
            manual_group, text="Ny eier / overstyring",
            command=self._on_new_manual_owner_change,
        ).pack(side="left")
        self._btn_edit_owner = ttk.Button(
            manual_group, text="Rediger valgt",
            command=self._on_edit_manual_owner_change, state="disabled",
        )
        self._btn_edit_owner.pack(side="left", padx=(4, 0))
        self._btn_remove_owner = ttk.Button(
            manual_group, text="Fjern valgt (skjul)",
            command=self._on_remove_owner_row, state="disabled",
        )
        self._btn_remove_owner.pack(side="left", padx=(4, 0))
        self._btn_delete_manual_owner = ttk.Button(
            manual_group, text="Slett overstyring",
            command=self._on_delete_manual_owner_change, state="disabled",
        )
        self._btn_delete_manual_owner.pack(side="left", padx=(4, 0))
        ttk.Label(
            owner_tools,
            text="Manuelle endringer overlever RF-1086-import. Konflikter må aksepteres i Registerendringer.",
            foreground="#667085",
        ).pack(side="left", padx=(12, 0))

        pw = ttk.PanedWindow(parent, orient="vertical")
        pw.grid(row=1, column=0, sticky="nsew")
        self._owners_pw = pw

        # ── Upper: union-compare tree with year-aware columns ──
        upper = ttk.Frame(pw)
        pw.add(upper, weight=3)
        upper.columnconfigure(0, weight=1)
        upper.rowconfigure(1, weight=1)

        ttk.Label(
            upper,
            textvariable=self.var_owners_caption,
            foreground="#475467",
        ).grid(row=0, column=0, sticky="w", pady=(0, 2))

        cols = (
            "owner", "orgnr", "kind",
            "shares_base", "shares_current", "shares_delta",
            "bought", "sold", "tx_value",
            "pct_current",
        )
        tree = ttk.Treeview(
            upper, columns=cols, show="headings", selectmode="browse",
        )
        tree.heading("owner", text="Aksjonær")
        tree.heading("orgnr", text="Org.nr")
        tree.heading("kind", text="Type")
        tree.heading("shares_base", text="Aksjer (base)")
        tree.heading("shares_current", text="Aksjer (nå)")
        tree.heading("shares_delta", text="\u0394 aksjer")
        tree.heading("bought", text="Kjøpt")
        tree.heading("sold", text="Solgt")
        tree.heading("tx_value", text="Transaksjonsverdi")
        tree.heading("pct_current", text="Eierandel (nå)")
        tree.column("owner", width=220, stretch=True)
        tree.column("orgnr", width=95)
        tree.column("kind", width=70)
        tree.column("shares_base", width=95, anchor="e")
        tree.column("shares_current", width=95, anchor="e")
        tree.column("shares_delta", width=80, anchor="e")
        tree.column("bought", width=70, anchor="e")
        tree.column("sold", width=70, anchor="e")
        tree.column("tx_value", width=110, anchor="e")
        tree.column("pct_current", width=100, anchor="e")

        tree.tag_configure("new", background="#EAF7F0")
        tree.tag_configure("removed", background="#F2F4F7", foreground="#98A2B3")
        tree.tag_configure("changed", background="#FFFBEB")
        tree.tag_configure("hidden", background="#F9FAFB", foreground="#98A2B3")
        tree.tag_configure("manual", background="#EAF7F0")
        tree.tag_configure("manual_override", background="#FFF4DD")

        ysb = ttk.Scrollbar(upper, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ysb.set)
        tree.grid(row=1, column=0, sticky="nsew")
        ysb.grid(row=1, column=1, sticky="ns")
        tree.bind("<<TreeviewSelect>>", self._on_compare_selected)
        self._tree_owners = tree

        # ── Lower: shareholder detail panel ──
        lower = ttk.Frame(pw)
        pw.add(lower, weight=2)
        lower.columnconfigure(0, weight=2)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(1, weight=1)

        self.var_compare_header = tk.StringVar(value="")
        ttk.Label(
            lower,
            textvariable=self.var_compare_header,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(6, 2))

        # ── Left: Aksjonærdetaljer (field grid) + Transaksjoner ──
        detail_left = ttk.Frame(lower)
        detail_left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        detail_left.columnconfigure(0, weight=1)
        detail_left.rowconfigure(1, weight=1)

        details_box = ttk.LabelFrame(detail_left, text="Aksjonærdetaljer", padding=6)
        details_box.grid(row=0, column=0, sticky="ew")
        details_box.columnconfigure(1, weight=1)
        details_box.columnconfigure(3, weight=1)

        self.var_detail_shares_base = tk.StringVar(value="–")
        self.var_detail_shares_current = tk.StringVar(value="–")
        self.var_detail_shares_delta = tk.StringVar(value="–")
        self.var_detail_pct_base = tk.StringVar(value="–")
        self.var_detail_pct_current = tk.StringVar(value="–")
        self.var_detail_change_type = tk.StringVar(value="–")
        self._lbl_detail_shares_base_title = ttk.Label(
            details_box, text="Aksjer (base):", foreground="#475467",
        )
        self._lbl_detail_shares_current_title = ttk.Label(
            details_box, text="Aksjer (nå):", foreground="#475467",
        )
        self._lbl_detail_pct_base_title = ttk.Label(
            details_box, text="Eierandel (base):", foreground="#475467",
        )
        self._lbl_detail_pct_current_title = ttk.Label(
            details_box, text="Eierandel (nå):", foreground="#475467",
        )
        self._lbl_detail_shares_base_title.grid(row=0, column=0, sticky="w")
        ttk.Label(details_box, textvariable=self.var_detail_shares_base).grid(row=0, column=1, sticky="w", padx=(6, 12))
        self._lbl_detail_shares_current_title.grid(row=0, column=2, sticky="w")
        ttk.Label(details_box, textvariable=self.var_detail_shares_current).grid(row=0, column=3, sticky="w", padx=(6, 0))
        ttk.Label(details_box, text="Δ aksjer:", foreground="#475467").grid(row=1, column=0, sticky="w")
        ttk.Label(details_box, textvariable=self.var_detail_shares_delta).grid(row=1, column=1, sticky="w", padx=(6, 12))
        ttk.Label(details_box, text="Endring:", foreground="#475467").grid(row=1, column=2, sticky="w")
        ttk.Label(details_box, textvariable=self.var_detail_change_type).grid(row=1, column=3, sticky="w", padx=(6, 0))
        self._lbl_detail_pct_base_title.grid(row=2, column=0, sticky="w")
        ttk.Label(details_box, textvariable=self.var_detail_pct_base).grid(row=2, column=1, sticky="w", padx=(6, 12))
        self._lbl_detail_pct_current_title.grid(row=2, column=2, sticky="w")
        ttk.Label(details_box, textvariable=self.var_detail_pct_current).grid(row=2, column=3, sticky="w", padx=(6, 0))

        tx_box = ttk.LabelFrame(detail_left, text="Transaksjoner", padding=4)
        tx_box.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        tx_box.columnconfigure(0, weight=1)
        tx_box.rowconfigure(1, weight=1)
        self._tx_box = tx_box

        self.var_compare_tx_empty = tk.StringVar(value="")
        self._lbl_compare_tx_empty = ttk.Label(
            tx_box,
            textvariable=self.var_compare_tx_empty,
            foreground="#98A2B3",
            wraplength=600,
            justify="left",
        )

        self.var_compare_no_import = tk.StringVar(value="")
        self._lbl_compare_no_import = ttk.Label(
            tx_box,
            textvariable=self.var_compare_no_import,
            foreground="#475467",
            wraplength=600,
            justify="left",
        )

        tx_cols = ("dato", "retning", "type", "aksjer", "beloep")
        tx_tree = ttk.Treeview(
            tx_box, columns=tx_cols, show="headings", selectmode="none", height=6,
        )
        tx_tree.heading("dato", text="Dato")
        tx_tree.heading("retning", text="Retning")
        tx_tree.heading("type", text="Type")
        tx_tree.heading("aksjer", text="Aksjer")
        tx_tree.heading("beloep", text="Beløp")
        tx_tree.column("dato", width=85)
        tx_tree.column("retning", width=70)
        tx_tree.column("type", width=90)
        tx_tree.column("aksjer", width=70, anchor="e")
        tx_tree.column("beloep", width=110, anchor="e")
        tx_tree.grid(row=1, column=0, sticky="nsew")
        tx_ysb = ttk.Scrollbar(tx_box, orient="vertical", command=tx_tree.yview)
        tx_tree.configure(yscrollcommand=tx_ysb.set)
        tx_ysb.grid(row=1, column=1, sticky="ns")
        self._tree_compare_tx = tx_tree

        # ── Right: Sporbarhet (field grid + actions) ──
        detail_right = ttk.LabelFrame(lower, text="Sporbarhet", padding=8)
        detail_right.grid(row=1, column=1, sticky="nsew")
        detail_right.columnconfigure(1, weight=1)

        self.var_compare_data_basis = tk.StringVar(value="–")
        self.var_compare_rf_status = tk.StringVar(value="ikke importert")
        self.var_compare_imported_at = tk.StringVar(value="–")
        self.var_compare_source_file = tk.StringVar(value="–")
        self.var_compare_source_year = tk.StringVar(value="–")
        for r, (label, var) in enumerate((
            ("Datagrunnlag:", self.var_compare_data_basis),
            ("RF-1086:", self.var_compare_rf_status),
            ("Kildeår:", self.var_compare_source_year),
            ("Importert:", self.var_compare_imported_at),
            ("Kildefil:", self.var_compare_source_file),
        )):
            ttk.Label(detail_right, text=label, foreground="#475467").grid(row=r, column=0, sticky="w")
            ttk.Label(detail_right, textvariable=var, wraplength=240, justify="left").grid(row=r, column=1, sticky="w", padx=(8, 0))

        self._btn_compare_open_pdf = ttk.Button(
            detail_right, text="Åpne RF-1086",
            command=self._on_compare_open_pdf, state="disabled",
        )
        self._btn_compare_open_pdf.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        self._btn_compare_import_detail = ttk.Button(
            detail_right, text="Vis importspor",
            command=self._on_compare_show_import_detail, state="disabled",
        )
        self._btn_compare_import_detail.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(2, 2))

    def refresh_from_session(self, sess: object) -> None:
        self._session = sess
        self._client = _safe_text(getattr(sess, "client", ""))
        self._year = _safe_text(getattr(sess, "year", ""))
        if not self._client or not self._year:
            self.var_context.set("AR")
            self.var_status.set("")
            self._overview = {}
            self._refresh_trees()
            return
        self.var_context.set(f"AR — {self._client} | {self._year}")
        self._refresh_current_overview()

    def _refresh_current_overview(self) -> None:
        if not self._client or not self._year:
            return
        self._overview_request_id += 1
        request_id = self._overview_request_id
        client = self._client
        year = self._year
        self._overview_loading = True
        self.var_status.set(f"Laster AR-oversikt for {client} | {year} ...")
        threading.Thread(
            target=self._load_overview_worker,
            args=(request_id, client, year),
            daemon=True,
        ).start()

    def _load_overview_worker(self, request_id: int, client: str, year: str) -> None:
        # Kritisk AR-last: bare get_client_ownership_overview, aldri tyngre
        # analyse. Sirkulært eierskap kjøres i en egen lazy worker
        # (_start_circular_worker) når brukeren faktisk åpner kart-fanen.
        overview: dict[str, Any] | None = None
        error: Exception | None = None
        try:
            overview = get_client_ownership_overview(client, year)
        except Exception as exc:  # pragma: no cover - handled on UI thread
            error = exc
        try:
            self.after(0, lambda: self._apply_loaded_overview(request_id, client, year, overview, error))
        except Exception:
            return

    def _apply_loaded_overview(
        self,
        request_id: int,
        client: str,
        year: str,
        overview: dict[str, Any] | None,
        error: Exception | None,
    ) -> None:
        if request_id != self._overview_request_id:
            return
        if client != self._client or year != self._year:
            return
        self._overview_loading = False
        if error is not None:
            self.var_status.set(f"AR-feil: {error}")
            messagebox.showerror("AR", str(error))
            return

        self._overview = overview or {}
        # Ny overview → tidligere circular-worker er automatisk stale.
        self._circular_request_id += 1
        client_orgnr = _safe_text(self._overview.get("client_orgnr")) or "-"
        self.var_orgnr.set(client_orgnr)

        accepted = self._overview.get("accepted_meta") or {}
        current_meta = self._overview.get("registry_meta") or {}
        pending = self._overview.get("pending_changes") or []
        owned = self._overview.get("owned_companies") or []
        owners = self._overview.get("owners") or []
        self_ownership = self._overview.get("self_ownership") or {}
        owners_year = _safe_text(self._overview.get("owners_year_used"))

        if client_orgnr == "-":
            self.var_status.set("Mangler org.nr — legg inn under Regnskap-fanen.")
        else:
            self.var_status.set("")
        self._update_trace_strip()
        self._refresh_trees()

    # ── Lazy circular-ownership worker ─────────────────────────
    # Kjøres kun når kart-fanen er synlig, aldri under kritisk AR-load.
    # Bruker egen request-id slik at gamle resultater ikke skriver seg inn
    # i en nyere overview.

    def _start_circular_worker(self) -> None:
        if not self._client or not self._year:
            return
        if not isinstance(self._overview, dict):
            return
        if "circular_ownership_cycles" in self._overview:
            return
        if self._circular_in_flight:
            return
        self._circular_request_id += 1
        request_id = self._circular_request_id
        client = self._client
        year = self._year
        self._circular_in_flight = True
        threading.Thread(
            target=self._circular_worker,
            args=(request_id, client, year),
            daemon=True,
        ).start()

    def _circular_worker(self, request_id: int, client: str, year: str) -> None:
        cycles: list = []
        error: Exception | None = None
        try:
            cycles = list(detect_circular_ownership(year))
        except Exception as exc:  # pragma: no cover - robust mot DB-feil
            error = exc
        try:
            self.after(0, lambda: self._apply_circular_result(request_id, client, year, cycles, error))
        except Exception:
            return

    def _apply_circular_result(
        self,
        request_id: int,
        client: str,
        year: str,
        cycles: list,
        error: Exception | None,
    ) -> None:
        self._circular_in_flight = False
        if request_id != self._circular_request_id:
            return
        if client != self._client or year != self._year:
            return
        if not isinstance(self._overview, dict):
            return
        self._overview["circular_ownership_cycles"] = [] if error else cycles
        # Kart-fanen kan vise varsel nå. Hvis brukeren fortsatt ser kartet
        # og ikke drar, tegn på nytt slik at varselet dukker opp.
        if self._is_chart_tab_selected() and not getattr(self, "_chart_dragging", False):
            self._refresh_org_chart()

    def _has_current_import(self) -> bool:
        """True iff a RF-1086 import exists for the current year in the overview."""
        ov = self._overview or {}
        return bool(ov.get("import_trace_current"))

    def _update_trace_strip(self) -> None:
        """Populate the top sporbarhetsstripe based on current overview."""
        ov = self._overview or {}
        base_year = _safe_text(ov.get("owners_base_year_used"))
        source_year = _safe_text(ov.get("owners_current_year_used"))
        view_year = _safe_text(self._year) or _safe_text(ov.get("year")) or source_year

        if base_year and view_year and base_year != view_year:
            self.var_trace_compare.set(f"Sammenligning: {base_year} → {view_year}")
        elif view_year:
            if source_year and source_year != view_year:
                self.var_trace_compare.set(
                    f"Sammenligning: {view_year} (videreført fra {source_year})"
                )
            else:
                self.var_trace_compare.set(
                    f"Sammenligning: {view_year} (ingen tidligere snapshot)"
                )
        else:
            self.var_trace_compare.set("Sammenligning: –")

        accepted = ov.get("accepted_meta") or {}
        source_kind = _safe_text(accepted.get("source_kind"))
        basis_label = {
            "carry_forward": "videreført",
            "register_baseline": "register",
            "accepted_update": "godkjent",
        }.get(source_kind, source_kind)
        basis_target = view_year or "–"
        if source_year and source_year != view_year and basis_label:
            basis_label = f"{basis_label} (fra {source_year})"
        self.var_trace_basis.set(
            f"Grunnlag for {basis_target}: {basis_label}" if basis_label else f"Grunnlag for {basis_target}: –"
        )

        trace = ov.get("import_trace_current") or {}
        if trace:
            reg_year = _safe_text(trace.get("register_year")) or _safe_text(trace.get("target_year")) or view_year
            imported_at = _safe_text(trace.get("imported_at_utc"))[:10]
            label = f"RF-1086 for {view_year or reg_year}: importert"
            if imported_at:
                label += f" {imported_at}"
            self.var_trace_import.set(label)
            stored = _safe_text(trace.get("stored_file_path"))
            self._current_source_pdf = stored
            state = "normal" if stored and Path(stored).exists() else "disabled"
            try:
                self._btn_open_source_pdf.configure(state=state)
            except Exception:
                pass
        else:
            self.var_trace_import.set(
                f"RF-1086 for {view_year}: ikke importert" if view_year else "RF-1086: ikke importert"
            )
            self._current_source_pdf = ""
            try:
                self._btn_open_source_pdf.configure(state="disabled")
            except Exception:
                pass

    def _open_current_source_pdf(self) -> None:
        path = self._current_source_pdf
        self._open_pdf_path(path)

    def _open_pdf_path(self, path: str | None) -> None:
        if not path:
            messagebox.showinfo("AR", "Ingen kildefil lagret for denne importen.")
            return
        p = Path(path)
        if not p.exists():
            messagebox.showwarning("AR", f"Kildefilen finnes ikke lenger:\n{p}")
            return
        import os
        try:
            os.startfile(str(p))  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("AR", f"Kunne ikke åpne PDF:\n{exc}")

    def _filter_owned_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        search_var = getattr(self, "var_owned_search", None)
        try:
            query_text = search_var.get() if search_var is not None else ""
        except Exception:
            query_text = ""
        query = _safe_text(query_text).casefold()
        if not query:
            return list(rows)
        out: list[dict[str, Any]] = []
        for row in rows:
            fields = (
                _safe_text(row.get("company_name")),
                _safe_text(row.get("company_orgnr")),
                _safe_text(row.get("matched_client")),
            )
            if any(query in f.casefold() for f in fields if f):
                out.append(row)
        return out

    def _refresh_trees(self) -> None:
        self._owned_rows_by_iid = {}
        self._owners_rows_by_iid = {}
        self._change_rows_by_iid = {}
        self._shareholder_change_rows_by_iid = {}

        self._tree_owned.delete(*self._tree_owned.get_children())
        all_owned = self._overview.get("owned_companies") or []
        filtered_owned = self._filter_owned_rows(list(all_owned))
        for idx, row in enumerate(filtered_owned, start=1):
            iid = f"owned-{idx}"
            self._owned_rows_by_iid[iid] = dict(row)
            source = _safe_text(row.get("source"))
            tag = (source,) if source in {"manual", "manual_override", "carry_forward"} else ()
            self._tree_owned.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row.get("company_name", ""),
                    row.get("company_orgnr", ""),
                    _fmt_pct(row.get("ownership_pct")),
                    _relation_label(row.get("relation_type")),
                    row.get("matched_client", ""),
                    "Ja" if row.get("has_active_sb") else "",
                    _source_label(source),
                ),
                tags=tag,
            )

        # ── Union-compare tree populated from owners_compare ──
        self._populate_compare_tree()

        # ── Aksjonærendringer i klienten (read-only, filtered owners_compare) ──
        sh_tree = getattr(self, "_tree_shareholder_changes", None)
        if sh_tree is not None:
            self._shareholder_change_rows_by_iid = {}
            sh_tree.delete(*sh_tree.get_children())

            ov = self._overview or {}
            raw_base_year = _safe_text(ov.get("owners_base_year_used"))
            source_year = _safe_text(ov.get("owners_current_year_used"))
            view_year = _safe_text(self._year) or _safe_text(ov.get("year")) or source_year or "nå"
            has_base = bool(raw_base_year) and raw_base_year != source_year
            try:
                if has_base:
                    sh_tree.heading("shares_base", text=f"Aksjer {raw_base_year}")
                else:
                    sh_tree.heading("shares_base", text="Aksjer (ingen sammenligning)")
                if source_year and source_year != view_year:
                    sh_tree.heading("shares_current", text=f"Aksjer {view_year} (fra {source_year})")
                    sh_tree.heading("pct_current", text=f"Eierandel {view_year} (fra {source_year})")
                else:
                    sh_tree.heading("shares_current", text=f"Aksjer {view_year}")
                    sh_tree.heading("pct_current", text=f"Eierandel {view_year}")
            except Exception:
                pass

            sh_rows = ov.get("owners_compare_changed") or []
            for idx, row in enumerate(sh_rows, start=1):
                iid = f"sh-change-{idx}"
                self._shareholder_change_rows_by_iid[iid] = dict(row)
                ct = _safe_text(row.get("change_type")).lower()
                change_label = {
                    "new": "Ny",
                    "removed": "Mangler",
                    "changed": "Endret",
                }.get(ct, ct or "-")
                shares_base = int(row.get("shares_base") or 0)
                shares_current = int(row.get("shares_current") or 0)
                delta = int(row.get("shares_delta") or 0)
                pct_current = float(row.get("ownership_pct_current") or 0.0)
                has_trace = "Ja" if _safe_text(row.get("current_import_id")) else ""
                sh_tree.insert(
                    "", "end", iid=iid,
                    values=(
                        _safe_text(row.get("shareholder_name")),
                        change_label,
                        _fmt_thousand(shares_base),
                        _fmt_thousand(shares_current),
                        _fmt_signed_thousand(delta),
                        _fmt_optional_pct(pct_current) if pct_current else "",
                        has_trace,
                    ),
                    tags=(ct,) if ct in {"new", "removed", "changed"} else (),
                )

            if hasattr(self, "_lbl_sh_changes_empty"):
                if sh_rows:
                    self.var_sh_changes_empty.set("")
                    try:
                        self._lbl_sh_changes_empty.grid_remove()
                    except Exception:
                        pass
                else:
                    year_text = _safe_text(self._year) or "valgt år"
                    self.var_sh_changes_empty.set(
                        f"Ingen aksjonærendringer registrert for {year_text}."
                    )
                    try:
                        self._lbl_sh_changes_empty.grid(row=0, column=0, sticky="w", pady=(0, 4))
                    except Exception:
                        pass

        self._tree_changes.delete(*self._tree_changes.get_children())
        pending_changes = self._overview.get("pending_changes") or []
        for idx, row in enumerate(pending_changes, start=1):
            iid = f"change-{idx}"
            self._change_rows_by_iid[iid] = dict(row)
            is_owner_row = _safe_text(row.get("kind")) == "owner"
            if is_owner_row:
                display_name = _safe_text(row.get("shareholder_name"))
                display_orgnr = _safe_text(row.get("shareholder_orgnr"))
                current_label = (
                    f"{_fmt_optional_pct(row.get('current_pct'))} | "
                    f"{_fmt_thousand(int(row.get('current_shares') or 0))} aksjer"
                )
                candidate_label = (
                    f"{_fmt_optional_pct(row.get('candidate_pct'))} | "
                    f"{_fmt_thousand(int(row.get('candidate_shares') or 0))} aksjer"
                )
            else:
                display_name = row.get("company_name", "")
                display_orgnr = row.get("company_orgnr", "")
                current_label = (
                    f"{_fmt_optional_pct(row.get('current_pct'))} | {_relation_label(row.get('current_relation'))}"
                    if row.get("current_pct") is not None
                    else "-"
                )
                candidate_label = (
                    f"{_fmt_optional_pct(row.get('candidate_pct'))} | {_relation_label(row.get('candidate_relation'))}"
                    if row.get("candidate_pct") is not None
                    else "-"
                )
            self._tree_changes.insert(
                "",
                "end",
                iid=iid,
                values=(
                    display_name,
                    display_orgnr,
                    _change_type_label(row.get("change_type")),
                    current_label,
                    candidate_label,
                    _source_label(row.get("current_source") or row.get("candidate_source")),
                ),
            )

        # Hide the whole pending-frame when empty; otherwise show it with active buttons.
        pending_frame = getattr(self, "_pending_frame", None)
        if pending_frame is not None:
            try:
                if pending_changes:
                    pending_frame.grid()
                else:
                    pending_frame.grid_remove()
            except Exception:
                pass
        self.var_changes_empty.set("")
        try:
            self._lbl_changes_empty.grid_remove()
        except Exception:
            pass
        try:
            self._btn_accept_all.configure(state="normal" if pending_changes else "disabled")
            self._btn_accept_selected.configure(state="disabled")
        except Exception:
            pass

        # ── Importhistorikk ──
        hist_tree = getattr(self, "_tree_history", None)
        if hist_tree is not None:
            self._history_rows_by_iid = {}
            hist_tree.delete(*hist_tree.get_children())
            history_rows = self._overview.get("import_history") or []
            for idx, row in enumerate(history_rows, start=1):
                iid = f"imp-{idx}"
                self._history_rows_by_iid[iid] = dict(row)
                stored = _safe_text(row.get("stored_file_path"))
                status = "OK" if stored and Path(stored).exists() else "Mangler fil" if stored else "-"
                reg_year = _safe_text(row.get("register_year")) or _safe_text(row.get("target_year"))
                hist_tree.insert(
                    "", "end", iid=iid,
                    values=(
                        reg_year,
                        _safe_text(row.get("imported_at_utc"))[:19],
                        _safe_text(row.get("source_file")),
                        _fmt_thousand(int(row.get("shareholders_count") or 0)),
                        status,
                    ),
                )

            if hasattr(self, "_lbl_history_empty"):
                if history_rows:
                    self.var_history_empty.set("")
                    try:
                        self._lbl_history_empty.grid_remove()
                    except Exception:
                        pass
                else:
                    self.var_history_empty.set("Ingen RF-1086-importer lagret.")
                    try:
                        self._lbl_history_empty.grid(row=0, column=0, sticky="w", pady=(0, 4))
                    except Exception:
                        pass

        self._chart_dirty = True
        # Ikke tegn kartet på nytt midt i en aktiv drag — det fjerner
        # canvas-elementer bruker er i ferd med å flytte. on_chart_release
        # plukker opp _chart_dirty og re-rendrer når brukeren slipper.
        if self._is_chart_tab_selected() and not getattr(self, "_chart_dragging", False):
            self._refresh_org_chart()
        self._on_new_manual_change()

    def _populate_compare_tree(self) -> None:
        page_ar_compare.populate_compare_tree(self)

    def _clear_compare_detail(self) -> None:
        page_ar_compare.clear_compare_detail(self)

    def _on_compare_selected(self, _event=None) -> None:
        page_ar_compare.on_compare_selected(self, _event)

    def _on_compare_open_pdf(self) -> None:
        page_ar_compare.on_compare_open_pdf(self)

    def _on_compare_show_import_detail(self) -> None:
        page_ar_compare.on_compare_show_import_detail(self)

    def _show_persisted_import_detail(self, import_id: str) -> None:
        page_ar_compare.show_persisted_import_detail(self, import_id)

    def _is_chart_tab_selected(self) -> bool:
        return page_ar_chart.is_chart_tab_selected(self)

    def _on_tab_changed(self, event=None) -> None:
        page_ar_chart.on_tab_changed(self, event)

    def _selected_change_keys(self) -> list[str]:
        return page_ar_compare.selected_change_keys(self)

    def _draw_box(
        self,
        canvas: tk.Canvas,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        title: str,
        subtitle: str,
        fill: str,
        accent: str = "#98A2B3",
        action_key: str | None = None,
    ) -> None:
        page_ar_chart.draw_box(
            self, canvas, x, y, width, height,
            title=title, subtitle=subtitle, fill=fill,
            accent=accent, action_key=action_key,
        )

    def _chart_action_key_from_current(self) -> str:
        return page_ar_chart.chart_action_key_from_current(self)

    def _on_chart_press(self, event) -> None:
        page_ar_chart.on_chart_press(self, event)

    def _on_chart_drag(self, event) -> None:
        page_ar_chart.on_chart_drag(self, event)

    def _on_chart_release(self, _event) -> None:
        page_ar_chart.on_chart_release(self, _event)

    def _on_chart_mousewheel(self, event) -> None:
        page_ar_chart.on_chart_mousewheel(self, event)

    def _on_chart_double_click(self, event) -> None:
        page_ar_chart.on_chart_double_click(self, event)

    def _open_owner_drilldown(
        self,
        *,
        orgnr: str = "",
        name: str = "",
        lookup_year: str = "",
    ) -> None:
        if not orgnr:
            return
        if not lookup_year:
            overview = self._overview if isinstance(self._overview, dict) else {}
            lookup_year = str(overview.get("owners_year_used") or self._year or "")
        import page_ar_drilldown
        dlg = page_ar_drilldown._OwnerDrilldownDialog(
            self, orgnr=orgnr, name=name, lookup_year=lookup_year,
        )
        dlg.show()

    def _update_chart_zoom_label(self) -> None:
        page_ar_chart.update_chart_zoom_label(self)

    def _chart_apply_zoom(self, factor: float, x: float | None = None, y: float | None = None) -> None:
        page_ar_chart.chart_apply_zoom(self, factor, x, y)

    def _chart_reset_view(self) -> None:
        page_ar_chart.chart_reset_view(self)

    def _chart_fit_view(self) -> None:
        page_ar_chart.chart_fit_view(self)

    def _chart_positions_path(self) -> Path | None:
        return page_ar_chart.chart_positions_path(self)

    def _load_chart_positions(self) -> dict[str, list[float]]:
        return page_ar_chart.load_chart_positions(self)

    def _save_chart_positions(self) -> None:
        page_ar_chart.save_chart_positions(self)

    def _clear_chart_positions(self) -> None:
        page_ar_chart.clear_chart_positions(self)

    def _redraw_edges_for_node(self, pos_key: str) -> None:
        page_ar_chart.redraw_edges_for_node(self, pos_key)

    def _update_chart_scrollregion(self) -> None:
        page_ar_chart.update_chart_scrollregion(self)

    def _select_owned_row(self, *, company_orgnr: str = "", company_name: str = "") -> None:
        page_ar_chart.select_owned_row(self, company_orgnr=company_orgnr, company_name=company_name)

    def _select_owner_row(self, *, owner_orgnr: str = "", owner_name: str = "") -> None:
        page_ar_chart.select_owner_row(self, owner_orgnr=owner_orgnr, owner_name=owner_name)

    def _execute_chart_action(self, action: dict[str, Any]) -> None:
        page_ar_chart.execute_chart_action(self, action)

    def _refresh_org_chart(self) -> None:
        page_ar_chart.refresh_org_chart(self)

    def _on_accept_selected_changes(self) -> None:
        page_ar_compare.on_accept_selected_changes(self)

    def _on_accept_all_changes(self) -> None:
        page_ar_compare.on_accept_all_changes(self)

    def _on_import_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Importer RF-1086 aksjonærregisteroppgave",
            filetypes=[("PDF (RF-1086)", "*.pdf"), ("Alle filer", "*.*")],
        )
        if not path:
            return
        self._import_registry_pdf(Path(path))

    def _import_registry_pdf(self, path: Path) -> None:
        from ar_registry_pdf_parser import parse_rf1086_pdf
        from ar_registry_pdf_review_dialog import ArRegistryPdfReviewDialog

        self.var_status.set("Leser PDF ...")
        self.update_idletasks()
        try:
            parse_result = parse_rf1086_pdf(path)
        except Exception as exc:
            messagebox.showerror("AR", f"Kunne ikke lese PDF:\n{exc}")
            self.var_status.set("")
            return

        year = parse_result.header.year or self._year or ""
        if not year:
            year = simpledialog.askstring(
                "Aksjonærregister",
                "Kunne ikke detektere år fra PDF. Oppgi år:",
                initialvalue=self._year or "",
            ) or ""
        if not year:
            self.var_status.set("")
            return

        dlg = ArRegistryPdfReviewDialog(self, pdf_path=path, parse_result=parse_result)
        self.wait_window(dlg)

        if not dlg.result:
            self.var_status.set("")
            return

        # Warn if register year differs from active AR year
        register_year = _safe_text(parse_result.header.year)
        if register_year and self._year and register_year != year:
            if not messagebox.askyesno(
                "AR",
                (
                    f"PDF-en angir registerår {register_year}, men du importerer til "
                    f"{year}. Fortsett likevel?"
                ),
            ):
                self.var_status.set("")
                return

        self.var_status.set("Importerer aksjonærregister fra PDF ...")
        self.update_idletasks()
        try:
            meta = import_registry_pdf(
                parse_result,
                year=year,
                source_file=path.name,
                client=self._client,
                source_path=path,
            )
        except Exception as exc:
            messagebox.showerror("AR", f"Import feilet:\n{exc}")
            self.var_status.set("")
            return

        if self._client and self._year:
            self._refresh_current_overview()
        if year == self._year:
            self.after(100, self._select_changes_tab_if_pending)
        self.var_status.set(f"RF-1086 importert ({meta.get('rows_read', 0)} rader)")

    def _select_changes_tab_if_pending(self) -> None:
        page_ar_compare.select_changes_tab_if_pending(self)

    def _export_excel(self) -> None:
        """Eksporter AR-data til Excel."""
        try:
            import session as _session
            import analyse_export_excel as _xls

            client = getattr(_session, "client", None) or ""
            year = str(getattr(_session, "year", "") or "")

            path = _xls.open_save_dialog(
                title="Eksporter aksjonærregister",
                default_filename=f"AR_{client}_{year}.xlsx".strip("_"),
                master=self,
            )
            if not path:
                return

            def _has_rows(tree) -> bool:
                try:
                    return bool(tree.get_children(""))
                except Exception:
                    return False

            sheets = []
            if hasattr(self, "_tree_owned") and _has_rows(self._tree_owned):
                sheets.append(_xls.treeview_to_sheet(
                    self._tree_owned, title="Eide selskaper",
                    heading="Eide selskaper"))
            if hasattr(self, "_tree_owners") and _has_rows(self._tree_owners):
                sheets.append(_ar_sheet_respecting_displaycolumns(
                    _xls, self._tree_owners, title="Eiere i klienten",
                    heading="Eiere i klienten"))
            if hasattr(self, "_tree_shareholder_changes") and _has_rows(self._tree_shareholder_changes):
                sheets.append(_xls.treeview_to_sheet(
                    self._tree_shareholder_changes, title="Aksjonærendringer",
                    heading="Aksjonærendringer i klienten"))
            if hasattr(self, "_tree_changes") and _has_rows(self._tree_changes):
                sheets.append(_xls.treeview_to_sheet(
                    self._tree_changes, title="Registerendringer",
                    heading="Ventende registerendringer i eide selskaper"))
            if hasattr(self, "_tree_history") and _has_rows(self._tree_history):
                sheets.append(_xls.treeview_to_sheet(
                    self._tree_history, title="Importhistorikk",
                    heading="Importhistorikk"))

            if not sheets:
                from tkinter import messagebox
                messagebox.showinfo("Eksport", "Ingen data å eksportere.")
                return

            _xls.export_and_open(path, sheets, title="AR", client=client, year=year)
        except Exception as exc:
            from tkinter import messagebox
            messagebox.showerror("Eksport", f"Feil ved eksport:\n{exc}")


from .import_detail_dialog import _ImportDetailDialog  # noqa: F401


class _ManualOwnerChangeDialog(tk.Toplevel):
    """Editor for ManualOwnerChange (upsert). Remove/delete use separate buttons."""

    _KIND_CHOICES = ("unknown", "company", "person")

    def __init__(self, parent: tk.Misc, *, prefill: dict[str, Any] | None) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("Manuell aksjonær-endring")
        self.resizable(False, False)
        self.saved = False
        self.result: ManualOwnerChange | None = None
        self._prefill = prefill or {}

        self.var_name = tk.StringVar(value=_safe_text(self._prefill.get("shareholder_name")))
        self.var_orgnr = tk.StringVar(value=_safe_text(self._prefill.get("shareholder_orgnr")))
        kind = _safe_text(self._prefill.get("shareholder_kind")) or "unknown"
        if kind not in self._KIND_CHOICES:
            kind = "unknown"
        self.var_kind = tk.StringVar(value=kind)
        self.var_shares = tk.StringVar(value=str(int(self._prefill.get("shares") or 0) or ""))
        self.var_total_shares = tk.StringVar(
            value=str(int(self._prefill.get("total_shares") or 0) or "")
        )
        pct_val = float(self._prefill.get("ownership_pct") or 0.0)
        self.var_pct = tk.StringVar(value=f"{pct_val:.4f}".rstrip("0").rstrip(".") if pct_val else "")
        self.var_note = tk.StringVar(value=_safe_text(self._prefill.get("note")))

        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        rows = (
            ("Aksjonær (navn):", ttk.Entry(body, textvariable=self.var_name, width=38)),
            ("Org.nr / fødselsår:", ttk.Entry(body, textvariable=self.var_orgnr, width=20)),
            (
                "Type:",
                ttk.Combobox(
                    body, textvariable=self.var_kind,
                    values=self._KIND_CHOICES, state="readonly", width=12,
                ),
            ),
            ("Aksjer:", ttk.Entry(body, textvariable=self.var_shares, width=14)),
            ("Totalt antall aksjer:", ttk.Entry(body, textvariable=self.var_total_shares, width=14)),
            ("Eierandel %:", ttk.Entry(body, textvariable=self.var_pct, width=14)),
            ("Notat:", ttk.Entry(body, textvariable=self.var_note, width=38)),
        )
        for r, (label, widget) in enumerate(rows):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=2)
            widget.grid(row=r, column=1, sticky="ew", pady=2, padx=(8, 0))

        help_text = (
            "Manuelle overstyringer overlever RF-1086-import. Ved avvik mot nytt "
            "register genereres en pending-endring som må godkjennes eksplisitt."
        )
        ttk.Label(
            body, text=help_text, foreground="#667085", wraplength=360, justify="left",
        ).grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(8, 2))

        btns = ttk.Frame(body)
        btns.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Avbryt", command=self._on_cancel).pack(side="right")
        ttk.Button(btns, text="Lagre", command=self._on_save).pack(side="right", padx=(0, 6))

        self.bind("<Escape>", lambda _e: self._on_cancel())
        self.bind("<Return>", lambda _e: self._on_save())
        self.grab_set()
        self.update_idletasks()
        try:
            self.geometry(
                f"+{parent.winfo_rootx() + 80}+{parent.winfo_rooty() + 80}"
            )
        except Exception:
            pass

    def _parse_int(self, text: str) -> int:
        text = (text or "").strip().replace(" ", "")
        if not text:
            return 0
        try:
            return int(float(text))
        except Exception:
            return 0

    def _on_save(self) -> None:
        name = _safe_text(self.var_name.get())
        orgnr = normalize_orgnr(self.var_orgnr.get())
        if not name and not orgnr:
            messagebox.showwarning(
                "AR", "Skriv inn aksjonær-navn eller org.nr.", parent=self,
            )
            return
        try:
            pct = float((self.var_pct.get() or "0").replace(",", ".").strip())
        except Exception:
            messagebox.showerror("AR", "Ugyldig eierandel.", parent=self)
            return
        change_id = _safe_text(self._prefill.get("change_id")) or ManualOwnerChange().change_id
        self.result = ManualOwnerChange(
            change_id=change_id,
            op=MANUAL_OWNER_OP_UPSERT,
            shareholder_name=name,
            shareholder_orgnr=orgnr,
            shareholder_kind=_safe_text(self.var_kind.get()) or "unknown",
            shares=self._parse_int(self.var_shares.get()),
            total_shares=self._parse_int(self.var_total_shares.get()),
            ownership_pct=pct,
            note=_safe_text(self.var_note.get()),
        )
        self.saved = True
        self.destroy()

    def _on_cancel(self) -> None:
        self.saved = False
        self.destroy()

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
import threading
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

import session
from ar_store import (
    ManualOwnedChange,
    accept_pending_ownership_changes,
    classify_relation_type,
    delete_manual_owned_change,
    get_client_ownership_overview,
    import_registry_pdf,
    normalize_orgnr,
    parse_year_from_filename,
    upsert_manual_owned_change,
)


def _fmt_pct(value: object) -> str:
    try:
        pct = float(value or 0.0)
    except Exception:
        pct = 0.0
    return f"{pct:.2f}".replace(".", ",")


def _fmt_optional_pct(value: object) -> str:
    if value in (None, ""):
        return "-"
    return _fmt_pct(value)


def _parse_float(value: object) -> float:
    text = str(value or "").strip().replace(" ", "").replace("\u00a0", "")
    if not text:
        return 0.0
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    return float(text)


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _relation_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "datter":
        return "Datter"
    if text == "tilknyttet":
        return "Tilknyttet"
    if text == "investering":
        return "Investering"
    if text == "vurder":
        return "Vurder"
    return text or "-"


def _source_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "register":
        return "Register"
    if text == "accepted_register":
        return "Godkjent register"
    if text == "carry_forward":
        return "Videreført"
    if text == "manual":
        return "Manuell"
    if text == "manual_override":
        return "Register + manuell"
    return text or "-"


def _fmt_thousand(n: object) -> str:
    try:
        value = int(n or 0)
    except Exception:
        return str(n or "")
    return f"{value:,}".replace(",", "\u00a0")


def _fmt_signed_thousand(n: object) -> str:
    try:
        value = int(n or 0)
    except Exception:
        return str(n or "")
    if value > 0:
        return f"+{_fmt_thousand(value)}"
    if value < 0:
        return f"\u2212{_fmt_thousand(-value)}"
    return "0"


def _fmt_currency(v: object) -> str:
    try:
        value = float(v or 0.0)
    except Exception:
        return str(v or "")
    if value == 0:
        return ""
    sign = "-" if value < 0 else ""
    abs_val = abs(value)
    whole, frac = divmod(round(abs_val * 100), 100)
    whole_str = f"{int(whole):,}".replace(",", "\u00a0")
    return f"{sign}{whole_str},{int(frac):02d}"


def _compare_change_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "new":
        return "Ny"
    if text == "removed":
        return "Borte"
    if text == "changed":
        return "Endret"
    if text == "unchanged":
        return "Uendret"
    return text or "-"


def _change_type_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "added":
        return "Ny i register"
    if text == "removed":
        return "Mangler i register"
    if text == "changed":
        return "Endret"
    return text or "-"


def _relation_fill(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "datter":
        return "#DBF5E8"
    if text == "tilknyttet":
        return "#FFF2D6"
    if text == "investering":
        return "#E7EEFF"
    if text == "vurder":
        return "#F2F4F7"
    return "#F8FAFC"


def _relation_accent(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "datter":
        return "#1F7A4D"
    if text == "tilknyttet":
        return "#B26B00"
    if text == "investering":
        return "#2952A3"
    if text == "vurder":
        return "#667085"
    return "#98A2B3"


def _build_owned_help_text(row: dict[str, Any] | None, *, year: str, accepted_meta: dict[str, Any] | None) -> str:
    if not row:
        return (
            "Velg en rad for Ã¥ se hva eierskapet betyr, hvilken kilde som brukes, "
            "og om raden kan sendes videre til konsolidering."
        )

    company_name = _safe_text(row.get("company_name")) or "ukjent selskap"
    pct_text = _fmt_pct(row.get("ownership_pct"))
    relation = _relation_label(row.get("relation_type"))
    source = _safe_text(row.get("source"))
    accepted_meta = accepted_meta or {}

    parts = [f"Klienten eier {pct_text} % av {company_name}. Klassifisering: {relation}."]

    if source == "carry_forward":
        source_year = _safe_text(accepted_meta.get("source_year"))
        if source_year:
            parts.append(f"Raden er viderefÃ¸rt fra akseptert eierstatus {source_year}.")
        else:
            parts.append("Raden er viderefÃ¸rt fra tidligere akseptert eierstatus.")
    elif source == "accepted_register":
        source_year = _safe_text(accepted_meta.get("register_year")) or year
        parts.append(f"Raden bygger pÃ¥ godkjent aksjonÃ¦rregister {source_year}.")
    elif source == "manual_override":
        parts.append("Raden er manuelt overstyrt og brukes foran registeret til nye endringer eventuelt godkjennes.")
    elif source == "manual":
        parts.append("Raden er lagt inn manuelt fordi eierskapet ikke finnes i registergrunnlaget ennÃ¥.")

    matched_client = _safe_text(row.get("matched_client"))
    if matched_client:
        if row.get("has_active_sb"):
            parts.append(f"Klientmatch funnet: {matched_client}, og aktiv SB finnes for {year}.")
        else:
            parts.append(f"Klientmatch funnet: {matched_client}, men aktiv SB mangler for {year}.")
    else:
        parts.append("Ingen klientmatch pÃ¥ org.nr ennÃ¥.")

    return " ".join(parts)


def _ar_sheet_respecting_displaycolumns(_xls, tree, *, title: str, heading: str) -> dict:
    """Build sheet dict from a Treeview, filtering to its current displaycolumns."""
    sheet = _xls.treeview_to_sheet(tree, title=title, heading=heading)
    try:
        all_cols = list(tree["columns"])
        dc = tree.cget("displaycolumns")
        if isinstance(dc, str):
            dc_list = [dc]
        else:
            dc_list = list(dc or [])
        if not dc_list or dc_list == ["#all"]:
            return sheet
        keep_idx = [all_cols.index(c) for c in dc_list if c in all_cols]
        if not keep_idx:
            return sheet
        cols = sheet.get("columns") or []
        sheet["columns"] = [cols[i] for i in keep_idx if i < len(cols)]
        new_rows = []
        for row in sheet.get("rows") or []:
            vals = row.get("values") or []
            row = dict(row)
            row["values"] = [vals[i] for i in keep_idx if i < len(vals)]
            new_rows.append(row)
        sheet["rows"] = new_rows
    except Exception:
        pass
    return sheet


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
        # ── 1. Aksjonærendringer i klienten (read-only, built from owners_compare) ──
        sh_frame = ttk.LabelFrame(parent, text="Aksjonærendringer i klienten", padding=4)
        sh_frame.grid(row=0, column=0, sticky="nsew")
        sh_frame.columnconfigure(0, weight=1)
        sh_frame.rowconfigure(1, weight=1)

        self.var_sh_changes_empty = tk.StringVar(value="")
        self._lbl_sh_changes_empty = ttk.Label(
            sh_frame,
            textvariable=self.var_sh_changes_empty,
            foreground="#98A2B3",
            wraplength=700,
            justify="left",
        )

        sh_cols = ("owner", "change", "shares_base", "shares_current", "delta", "pct_current", "has_trace")
        sh_tree = ttk.Treeview(sh_frame, columns=sh_cols, show="headings", selectmode="browse")
        sh_tree.heading("owner", text="Aksjonær")
        sh_tree.heading("change", text="Endring")
        sh_tree.heading("shares_base", text="Aksjer (base)")
        sh_tree.heading("shares_current", text="Aksjer (nå)")
        sh_tree.heading("delta", text="\u0394 aksjer")
        sh_tree.heading("pct_current", text="Eierandel (nå)")
        sh_tree.heading("has_trace", text="RF-1086")
        sh_tree.column("owner", width=240, stretch=True)
        sh_tree.column("change", width=100)
        sh_tree.column("shares_base", width=110, anchor="e")
        sh_tree.column("shares_current", width=110, anchor="e")
        sh_tree.column("delta", width=90, anchor="e")
        sh_tree.column("pct_current", width=110, anchor="e")
        sh_tree.column("has_trace", width=110, anchor="center")
        sh_ysb = ttk.Scrollbar(sh_frame, orient="vertical", command=sh_tree.yview)
        sh_tree.configure(yscrollcommand=sh_ysb.set)
        sh_tree.grid(row=1, column=0, sticky="nsew")
        sh_ysb.grid(row=1, column=1, sticky="ns")
        sh_tree.bind("<Double-1>", self._on_shareholder_change_open)
        sh_tree.bind("<Return>", self._on_shareholder_change_open)
        self._tree_shareholder_changes = sh_tree
        self._shareholder_change_rows_by_iid: dict[str, dict] = {}

        # ── 2. Ventende registerendringer i eide selskaper (operative queue) ──
        pending_frame = ttk.LabelFrame(
            parent, text="Ventende registerendringer i eide selskaper", padding=4,
        )
        pending_frame.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        pending_frame.columnconfigure(0, weight=1)
        pending_frame.rowconfigure(2, weight=1)
        self._pending_frame = pending_frame

        bar = ttk.Frame(pending_frame)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self._btn_accept_selected = ttk.Button(
            bar, text="Godta valgte", command=self._on_accept_selected_changes, state="disabled",
        )
        self._btn_accept_selected.pack(side="left")
        self._btn_accept_all = ttk.Button(
            bar, text="Godta alle", command=self._on_accept_all_changes, state="disabled",
        )
        self._btn_accept_all.pack(side="left", padx=(4, 0))

        self.var_changes_empty = tk.StringVar(value="")
        self._lbl_changes_empty = ttk.Label(
            pending_frame,
            textvariable=self.var_changes_empty,
            foreground="#98A2B3",
            wraplength=700,
            justify="left",
        )

        tree = ttk.Treeview(
            pending_frame,
            columns=("company", "orgnr", "change", "current", "candidate", "source"),
            show="headings",
            selectmode="extended",
        )
        tree.heading("company", text="Selskap")
        tree.heading("orgnr", text="Org.nr")
        tree.heading("change", text="Endring")
        tree.heading("current", text="Gjeldende")
        tree.heading("candidate", text="Nytt register")
        tree.heading("source", text="Kilde")
        tree.column("company", width=260, stretch=True)
        tree.column("orgnr", width=95)
        tree.column("change", width=110)
        tree.column("current", width=180, stretch=True)
        tree.column("candidate", width=180, stretch=True)
        tree.column("source", width=130)
        tree.grid(row=2, column=0, sticky="nsew")
        tree.bind("<<TreeviewSelect>>", self._on_changes_selection_changed)
        self._tree_changes = tree

        # ── 3. Importhistorikk ──
        hist_frame = ttk.LabelFrame(parent, text="Importhistorikk", padding=4)
        hist_frame.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        hist_frame.columnconfigure(0, weight=1)
        hist_frame.rowconfigure(1, weight=1)

        self.var_history_empty = tk.StringVar(value="")
        self._lbl_history_empty = ttk.Label(
            hist_frame,
            textvariable=self.var_history_empty,
            foreground="#98A2B3",
            wraplength=700,
            justify="left",
        )

        hist_cols = ("register_year", "imported_at", "source_file", "shareholders", "status")
        hist_tree = ttk.Treeview(hist_frame, columns=hist_cols, show="headings", selectmode="browse")
        for cid, text, width, anchor in [
            ("register_year", "Registerår", 90, "center"),
            ("imported_at", "Importert", 150, "w"),
            ("source_file", "Kildefil", 340, "w"),
            ("shareholders", "Aksjonærer", 110, "e"),
            ("status", "Status", 120, "w"),
        ]:
            hist_tree.heading(cid, text=text)
            hist_tree.column(cid, width=width, anchor=anchor, stretch=(cid == "source_file"))

        hist_ysb = ttk.Scrollbar(hist_frame, orient="vertical", command=hist_tree.yview)
        hist_tree.configure(yscrollcommand=hist_ysb.set)
        hist_tree.grid(row=1, column=0, sticky="nsew")
        hist_ysb.grid(row=1, column=1, sticky="ns")

        hist_tree.bind("<Double-1>", self._on_history_open_detail)
        hist_tree.bind("<Return>", self._on_history_open_detail)

        self._tree_history = hist_tree
        self._history_rows_by_iid: dict[str, dict] = {}

    def _on_changes_selection_changed(self, _event=None) -> None:
        try:
            sel = self._tree_changes.selection()
            self._btn_accept_selected.configure(state="normal" if sel else "disabled")
        except Exception:
            pass

    def _on_shareholder_change_open(self, _event=None) -> None:
        tree = getattr(self, "_tree_shareholder_changes", None)
        if tree is None:
            return
        sel = tree.selection()
        if not sel:
            return
        row = self._shareholder_change_rows_by_iid.get(sel[0]) or {}
        orgnr = _safe_text(row.get("shareholder_orgnr"))
        name = _safe_text(row.get("shareholder_name"))
        target_iid = None
        for iid, cmp_row in self._compare_rows_by_iid.items():
            if orgnr and _safe_text(cmp_row.get("shareholder_orgnr")) == orgnr:
                target_iid = iid
                break
            if not orgnr and name and _safe_text(cmp_row.get("shareholder_name")) == name:
                target_iid = iid
                break
        try:
            self._nb.select(self._frm_owners)
        except Exception:
            pass
        if target_iid is None:
            return
        try:
            self._tree_owners.selection_set((target_iid,))
            self._tree_owners.focus(target_iid)
            self._tree_owners.see(target_iid)
            self._on_compare_selected()
        except Exception:
            pass

    def _on_history_open_detail(self, _event=None) -> None:
        tree = getattr(self, "_tree_history", None)
        if tree is None:
            return
        sel = tree.selection()
        if not sel:
            return
        row = self._history_rows_by_iid.get(sel[0]) or {}
        import_id = _safe_text(row.get("import_id"))
        if not import_id:
            return
        self._show_persisted_import_detail(import_id)

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
        orgnr = normalize_orgnr(_safe_text(row.get("company_orgnr")))
        name = _safe_text(row.get("company_name"))
        self._brreg_current_orgnr = orgnr
        self._selected_nr = orgnr
        self._update_brreg_header(orgnr, name)
        try:
            if orgnr and not (force_refresh and orgnr in self._brreg_data):
                pass
            self._btn_brreg_refresh.configure(state="normal" if orgnr else "disabled")
        except Exception:
            pass

        if not orgnr:
            self.var_brreg_status.set("Ingen gyldig org.nr for denne raden — BRREG kan ikke hentes.")
            try:
                import reskontro_brreg_panel
                reskontro_brreg_panel.update_brreg_panel(self, "")
            except Exception:
                pass
            return

        if not force_refresh and orgnr in self._brreg_data:
            self.var_brreg_status.set("Vist fra cache.")
            try:
                import reskontro_brreg_panel
                reskontro_brreg_panel.update_brreg_panel(self, orgnr)
            except Exception:
                pass
            return

        if orgnr in self._brreg_loading and not force_refresh:
            self.var_brreg_status.set("Henter BRREG-data…")
            return

        self._brreg_request_id += 1
        request_id = self._brreg_request_id
        self._brreg_loading.add(orgnr)
        self.var_brreg_status.set("Henter BRREG-data…")
        use_cache = not force_refresh
        threading.Thread(
            target=self._brreg_worker,
            args=(orgnr, request_id, use_cache),
            daemon=True,
        ).start()

    def _brreg_worker(self, orgnr: str, request_id: int, use_cache: bool) -> None:
        enhet = None
        regnskap = None
        error: str | None = None
        try:
            import brreg_client
            enhet = brreg_client.fetch_enhet(orgnr, use_cache=use_cache)
            regnskap = brreg_client.fetch_regnskap(orgnr, use_cache=use_cache)
        except Exception as exc:
            error = str(exc)
        try:
            self.after(0, self._brreg_apply_result, request_id, orgnr, enhet, regnskap, error)
        except Exception:
            pass

    def _brreg_apply_result(
        self,
        request_id: int,
        orgnr: str,
        enhet: dict[str, Any] | None,
        regnskap: dict[str, Any] | None,
        error: str | None,
    ) -> None:
        self._brreg_loading.discard(orgnr)
        if error:
            if orgnr == self._brreg_current_orgnr:
                self.var_brreg_status.set(f"Feil ved henting: {error}")
            return
        self._brreg_data[orgnr] = {"enhet": enhet or {}, "regnskap": regnskap or {}}
        if orgnr != self._brreg_current_orgnr:
            return
        if request_id != self._brreg_request_id:
            return
        self.var_brreg_status.set("Hentet fra BRREG.")
        try:
            import reskontro_brreg_panel
            reskontro_brreg_panel.update_brreg_panel(self, orgnr)
        except Exception as exc:
            self.var_brreg_status.set(f"Panel-feil: {exc}")

    def _on_brreg_refresh_clicked(self) -> None:
        row = self._selected_owned_row()
        if row is None:
            return
        orgnr = normalize_orgnr(_safe_text(row.get("company_orgnr")))
        if orgnr and orgnr in self._brreg_data:
            self._brreg_data.pop(orgnr, None)
        self._load_brreg_for_selected_row(row, force_refresh=True)

    def _update_brreg_header(self, orgnr: str, name: str) -> None:
        if not orgnr and not name:
            self.var_brreg_header.set("— velg et eid selskap —")
            return
        if orgnr and name:
            self.var_brreg_header.set(f"{name} ({orgnr})")
        elif name:
            self.var_brreg_header.set(name)
        else:
            self.var_brreg_header.set(orgnr)

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

    def _resolve_consolidation_page(self):
        app = getattr(session, "APP", None)
        if app is None:
            return None, None
        page = getattr(app, "page_consolidation", None)
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
        parent.rowconfigure(0, weight=1)

        pw = ttk.PanedWindow(parent, orient="vertical")
        pw.grid(row=0, column=0, sticky="nsew")
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

    def _has_current_import(self) -> bool:
        """True iff a RF-1086 import exists for the current year in the overview."""
        ov = self._overview or {}
        return bool(ov.get("import_trace_current"))

    def _update_trace_strip(self) -> None:
        """Populate the top sporbarhetsstripe based on current overview."""
        ov = self._overview or {}
        base_year = _safe_text(ov.get("owners_base_year_used"))
        cur_year = _safe_text(ov.get("owners_current_year_used")) or _safe_text(self._year)

        if base_year and cur_year and base_year != cur_year:
            self.var_trace_compare.set(f"Sammenligning: {base_year} → {cur_year}")
        elif cur_year:
            self.var_trace_compare.set(f"Sammenligning: {cur_year}")
        else:
            self.var_trace_compare.set("Sammenligning: –")

        accepted = ov.get("accepted_meta") or {}
        source_kind = _safe_text(accepted.get("source_kind"))
        basis_label = {
            "carry_forward": "videreført",
            "register_baseline": "register",
            "accepted_update": "godkjent",
        }.get(source_kind, source_kind)
        basis_target = cur_year or "–"
        self.var_trace_basis.set(
            f"Grunnlag for {basis_target}: {basis_label}" if basis_label else f"Grunnlag for {basis_target}: –"
        )

        trace = ov.get("import_trace_current") or {}
        if trace:
            reg_year = _safe_text(trace.get("register_year")) or _safe_text(trace.get("target_year")) or cur_year
            imported_at = _safe_text(trace.get("imported_at_utc"))[:10]
            label = f"RF-1086 for {cur_year or reg_year}: importert"
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
                f"RF-1086 for {cur_year}: ikke importert" if cur_year else "RF-1086: ikke importert"
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
            base_year = _safe_text(ov.get("owners_base_year_used")) or "base"
            cur_year = _safe_text(ov.get("owners_current_year_used")) or _safe_text(self._year) or "nå"
            try:
                sh_tree.heading("shares_base", text=f"Aksjer {base_year}")
                sh_tree.heading("shares_current", text=f"Aksjer {cur_year}")
                sh_tree.heading("pct_current", text=f"Eierandel {cur_year}")
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
                    row.get("company_name", ""),
                    row.get("company_orgnr", ""),
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
        if self._is_chart_tab_selected():
            self._refresh_org_chart()
        self._on_new_manual_change()

    def _populate_compare_tree(self) -> None:
        """Refill owners_compare tree and update year-aware column headings."""
        tree = self._tree_owners
        self._compare_rows_by_iid = {}
        self._owners_rows_by_iid = {}
        tree.delete(*tree.get_children())

        ov = self._overview or {}
        compare_rows = ov.get("owners_compare") or []
        base_year = _safe_text(ov.get("owners_base_year_used")) or "base"
        cur_year = _safe_text(ov.get("owners_current_year_used")) or _safe_text(ov.get("year")) or "nå"
        has_import = self._has_current_import()
        try:
            tree.heading("shares_base", text=f"Aksjer {base_year}")
            tree.heading("shares_current", text=f"Aksjer {cur_year}")
            tree.heading("pct_current", text=f"Eierandel {cur_year}")
        except Exception:
            pass

        # Show transaction columns only when current RF-1086 backs the values.
        try:
            if has_import:
                tree.configure(displaycolumns="#all")
            else:
                tree.configure(displaycolumns=(
                    "owner", "orgnr", "kind",
                    "shares_base", "shares_current", "shares_delta",
                    "pct_current",
                ))
        except Exception:
            pass

        if not compare_rows:
            self.var_owners_caption.set(
                "Ingen aksjonærdata importert ennå — bruk «Importer RF-1086 (PDF)» for å fylle oversikten.",
            )
        elif has_import:
            self.var_owners_caption.set(
                f"Aksjonærer i klienten — {base_year} → {cur_year} (RF-1086)",
            )
        else:
            self.var_owners_caption.set(
                f"Aksjonærer i klienten — {base_year} → {cur_year}",
            )

        for idx, row in enumerate(compare_rows, start=1):
            iid = f"compare-{idx}"
            self._compare_rows_by_iid[iid] = dict(row)
            change_type = _safe_text(row.get("change_type"))
            tag = (change_type,) if change_type in {"new", "removed", "changed"} else ()
            shares_base = int(row.get("shares_base") or 0)
            shares_current = int(row.get("shares_current") or 0)
            delta = int(row.get("shares_delta") or 0)
            bought = int(row.get("shares_bought") or 0)
            sold = int(row.get("shares_sold") or 0)
            tx_val = float(row.get("transaction_value_total") or 0.0)
            tree.insert(
                "", "end", iid=iid,
                values=(
                    _safe_text(row.get("shareholder_name")),
                    _safe_text(row.get("shareholder_orgnr")),
                    _safe_text(row.get("shareholder_kind")) or "unknown",
                    _fmt_thousand(shares_base),
                    _fmt_thousand(shares_current),
                    _fmt_signed_thousand(delta),
                    _fmt_thousand(bought) if bought else "",
                    _fmt_thousand(sold) if sold else "",
                    _fmt_currency(tx_val) if tx_val else "",
                    _fmt_pct(row.get("ownership_pct_current")),
                ),
                tags=tag,
            )

        # Clear detail panel
        self._clear_compare_detail()

    def _clear_compare_detail(self) -> None:
        self.var_compare_header.set("")
        self.var_detail_shares_base.set("–")
        self.var_detail_shares_current.set("–")
        self.var_detail_shares_delta.set("–")
        self.var_detail_pct_base.set("–")
        self.var_detail_pct_current.set("–")
        self.var_detail_change_type.set("–")
        self.var_compare_imported_at.set("–")
        self.var_compare_source_file.set("–")
        self.var_compare_source_year.set("–")
        has_import = self._has_current_import()
        accepted = (self._overview or {}).get("accepted_meta") or {}
        basis_kind = _safe_text(accepted.get("source_kind"))
        basis_label = {
            "carry_forward": "Videreført",
            "register_baseline": "Register",
            "accepted_update": "Godkjent",
        }.get(basis_kind, "Videreført")
        self.var_compare_data_basis.set(basis_label if not has_import else "RF-1086")
        self.var_compare_rf_status.set("importert" if has_import else "ikke importert")
        self.var_compare_tx_empty.set("")
        self.var_compare_no_import.set("")
        try:
            self._lbl_compare_tx_empty.grid_remove()
            self._lbl_compare_no_import.grid_remove()
            self._tree_compare_tx.delete(*self._tree_compare_tx.get_children())
            self._btn_compare_open_pdf.grid_remove()
            self._btn_compare_import_detail.grid_remove()
        except Exception:
            pass

    def _on_compare_selected(self, _event=None) -> None:
        sel = self._tree_owners.selection()
        if not sel:
            self._clear_compare_detail()
            return
        row = self._compare_rows_by_iid.get(sel[0])
        if not row:
            self._clear_compare_detail()
            return

        name = _safe_text(row.get("shareholder_name"))
        orgnr = _safe_text(row.get("shareholder_orgnr"))
        header = f"{name}" + (f"  ({orgnr})" if orgnr else "")
        self.var_compare_header.set(header)

        base_year = _safe_text(row.get("base_year")) or "base"
        cur_year = _safe_text(row.get("current_year")) or "nå"
        sb = int(row.get("shares_base") or 0)
        sc = int(row.get("shares_current") or 0)
        pb = float(row.get("ownership_pct_base") or 0.0)
        pc = float(row.get("ownership_pct_current") or 0.0)
        change = _compare_change_label(row.get("change_type"))
        self._lbl_detail_shares_base_title.configure(text=f"Aksjer {base_year}:")
        self._lbl_detail_shares_current_title.configure(text=f"Aksjer {cur_year}:")
        self._lbl_detail_pct_base_title.configure(text=f"Eierandel {base_year}:")
        self._lbl_detail_pct_current_title.configure(text=f"Eierandel {cur_year}:")
        self.var_detail_shares_base.set(_fmt_thousand(sb))
        self.var_detail_shares_current.set(_fmt_thousand(sc))
        self.var_detail_shares_delta.set(_fmt_signed_thousand(sc - sb))
        self.var_detail_pct_base.set(f"{_fmt_pct(pb)} %")
        self.var_detail_pct_current.set(f"{_fmt_pct(pc)} %")
        self.var_detail_change_type.set(change)

        # Transactions from trace detail
        key = ""
        if orgnr:
            key = f"org:{orgnr}"
        elif name:
            key = f"name:{name.casefold()}"

        trace = {}
        try:
            from ar_store import get_shareholder_trace_detail
            trace = get_shareholder_trace_detail(self._client, self._year, key) or {}
        except Exception:
            trace = {}

        has_import = self._has_current_import()
        year_for_msg = _safe_text(self._year) or "valgt år"

        self._tree_compare_tx.delete(*self._tree_compare_tx.get_children())
        if not has_import:
            # No RF-1086 for current year: replace tx grid with compact info block
            self.var_compare_no_import.set(
                f"RF-1086 for {year_for_msg} er ikke importert."
            )
            try:
                self._lbl_compare_no_import.grid(row=0, column=0, sticky="ew", pady=(0, 4))
                self._lbl_compare_tx_empty.grid_remove()
                self._tree_compare_tx.grid_remove()
            except Exception:
                pass
        else:
            self.var_compare_no_import.set("")
            try:
                self._lbl_compare_no_import.grid_remove()
                self._tree_compare_tx.grid(row=1, column=0, sticky="nsew")
            except Exception:
                pass
            tx_rows = trace.get("transactions") or []
            for tx in tx_rows:
                direction = _safe_text(tx.get("direction"))
                retning = "Tilgang" if direction == "tilgang" else "Avgang" if direction == "avgang" else direction
                self._tree_compare_tx.insert(
                    "", "end",
                    values=(
                        _safe_text(tx.get("date")),
                        retning,
                        _safe_text(tx.get("trans_type")),
                        _fmt_thousand(int(tx.get("shares") or 0)),
                        _fmt_currency(float(tx.get("amount") or 0.0)),
                    ),
                )
            if tx_rows:
                self.var_compare_tx_empty.set("")
                try:
                    self._lbl_compare_tx_empty.grid_remove()
                except Exception:
                    pass
            else:
                self.var_compare_tx_empty.set("Ingen registrerte kjøp/salg.")
                try:
                    self._lbl_compare_tx_empty.grid(row=0, column=0, sticky="w", pady=(0, 4))
                except Exception:
                    pass

        current_import = trace.get("current_import") or {}
        accepted = (self._overview or {}).get("accepted_meta") or {}
        basis_kind = _safe_text(accepted.get("source_kind"))
        basis_label = {
            "carry_forward": "Videreført",
            "register_baseline": "Register",
            "accepted_update": "Godkjent",
        }.get(basis_kind, "Videreført")
        if has_import:
            self.var_compare_data_basis.set("RF-1086")
            self.var_compare_rf_status.set("importert")
            self.var_compare_source_year.set(
                _safe_text(current_import.get("register_year"))
                or _safe_text(current_import.get("target_year")) or "–"
            )
            self.var_compare_imported_at.set(
                _safe_text(current_import.get("imported_at_utc"))[:16] or "–"
            )
            self.var_compare_source_file.set(
                _safe_text(current_import.get("source_file")) or "–"
            )
        else:
            self.var_compare_data_basis.set(basis_label)
            self.var_compare_rf_status.set("ikke importert")
            self.var_compare_source_year.set("–")
            self.var_compare_imported_at.set("–")
            self.var_compare_source_file.set("–")

        stored = _safe_text(trace.get("stored_file_path"))
        self._current_compare_pdf = stored
        self._current_compare_import_id = _safe_text(current_import.get("import_id"))
        try:
            if has_import:
                pdf_state = "normal" if stored and Path(stored).exists() else "disabled"
                self._btn_compare_open_pdf.configure(state=pdf_state)
                self._btn_compare_open_pdf.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 2))
                detail_state = "normal" if self._current_compare_import_id else "disabled"
                self._btn_compare_import_detail.configure(state=detail_state)
                self._btn_compare_import_detail.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(2, 2))
            else:
                self._btn_compare_open_pdf.grid_remove()
                self._btn_compare_import_detail.grid_remove()
        except Exception:
            pass

    def _on_compare_open_pdf(self) -> None:
        self._open_pdf_path(getattr(self, "_current_compare_pdf", ""))

    def _on_compare_show_import_detail(self) -> None:
        import_id = getattr(self, "_current_compare_import_id", "")
        if not import_id:
            messagebox.showinfo("AR", "Ingen import knyttet til denne aksjonæren.")
            return
        self._show_persisted_import_detail(import_id)

    def _show_persisted_import_detail(self, import_id: str) -> None:
        try:
            from ar_store import _load_import_detail
        except Exception as exc:
            messagebox.showerror("AR", f"Kunne ikke laste importdetaljer:\n{exc}")
            return
        detail = _load_import_detail(import_id) or {}
        if not detail:
            messagebox.showinfo("AR", "Fant ingen lagrede importdetaljer.")
            return
        _ImportDetailDialog(self, detail=detail).show()

    def _is_chart_tab_selected(self) -> bool:
        try:
            return str(self._nb.select()) == str(self._frm_chart)
        except Exception:
            return False

    def _on_tab_changed(self, event=None) -> None:
        if event is not None and getattr(event, "widget", None) is not self._nb:
            return
        if self._chart_dirty and not self._overview_loading and self._is_chart_tab_selected():
            self._refresh_org_chart()

    def _selected_change_keys(self) -> list[str]:
        keys: list[str] = []
        for iid in self._tree_changes.selection():
            row = self._change_rows_by_iid.get(iid)
            if row is None:
                continue
            key = _safe_text(row.get("change_key"))
            if key:
                keys.append(key)
        return keys

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
        left = x - width / 2
        top = y - height / 2
        right = x + width / 2
        bottom = y + height / 2
        tags = ("chart-node",)
        if action_key:
            tags = ("chart-node", action_key)
        canvas.create_rectangle(left + 2, top + 3, right + 2, bottom + 3, fill="#E4E7EC", outline="", tags=tags)
        canvas.create_rectangle(left, top, right, bottom, fill=fill, outline="#D0D5DD", width=1, tags=tags)
        canvas.create_rectangle(left, top, right, top + 4, fill=accent, outline=accent, tags=tags)
        canvas.create_text(x, y - 6, text=title, font=("Segoe UI", 9, "bold"), width=width - 16, tags=tags)
        canvas.create_text(x, y + 12, text=subtitle, font=("Segoe UI", 8), width=width - 16, fill="#475467", tags=tags)

    def _chart_action_key_from_current(self) -> str:
        canvas = self._org_canvas
        for tag in canvas.gettags("current"):
            if tag.startswith("node:"):
                return tag
        return ""

    def _on_chart_press(self, event) -> None:
        self._chart_dragging = False
        self._chart_drag_node = None
        self._chart_press_xy = (int(event.x), int(event.y))
        action_key = self._chart_action_key_from_current()
        self._chart_pending_action = self._chart_node_actions.get(action_key)
        if action_key:
            self._chart_drag_node = action_key
        else:
            self._org_canvas.scan_mark(event.x, event.y)

    def _on_chart_drag(self, event) -> None:
        dx = abs(int(event.x) - self._chart_press_xy[0])
        dy = abs(int(event.y) - self._chart_press_xy[1])
        if dx > 4 or dy > 4:
            self._chart_dragging = True
        if self._chart_drag_node and self._chart_dragging:
            canvas = self._org_canvas
            # Convert to canvas coords
            cx = canvas.canvasx(event.x)
            cy = canvas.canvasy(event.y)
            # Move all items with this action_key tag
            ak = self._chart_drag_node
            pos_key = self._chart_node_keys.get(ak, "")
            if not pos_key:
                return
            old_x, old_y = self._chart_node_centers.get(pos_key, (cx, cy))
            move_dx = cx - old_x
            move_dy = cy - old_y
            for item_id in canvas.find_withtag(ak):
                canvas.move(item_id, move_dx, move_dy)
            self._chart_node_centers[pos_key] = (cx, cy)
            self._redraw_edges_for_node(pos_key)
        elif not self._chart_drag_node:
            self._org_canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_chart_release(self, _event) -> None:
        if self._chart_dragging and self._chart_drag_node:
            self._save_chart_positions()
            self._update_chart_scrollregion()
            self._chart_drag_node = None
            self._chart_pending_action = None
            return
        action = self._chart_pending_action
        self._chart_pending_action = None
        self._chart_drag_node = None
        if self._chart_dragging or not action:
            return
        self._execute_chart_action(action)

    def _on_chart_mousewheel(self, event) -> None:
        if event.delta == 0:
            return
        factor = 1.1 if event.delta > 0 else 1 / 1.1
        self._chart_apply_zoom(factor, event.x, event.y)

    def _update_chart_zoom_label(self) -> None:
        self.var_chart_zoom.set(f"{int(round(self._chart_zoom * 100))} %")

    def _chart_apply_zoom(self, factor: float, x: float | None = None, y: float | None = None) -> None:
        canvas = self._org_canvas
        new_zoom = max(0.6, min(2.5, self._chart_zoom * factor))
        factor = new_zoom / self._chart_zoom
        if abs(factor - 1.0) < 0.001:
            return
        cx = canvas.canvasx(x if x is not None else canvas.winfo_width() / 2)
        cy = canvas.canvasy(y if y is not None else canvas.winfo_height() / 2)
        self._chart_zoom = new_zoom
        self._update_chart_zoom_label()
        canvas.scale("all", cx, cy, factor, factor)
        bbox = canvas.bbox("all")
        if bbox:
            canvas.configure(scrollregion=(bbox[0] - 40, bbox[1] - 40, bbox[2] + 40, bbox[3] + 40))

    def _chart_reset_view(self) -> None:
        if self._overview_loading:
            return
        self._clear_chart_positions()
        self._refresh_org_chart()

    def _chart_fit_view(self) -> None:
        if self._overview_loading:
            return
        canvas = self._org_canvas
        canvas.update_idletasks()
        bbox = canvas.bbox("all")
        if not bbox:
            return
        content_w = max(1, bbox[2] - bbox[0])
        content_h = max(1, bbox[3] - bbox[1])
        viewport_w = max(1, canvas.winfo_width() - 40)
        viewport_h = max(1, canvas.winfo_height() - 40)
        factor = min(viewport_w / content_w, viewport_h / content_h, 1.5)
        factor = max(0.5, min(2.0, factor))
        self._chart_zoom = 1.0
        self._refresh_org_chart()
        if abs(factor - 1.0) > 0.01:
            self._chart_apply_zoom(factor)

    # ── Chart position persistence ──────────────────────────────────

    def _chart_positions_path(self) -> Path | None:
        if not self._client or not self._year:
            return None
        import client_store
        d = client_store.years_dir(self._client, year=self._year) / "aksjonaerregister"
        d.mkdir(parents=True, exist_ok=True)
        return d / "chart_positions.json"

    def _load_chart_positions(self) -> dict[str, list[float]]:
        p = self._chart_positions_path()
        if not p or not p.exists():
            return {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_chart_positions(self) -> None:
        p = self._chart_positions_path()
        if not p:
            return
        data = {k: list(v) for k, v in self._chart_node_centers.items()}
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _clear_chart_positions(self) -> None:
        p = self._chart_positions_path()
        if p and p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    # ── Edge redrawing ──────────────────────────────────────────────

    def _redraw_edges_for_node(self, pos_key: str) -> None:
        canvas = self._org_canvas
        bw, bh = self._chart_box_size
        for from_key, to_key, line_tag, lbl_tag in self._chart_edges:
            if from_key != pos_key and to_key != pos_key:
                continue
            fx, fy = self._chart_node_centers.get(from_key, (0, 0))
            tx, ty = self._chart_node_centers.get(to_key, (0, 0))
            # Line: from bottom of upper node to top of lower node
            if fy < ty:
                y1, y2 = fy + bh / 2, ty - bh / 2
            else:
                y1, y2 = fy - bh / 2, ty + bh / 2
            for item in canvas.find_withtag(line_tag):
                canvas.coords(item, fx, y1, tx, y2)
            for item in canvas.find_withtag(lbl_tag):
                canvas.coords(item, (fx + tx) / 2, (y1 + y2) / 2)

    def _update_chart_scrollregion(self) -> None:
        canvas = self._org_canvas
        bbox = canvas.bbox("all")
        if bbox:
            pad = 30
            canvas.configure(scrollregion=(bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad))

    def _select_owned_row(self, *, company_orgnr: str = "", company_name: str = "") -> None:
        self._nb.select(0)
        target_orgnr = _safe_text(company_orgnr)
        target_name = _safe_text(company_name).casefold()
        for iid, row in self._owned_rows_by_iid.items():
            if target_orgnr and _safe_text(row.get("company_orgnr")) == target_orgnr:
                self._tree_owned.selection_set((iid,))
                self._tree_owned.focus(iid)
                self._tree_owned.see(iid)
                self._on_owned_selected()
                return
            if target_name and _safe_text(row.get("company_name")).casefold() == target_name:
                self._tree_owned.selection_set((iid,))
                self._tree_owned.focus(iid)
                self._tree_owned.see(iid)
                self._on_owned_selected()
                return

    def _select_owner_row(self, *, owner_orgnr: str = "", owner_name: str = "") -> None:
        self._nb.select(1)
        target_orgnr = _safe_text(owner_orgnr)
        target_name = _safe_text(owner_name).casefold()
        for iid, row in self._owners_rows_by_iid.items():
            if target_orgnr and _safe_text(row.get("shareholder_orgnr")) == target_orgnr:
                self._tree_owners.selection_set((iid,))
                self._tree_owners.focus(iid)
                self._tree_owners.see(iid)
                return
            if target_name and _safe_text(row.get("shareholder_name")).casefold() == target_name:
                self._tree_owners.selection_set((iid,))
                self._tree_owners.focus(iid)
                self._tree_owners.see(iid)
                return

    def _execute_chart_action(self, action: dict[str, Any]) -> None:
        kind = _safe_text(action.get("kind"))
        if kind == "owned":
            self._select_owned_row(
                company_orgnr=_safe_text(action.get("company_orgnr")),
                company_name=_safe_text(action.get("company_name")),
            )
            return
        if kind == "owner":
            self._select_owner_row(
                owner_orgnr=_safe_text(action.get("shareholder_orgnr")),
                owner_name=_safe_text(action.get("shareholder_name")),
            )
            return
        if kind == "root":
            self._nb.select(0)

    def _refresh_org_chart(self) -> None:
        canvas = self._org_canvas
        canvas.delete("all")
        canvas.configure(background="#FAFAF8")
        self._chart_node_actions = {}
        self._chart_node_keys = {}
        self._chart_node_centers = {}
        self._chart_edges = []
        self._chart_zoom = 1.0
        self._update_chart_zoom_label()

        root_name = self._client or "Klient"
        root_orgnr = _safe_text(self._overview.get("client_orgnr"))
        owners = self._overview.get("owners") or []
        children = self._overview.get("owned_companies") or []

        if not root_name or (not root_orgnr and not owners and not children):
            canvas.create_text(320, 120, text="Ingen eierdata tilgjengelig ennå.", font=("Segoe UI", 10), fill="#667085")
            canvas.configure(scrollregion=(0, 0, 640, 240))
            self._chart_dirty = False
            return

        box_w, box_h = 172, 56
        self._chart_box_size = (box_w, box_h)

        # Load saved positions
        saved = self._load_chart_positions()

        # Compute default positions
        node_count = max(len(owners), len(children), 1)
        total_w = max(800, node_count * 200)
        center_x = total_w / 2
        owner_y_default = 60
        root_y_default = 200
        child_y_default = 340

        # ── Root node ───────────────────────────────────────────────
        root_pos_key = f"root:{root_orgnr or root_name}"
        root_action_key = "node:root"
        rx, ry = saved.get(root_pos_key, [center_x, root_y_default])
        self._chart_node_keys[root_action_key] = root_pos_key
        self._chart_node_centers[root_pos_key] = (rx, ry)
        self._chart_node_actions[root_action_key] = {"kind": "root"}
        self._draw_box(
            canvas, rx, ry, box_w + 16, box_h + 4,
            title=root_name,
            subtitle=root_orgnr or self._year,
            fill="#E6F0FF", accent="#2952A3",
            action_key=root_action_key,
        )

        # Self-ownership note (attached to root)
        self_ownership = self._overview.get("self_ownership") or {}
        if self_ownership:
            note = f"Egne aksjer: {_fmt_pct(self_ownership.get('ownership_pct'))}%"
            shares = int(self_ownership.get("shares") or 0)
            total = int(self_ownership.get("total_shares") or 0)
            if shares and total:
                note = f"{note} ({shares} av {total})"
            canvas.create_text(
                rx, ry + 46, text=note,
                font=("Segoe UI", 8, "italic"), fill="#8A5A00",
                tags=("chart-node", root_action_key),
            )

        # ── Owner nodes ─────────────────────────────────────────────
        if owners:
            owner_gap = total_w / (len(owners) + 1)
            for idx, row in enumerate(owners, start=1):
                orgnr = _safe_text(row.get("shareholder_orgnr"))
                name = _safe_text(row.get("shareholder_name"))
                pos_key = f"owner:{orgnr or name}"
                action_key = f"node:owner:{idx}"
                default_x = owner_gap * idx
                ox, oy = saved.get(pos_key, [default_x, owner_y_default])
                self._chart_node_keys[action_key] = pos_key
                self._chart_node_centers[pos_key] = (ox, oy)
                self._chart_node_actions[action_key] = {
                    "kind": "owner",
                    "shareholder_name": name,
                    "shareholder_orgnr": orgnr,
                }
                self._draw_box(
                    canvas, ox, oy, box_w, box_h,
                    title=name or "Ukjent eier",
                    subtitle=orgnr or _safe_text(row.get("shareholder_kind")) or "-",
                    fill="#F8FAFC", accent="#667085",
                    action_key=action_key,
                )
                # Edge: owner → root
                line_tag = f"edge:line:{pos_key}"
                lbl_tag = f"edge:lbl:{pos_key}"
                y1 = oy + box_h / 2
                y2 = ry - (box_h + 4) / 2
                canvas.create_line(ox, y1, rx, y2, fill="#B0B8C8", width=1, tags=(line_tag,))
                canvas.create_text(
                    (ox + rx) / 2, (y1 + y2) / 2,
                    text=f"{_fmt_pct(row.get('ownership_pct'))}%",
                    font=("Segoe UI", 8), fill="#475467", tags=(lbl_tag,),
                )
                self._chart_edges.append((pos_key, root_pos_key, line_tag, lbl_tag))

        # ── Child nodes ─────────────────────────────────────────────
        if children:
            child_gap = total_w / (len(children) + 1)
            for idx, row in enumerate(children, start=1):
                orgnr = _safe_text(row.get("company_orgnr"))
                name = _safe_text(row.get("company_name"))
                pos_key = f"child:{orgnr or name}"
                action_key = f"node:owned:{idx}"
                default_x = child_gap * idx
                cx, cy = saved.get(pos_key, [default_x, child_y_default])
                self._chart_node_keys[action_key] = pos_key
                self._chart_node_centers[pos_key] = (cx, cy)
                self._chart_node_actions[action_key] = {
                    "kind": "owned",
                    "company_name": name,
                    "company_orgnr": orgnr,
                }
                self._draw_box(
                    canvas, cx, cy, box_w, box_h,
                    title=name or "Ukjent selskap",
                    subtitle=f"{orgnr or '-'} | {_relation_label(row.get('relation_type'))}",
                    fill=_relation_fill(row.get("relation_type")),
                    accent=_relation_accent(row.get("relation_type")),
                    action_key=action_key,
                )
                # Edge: root → child
                line_tag = f"edge:line:{pos_key}"
                lbl_tag = f"edge:lbl:{pos_key}"
                y1 = ry + (box_h + 4) / 2
                y2 = cy - box_h / 2
                canvas.create_line(rx, y1, cx, y2, fill="#B0B8C8", width=1, tags=(line_tag,))
                canvas.create_text(
                    (rx + cx) / 2, (y1 + y2) / 2,
                    text=f"{_fmt_pct(row.get('ownership_pct'))}%",
                    font=("Segoe UI", 8), fill="#475467", tags=(lbl_tag,),
                )
                self._chart_edges.append((root_pos_key, pos_key, line_tag, lbl_tag))

        # Circular ownership warning
        if self._year:
            try:
                from ar_store import detect_circular_ownership
                cycles = detect_circular_ownership(self._year)
                if cycles:
                    cycle_text = "Sirkulært eierskap: " + "; ".join(
                        " \u2192 ".join(c) + " \u2192 " + c[0] for c in cycles[:3]
                    )
                    all_ys = [v[1] for v in self._chart_node_centers.values()]
                    warn_y = max(all_ys) + box_h / 2 + 30 if all_ys else 400
                    canvas.create_text(
                        center_x, warn_y, text=f"\u26a0 {cycle_text}",
                        font=("Segoe UI", 9), fill="#856404",
                    )
            except Exception:
                pass

        # Set scrollregion and auto-fit
        self._update_chart_scrollregion()
        canvas.update_idletasks()
        self._chart_dirty = False

        # Auto-fit to viewport on first draw
        if not saved:
            self.after(50, self._chart_fit_view)

    def _on_accept_selected_changes(self) -> None:
        if not self._client or not self._year:
            return
        keys = self._selected_change_keys()
        if not keys:
            messagebox.showinfo("AR", "Velg minst Ã©n registerendring Ã¥ godta.")
            return
        accept_pending_ownership_changes(self._client, self._year, keys)
        self._refresh_current_overview()
        self.var_status.set(f"Godkjente {len(keys)} registerendringer.")

    def _on_accept_all_changes(self) -> None:
        if not self._client or not self._year:
            return
        pending = self._overview.get("pending_changes") or []
        if not pending:
            messagebox.showinfo("AR", "Det finnes ingen ventende registerendringer.")
            return
        if not messagebox.askyesno("AR", f"Godta alle {len(pending)} registerendringer for {self._year}?"):
            return
        accept_pending_ownership_changes(self._client, self._year)
        self._refresh_current_overview()
        self.var_status.set(f"Godkjente alle registerendringer for {self._year}.")

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
        pending = self._overview.get("pending_changes") or []
        if not pending:
            return
        try:
            self._nb.select(self._frm_changes)
        except Exception:
            return

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


class _ImportDetailDialog(tk.Toplevel):
    """Read-only view of a persisted RF-1086 import (stored in ar_store)."""

    def __init__(self, master: tk.Misc, *, detail: dict) -> None:
        super().__init__(master)
        self._detail = detail or {}
        header = self._detail.get("header") or {}
        reg_year = _safe_text(header.get("register_year")) or _safe_text(header.get("target_year"))
        company = _safe_text(header.get("company_name")) or _safe_text(header.get("company_orgnr"))
        self.title(f"Importdetaljer — {company} ({reg_year})")
        self.geometry("1100x720")
        self.minsize(900, 560)
        self.resizable(True, True)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=2)
        self.rowconfigure(2, weight=1)

        self._build_header(header)
        self._build_shareholders()
        self._build_transactions()
        self._build_buttons(header)

        self.grab_set()
        self.focus_set()

    def _build_header(self, header: dict) -> None:
        info = ttk.LabelFrame(self, text="Importinfo", padding=6)
        info.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 0))
        info.columnconfigure(1, weight=1)

        company = _safe_text(header.get("company_name"))
        orgnr = _safe_text(header.get("company_orgnr"))
        reg_year = _safe_text(header.get("register_year"))
        target_year = _safe_text(header.get("target_year"))
        source = _safe_text(header.get("source_file"))
        imported_at = _safe_text(header.get("imported_at_utc"))[:19]
        sh_count = int(header.get("shareholders_count") or 0)

        rows = [
            ("Selskap:", f"{company}  ({orgnr})" if orgnr else company),
            ("Registerår:", reg_year + (f"  (klientår {target_year})" if target_year and target_year != reg_year else "")),
            ("Importert:", imported_at or "-"),
            ("Kildefil:", source or "-"),
            ("Aksjonærer:", _fmt_thousand(sh_count)),
        ]
        for r, (lbl, val) in enumerate(rows):
            ttk.Label(info, text=lbl, font=("Segoe UI", 9, "bold")).grid(row=r, column=0, sticky="w", padx=(0, 8))
            ttk.Label(info, text=val, wraplength=900, justify="left").grid(row=r, column=1, sticky="w")

    def _build_shareholders(self) -> None:
        frame = ttk.LabelFrame(self, text="Aksjonærer", padding=4)
        frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(6, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        cols = ("id", "navn", "type", "start", "slutt", "pct_start", "pct_end", "side")
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        headings = [
            ("id", "ID", 110),
            ("navn", "Navn", 220),
            ("type", "Type", 70),
            ("start", "Aksjer start", 100),
            ("slutt", "Aksjer slutt", 100),
            ("pct_start", "% start", 80),
            ("pct_end", "% slutt", 80),
            ("side", "Side", 50),
        ]
        for cid, text, width in headings:
            tree.heading(cid, text=text)
            anchor = "e" if cid in {"start", "slutt", "pct_start", "pct_end"} else ("center" if cid == "side" else "w")
            tree.column(cid, width=width, anchor=anchor)

        ysb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ysb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")

        self._tree_sh = tree
        self._sh_by_iid: dict[str, dict] = {}

        for idx, sh in enumerate(self._detail.get("shareholders") or [], start=1):
            iid = f"sh-{idx}"
            self._sh_by_iid[iid] = sh
            kind = _safe_text(sh.get("shareholder_kind")) or "-"
            kind_label = "Person" if kind == "person" else ("Selskap" if kind == "company" else kind)
            tree.insert("", "end", iid=iid, values=(
                _safe_text(sh.get("shareholder_id")),
                _safe_text(sh.get("shareholder_name")),
                kind_label,
                _fmt_thousand(int(sh.get("shares_start") or 0)),
                _fmt_thousand(int(sh.get("shares_end") or 0)),
                _fmt_pct(sh.get("ownership_pct_start") or 0.0),
                _fmt_pct(sh.get("ownership_pct_end") or 0.0),
                int(sh.get("page_number") or 0) or "",
            ))

        tree.bind("<<TreeviewSelect>>", self._on_sh_select)

    def _build_transactions(self) -> None:
        frame = ttk.LabelFrame(self, text="Transaksjoner", padding=4)
        frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(6, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        self._tx_header = ttk.Label(frame, text="Velg en aksjonær for å se transaksjoner.", foreground="#667085")
        self._tx_header.grid(row=0, column=0, sticky="w", pady=(0, 4))

        cols = ("retning", "type", "aksjer", "dato", "beloep")
        tree = ttk.Treeview(frame, columns=cols, show="headings", selectmode="none", height=6)
        for cid, text, width, anchor in [
            ("retning", "Retning", 80, "w"),
            ("type", "Type", 110, "w"),
            ("aksjer", "Aksjer", 80, "e"),
            ("dato", "Dato", 100, "w"),
            ("beloep", "Beløp", 120, "e"),
        ]:
            tree.heading(cid, text=text)
            tree.column(cid, width=width, anchor=anchor)

        ysb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=ysb.set)
        tree.grid(row=1, column=0, sticky="nsew")
        ysb.grid(row=1, column=1, sticky="ns")

        self._tree_tx = tree

    def _build_buttons(self, header: dict) -> None:
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=3, column=0, sticky="ew", padx=6, pady=8)
        btn_frame.columnconfigure(0, weight=1)

        stored = _safe_text(header.get("stored_file_path"))
        self._stored_path = stored
        state = "normal" if stored and Path(stored).exists() else "disabled"
        ttk.Button(
            btn_frame, text="Åpne kilde-PDF", command=self._open_source,
            state=state,
        ).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(btn_frame, text="Lukk", command=self.destroy).grid(row=0, column=2)

    def _on_sh_select(self, _event=None) -> None:
        sel = self._tree_sh.selection()
        self._tree_tx.delete(*self._tree_tx.get_children())
        if not sel:
            self._tx_header.config(text="Velg en aksjonær for å se transaksjoner.")
            return
        sh = self._sh_by_iid.get(sel[0]) or {}
        name = _safe_text(sh.get("shareholder_name"))
        sh_id = _safe_text(sh.get("shareholder_id"))
        self._tx_header.config(text=f"{name}  ({sh_id})" if sh_id else name)

        by_ref = self._detail.get("by_ref") or {}
        ref = ""
        if sh_id:
            ref = f"id:{sh_id}"
        elif name:
            ref = f"name:{name.casefold()}"
        entry = by_ref.get(ref) or {}
        for tx in entry.get("transactions") or []:
            direction = _safe_text(tx.get("direction"))
            retning = "Tilgang" if direction == "tilgang" else ("Avgang" if direction == "avgang" else direction)
            self._tree_tx.insert("", "end", values=(
                retning,
                _safe_text(tx.get("trans_type")),
                _fmt_thousand(int(tx.get("shares") or 0)),
                _safe_text(tx.get("date")),
                _fmt_currency(float(tx.get("amount") or 0.0)),
            ))

    def _open_source(self) -> None:
        path = self._stored_path
        if not path:
            return
        try:
            import os
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("AR", f"Kunne ikke åpne PDF:\n{exc}")

    def show(self) -> None:
        self.wait_window(self)

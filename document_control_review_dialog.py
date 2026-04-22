"""document_control_review_dialog

DocumentControlReviewDialog — side-by-side comparison of accounting (HB)
values vs. PDF-extracted values per bilag.

Layout
------
┌──────────────────────────────────────────────────────────────────────────┐
│ Header: Bilag 575 — Spor AS   1/33 (Avvik)   ◄ Forrige  Neste ►  Lagre og neste  Lukk │
├──────────┬──────────────────────────────────────────────┬────────────────┤
│  Liste   │  Felt        Regnskap (HB)  ✓/✗  PDF-innlest │  PDF-visning   │
│  ● 575   │  Leverandør  [Spor AS    ]  ✓   [Spor AS   ] │                │
│  ○ 314   │  Fakturanr   [          ]  –   [32498     ] │  [PDF page]    │
│  ○ ...   │  Fakturadato [31.12.2025]  ✓   [31.12.2025] │                │
│          │  Total       [9 080,00  ]  ✗   [11 507,40 ] │                │
│          │  ...                                         │                │
│          │  Avvik: [tekst]                              │                │
│          │  Notater: [tekst]                            │                │
│          │  [Lagre og neste ►]  [Bare lagre]            │                │
└──────────┴──────────────────────────────────────────────┴────────────────┘
│ ● 8 OK  |  ○ 25 avvik                                                    │
"""
from __future__ import annotations

import re
from dataclasses import fields as dc_fields
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

from document_control_batch_service import BatchDocumentResult, _is_real_avvik
from document_control_app_service import (
    build_voucher_context,
    find_or_extract_bilag_document,
    load_saved_review,
    save_document_review,
)
from document_control_viewer import DocumentPreviewFrame, PreviewTarget, preview_target_from_evidence
from document_engine.engine import (
    build_validation_messages,
    normalize_bilag_key,
)
from document_engine.format_utils import (
    amount_search_variants,
    normalize_orgnr,
    orgnr_matches,
    parse_amount_flexible,
)
from document_engine.models import DocumentFacts, VoucherContext


# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------

FIELD_DEFS: list[tuple[str, str]] = [
    ("supplier_name",   "Leverandør"),
    ("supplier_orgnr",  "Org.nr."),
    ("invoice_number",  "Fakturanr."),
    ("invoice_date",    "Fakturadato"),
    ("due_date",        "Forfallsdato"),
    ("subtotal_amount", "Beløp ekskl. mva"),
    ("vat_amount",      "MVA"),
    ("total_amount",    "Total"),
    ("currency",        "Valuta"),
    ("description",     "Beskrivelse"),
    ("period",          "Periode"),
]

_AMOUNT_KEYS = {"subtotal_amount", "vat_amount", "total_amount"}
_DATE_KEYS   = {"invoice_date", "due_date"}
_ORGNR_KEYS  = {"supplier_orgnr"}
# Info-only fields: shown for auditor reference, never matched against HB
_INFO_KEYS   = {"description", "period"}

_TEXT_COLS   = ("Tekst", "Beskrivelse", "Dokumenttekst", "Bilagstekst", "Description")
_DATE_COLS   = ("Dato", "Dokumentdato", "Bokf.dato", "InvoiceDate")

_TAG_OK    = "row_ok"
_TAG_AVVIK = "row_avvik"
_TAG_IKKE  = "row_ikke"


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class DocumentControlReviewDialog(tk.Toplevel):
    """Step-through review: navigate batch results, compare HB vs PDF values."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        results: list[BatchDocumentResult],
        df_all: Any,        # pd.DataFrame
        client: str | None,
        year: str | None,
    ) -> None:
        super().__init__(master)
        self.title("Gjennomgang — dokumentkontroll")
        self.geometry("1500x860")
        self.minsize(1100, 640)
        self.resizable(True, True)

        self._results        = list(results)
        self._df_all         = df_all
        self._client         = client
        self._year           = year
        self._current_index  = 0
        self._last_segments: list[Any] | None = None   # segments from most recent analysis
        self._last_raw_text_excerpt: str = ""           # raw text from most recent analysis (persisted on save)
        self._bilagsprint_pages: set[int] = set()       # 1-based page numbers that are bilagsprint

        # Per-result mutable state
        self._pdf_state:    list[dict[str, str]] = [_init_pdf_state(r) for r in self._results]
        self._status_state: list[str]            = [r.status for r in self._results]
        self._avvik_state:  list[list[str]]      = [list(r.validation_messages) for r in self._results]
        self._notes_state:  list[str]            = [""] * len(self._results)
        self._hit_idx_state: list[dict[str, int]] = [{} for _ in self._results]
        self._saved_fields: list[dict[str, str] | None] = [None] * len(self._results)  # disk snapshot per bilag
        self._saved_evidence: list[dict[str, Any] | None] = [None] * len(self._results)  # saved page+bbox per bilag
        self._load_persisted_state()

        # StringVars
        self.hb_vars:  dict[str, tk.StringVar] = {key: tk.StringVar() for key, _ in FIELD_DEFS}
        self.pdf_vars: dict[str, tk.StringVar] = {key: tk.StringVar() for key, _ in FIELD_DEFS}
        self._var_header     = tk.StringVar()
        self._var_progress   = tk.StringVar()
        self._var_status_bar = tk.StringVar()
        self._var_file_path  = tk.StringVar()
        self._match_labels:  dict[str, tk.Label] = {}
        self._page_labels:   dict[str, tk.Label] = {}
        self._saved_labels:  dict[str, tk.Label] = {}  # disk-saved indicator per field
        self._field_evidence: dict[str, Any]     = {}  # populated after re-analysis
        # All PDF search hits per field: list of (page, bbox)
        self._field_hits:      dict[str, list[tuple[int, tuple]]] = {}
        self._field_hit_index: dict[str, int] = {}  # current hit index per field
        self._suppress_pdf_search: bool = False  # avoid searching during programmatic set
        self._search_timers: dict[str, str] = {}  # after() IDs for debounced PDF search
        self._pinned_fields: set[str] = set()  # fields where user has explicitly chosen a hit

        # Live match update on each PDF var change
        for key, _ in FIELD_DEFS:
            self.pdf_vars[key].trace_add("write", lambda *_, k=key: self._on_pdf_var_change(k))

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_ui()
        self._populate_list()
        if self._results:
            self._load_index(0)

        # Keyboard shortcuts
        self.bind("<Control-Return>", lambda _: self._save_and_next())
        self.bind("<Control-s>",      lambda _: self._save_current())
        self.bind("<Escape>",         lambda _: self.destroy())
        self.bind("<Control-Right>",  lambda _: self._go_next())
        self.bind("<Control-Left>",   lambda _: self._go_prev())

        self.grab_set()
        self.focus_set()

    def _load_persisted_state(self) -> None:
        """Restore field values, notes, and hit indices from disk-saved records."""
        try:
            from document_control_store import load_document_store, record_key
            store = load_document_store()
            records = store.get("records", {})
        except Exception:
            return
        for i, r in enumerate(self._results):
            key = record_key(self._client, self._year, r.bilag_nr)
            saved = records.get(key)
            if not saved:
                continue
            # Restore field values (overwrite batch-analysis defaults)
            saved_fields = saved.get("fields")
            if saved_fields and isinstance(saved_fields, dict):
                self._saved_fields[i] = dict(saved_fields)
                for field_key in saved_fields:
                    if field_key in self._pdf_state[i]:
                        self._pdf_state[i][field_key] = str(saved_fields[field_key] or "")
            # Restore notes
            saved_notes = saved.get("notes", "")
            if saved_notes:
                self._notes_state[i] = str(saved_notes)
            # Restore hit indices
            if isinstance(saved.get("field_hit_indices"), dict):
                self._hit_idx_state[i] = {
                    k: int(v) for k, v in saved["field_hit_indices"].items()
                    if isinstance(v, (int, float))
                }
            # Restore saved evidence (page+bbox per field)
            saved_ev = saved.get("field_evidence")
            if saved_ev and isinstance(saved_ev, dict):
                self._saved_evidence[i] = dict(saved_ev)

    # ------------------------------------------------------------------
    # UI building
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── Row 0: Header / navigation ──────────────────────────────────
        header = ttk.Frame(self, padding=(10, 4, 10, 2))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(2, weight=1)

        ttk.Label(header, textvariable=self._var_header,
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._var_progress,
                  foreground="#555").grid(row=0, column=1, sticky="w", padx=(16, 0))

        nav = ttk.Frame(header)
        nav.grid(row=0, column=3, sticky="e")
        # PDF controls (page nav + zoom) are populated by _build_pdf_pane once
        # the preview widget exists — they live here so the canvas gets the
        # full vertical space of the PDF pane.
        self._pdf_toolbar_slot = ttk.Frame(nav)
        self._pdf_toolbar_slot.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(nav, text="Lukk", command=self.destroy).pack(side=tk.LEFT)

        # ── Row 1: Three-pane body (resizable) ──────────────────────────
        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 2))

        # Left: bilag list
        list_frame = ttk.Frame(body)
        self._build_list_pane(list_frame)
        body.add(list_frame, weight=0)

        # Middle: comparison fields
        comp_frame = ttk.Frame(body)
        self._build_comparison_pane(comp_frame)
        body.add(comp_frame, weight=2)

        # Right: PDF viewer
        pdf_frame = ttk.Frame(body)
        self._build_pdf_pane(pdf_frame)
        body.add(pdf_frame, weight=3)

        # ── Row 2: Status bar ────────────────────────────────────────────
        ttk.Label(self, textvariable=self._var_status_bar,
                  foreground="#555", padding=(10, 1)).grid(row=2, column=0, sticky="w")

    def _build_list_pane(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="nsew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        self._list = ttk.Treeview(
            left, columns=("Status", "Bilag", "Leverandør"),
            show="headings", selectmode="browse", height=30
        )
        self._list.heading("Status",     text="")
        self._list.heading("Bilag",      text="Bilag")
        self._list.heading("Leverandør", text="Leverandør")
        self._list.column("Status",     width=22,  stretch=False, anchor="center")
        self._list.column("Bilag",      width=55,  stretch=False, anchor="e")
        self._list.column("Leverandør", width=150, anchor="w")

        self._list.tag_configure(_TAG_OK,    foreground="#1a7a1a")
        self._list.tag_configure(_TAG_AVVIK, foreground="#b52020")
        self._list.tag_configure(_TAG_IKKE,  foreground="#888")

        vsb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self._list.yview)
        self._list.configure(yscrollcommand=vsb.set)
        self._list.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._list.bind("<<TreeviewSelect>>", self._on_list_select)
        self._list.bind("<Double-1>", self._on_list_double_click)

    def _build_comparison_pane(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        # Outer container — stretches with PanedWindow sash
        outer = ttk.Frame(parent, padding=(0, 0, 8, 0))
        outer.grid(row=0, column=0, sticky="nsew")
        outer.rowconfigure(1, weight=1)  # canvas row expands
        outer.columnconfigure(0, weight=1)

        # ── Fixed action bar above the field list ────────────────────────
        action_bar = ttk.Frame(outer)
        action_bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Button(action_bar, text="◄ Forrige bilag", command=self._go_prev).pack(side=tk.LEFT)
        ttk.Button(action_bar, text="Neste bilag ►",    command=self._go_next).pack(side=tk.LEFT, padx=(6, 0))

        # ── Scrollable canvas for comparison fields ───────────────────────
        _canvas = tk.Canvas(outer, highlightthickness=0, bd=0)
        _canvas.grid(row=1, column=0, sticky="nsew")
        _vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=_canvas.yview)
        _vsb.grid(row=1, column=1, sticky="ns")
        _canvas.configure(yscrollcommand=_vsb.set)

        # Inner frame holds all the field widgets
        inner = ttk.Frame(_canvas)
        _win = _canvas.create_window((0, 0), window=inner, anchor="nw")

        def _fit_width(evt: tk.Event) -> None:  # type: ignore[type-arg]
            _canvas.itemconfig(_win, width=evt.width)
        _canvas.bind("<Configure>", _fit_width)

        def _update_scroll(evt: tk.Event) -> None:  # type: ignore[type-arg]
            _canvas.configure(scrollregion=_canvas.bbox("all"))
        inner.bind("<Configure>", _update_scroll)

        def _on_wheel(evt: tk.Event) -> None:  # type: ignore[type-arg]
            _canvas.yview_scroll(int(-1 * (evt.delta / 120)), "units")
        _canvas.bind("<MouseWheel>", _on_wheel)
        inner.bind("<MouseWheel>", _on_wheel)

        # ── File bar (collapsed by default — click ► to expand) ──────────
        file_bar = ttk.Frame(outer)
        file_bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        file_bar.columnconfigure(1, weight=1)

        self._file_detail = ttk.Frame(file_bar)
        self._file_detail.columnconfigure(0, weight=1)
        ttk.Entry(self._file_detail, textvariable=self._var_file_path,
                  state="readonly").grid(row=0, column=0, sticky="ew")
        ttk.Button(self._file_detail, text="Velg...",   command=self._choose_file,  width=7).grid(row=0, column=1, padx=(4, 0))
        ttk.Button(self._file_detail, text="Les oppl.", command=self._reanalyse,    width=9).grid(row=0, column=2, padx=(4, 0))

        self._file_bar_expanded = False
        self._file_toggle_btn = ttk.Button(file_bar, text="Dok ►", width=6, command=self._toggle_file_bar)
        self._file_toggle_btn.grid(row=0, column=0, sticky="w")

        # ── Build field rows inside the scrollable inner frame ───────────
        # col 0=label, 1=HB entry, 2=icon, 3=PDF entry, 4=copy btn, 5=page badge
        inner.columnconfigure(1, weight=1)
        inner.columnconfigure(3, weight=1)

        # Column headers
        ttk.Label(inner, text="Felt", font=("Segoe UI", 9, "bold"),
                  foreground="#555", width=16, anchor="w").grid(
            row=0, column=0, sticky="w", padx=(4, 8), pady=(4, 2))
        ttk.Label(inner, text="Regnskap (HB)", font=("Segoe UI", 9, "bold"),
                  foreground="#5d8aa8", width=20, anchor="w").grid(
            row=0, column=1, sticky="w", padx=(0, 4), pady=(4, 2))
        ttk.Label(inner, text="", width=3).grid(row=0, column=2)
        ttk.Label(inner, text="PDF (innlest)", font=("Segoe UI", 9, "bold"),
                  foreground="#7b241c", width=20, anchor="w").grid(
            row=0, column=3, sticky="w", pady=(4, 2))

        ttk.Separator(inner, orient="horizontal").grid(
            row=1, column=0, columnspan=5, sticky="ew", pady=(0, 4))

        _info_separator_added = False
        r = 2  # running row counter (rows 0-1 used for headers/separator above)
        for row_i, (key, label) in enumerate(FIELD_DEFS):
            is_info = key in _INFO_KEYS

            # Add a thin separator before the first info-only field
            if is_info and not _info_separator_added:
                _info_separator_added = True
                ttk.Separator(inner, orient="horizontal").grid(
                    row=r, column=0, columnspan=6, sticky="ew", pady=(4, 2))
                r += 1

            # Label — italic for info-only fields
            lbl_font = ("Segoe UI", 9, "italic") if is_info else ("Segoe UI", 9)
            lbl_fg = "#6a6a6a" if is_info else "#000"
            tk.Label(inner, text=label, width=16, anchor="w",
                     font=lbl_font, fg=lbl_fg).grid(
                row=r, column=0, sticky="w", padx=(4, 8), pady=1)

            # HB value (read-only) — hidden for info-only fields
            hb_ent = tk.Entry(
                inner,
                textvariable=self.hb_vars[key],
                state="readonly",
                readonlybackground="#f5f5f5" if is_info else "#ebebeb",
                fg="#999" if is_info else "#555",
                relief="flat",
                width=20,
            )
            hb_ent.grid(row=r, column=1, sticky="ew", padx=(0, 4), pady=1)

            # Match icon — always "–" for info fields
            match_lbl = tk.Label(inner, text="–", font=("Segoe UI", 11),
                                 fg="#aaa", width=2, anchor="center")
            match_lbl.grid(row=r, column=2, padx=2, pady=1)
            self._match_labels[key] = match_lbl

            # PDF value (editable)
            pdf_ent = ttk.Entry(inner, textvariable=self.pdf_vars[key], width=20)
            pdf_ent.grid(row=r, column=3, sticky="ew", pady=1)

            # Copy HB → PDF (hidden for info-only fields since HB is empty)
            if not is_info:
                ttk.Button(inner, text="←", width=2,
                           command=lambda k=key: self._copy_hb_to_pdf(k)).grid(
                    row=r, column=4, padx=(4, 4), pady=1)

            # Page badge — shows which PDF page the value was extracted from.
            # Click cycles through hits; the chosen position is pinned.
            page_lbl = tk.Label(inner, text="", fg="#999", font=("Segoe UI", 8),
                                width=8, anchor="w", cursor="hand2")
            page_lbl.grid(row=r, column=5, sticky="w", padx=(0, 2))
            page_lbl.bind("<Button-1>", lambda _e, k=key: self._focus_pdf_field(k))
            self._page_labels[key] = page_lbl

            # Saved indicator — shows disk-saved value, click to navigate to saved PDF position
            saved_lbl = tk.Label(inner, text="", fg="#999", font=("Segoe UI", 7),
                                  anchor="w", cursor="hand2")
            saved_lbl.grid(row=r, column=6, sticky="w", padx=(0, 4))
            saved_lbl.bind("<Button-1>", lambda _e, k=key: self._goto_saved_position(k))
            self._saved_labels[key] = saved_lbl

            # Bind mousewheel on each entry too
            hb_ent.bind("<MouseWheel>", _on_wheel)
            r += 1

        # ── Avvik ────────────────────────────────────────────────────────
        sep_r = r
        ttk.Separator(inner, orient="horizontal").grid(
            row=sep_r, column=0, columnspan=5, sticky="ew", pady=(6, 3))

        avvik_r = sep_r + 1
        ttk.Label(inner, text="Avvik", font=("Segoe UI", 9, "bold"),
                  foreground="#b52020", width=16, anchor="nw").grid(
            row=avvik_r, column=0, sticky="nw", padx=(4, 8), pady=(0, 1))
        self._txt_avvik = tk.Text(inner, height=3, wrap="word",
                                  state="disabled", background="#fff8f8",
                                  relief="flat", width=40)
        self._txt_avvik.grid(row=avvik_r, column=1, columnspan=3,
                             sticky="ew", pady=(0, 3))
        self._txt_avvik.bind("<MouseWheel>", _on_wheel)

        # ── Notater ──────────────────────────────────────────────────────
        notes_r = avvik_r + 1
        ttk.Label(inner, text="Notater", width=16, anchor="nw").grid(
            row=notes_r, column=0, sticky="nw", padx=(4, 8), pady=(0, 1))
        self._txt_notes = tk.Text(inner, height=3, wrap="word", width=40)
        self._txt_notes.grid(row=notes_r, column=1, columnspan=3,
                             sticky="ew", pady=(0, 3))
        self._txt_notes.bind("<MouseWheel>", _on_wheel)

        # Tall Lagre-button alongside Avvik/Notater — close to the fields
        # the user is editing, no scrolling or mouse trip needed.
        ttk.Button(inner, text="Lagre", command=self._save_current).grid(
            row=avvik_r, column=4, columnspan=2, rowspan=2,
            sticky="nsew", padx=(6, 4), pady=(0, 3))

    def _build_pdf_pane(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        right = ttk.Frame(parent)
        right.grid(row=0, column=0, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        # show_toolbar=False — page/zoom controls live in the header strip so
        # the canvas gets the full vertical space of the pane.
        self._preview = DocumentPreviewFrame(right, show_toolbar=False)
        self._preview.grid(row=0, column=0, sticky="nsew")

        slot = getattr(self, "_pdf_toolbar_slot", None)
        if slot is not None:
            ttk.Button(slot, text="◄", command=self._preview.show_previous_page, width=3).pack(side=tk.LEFT)
            ttk.Label(slot, textvariable=self._preview.var_page, width=7, anchor="center").pack(side=tk.LEFT, padx=2)
            ttk.Button(slot, text="►", command=self._preview.show_next_page, width=3).pack(side=tk.LEFT, padx=(0, 8))
            ttk.Button(slot, text="−", command=self._preview.zoom_out, width=2).pack(side=tk.LEFT)
            ttk.Button(slot, text="+", command=self._preview.zoom_in, width=2).pack(side=tk.LEFT)
            ttk.Button(slot, text="Tilpass", command=self._preview.fit_to_width, width=7).pack(side=tk.LEFT, padx=(4, 0))

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _populate_list(self) -> None:
        for item in self._list.get_children():
            self._list.delete(item)
        for idx, r in enumerate(self._results):
            dot, tag = _status_dot(self._status_state[idx])
            display_name = self._pdf_state[idx].get("supplier_name", "").strip() or r.supplier_name
            self._list.insert("", tk.END, iid=str(idx),
                              values=(dot, r.bilag_nr, display_name), tags=(tag,))
        self._refresh_summary()

    def _update_list_row(self, idx: int) -> None:
        dot, tag = _status_dot(self._status_state[idx])
        r = self._results[idx]
        # Use edited supplier name from PDF state if available
        display_name = self._pdf_state[idx].get("supplier_name", "").strip() or r.supplier_name
        self._list.item(str(idx), values=(dot, r.bilag_nr, display_name), tags=(tag,))
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        n_ok    = sum(1 for s in self._status_state if s == "ok")
        n_avvik = sum(1 for s in self._status_state if s == "avvik")
        n_ikke  = sum(1 for s in self._status_state if s == "ikke_funnet")
        n_feil  = sum(1 for s in self._status_state if s == "feil")
        parts = [f"● {n_ok} OK", f"○ {n_avvik} avvik"]
        if n_ikke:
            parts.append(f"{n_ikke} ikke funnet")
        if n_feil:
            parts.append(f"{n_feil} feil")
        self._var_status_bar.set("  |  ".join(parts))

    # ------------------------------------------------------------------
    # Loading a bilag
    # ------------------------------------------------------------------

    def _load_index(self, idx: int) -> None:
        if not (0 <= idx < len(self._results)):
            return
        self._current_index = idx
        r      = self._results[idx]
        status = self._status_state[idx]

        # Header
        self._var_header.set(
            f"Bilag {r.bilag_nr}  —  {r.supplier_name or '(leverandør ukjent)'}"
        )
        _slabel = {"ok": "OK", "avvik": "Avvik", "ikke_funnet": "Ikke funnet", "feil": "Feil"}
        self._var_progress.set(f"{idx + 1} / {len(self._results)}  ({_slabel.get(status, status)})")

        # Highlight list row
        try:
            self._list.selection_set(str(idx))
            self._list.see(str(idx))
        except Exception:
            pass

        # Extract accounting (HB) values — MUST be set before PDF vars so
        # match traces fire with the correct HB values.
        df_bilag = _bilag_rows(self._df_all, r.bilag_nr)
        hb = _extract_hb_values(df_bilag, r.accounting_ref, bilag_nr=r.bilag_nr)
        for key, _ in FIELD_DEFS:
            self.hb_vars[key].set(hb.get(key, ""))

        # PDF values (editable) — suppress search during programmatic load
        self._suppress_pdf_search = True
        pdf_state = self._pdf_state[idx]
        for key, _ in FIELD_DEFS:
            self.pdf_vars[key].set(pdf_state.get(key, ""))
        self._suppress_pdf_search = False

        # Force-refresh all match icons with fresh HB values
        self._update_all_matches(hb)

        # Avvik text
        self._set_avvik_text(self._avvik_state[idx])

        # Notes
        self._txt_notes.delete("1.0", "end")
        self._txt_notes.insert("1.0", self._notes_state[idx])

        # Clear previous field evidence, hits, page badges, and pins
        # Restore saved evidence from disk so _auto_analyse preserves it
        saved_ev = self._saved_evidence[idx] if 0 <= idx < len(self._saved_evidence) else None
        self._field_evidence = dict(saved_ev) if saved_ev else {}
        self._field_hits = {}
        self._field_hit_index = {}
        self._pinned_fields.clear()
        self._last_raw_text_excerpt = ""  # reset per bilag; _auto_analyse re-populates
        self._update_page_labels()
        self._update_saved_indicators()
        self._preview.set_highlight(None)

        # Load PDF (prefer extracted sub-PDF)
        file_path = r.extracted_path or ""
        if not file_path or not Path(file_path).exists():
            try:
                extracted = find_or_extract_bilag_document(
                    r.bilag_nr, client=self._client, year=self._year
                )
                if extracted:
                    file_path = str(extracted)
                    self._results[idx] = _replace_extracted_path(r, file_path)
            except Exception:
                pass

        self._var_file_path.set(file_path)
        self._preview.load_file(file_path if file_path and Path(file_path).exists() else None)
        # Load segments for coordinate-based learning when user saves
        self._reload_segments_for(file_path)
        # Detect bilagsprint pages FIRST (synchronously) — must happen before
        # any search or restore so that bilagsprint filtering is available.
        if file_path and Path(file_path).exists():
            self._detect_bilagsprint_pages(file_path)

        # Immediately restore hit indices from saved state (fast — just PDF text search)
        # This gives instant visual feedback; _auto_analyse later refines with full analysis.
        if file_path and Path(file_path).exists():
            self._restore_hit_indices_sync(idx)

        # Auto-analyse to populate page badges and field evidence
        if file_path and Path(file_path).exists():
            self.after(200, lambda fp=file_path, i=idx: self._auto_analyse(fp, i))

    def _reload_segments_for(self, path: str | None) -> None:
        """Re-extract PDF segments + raw text into ``self._last_*`` for *path*.

        Every code path that changes which document is displayed (bilag
        navigation, manual file selection, reanalyse) MUST route through
        this helper. Otherwise a subsequent save would learn against the
        segments of the previously displayed document — and saving without
        first running ``Les oppl.`` would send an empty ``raw_text_excerpt``.
        """
        self._last_segments = None
        self._last_raw_text_excerpt = ""
        if not path:
            return
        p = Path(path)
        if not p.exists():
            return
        try:
            from document_engine.engine import extract_text_from_file as _etf
            result = _etf(p)
            self._last_segments = result.segments or None
            # analyze_document truncates the raw text at 4000 chars before
            # exposing it as raw_text_excerpt; mirror that here so saves made
            # without re-running full analysis persist a comparable excerpt.
            raw_text = getattr(result, "text", "") or ""
            self._last_raw_text_excerpt = raw_text[:4000]
        except Exception:
            pass

    def _sort_hits(self, raw_hits: list[tuple]) -> list[tuple]:
        """Sort a hit list so bilagsprint (Tripletex cover) pages come last.

        Every call that builds a hit list MUST route through this helper so
        that every code path (restore, auto-analyse, reanalyse, live search)
        treats bilagsprint pages as the least preferred match.
        """
        bp = self._bilagsprint_pages
        return sorted(raw_hits, key=lambda h: (h[0] in bp, h[0]))

    def _restore_hit_indices_sync(self, idx: int) -> None:
        """Synchronously restore hit indices so page badges appear immediately."""
        saved = self._hit_idx_state[idx]
        if not saved:
            return
        for key, _ in FIELD_DEFS:
            val = self.pdf_vars[key].get().strip()
            if not val or len(val) < 2:
                continue
            raw_hits = self._preview.search_all_pages(val)
            if not raw_hits:
                continue
            hits = self._sort_hits(raw_hits)
            self._field_hits[key] = hits
            target_idx = saved.get(key, 0)
            target_idx = min(target_idx, len(hits) - 1)
            self._field_hit_index[key] = target_idx
            page, bbox = hits[target_idx]
            self._update_evidence_location(key, page, bbox)
        self._update_page_labels()

    def _detect_bilagsprint_pages(self, file_path: str) -> None:
        """Detect bilagsprint pages and skip past the first one.

        Runs synchronously so that bilagsprint filtering is available for
        all subsequent operations (_restore_hit_indices_sync, _auto_analyse,
        _search_pdf_for_field).
        """
        self._bilagsprint_pages = set()
        try:
            import fitz
            doc = fitz.open(file_path)
            page_count = len(doc)
            for page_idx in range(page_count):
                text = doc[page_idx].get_text()
                if _is_bilagsprint_text(text):
                    self._bilagsprint_pages.add(page_idx + 1)  # 1-based
            doc.close()
            if 1 in self._bilagsprint_pages and page_count >= 2:
                self._preview.show_page(2)
        except Exception:
            pass

    def _set_avvik_text(self, msgs: list[str]) -> None:
        self._txt_avvik.configure(state="normal")
        self._txt_avvik.delete("1.0", "end")
        self._txt_avvik.insert("1.0", "\n".join(msgs) if msgs else "Ingen avvik.")
        self._txt_avvik.configure(state="disabled")

    # ------------------------------------------------------------------
    # Match indicators
    # ------------------------------------------------------------------

    def _update_all_matches(self, hb: dict[str, str]) -> None:
        for key, _ in FIELD_DEFS:
            self._update_match(key, hb_override=hb.get(key, ""))

    def _update_match(self, key: str, *, hb_override: str | None = None) -> None:
        hb_val  = hb_override if hb_override is not None else self.hb_vars[key].get()
        pdf_val = self.pdf_vars[key].get()
        lbl = self._match_labels.get(key)
        if lbl is None:
            return

        # Info-only fields — no match indicator
        if key in _INFO_KEYS:
            lbl.configure(text="–", fg="#aaa")
            return

        if not hb_val.strip():
            lbl.configure(text="–", fg="#aaa")
            return

        if _field_matches(key, hb_val, pdf_val):
            lbl.configure(text="✓", fg="#1a7a1a")
        else:
            lbl.configure(text="✗", fg="#b52020")

    def _copy_hb_to_pdf(self, key: str) -> None:
        """Copy the HB value for *key* into the PDF field."""
        self.pdf_vars[key].set(self.hb_vars[key].get())

    def _on_pdf_var_change(self, key: str) -> None:
        """Called whenever a PDF field value changes (user edit or programmatic)."""
        self._update_match(key)
        if self._suppress_pdf_search:
            return
        # Text changed → unpin the field so the search picks the best match
        self._pinned_fields.discard(key)
        # Cancel any pending search for this field
        prev = self._search_timers.pop(key, None)
        if prev is not None:
            self.after_cancel(prev)
        # Debounce: wait 400ms after last keystroke before searching
        timer_id = self.after(400, lambda k=key: self._do_deferred_search(k))
        self._search_timers[key] = timer_id

    def _do_deferred_search(self, key: str) -> None:
        """Run after debounce delay."""
        self._search_timers.pop(key, None)
        self._search_pdf_for_field(key)

    def _search_pdf_for_field(self, key: str) -> None:
        """Search the entire PDF for the current value of *key* and update evidence.

        If the field is pinned (user explicitly chose a hit position), the
        hit index is preserved.  The pin is cleared when the field VALUE changes
        (user types a completely new string).
        """
        val = self.pdf_vars[key].get().strip()
        if not val or len(val) < 2:
            self._field_hits[key] = []
            self._field_hit_index[key] = 0
            self._pinned_fields.discard(key)
            self._update_page_label_for(key)
            return

        # Formatted amounts and org numbers rarely match the stored value
        # literally (PDF may show "1,175.00" while the field holds
        # "1175,00", or "NO 965 004 211 MVA" vs "965004211"). Try variants
        # until one yields hits, so trefflenker still work.
        raw_hits: list[tuple[int, tuple[float, float, float, float]]] = []
        for variant in _pdf_search_variants(key, val):
            raw_hits = self._preview.search_all_pages(variant)
            if raw_hits:
                break
        hits = self._sort_hits(raw_hits)
        old_hits = self._field_hits.get(key, [])
        self._field_hits[key] = hits

        # Index policy:
        #  - Pinned field + hit list unchanged → keep the user's chosen idx.
        #  - Otherwise (new value, unpinned, or hit list shape changed) →
        #    start from 0 so the user sees the best (non-bilagsprint) hit.
        #
        # Previously this code also preserved prev_idx when the field was
        # simply unpinned, which caused the search to land back on a
        # bilagsprint page (page 1) after the user typed a new value.
        prev_idx = self._field_hit_index.get(key, 0)
        if key in self._pinned_fields and len(hits) == len(old_hits) and 0 <= prev_idx < len(hits):
            idx = prev_idx
        else:
            idx = 0
            self._pinned_fields.discard(key)
        self._field_hit_index[key] = idx

        if hits:
            page, bbox = hits[idx]
            self._update_evidence_location(key, page, bbox)
        else:
            # No hits — remove evidence entirely
            self._field_evidence.pop(key, None)
            self._pinned_fields.discard(key)
        self._update_page_label_for(key)

    def _update_evidence_location(self, key: str, page: int, bbox: tuple) -> None:
        """Update (or create) field evidence with a new page + bbox location."""
        from document_engine.models import FieldEvidence
        ev = self._field_evidence.get(key)
        if ev is not None and not isinstance(ev, dict):
            ev.page = page
            ev.bbox = bbox
            ev.raw_value = self.pdf_vars[key].get().strip()
            ev.normalized_value = ev.raw_value
        else:
            self._field_evidence[key] = FieldEvidence(
                field_name=key,
                normalized_value=self.pdf_vars[key].get().strip(),
                raw_value=self.pdf_vars[key].get().strip(),
                source="user_search",
                confidence=1.0,
                page=page,
                bbox=bbox,
            )

    def _focus_pdf_field(self, key: str) -> None:
        """Navigate the PDF viewer to where *key* was found.

        If multiple hits exist, cycle to the next one on each click.
        The chosen position is pinned so automated searches won't overwrite it.
        """
        # Cancel any pending debounce search so it doesn't overwrite our
        # hit index right after the user explicitly picks a position.
        prev_timer = self._search_timers.pop(key, None)
        if prev_timer is not None:
            self.after_cancel(prev_timer)

        hits = self._field_hits.get(key, [])
        if len(hits) > 1:
            # Cycle to next hit
            idx = self._field_hit_index.get(key, 0)
            idx = (idx + 1) % len(hits)
            self._field_hit_index[key] = idx
            page, bbox = hits[idx]
            self._update_evidence_location(key, page, bbox)
            # Pin this field — automated searches will respect this choice
            self._pinned_fields.add(key)
            self._update_page_label_for(key)

        label = next((lbl for k, lbl in FIELD_DEFS if k == key), key)
        target = preview_target_from_evidence(key, self._field_evidence, label=label)
        if target:
            self._preview.set_highlight(target)

    def _update_page_label_for(self, key: str) -> None:
        """Update the page badge for a single field."""
        lbl = self._page_labels.get(key)
        if lbl is None:
            return
        evidence = self._field_evidence.get(key)
        hits = self._field_hits.get(key, [])
        n_hits = len(hits)
        is_pinned = key in self._pinned_fields

        if evidence is not None:
            page = getattr(evidence, "page", None) if not isinstance(evidence, dict) else evidence.get("page")
            if page:
                badge = f"s.{page}"
                if n_hits > 1:
                    hit_idx = self._field_hit_index.get(key, 0)
                    badge = f"s.{page} {hit_idx+1}/{n_hits}"
                if is_pinned:
                    badge += " \u2713"  # ✓ checkmark for pinned
                lbl.configure(
                    text=badge,
                    fg="#1a7a1a" if is_pinned else "#c07a00",
                    cursor="hand2",
                    font=("Segoe UI", 8, "bold" if is_pinned else "underline"),
                )
                return
        lbl.configure(text="", fg="#ccc", cursor="arrow", font=("Segoe UI", 8))

    def _update_page_labels(self) -> None:
        """Refresh page-badge labels for all fields."""
        for key, _ in FIELD_DEFS:
            self._update_page_label_for(key)

    def _update_saved_indicators(self) -> None:
        """Show disk-saved value next to each field for comparison."""
        idx = self._current_index
        saved = self._saved_fields[idx] if 0 <= idx < len(self._saved_fields) else None
        saved_ev = self._saved_evidence[idx] if 0 <= idx < len(self._saved_evidence) else None
        for key, _ in FIELD_DEFS:
            lbl = self._saved_labels.get(key)
            if lbl is None:
                continue
            if saved is None:
                lbl.configure(text="", fg="#b0b0b0", font=("Segoe UI", 7))
                continue
            disk_val = str(saved.get(key, "") or "").strip()
            gui_val = self.pdf_vars[key].get().strip()
            has_pos = saved_ev and key in saved_ev and saved_ev[key].get("page") is not None
            page_str = f" s.{saved_ev[key]['page']}" if has_pos else ""
            if not disk_val:
                lbl.configure(text="", fg="#b0b0b0", font=("Segoe UI", 7))
                continue
            # Consider equivalent values (e.g. "1 175,00" vs "1,175.00" or
            # "NO 965 004 211 MVA" vs "965004211") as a match so the saved
            # indicator goes green on format differences.
            equivalent = disk_val == gui_val or (
                bool(gui_val) and _field_matches(key, disk_val, gui_val)
            )
            color = "#1a7a1a" if equivalent else "#cc6600"
            lbl.configure(
                text=f"Lagret{page_str}: {disk_val[:20]}",
                fg=color,
                font=("Segoe UI", 7, "underline") if has_pos else ("Segoe UI", 7),
            )

    def _goto_saved_position(self, key: str) -> None:
        """Navigate PDF viewer to the saved position for this field."""
        idx = self._current_index
        saved_ev = self._saved_evidence[idx] if 0 <= idx < len(self._saved_evidence) else None
        if not saved_ev:
            return
        ev = saved_ev.get(key)
        if not ev or not isinstance(ev, dict):
            return
        page = ev.get("page")
        if page is None:
            return
        bbox = ev.get("bbox")
        bbox_t = tuple(bbox) if bbox and isinstance(bbox, (list, tuple)) and len(bbox) >= 4 else None
        label = next((lbl for k, lbl in FIELD_DEFS if k == key), key)
        target = PreviewTarget(
            field_name=key,
            page=page,
            bbox=bbox_t,
            label=label,
            source="saved",
            raw_value=ev.get("raw_value", ""),
            normalized_value=ev.get("normalized_value", ""),
        )
        self._preview.set_highlight(target)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _auto_save_before_nav(self) -> None:
        """Silently persist current edits before navigating away."""
        if not self._results:
            return
        self._save_current(advance=False, silent=True)

    def _go_prev(self) -> None:
        if self._current_index > 0:
            self._auto_save_before_nav()
            self._load_index(self._current_index - 1)

    def _go_next(self) -> None:
        if self._current_index < len(self._results) - 1:
            self._auto_save_before_nav()
            self._load_index(self._current_index + 1)

    def _on_list_double_click(self, _evt: tk.Event) -> None:  # type: ignore[type-arg]
        """Show accounting entry drilldown for the selected bilag."""
        sel = self._list.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except ValueError:
            return
        r = self._results[idx]
        df_bilag = _bilag_rows(self._df_all, r.bilag_nr)
        _show_drilldown(self, bilag_nr=r.bilag_nr, df_bilag=df_bilag)

    def _on_list_select(self, _evt: tk.Event) -> None:  # type: ignore[type-arg]
        sel = self._list.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except ValueError:
            return
        if idx != self._current_index:
            self._auto_save_before_nav()
            self._load_index(idx)

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------

    def _save_current(self, *, advance: bool = False, silent: bool = False) -> None:
        idx = self._current_index
        r   = self._results[idx]

        # Collect edited PDF fields
        fields = {key: self.pdf_vars[key].get().strip() for key, _ in FIELD_DEFS}
        self._pdf_state[idx] = dict(fields)
        self._hit_idx_state[idx] = dict(self._field_hit_index)
        notes = self._txt_notes.get("1.0", "end").strip()
        self._notes_state[idx] = notes

        # Re-evaluate avvik with corrected field values
        df_bilag    = _bilag_rows(self._df_all, r.bilag_nr)
        voucher_ctx = build_voucher_context(df_bilag)
        facts       = DocumentFacts.from_mapping(fields)
        all_msgs    = build_validation_messages(facts, voucher_ctx)
        real_avvik  = [m for m in all_msgs if _is_real_avvik(m)]
        self._avvik_state[idx] = real_avvik
        if not silent:
            self._set_avvik_text(real_avvik)

        # Update status
        new_status = "ok" if not real_avvik else "avvik"
        if r.status == "ikke_funnet" and not r.extracted_path:
            new_status = "ikke_funnet"
        self._status_state[idx] = new_status
        self._update_list_row(idx)
        # Update header with (possibly edited) supplier name
        display_name = fields.get("supplier_name", "").strip() or r.supplier_name or "(leverandør ukjent)"
        self._var_header.set(f"Bilag {r.bilag_nr}  —  {display_name}")
        if not silent:
            self._var_progress.set(
                f"{idx + 1} / {len(self._results)}  ({'OK' if new_status == 'ok' else 'Avvik'})"
            )

        # Persist to store — pass segments for coordinate-based profile learning
        file_path = r.extracted_path or self._var_file_path.get().strip()
        try:
            save_document_review(
                client=self._client,
                year=self._year,
                bilag=r.bilag_nr,
                file_path=file_path,
                field_values=fields,
                validation_messages=real_avvik,
                raw_text_excerpt=self._last_raw_text_excerpt,
                notes=notes,
                segments=self._last_segments,
                field_hit_indices=dict(self._field_hit_index),
                field_evidence=dict(self._field_evidence),
            )
            # Update saved snapshots so indicators reflect disk state
            self._saved_fields[idx] = dict(fields)
            # Snapshot evidence (page+bbox) for "show saved location"
            ev_snapshot: dict[str, Any] = {}
            for k, v in self._field_evidence.items():
                if hasattr(v, "to_dict"):
                    ev_snapshot[k] = v.to_dict()
                elif isinstance(v, dict):
                    ev_snapshot[k] = dict(v)
            self._saved_evidence[idx] = ev_snapshot if ev_snapshot else None
            if not silent:
                self._var_status_bar.set(
                    f"Lagret bilag {r.bilag_nr} ({new_status.upper()})  —  klient={self._client or '?'}, år={self._year or '?'}"
                )
                self._update_saved_indicators()
        except Exception as exc:
            if not silent:
                messagebox.showerror("Lagringsfeil", str(exc), parent=self)
            return

        if advance:
            if idx < len(self._results) - 1:
                self._load_index(idx + 1)
            else:
                self._show_finish_dialog()

    def _save_and_next(self) -> None:
        self._save_current(advance=True)

    # ------------------------------------------------------------------
    # Finish / export
    # ------------------------------------------------------------------

    def _collect_bilag_data(self) -> list[dict[str, Any]]:
        """Build a list of bilag dicts for export from dialog state."""
        bilag_data: list[dict[str, Any]] = []
        for i, r in enumerate(self._results):
            df_bilag = _bilag_rows(self._df_all, r.bilag_nr)
            hb = _extract_hb_values(df_bilag, r.accounting_ref, bilag_nr=r.bilag_nr)
            pdf = dict(self._pdf_state[i])
            status = self._status_state[i]
            avvik = list(self._avvik_state[i])
            notes = self._notes_state[i]
            bilag_data.append({
                "bilag_nr": r.bilag_nr,
                "status": status,
                "hb_fields": hb,
                "pdf_fields": pdf,
                "avvik": avvik,
                "notes": notes,
            })
        return bilag_data

    def _show_finish_dialog(self) -> None:
        """Show completion dialog with export options."""
        n = len(self._results)
        n_ok = sum(1 for s in self._status_state if s == "ok")
        n_avvik = sum(1 for s in self._status_state if s == "avvik")
        n_ikke = sum(1 for s in self._status_state if s == "ikke_funnet")

        win = tk.Toplevel(self)
        win.title("Bilagskontroll ferdig")
        win.geometry("420x260")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=f"Alle {n} bilag er gjennomgått.",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(frm, text=f"OK: {n_ok}   Avvik: {n_avvik}   Ikke funnet: {n_ikke}",
                  foreground="#555").pack(anchor="w", pady=(4, 12))

        ttk.Label(frm, text="Eksporter rapport:").pack(anchor="w", pady=(0, 4))

        btn_frm = ttk.Frame(frm)
        btn_frm.pack(fill="x", pady=(0, 8))

        def _do_export_excel() -> None:
            try:
                from document_control_export import export_to_excel, open_file
                data = self._collect_bilag_data()
                path = export_to_excel(
                    client=self._client or "ukjent",
                    year=self._year or "ukjent",
                    bilag_data=data,
                )
                open_file(path)
                self._var_status_bar.set(f"Excel-rapport eksportert: {path}")
            except Exception as exc:
                messagebox.showerror("Eksportfeil", str(exc), parent=win)

        def _do_export_html() -> None:
            try:
                from document_control_export import export_to_html, open_file
                data = self._collect_bilag_data()
                path = export_to_html(
                    client=self._client or "ukjent",
                    year=self._year or "ukjent",
                    bilag_data=data,
                )
                open_file(path)
                self._var_status_bar.set(f"HTML-rapport eksportert: {path}")
            except Exception as exc:
                messagebox.showerror("Eksportfeil", str(exc), parent=win)

        def _do_export_both() -> None:
            _do_export_excel()
            _do_export_html()

        ttk.Button(btn_frm, text="Excel (.xlsx)", command=_do_export_excel).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frm, text="HTML (utskrift)", command=_do_export_html).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frm, text="Begge", command=_do_export_both).pack(side="left")

        ttk.Separator(frm).pack(fill="x", pady=8)
        ttk.Button(frm, text="Lukk", command=win.destroy).pack(anchor="e")

    # ------------------------------------------------------------------
    # File / re-analysis
    # ------------------------------------------------------------------

    def _toggle_file_bar(self) -> None:
        if self._file_bar_expanded:
            self._file_detail.grid_forget()
            self._file_toggle_btn.configure(text="Dok ►")
        else:
            self._file_detail.grid(row=0, column=1, sticky="ew", padx=(4, 0))
            self._file_toggle_btn.configure(text="Dok ▼")
        self._file_bar_expanded = not self._file_bar_expanded

    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Velg dokument",
            filetypes=[("Dokumenter", "*.pdf *.xml *.txt *.png *.jpg"), ("Alle", "*.*")],
        )
        if not path:
            return
        self._var_file_path.set(path)
        idx = self._current_index
        self._results[idx] = _replace_extracted_path(self._results[idx], path)
        self._preview.load_file(path)
        # Reload segments AND raw text so saving without a follow-up "Les oppl."
        # still persists the correct excerpt/coordinates for the new file.
        self._reload_segments_for(path)

    def _auto_analyse(self, file_path: str, expected_idx: int) -> None:
        """Run analysis silently on bilag load to populate page badges.

        Unlike _reanalyse, this does NOT overwrite user-edited PDF fields —
        it only populates field_evidence (for page badges and highlight).
        If the user has navigated away, the result is discarded.
        """
        if self._current_index != expected_idx:
            return
        if not file_path or not Path(file_path).exists():
            return
        r = self._results[expected_idx]
        df_bilag = _bilag_rows(self._df_all, r.bilag_nr)
        try:
            from document_control_app_service import analyze_document_for_bilag
            analysis = analyze_document_for_bilag(file_path, df_bilag=df_bilag)
        except Exception:
            return
        # Guard: user may have navigated away during analysis
        if self._current_index != expected_idx:
            return
        # Capture extracted raw text AND segments from the analysis itself, so
        # that saving learns against the same geometry analyze_document chose
        # (important after a redo-OCR swap — a fresh _reload_segments_for call
        # would pick the native extraction again, not the redo result).
        self._last_raw_text_excerpt = analysis.raw_text_excerpt or ""
        analysis_segments = getattr(analysis, "segments", None)
        if analysis_segments:
            self._last_segments = list(analysis_segments)
        # Merge analysis evidence but preserve existing entries that have bbox
        # (e.g. restored from disk or user-confirmed positions)
        new_evidence = dict(analysis.field_evidence or {})
        for key, ev in self._field_evidence.items():
            ev_bbox = getattr(ev, "bbox", None) if not isinstance(ev, dict) else ev.get("bbox")
            if ev_bbox is not None:
                new_evidence[key] = ev
        self._field_evidence = new_evidence

        # Fill empty PDF fields from analysis — but only for bilag that have
        # never been saved (otherwise the user's choices take precedence).
        _has_saved = False
        try:
            _has_saved = load_saved_review(self._client, self._year, r.bilag_nr) is not None
        except Exception:
            pass
        self._suppress_pdf_search = True
        fields = analysis.fields or {}
        for key, _ in FIELD_DEFS:
            if _has_saved:
                continue
            if not self.pdf_vars[key].get().strip() and fields.get(key, "").strip():
                self.pdf_vars[key].set(fields[key])
        self._suppress_pdf_search = False

        # Build hit lists so cycling works immediately
        for key, _ in FIELD_DEFS:
            # Skip pinned fields — user has explicitly chosen a position
            if key in self._pinned_fields:
                continue
            val = self.pdf_vars[key].get().strip()
            hits: list[tuple[int, tuple]] = []
            if val and len(val) >= 2:
                hits = self._sort_hits(self._preview.search_all_pages(val))
            # Fallback: search for raw_value from evidence (e.g. text-month date)
            if not hits:
                ev = self._field_evidence.get(key)
                raw = getattr(ev, "raw_value", "") if ev and not isinstance(ev, dict) else ""
                if raw and raw != val and len(raw) >= 2:
                    hits = self._sort_hits(self._preview.search_all_pages(raw))
            self._field_hits[key] = hits
            # Restore persisted hit index if available, else default to 0
            saved_idx = self._hit_idx_state[expected_idx].get(key, 0)
            self._field_hit_index[key] = min(saved_idx, max(len(hits) - 1, 0))
        self._update_page_labels()

        # Update evidence to point to the restored hit index
        for key, _ in FIELD_DEFS:
            if key in self._pinned_fields:
                continue
            hits = self._field_hits.get(key, [])
            idx_h = self._field_hit_index.get(key, 0)
            if hits and 0 <= idx_h < len(hits):
                page, bbox = hits[idx_h]
                self._update_evidence_location(key, page, bbox)

        # Sync _pdf_state only for fields that were actually filled by analysis
        # (don't overwrite user-saved values)
        if not _has_saved:
            self._pdf_state[expected_idx] = {
                key: self.pdf_vars[key].get() for key, _ in FIELD_DEFS
            }

    def _reanalyse(self) -> None:
        file_path = self._var_file_path.get().strip()
        if not file_path or not Path(file_path).exists():
            messagebox.showinfo("Analyse", "Velg et dokument først.", parent=self)
            return
        idx      = self._current_index
        r        = self._results[idx]
        df_bilag = _bilag_rows(self._df_all, r.bilag_nr)

        self._var_status_bar.set("Analyserer dokument...")
        self.configure(cursor="wait")
        self.update_idletasks()
        try:
            from document_control_app_service import analyze_document_for_bilag
            analysis = analyze_document_for_bilag(file_path, df_bilag=df_bilag)
        except Exception as exc:
            self.configure(cursor="")
            self._var_status_bar.set("")
            messagebox.showerror("Analyse", str(exc), parent=self)
            return
        finally:
            self.configure(cursor="")
            self._var_status_bar.set("")

        # Capture raw text AND segments from the analysis itself, so saving
        # learns against the same geometry analyze_document chose. Only fall
        # back to an independent re-extraction if the analysis happens not to
        # expose segments (older code path, or XML input).
        self._last_raw_text_excerpt = analysis.raw_text_excerpt or ""
        analysis_segments = getattr(analysis, "segments", None)
        if analysis_segments:
            self._last_segments = list(analysis_segments)

        fields   = analysis.fields or {}
        new_state = {key: fields.get(key, "") for key, _ in FIELD_DEFS}
        self._pdf_state[idx] = new_state
        self._suppress_pdf_search = True
        for key, _ in FIELD_DEFS:
            self.pdf_vars[key].set(new_state.get(key, ""))
        self._suppress_pdf_search = False

        # Store field evidence for location highlighting + page badges
        self._field_evidence = dict(analysis.field_evidence or {})
        # Build initial hit lists from evidence so cycling works
        for key, _ in FIELD_DEFS:
            val = new_state.get(key, "").strip()
            hits_r: list[tuple[int, tuple]] = []
            if val and len(val) >= 2:
                hits_r = self._sort_hits(self._preview.search_all_pages(val))
            # Fallback: search for raw_value from evidence (e.g. text-month date)
            if not hits_r:
                ev = self._field_evidence.get(key)
                raw = getattr(ev, "raw_value", "") if ev and not isinstance(ev, dict) else ""
                if raw and raw != val and len(raw) >= 2:
                    hits_r = self._sort_hits(self._preview.search_all_pages(raw))
            self._field_hits[key] = hits_r
            self._field_hit_index[key] = 0
        self._update_page_labels()

        # Only fall back to an independent re-extraction if the analysis did
        # not expose segments — otherwise we'd overwrite the redo-OCR geometry
        # with the native extraction.
        if not analysis_segments:
            self._reload_segments_for(file_path)

        real_avvik = [m for m in (analysis.validation_messages or []) if _is_real_avvik(m)]
        self._avvik_state[idx] = real_avvik
        self._set_avvik_text(real_avvik)

        new_status = "ok" if not real_avvik else "avvik"
        self._status_state[idx] = new_status
        self._update_list_row(idx)
        self._var_progress.set(
            f"{idx + 1} / {len(self._results)}  ({'OK' if new_status == 'ok' else 'Avvik'})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _show_drilldown(parent: tk.Misc, *, bilag_nr: str, df_bilag: pd.DataFrame) -> None:
    """Open a modal popup showing accounting lines for *bilag_nr*."""
    win = tk.Toplevel(parent)
    win.title(f"Bilagsføring — bilag {bilag_nr}")
    win.geometry("900x400")
    win.minsize(600, 280)
    win.resizable(True, True)
    try:
        win.transient(parent.winfo_toplevel())
    except Exception:
        pass
    win.grab_set()

    win.columnconfigure(0, weight=1)
    win.rowconfigure(1, weight=1)

    ttk.Label(win, text=f"Bilagsføring — bilag {bilag_nr}",
              font=("Segoe UI", 10, "bold"), padding=(10, 8, 10, 4)).grid(
        row=0, column=0, sticky="w")

    # Determine which columns to show
    preferred = ["Dato", "Konto", "Kontonavn", "Tekst",
                 "Beløp", "MVA-kode", "MVA-beløp", "Referanse", "Valuta",
                 "Leverandørnavn", "Leverandørorgnr"]
    if df_bilag is None or df_bilag.empty:
        show_cols = preferred
    else:
        show_cols = [c for c in preferred if c in df_bilag.columns]
        # add any remaining columns not in preferred
        extra = [c for c in df_bilag.columns
                 if c not in show_cols and c not in ("Bilag", "Bilagsnr")]
        show_cols += extra[:4]  # max 4 extra columns

    frame = ttk.Frame(win, padding=(8, 0, 8, 8))
    frame.grid(row=1, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)

    tree = ttk.Treeview(frame, columns=show_cols, show="headings",
                        selectmode="browse")
    for col in show_cols:
        anchor = "e" if col in ("Beløp", "MVA-beløp") else "w"
        width  = 90  if col in ("Beløp", "MVA-beløp", "Dato", "Konto", "MVA-kode", "Valuta") else 160
        tree.heading(col, text=col)
        tree.column(col, width=width, anchor=anchor, stretch=(col == "Tekst"))

    if df_bilag is not None and not df_bilag.empty:
        for _, row in df_bilag.iterrows():
            values = []
            for col in show_cols:
                v = row.get(col, "") if col in df_bilag.columns else ""
                if pd.isna(v):
                    v = ""
                elif col in ("Beløp", "MVA-beløp"):
                    try:
                        v = f"{float(v):,.2f}".replace(",", "\u00a0").replace(".", ",")
                    except Exception:
                        pass
                values.append(str(v))
            tree.insert("", tk.END, values=values)

    vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL,   command=tree.yview)
    hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    ttk.Button(win, text="Lukk", command=win.destroy,
               padding=(8, 4)).grid(row=2, column=0, sticky="e",
                                    padx=10, pady=(0, 8))
    win.bind("<Escape>", lambda _e: win.destroy())
    win.focus_set()


def _status_dot(status: str) -> tuple[str, str]:
    return {
        "ok":          ("●", _TAG_OK),
        "avvik":       ("○", _TAG_AVVIK),
        "ikke_funnet": ("–", _TAG_IKKE),
        "feil":        ("!", _TAG_AVVIK),
    }.get(status, ("?", _TAG_IKKE))


def _bilag_rows(df: Any, bilag_nr: str) -> pd.DataFrame:
    if df is None or getattr(df, "empty", True) or "Bilag" not in df.columns:
        return pd.DataFrame()
    key  = normalize_bilag_key(bilag_nr)
    mask = df["Bilag"].map(normalize_bilag_key) == key
    return df.loc[mask].copy()


def _init_pdf_state(r: BatchDocumentResult) -> dict[str, str]:
    """Initial PDF field values from a BatchDocumentResult."""
    base: dict[str, str] = {
        "supplier_name":   r.supplier_name  or "",
        "supplier_orgnr":  "",
        "invoice_number":  r.invoice_number or "",
        "invoice_date":    r.invoice_date   or "",
        "due_date":        "",
        "subtotal_amount": "",
        "vat_amount":      "",
        "total_amount":    _fmt_amount(r.invoice_total),
        "currency":        "",
    }
    return {key: base.get(key, "") for key, _ in FIELD_DEFS}


def _fmt_amount(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")


def _extract_hb_values(
    df_bilag: pd.DataFrame,
    accounting_ref: float,
    *,
    bilag_nr: str = "",
) -> dict[str, str]:
    """Extract accounting-side field values for display in the HB column.

    Supplier name and org.nr come specifically from reskontro lines — rows where
    Leverandørnr is populated (the AP/2400 creditor posting).  Other lines are
    expense/VAT lines that don't carry supplier identity.

    VAT and net amounts are derived from the accounting line detail (MVA-beløp
    column or konto 2700-2799 lines).
    """
    hb: dict[str, str] = {}

    if df_bilag is None or df_bilag.empty:
        if accounting_ref:
            hb["total_amount"] = _fmt_amount(accounting_ref)
        return hb

    cols = set(df_bilag.columns)

    # ── Reskontro rows: lines where Leverandørnr is populated ───────────
    # These are the AP creditor postings (konto 2400) that carry supplier info.
    reskontro_rows = df_bilag
    if "Leverandørnr" in cols:
        mask = df_bilag["Leverandørnr"].notna() & (
            df_bilag["Leverandørnr"].astype(str).str.strip() != ""
        )
        if mask.any():
            reskontro_rows = df_bilag[mask]

    # ── Supplier name — from reskontro rows ─────────────────────────────
    for col in ("Leverandørnavn", "Kreditornavn", "CreditorName"):
        if col in cols:
            ser = reskontro_rows[col].dropna().astype(str)
            v = _first_valid(ser)
            if v:
                hb["supplier_name"] = v
                break

    # ── Org.nr — from reskontro rows ────────────────────────────────────
    for col in ("Leverandørorgnr", "Kundeorgnr", "CreditorOrgNr"):
        if col in cols:
            ser = reskontro_rows[col].dropna().astype(str)
            v = _first_valid(ser)
            if v:
                hb["supplier_orgnr"] = v
                break

    # ── Invoice date ────────────────────────────────────────────────────
    for col in _DATE_COLS:
        if col in cols:
            ser = df_bilag[col].dropna()
            if not ser.empty:
                hb["invoice_date"] = _norm_date(str(ser.iloc[0]))
                break

    # ── Invoice reference — from reskontro rows, excluding the bilag nr ─
    # The AP line's Referanse should be the supplier's invoice number.
    bilag_key = normalize_bilag_key(bilag_nr) if bilag_nr else ""
    if "Referanse" in cols:
        for v_raw in reskontro_rows["Referanse"].dropna().astype(str):
            v = v_raw.strip()
            if not v or v.lower() in ("nan", "none"):
                continue
            # Skip if the reference is just the bilag number itself
            if bilag_key and normalize_bilag_key(v) == bilag_key:
                continue
            hb["invoice_number"] = v
            break

    # ── Total, MVA og netto — fra kontolinjene direkte ───────────────────
    #
    # Kilde 1 (best): Konto-kolonne i df_bilag
    #   • Total  = abs(kredit på konto 2400-2499) — alltid lik fakturabeløp inkl. mva
    #   • MVA    = debet på konto 2710-2719 (inngående merverdiavgift)
    #   • Netto  = Total − MVA
    #
    # Kilde 2 (fallback): MVA-beløp-kolonnen fra SAF-T
    #
    # Kilde 3 (siste utvei): accounting_ref fra batch-servicen
    #
    total_from_ap:  float | None = None
    mva_from_konto: float | None = None

    if "Konto" in cols and "Beløp" in cols:
        konto_str = df_bilag["Konto"].astype(str)

        # 2400-2499: Leverandørgjeld (AP) — kredit = fakturatotal inkl. mva
        ap_mask = konto_str.str.match(r"^24\d{2}$")
        if ap_mask.any():
            ap_vals = pd.to_numeric(df_bilag.loc[ap_mask, "Beløp"], errors="coerce").dropna()
            credits = ap_vals[ap_vals < 0]
            if not credits.empty:
                total_from_ap = float(credits.abs().sum())
            elif not ap_vals.empty:
                total_from_ap = float(ap_vals.abs().sum())  # reversering

        # 2710-2719: Inngående merverdiavgift — debet = MVA-beløp
        mva_mask = konto_str.str.match(r"^271\d$")
        if mva_mask.any():
            mva_vals = pd.to_numeric(df_bilag.loc[mva_mask, "Beløp"], errors="coerce").dropna()
            debits = mva_vals[mva_vals > 0]
            mva_sum = float(debits.sum()) if not debits.empty else float(mva_vals.abs().sum())
            if mva_sum > 0.005:
                mva_from_konto = mva_sum

    # Fallback MVA: MVA-beløp-kolonnen fra SAF-T
    if mva_from_konto is None and "MVA-beløp" in cols:
        mva_series = pd.to_numeric(df_bilag["MVA-beløp"], errors="coerce").dropna()
        mva_sum = float(mva_series[mva_series > 0].sum())
        if mva_sum < 0.005:
            mva_sum = float(mva_series.abs().sum())
        if mva_sum > 0.005:
            mva_from_konto = mva_sum

    # Sett total
    if total_from_ap is not None:
        hb["total_amount"] = _fmt_amount(total_from_ap)
    elif accounting_ref:
        hb["total_amount"] = _fmt_amount(accounting_ref)

    # Sett MVA
    if mva_from_konto is not None:
        hb["vat_amount"] = _fmt_amount(mva_from_konto)

    # Sett netto = total − MVA
    if "total_amount" in hb and "vat_amount" in hb:
        t = _parse_amount(hb["total_amount"])
        v = _parse_amount(hb["vat_amount"])
        if t is not None and v is not None and t > v:
            hb["subtotal_amount"] = _fmt_amount(t - v)

    # ── Currency ─────────────────────────────────────────────────────────
    for col in ("Valuta", "Currency"):
        if col in cols:
            ser = df_bilag[col].dropna().astype(str)
            v = _first_valid(ser)
            if v:
                hb["currency"] = v
                break

    return hb


def _first_valid(ser: pd.Series) -> str:
    """Return first non-empty, non-nan string value from a Series, or ''."""
    for v in ser:
        v = str(v).strip()
        if v and v.lower() not in ("nan", "none"):
            return v
    return ""


def _is_bilagsprint_text(text: str) -> bool:
    """Return True if the page text looks like a Tripletex bilagsprint."""
    import re as _re
    lowered = text.lower()
    has_bilag_nr  = bool(_re.search(r"bilag\s+nummer\s+\d", lowered))
    has_kontering = bool(_re.search(
        r"konteringssammendrag|sum\s+debet|sum\s+kredit|kontostrengen",
        lowered,
    ))
    return has_bilag_nr and has_kontering


_MONTH_NAMES: dict[str, int] = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
    "january": 1, "february": 2, "march": 3, "may": 5,
    "june": 6, "july": 7, "october": 10, "december": 12,
}

_TEXT_DATE_RE = re.compile(
    r"(\d{1,2})\.\s*("
    + "|".join(_MONTH_NAMES.keys())
    + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _norm_date(text: str) -> str:
    """Normalise a date string to dd.mm.yyyy.

    Handles numeric formats (05.11.2025, 2025-11-05, 05/11/25)
    and Norwegian/English text months (5. november 2025).
    """
    text = re.sub(r"\s+", " ", text or "").strip()

    # Try text-month format BEFORE stripping timestamp suffix (which eats " 2025")
    m = _TEXT_DATE_RE.search(text)
    if m:
        day, month_name, year = m.group(1), m.group(2).lower(), m.group(3)
        month_num = _MONTH_NAMES.get(month_name)
        if month_num:
            return f"{int(day):02d}.{month_num:02d}.{int(year):04d}"

    # Strip ISO timestamp suffix (e.g. "2025-11-05T12:00:00Z" → "2025-11-05")
    text = re.sub(r"[T ][\d:Z+\-]+$", "", text).strip()
    text = text.replace("/", ".").replace("-", ".")
    parts = text.split(".")
    if len(parts) != 3:
        return text
    if len(parts[0]) == 4:
        year, month, day = parts
    else:
        day, month, year = parts
    if len(year) == 2:
        year = f"20{year}"
    try:
        d, m_val, y = int(day), int(month), int(year)
        return f"{d:02d}.{m_val:02d}.{y:04d}"
    except Exception:
        return text


def _norm_orgnr(text: str) -> str:
    """Normalise org number by stripping all non-digits."""
    return normalize_orgnr(text)


def _field_matches(key: str, hb_val: str, pdf_val: str) -> bool:
    """Return True if HB and PDF values are considered equivalent for *key*."""
    hb  = hb_val.strip()
    pdf = pdf_val.strip()
    if not pdf:
        return False

    # Info-only fields are never matched
    if key in _INFO_KEYS:
        return False

    if key in _AMOUNT_KEYS:
        hb_n  = _parse_amount(hb)
        pdf_n = _parse_amount(pdf)
        if hb_n is None or pdf_n is None:
            return False
        return abs(hb_n - pdf_n) <= max(1.0, abs(hb_n) * 0.001)

    if key in _DATE_KEYS:
        return _norm_date(hb) == _norm_date(pdf)

    if key in _ORGNR_KEYS:
        return orgnr_matches(hb, pdf)

    h = hb.lower()
    p = pdf.lower()
    if h == p or h in p or p in h:
        return True
    h_tok = {t for t in re.split(r"[\s,./\-]+", h) if len(t) >= 3}
    p_tok = {t for t in re.split(r"[\s,./\-]+", p) if len(t) >= 3}
    if h_tok and p_tok:
        return len(h_tok & p_tok) / min(len(h_tok), len(p_tok)) >= 0.5
    return False


def _parse_amount(text: str) -> float | None:
    return parse_amount_flexible(text)


def _pdf_search_variants(key: str, value: str) -> list[str]:
    """Return alternative text variants to search the PDF for *value*.

    The direct value is always first. Amount fields defer to
    :func:`document_engine.format_utils.amount_search_variants` (Norwegian
    and international number forms, full-decimal before bare integer).
    Org.nr. fields expand into digits-only, space-grouped, and
    ``NO .. MVA`` variants.
    """
    value = (value or "").strip()
    if not value:
        return []
    variants: list[str] = [value]

    def _add(v: str) -> None:
        v = v.strip()
        if v and v not in variants:
            variants.append(v)

    if key in _AMOUNT_KEYS:
        for variant in amount_search_variants(value):
            _add(variant)
        return variants

    if key in _ORGNR_KEYS:
        digits = _norm_orgnr(value)
        if len(digits) == 9:
            spaced = f"{digits[:3]} {digits[3:6]} {digits[6:]}"
            _add(digits)
            _add(spaced)
            _add(f"NO {spaced}")
            _add(f"NO{spaced}")
            _add(f"NO {spaced} MVA")
            _add(f"NO{digits}MVA")
        else:
            _add(digits)
        return variants

    return variants


def _replace_extracted_path(r: BatchDocumentResult, path: str) -> BatchDocumentResult:
    """Return a copy of *r* with extracted_path replaced."""
    d = {f.name: getattr(r, f.name) for f in dc_fields(r)}
    d["extracted_path"] = path
    return BatchDocumentResult(**d)

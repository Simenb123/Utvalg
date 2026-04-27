from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import session
from ..backend.crmsystem import CRMSystemLookupResult, load_materiality_from_crm, suggest_client_numbers_from_name
from ..backend.engine import (
    BENCHMARK_KEYS,
    BENCHMARK_LABELS,
    MaterialityCalculation,
    build_benchmark_amounts_for_session,
    calculate_materiality,
    get_default_percentages,
    normalize_benchmark_key,
    pick_default_benchmark,
)
from ..backend.store import (
    DEFAULT_SELECTION_THRESHOLD_KEY,
    SELECTION_THRESHOLD_LABELS,
    build_candidate_client_numbers,
    get_selection_threshold_label,
    load_state,
    materiality_dir,
    merge_state,
    normalize_selection_threshold_key,
    resolve_selection_threshold,
)
from ..backend.workpaper_excel import export_materiality_workpaper


_SUPPORTED_SELECTION_THRESHOLD_KEYS = (
    "performance_materiality",
    "overall_materiality",
    "clearly_trivial",
)
_SUPPORTED_SELECTION_THRESHOLD_LABELS = [
    SELECTION_THRESHOLD_LABELS[key] for key in _SUPPORTED_SELECTION_THRESHOLD_KEYS
]


def _fmt_amount(value: object) -> str:
    try:
        if value is None:
            return "-"
        amount = float(value)  # type: ignore[arg-type]
        return f"{amount:,.0f}".replace(",", "\u202f")
    except Exception:
        return "-"


def _fmt_amount_input(value: object) -> str:
    try:
        amount = round(float(value or 0.0))
    except Exception:
        amount = 0
    return f"{amount:,.0f}".replace(",", " ") if amount > 0 else ""


def _fmt_pct(value: object, *, decimals: int = 1) -> str:
    try:
        pct = float(value or 0.0)
    except Exception:
        pct = 0.0
    return f"{pct:.{decimals}f}".replace(".", ",")


def _parse_float(value: object, default: float = 0.0) -> float:
    raw = str(value or "").strip()
    if not raw:
        return default
    raw = raw.replace(" ", "").replace("\u202f", "").replace(",", ".")
    try:
        return float(raw)
    except Exception:
        return default


def _source_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return "-"
    source = str(payload.get("source") or "").strip().lower()
    if source == "crmsystem":
        return "CRMSystem"
    if source == "local_calculation":
        return "Lokal beregning"
    return source or "-"


def _supported_threshold_key(value: object) -> str:
    key = normalize_selection_threshold_key(value)
    if key in _SUPPORTED_SELECTION_THRESHOLD_KEYS:
        return key
    return DEFAULT_SELECTION_THRESHOLD_KEY


def _resolve_active_threshold_display(active_materiality: object, threshold_key: object) -> tuple[str, str]:
    resolved_key, resolved_amount = resolve_selection_threshold(active_materiality, threshold_key)
    return (
        get_selection_threshold_label(resolved_key),
        _fmt_amount(resolved_amount) if resolved_amount is not None else "-",
    )


def _inverse_pct_texts(calc: MaterialityCalculation | None) -> tuple[str, str, str]:
    if calc is None or float(calc.benchmark_amount or 0.0) <= 0.0:
        return "-", "-", "-"
    return (
        f"{_fmt_pct(calc.om_pct, decimals=2)} %",
        f"{_fmt_pct(calc.pm_pct, decimals=2)} %",
        f"{_fmt_pct(calc.trivial_pct, decimals=2)} %",
    )


def _safe_filename_part(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "-", str(value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "klient"


class MaterialityPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent)
        self._session: object = session
        self._client = ""
        self._year = ""
        self._state: dict[str, Any] = {}
        self._benchmark_amounts: dict[str, float] = {}
        self._benchmark_key_by_label = {label: key for key, label in BENCHMARK_LABELS.items()}
        self._crm_lookup: CRMSystemLookupResult | None = None
        self._selected_om_sync_guard = False
        self._selected_om_autofill = True
        self._threshold_choice_sync_guard = False

        self.var_context = tk.StringVar(value="Ingen klient lastet")
        self.var_status = tk.StringVar(value="Last inn klient og år for å jobbe med vesentlighet.")
        self.var_crm_path = tk.StringVar(value="CRMSystem er ikke lest ennå.")
        self.var_crm_client_number = tk.StringVar(value="")
        self.var_crm_match = tk.StringVar(value="-")
        self.var_crm_year = tk.StringVar(value="-")
        self.var_crm_materiality = tk.StringVar(value="-")
        self.var_crm_pmateriality = tk.StringVar(value="-")
        self.var_crm_trivial = tk.StringVar(value="-")
        self.var_crm_source_updated = tk.StringVar(value="-")
        self.var_crm_synced = tk.StringVar(value="-")

        self.var_benchmark = tk.StringVar(value="")
        self.var_benchmark_amount = tk.StringVar(value="-")
        self.var_reference_pct_range = tk.StringVar(value="-")
        self.var_reference_amount_range = tk.StringVar(value="-")
        self.var_threshold_choice = tk.StringVar(value=SELECTION_THRESHOLD_LABELS[DEFAULT_SELECTION_THRESHOLD_KEY])
        self.var_selected_om = tk.StringVar(value="")
        self.var_pm_pct = tk.StringVar(value="")
        self.var_trivial_pct = tk.StringVar(value="")
        self.var_calc_om = tk.StringVar(value="-")
        self.var_calc_pm = tk.StringVar(value="-")
        self.var_calc_trivial = tk.StringVar(value="-")
        self.var_calc_om_pct_of_benchmark = tk.StringVar(value="-")
        self.var_calc_pm_pct_of_om = tk.StringVar(value="-")
        self.var_calc_trivial_pct_of_pm = tk.StringVar(value="-")

        self.var_active_source = tk.StringVar(value="-")
        self.var_active_om = tk.StringVar(value="-")
        self.var_active_pm = tk.StringVar(value="-")
        self.var_active_trivial = tk.StringVar(value="-")
        self.var_active_threshold = tk.StringVar(value="-")
        self.var_active_threshold_amount = tk.StringVar(value="-")
        self.var_active_saved = tk.StringVar(value="-")

        self._configure_styles()
        self._build_ui()

        for var in (self.var_pm_pct, self.var_trivial_pct):
            var.trace_add("write", lambda *_: self._refresh_calculation())
        self.var_selected_om.trace_add("write", lambda *_: self._on_selected_om_changed())

    def _configure_styles(self) -> None:
        import src.shared.ui.tokens as vt

        style = ttk.Style(self)
        primary = vt.hex_gui(vt.TEXT_PRIMARY)
        muted = vt.hex_gui(vt.TEXT_MUTED)
        accent = vt.hex_gui(vt.FOREST)
        body_family = vt.FONT_FAMILY_BODY
        display_family = vt.FONT_FAMILY_DISPLAY

        style.configure(
            "MaterialityTitle.TLabel",
            foreground=primary,
            font=(display_family, 15, "bold"),
        )
        style.configure(
            "MaterialityContext.TLabel",
            foreground=primary,
            font=(body_family, 10, "bold"),
        )
        style.configure(
            "MaterialitySub.TLabel",
            foreground=muted,
            font=(body_family, 9),
        )
        style.configure(
            "MaterialityStatus.TLabel",
            foreground=accent,
            font=(body_family, 9, "bold"),
        )
        style.configure(
            "MaterialityKey.TLabel",
            foreground=muted,
            font=(body_family, 9),
        )
        style.configure(
            "MaterialityValue.TLabel",
            foreground=primary,
            font=(body_family, 10),
        )
        style.configure(
            "MaterialityAmount.TLabel",
            foreground=primary,
            font=(body_family, 10, "bold"),
        )
        style.configure(
            "MaterialitySection.TLabel",
            foreground=accent,
            font=(body_family, 9, "bold"),
        )
        style.configure(
            "MaterialityMetricTitle.TLabel",
            foreground=muted,
            font=(body_family, 9),
        )
        style.configure(
            "MaterialityMetricValue.TLabel",
            foreground=primary,
            font=(display_family, 13, "bold"),
        )
        style.configure(
            "MaterialityMetricText.TLabel",
            foreground=accent,
            font=(body_family, 10, "bold"),
        )
        style.configure(
            "MaterialityMetricSub.TLabel",
            foreground=muted,
            font=(body_family, 9),
        )
        style.configure("MaterialityMetricCard.TFrame", borderwidth=1, relief="solid")
        style.configure("MaterialityGroup.TLabelframe.Label", font=(body_family, 10, "bold"))
        style.configure("MaterialitySummary.TLabelframe.Label", font=(body_family, 10, "bold"))

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        outer = ttk.Frame(self, padding=(12, 10, 12, 12))
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title_box = ttk.Frame(header)
        title_box.grid(row=0, column=0, sticky="w")
        ttk.Label(title_box, text="Vesentlighet", style="MaterialityTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(title_box, textvariable=self.var_context, style="MaterialityContext.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        ttk.Label(
            title_box,
            text="Henter CRM-verdier, beregner benchmark og dokumenterer aktiv verdi for utvalg.",
            style="MaterialitySub.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))
        ttk.Label(title_box, textvariable=self.var_status, style="MaterialityStatus.TLabel", wraplength=860).grid(
            row=3, column=0, sticky="w", pady=(6, 0)
        )

        actions = ttk.Frame(header)
        actions.grid(row=0, column=1, sticky="e")
        self.btn_export = ttk.Button(
            actions,
            text="Eksporter arbeidspapir",
            style="Secondary.TButton",
            command=self._export_workpaper,
        )
        self.btn_export.grid(row=0, column=0, padx=(0, 8))
        self.btn_refresh = ttk.Button(actions, text="Oppdater", style="Primary.TButton", command=self._reload_all)
        self.btn_refresh.grid(row=0, column=1)

        stats = ttk.LabelFrame(outer, text="Aktiv oversikt", style="MaterialitySummary.TLabelframe", padding=(10, 8))
        stats.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        for col in range(4):
            stats.columnconfigure(col, weight=1)
        self._build_metric_card(stats, 0, "Aktiv OM", self.var_active_om, self.var_active_source)
        self._build_metric_card(stats, 1, "Aktiv PM", self.var_active_pm, self.var_active_saved)
        self._build_metric_card(stats, 2, "Aktiv ClearlyTriv", self.var_active_trivial, tk.StringVar(value=""))
        self._build_metric_card(
            stats,
            3,
            "Utvalg bruker",
            self.var_active_threshold_amount,
            self.var_active_threshold,
        )

        body = ttk.Frame(outer)
        body.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        self._build_crm_card(body).grid(row=0, column=0, sticky="new", padx=(0, 6))
        self._build_calc_card(body).grid(row=0, column=1, sticky="new", padx=(6, 0))

        self._build_active_card(outer).grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Frame(outer).grid(row=4, column=0, sticky="nsew")

    def _build_metric_card(
        self,
        parent: ttk.Frame,
        column: int,
        title: str,
        value_var: tk.StringVar,
        sub_var: tk.StringVar,
        *,
        text_style: str = "MaterialityMetricValue.TLabel",
    ) -> None:
        card = ttk.Frame(parent, style="MaterialityMetricCard.TFrame", padding=(10, 8))
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 6, 0))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=title, style="MaterialityMetricTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, textvariable=value_var, style=text_style).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(card, textvariable=sub_var, style="MaterialityMetricSub.TLabel").grid(row=2, column=0, sticky="w")

    def _build_crm_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = ttk.LabelFrame(parent, text="CRMSystem / faktiske verdier", style="MaterialityGroup.TLabelframe", padding=(12, 10))
        card.columnconfigure(1, weight=1)
        card.columnconfigure(3, weight=1)

        ttk.Label(
            card,
            text="Faktiske verdier leses fra CRMSystem. Manuell overstyring trengs bare hvis klientnavn ikke kan matches automatisk.",
            style="MaterialitySub.TLabel",
            wraplength=520,
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        self._add_card_value(card, 1, "CRM-DB", self.var_crm_path, span=3, pady=(10, 0))

        ttk.Label(card, text="Klientnr i CRM/DescARTES", style="MaterialityKey.TLabel").grid(
            row=2, column=0, sticky="w", pady=(10, 0)
        )
        entry = ttk.Entry(card, textvariable=self.var_crm_client_number, width=14, justify="right")
        entry.grid(row=2, column=1, sticky="w", pady=(10, 0))
        button_row = ttk.Frame(card)
        button_row.grid(row=2, column=2, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(button_row, text="Lagre klientnr", width=15, command=self._save_client_number).grid(row=0, column=0)
        ttk.Button(
            button_row,
            text="Les fra CRMSystem",
            style="Secondary.TButton",
            width=17,
            command=self._refresh_crm_lookup,
        ).grid(row=0, column=1, padx=(8, 0))
        self.btn_use_crm = ttk.Button(
            button_row,
            text="Bruk CRMSystem-verdier",
            style="Primary.TButton",
            width=20,
            command=self._adopt_crm_values,
        )
        self.btn_use_crm.grid(row=0, column=2, padx=(8, 0))

        ttk.Separator(card).grid(row=3, column=0, columnspan=4, sticky="ew", pady=10)

        self._add_card_value(card, 4, "Match", self.var_crm_match)
        self._add_card_value(card, 4, "Oppdragsår", self.var_crm_year, column=2)
        self._add_card_value(card, 5, "Materiality", self.var_crm_materiality, value_style="MaterialityAmount.TLabel")
        self._add_card_value(
            card,
            5,
            "Arbeidsvesentlighet (PM)",
            self.var_crm_pmateriality,
            column=2,
            value_style="MaterialityAmount.TLabel",
        )
        self._add_card_value(card, 6, "ClearlyTriv", self.var_crm_trivial, value_style="MaterialityAmount.TLabel")
        self._add_card_value(card, 6, "Kilde oppdatert", self.var_crm_source_updated, column=2)
        self._add_card_value(card, 7, "Sist synket til CRM", self.var_crm_synced)
        return card

    def _build_calc_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = ttk.LabelFrame(parent, text="Forslag fra regnskapsdata", style="MaterialityGroup.TLabelframe", padding=(12, 10))
        card.columnconfigure(1, weight=1)
        ttk.Label(
            card,
            text="Inspirert av hjelpearket for vesentlighetsgrenser. Velg total vesentlighet innenfor referanseintervallet.",
            style="MaterialitySub.TLabel",
            wraplength=520,
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(card, text="Benchmark og referanse", style="MaterialitySection.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Label(card, text="Benchmark", style="MaterialityKey.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.cmb_benchmark = ttk.Combobox(
            card,
            state="readonly",
            values=[BENCHMARK_LABELS[key] for key in BENCHMARK_KEYS],
            textvariable=self.var_benchmark,
            width=24,
        )
        self.cmb_benchmark.grid(row=2, column=1, sticky="w", pady=(8, 0))
        self.cmb_benchmark.bind("<<ComboboxSelected>>", lambda _e: self._on_benchmark_selected())

        self._add_card_value(card, 3, "Benchmarkgrunnlag", self.var_benchmark_amount, value_style="MaterialityAmount.TLabel")
        self._add_card_value(card, 4, "Referanseverdier (%)", self.var_reference_pct_range, value_style="MaterialityAmount.TLabel")
        self._add_card_value(card, 5, "Beregnet intervall", self.var_reference_amount_range, value_style="MaterialityAmount.TLabel")

        ttk.Label(card, text="Valg og satser", style="MaterialitySection.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        ttk.Label(card, text="Bruk i Utvalg", style="MaterialityKey.TLabel").grid(
            row=7, column=0, sticky="w", pady=(8, 0)
        )
        self.cmb_threshold_choice = ttk.Combobox(
            card,
            state="readonly",
            values=list(_SUPPORTED_SELECTION_THRESHOLD_LABELS),
            textvariable=self.var_threshold_choice,
            width=26,
        )
        self.cmb_threshold_choice.grid(row=7, column=1, sticky="w", pady=(8, 0))
        self.cmb_threshold_choice.bind("<<ComboboxSelected>>", self._on_threshold_choice_selected)
        ttk.Label(card, text="Total vesentlighet", style="MaterialityKey.TLabel").grid(
            row=8, column=0, sticky="w", pady=(8, 0)
        )
        ent_selected_om = ttk.Entry(card, textvariable=self.var_selected_om, width=14, justify="right")
        ent_selected_om.grid(row=8, column=1, sticky="w", pady=(8, 0))
        ent_selected_om.bind("<FocusOut>", lambda _e: self._format_selected_om_entry())

        ttk.Label(card, text="Arb.ves.het % av total", style="MaterialityKey.TLabel").grid(
            row=9, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Entry(card, textvariable=self.var_pm_pct, width=14, justify="right").grid(row=9, column=1, sticky="w", pady=(8, 0))

        ttk.Label(card, text="Grense ubet feil % av arb.ves.het", style="MaterialityKey.TLabel").grid(
            row=10, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Entry(card, textvariable=self.var_trivial_pct, width=14, justify="right").grid(row=10, column=1, sticky="w", pady=(8, 0))

        ttk.Label(card, text="Beregnet resultat", style="MaterialitySection.TLabel").grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        self._add_card_value(card, 12, "Beregnet OM", self.var_calc_om, pady=(8, 0), value_style="MaterialityAmount.TLabel")
        self._add_card_value(card, 13, "Beregnet PM", self.var_calc_pm, value_style="MaterialityAmount.TLabel")
        self._add_card_value(card, 14, "Beregnet ClearlyTriv", self.var_calc_trivial, value_style="MaterialityAmount.TLabel")

        ttk.Label(card, text="Avledede prosenter", style="MaterialitySection.TLabel").grid(
            row=15, column=0, columnspan=2, sticky="w", pady=(10, 0)
        )
        self._add_card_value(card, 16, "Valgt OM i % av benchmark", self.var_calc_om_pct_of_benchmark, pady=(8, 0))
        self._add_card_value(card, 17, "PM i % av valgt OM", self.var_calc_pm_pct_of_om)
        self._add_card_value(card, 18, "ClearlyTriv i % av PM", self.var_calc_trivial_pct_of_pm)

        self.btn_save_calc = ttk.Button(
            card,
            text="Lagre beregning som aktiv",
            style="Primary.TButton",
            width=22,
            command=self._save_local_calculation,
        )
        self.btn_save_calc.grid(row=19, column=0, columnspan=2, sticky="w", pady=(14, 0))
        return card

    def _build_active_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = ttk.LabelFrame(parent, text="Aktiv dokumentasjon", style="MaterialityGroup.TLabelframe", padding=(12, 10))
        card.columnconfigure(1, weight=1)
        card.columnconfigure(3, weight=1)
        ttk.Label(
            card,
            text="Dette er verdiene som brukes videre i Utvalg-1 og som eksporteres i arbeidspapiret.",
            style="MaterialitySub.TLabel",
        ).grid(row=0, column=0, columnspan=4, sticky="w")

        self._add_card_value(card, 1, "Kilde", self.var_active_source, pady=(10, 0))
        self._add_card_value(card, 1, "Brukes i Utvalg", self.var_active_threshold, column=2, pady=(10, 0))
        self._add_card_value(card, 2, "Aktiv terskelbeløp", self.var_active_threshold_amount, value_style="MaterialityAmount.TLabel")
        self._add_card_value(card, 2, "Lagret", self.var_active_saved, column=2)
        self._add_card_value(card, 3, "Aktiv OM", self.var_active_om, value_style="MaterialityAmount.TLabel")
        self._add_card_value(card, 3, "Aktiv PM", self.var_active_pm, column=2, value_style="MaterialityAmount.TLabel")
        self._add_card_value(card, 4, "Aktiv ClearlyTriv", self.var_active_trivial, value_style="MaterialityAmount.TLabel")
        return card

    def _selected_threshold_choice_key(self) -> str:
        label = str(self.var_threshold_choice.get() or "").strip()
        key = next((key for key in _SUPPORTED_SELECTION_THRESHOLD_KEYS if SELECTION_THRESHOLD_LABELS[key] == label), "")
        return _supported_threshold_key(key)

    def _sync_threshold_choice_from_state(self) -> None:
        choice_key = _supported_threshold_key((self._state or {}).get("selection_threshold_key"))
        self._threshold_choice_sync_guard = True
        try:
            self.var_threshold_choice.set(SELECTION_THRESHOLD_LABELS[choice_key])
        finally:
            self._threshold_choice_sync_guard = False

    def _on_threshold_choice_selected(self, _event=None) -> None:
        if self._threshold_choice_sync_guard:
            return
        if not self._client or not self._year:
            return

        choice_key = self._selected_threshold_choice_key()
        current_key = normalize_selection_threshold_key((self._state or {}).get("selection_threshold_key"))
        if current_key == choice_key:
            return

        self._state = merge_state(self._client, self._year, {"selection_threshold_key": choice_key})
        self._set_active_materiality(self._state.get("active_materiality"))
        self.var_status.set(f"Utvalg bruker nå {get_selection_threshold_label(choice_key)}.")
        self._notify_utvalg_materiality_updated()

    def _add_card_value(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        value_var: tk.StringVar,
        *,
        column: int = 0,
        span: int = 1,
        pady: tuple[int, int] = (6, 0),
        value_style: str = "MaterialityValue.TLabel",
    ) -> None:
        ttk.Label(parent, text=label, style="MaterialityKey.TLabel").grid(row=row, column=column, sticky="w", pady=pady)
        ttk.Label(parent, textvariable=value_var, style=value_style).grid(
            row=row,
            column=column + 1,
            columnspan=span,
            sticky="w",
            padx=(10, 0),
            pady=pady,
        )

    def refresh_from_session(self, session_module: object = session) -> None:
        self._session = session_module
        self._client = str(getattr(session_module, "client", "") or "").strip()
        self._year = str(getattr(session_module, "year", "") or "").strip()
        self._reload_all()

    def _reload_all(self) -> None:
        if not self._client or not self._year:
            self.var_context.set("Ingen klient lastet")
            self.var_status.set("Last inn klient og år for å jobbe med vesentlighet.")
            self._state = {}
            self._benchmark_amounts = {}
            self.var_crm_path.set("CRMSystem er ikke lest ennå.")
            self.var_crm_client_number.set("")
            self._clear_crm_values()
            self._clear_local_calculation()
            self._set_active_materiality(None)
            self._update_action_states()
            return

        self.var_context.set(f"{self._client} | {self._year}")
        self._state = load_state(self._client, self._year)
        self._sync_threshold_choice_from_state()
        candidates = build_candidate_client_numbers(self._client, str(self._state.get("crm_client_number") or ""))
        crm_client_number = str(self._state.get("crm_client_number") or "").strip() or (candidates[0] if candidates else "")
        self.var_crm_client_number.set(crm_client_number)

        self._benchmark_amounts = build_benchmark_amounts_for_session(self._session)
        self._load_local_calculation_state()
        self._refresh_crm_lookup()
        self._set_active_materiality(self._state.get("active_materiality"))

        if not any(abs(float(v or 0.0)) > 0.0 for v in self._benchmark_amounts.values()):
            self.var_status.set("Fant ikke benchmarkgrunnlag i regnskapsdataene ennå.")
        self._update_action_states()

    def _update_action_states(self) -> None:
        can_export = bool(self._client and self._year)
        can_use_crm = bool(self._crm_lookup is not None and self._crm_lookup.record is not None)
        can_save_calc = self._current_calc_payload() is not None

        self.btn_export.state(["!disabled"] if can_export else ["disabled"])
        self.btn_use_crm.state(["!disabled"] if can_use_crm else ["disabled"])
        self.btn_save_calc.state(["!disabled"] if can_save_calc else ["disabled"])

    def _clear_local_calculation(self) -> None:
        self.var_benchmark.set("")
        self.var_benchmark_amount.set("-")
        self.var_reference_pct_range.set("-")
        self.var_reference_amount_range.set("-")
        self._set_selected_om_value("", autofill=True)
        self.var_pm_pct.set("")
        self.var_trivial_pct.set("")
        self.var_calc_om.set("-")
        self.var_calc_pm.set("-")
        self.var_calc_trivial.set("-")

    def _load_local_calculation_state(self) -> None:
        saved = self._state.get("last_local_calculation")
        saved_calc = saved if isinstance(saved, dict) else None

        benchmark_key = normalize_benchmark_key((saved_calc or {}).get("benchmark_key") or "")
        if benchmark_key not in BENCHMARK_LABELS:
            benchmark_key = normalize_benchmark_key(pick_default_benchmark(self._benchmark_amounts) or "revenue")
        if benchmark_key not in BENCHMARK_LABELS:
            benchmark_key = "revenue"

        default_om_pct, default_pm_pct, default_trivial_pct = get_default_percentages(benchmark_key)
        selected_om = None
        pm_pct = default_pm_pct
        trivial_pct = default_trivial_pct
        self._selected_om_autofill = True

        if saved_calc:
            selected_om = _parse_float(saved_calc.get("overall_materiality"), 0.0) or None
            pm_pct = _parse_float(saved_calc.get("pm_pct"), default_pm_pct)
            trivial_pct = _parse_float(saved_calc.get("trivial_pct"), default_trivial_pct)
            self._selected_om_autofill = selected_om in (None, 0.0)

        if selected_om is None:
            amount = abs(float(self._benchmark_amounts.get(benchmark_key) or 0.0))
            calc = calculate_materiality(
                benchmark_key,
                amount,
                om_pct=default_om_pct,
                pm_pct=pm_pct,
                trivial_pct=trivial_pct,
            )
            selected_om = calc.om if amount > 0 else None

        self.var_benchmark.set(BENCHMARK_LABELS.get(benchmark_key, benchmark_key))
        self._set_selected_om_value(selected_om, autofill=self._selected_om_autofill)
        self.var_pm_pct.set(_fmt_pct(pm_pct))
        self.var_trivial_pct.set(_fmt_pct(trivial_pct))
        self._refresh_calculation()

    def _benchmark_key(self) -> str:
        label = str(self.var_benchmark.get() or "").strip()
        key = self._benchmark_key_by_label.get(label, label)
        key = normalize_benchmark_key(key)
        if key not in BENCHMARK_LABELS:
            key = normalize_benchmark_key(pick_default_benchmark(self._benchmark_amounts) or "revenue")
        return key if key in BENCHMARK_LABELS else "revenue"

    def _set_selected_om_value(self, value: object, *, autofill: bool) -> None:
        self._selected_om_sync_guard = True
        try:
            self.var_selected_om.set(_fmt_amount_input(value))
        finally:
            self._selected_om_sync_guard = False
        self._selected_om_autofill = autofill

    def _format_selected_om_entry(self) -> None:
        value = _parse_float(self.var_selected_om.get(), 0.0)
        if value > 0:
            self._set_selected_om_value(value, autofill=False)
        else:
            self._set_selected_om_value("", autofill=self._selected_om_autofill)
        self._refresh_calculation()

    def _on_selected_om_changed(self) -> None:
        if self._selected_om_sync_guard:
            return
        if str(self.var_selected_om.get() or "").strip():
            self._selected_om_autofill = False
        self._refresh_calculation()

    def _on_benchmark_selected(self) -> None:
        benchmark_key = self._benchmark_key()
        amount = abs(float(self._benchmark_amounts.get(benchmark_key) or 0.0))
        default_om_pct, default_pm_pct, default_trivial_pct = get_default_percentages(benchmark_key)

        if not str(self.var_pm_pct.get() or "").strip():
            self.var_pm_pct.set(_fmt_pct(default_pm_pct))
        if not str(self.var_trivial_pct.get() or "").strip():
            self.var_trivial_pct.set(_fmt_pct(default_trivial_pct))

        current_selected_om = _parse_float(self.var_selected_om.get(), 0.0)
        if amount > 0 and (self._selected_om_autofill or current_selected_om <= 0.0):
            calc = calculate_materiality(
                benchmark_key,
                amount,
                om_pct=default_om_pct,
                pm_pct=_parse_float(self.var_pm_pct.get(), default_pm_pct),
                trivial_pct=_parse_float(self.var_trivial_pct.get(), default_trivial_pct),
            )
            self._set_selected_om_value(calc.om, autofill=True)
        self._refresh_calculation()

    def _refresh_calculation(self) -> None:
        benchmark_key = self._benchmark_key()
        amount = abs(float(self._benchmark_amounts.get(benchmark_key) or 0.0))
        default_om_pct, default_pm_pct, default_trivial_pct = get_default_percentages(benchmark_key)
        pm_pct = _parse_float(self.var_pm_pct.get(), default_pm_pct)
        trivial_pct = _parse_float(self.var_trivial_pct.get(), default_trivial_pct)
        selected_om = _parse_float(self.var_selected_om.get(), 0.0)

        self.var_benchmark_amount.set(_fmt_amount(amount) if amount > 0 else "-")
        if amount > 0:
            calc = calculate_materiality(
                benchmark_key,
                amount,
                om_pct=default_om_pct,
                pm_pct=pm_pct,
                trivial_pct=trivial_pct,
                selected_om=selected_om if selected_om > 0 else None,
            )
            self.var_reference_pct_range.set(f"{calc.reference_pct_low:.1f}% - {calc.reference_pct_high:.1f}%".replace(".", ","))
            self.var_reference_amount_range.set(
                f"{calc.reference_amount_low:,.0f} - {calc.reference_amount_high:,.0f}".replace(",", " ")
            )
            self.var_calc_om.set(_fmt_amount(calc.om))
            self.var_calc_pm.set(_fmt_amount(calc.pm))
            self.var_calc_trivial.set(_fmt_amount(calc.trivial))
            om_pct_text, pm_pct_text, trivial_pct_text = _inverse_pct_texts(calc)
            self.var_calc_om_pct_of_benchmark.set(om_pct_text)
            self.var_calc_pm_pct_of_om.set(pm_pct_text)
            self.var_calc_trivial_pct_of_pm.set(trivial_pct_text)
        else:
            self.var_reference_pct_range.set("-")
            self.var_reference_amount_range.set("-")
            self.var_calc_om.set("-")
            self.var_calc_pm.set("-")
            self.var_calc_trivial.set("-")
            self.var_calc_om_pct_of_benchmark.set("-")
            self.var_calc_pm_pct_of_om.set("-")
            self.var_calc_trivial_pct_of_pm.set("-")
        self._update_action_states()

    def _save_client_number(self) -> None:
        if not self._client or not self._year:
            return

        digits = "".join(ch for ch in str(self.var_crm_client_number.get() or "").strip() if ch.isdigit())
        if not digits:
            candidates = build_candidate_client_numbers(self._client)
            digits = candidates[0] if candidates else ""
        if not digits:
            self.var_status.set("Fant ikke noe klientnummer å lagre for klienten.")
            return

        self.var_crm_client_number.set(digits)
        self._state = merge_state(self._client, self._year, {"crm_client_number": digits})
        self.var_status.set("Lagret klientnummer for CRM-oppslag.")
        self._refresh_crm_lookup()

    def _refresh_crm_lookup(self) -> None:
        self._crm_lookup = None

        if not self._client or not self._year:
            self.var_crm_path.set("CRMSystem er ikke lest ennå.")
            self._clear_crm_values()
            self._update_action_states()
            return

        prefixed_candidates = build_candidate_client_numbers(self._client, self.var_crm_client_number.get())
        name_candidates = suggest_client_numbers_from_name(self._client)
        candidates: list[str] = []
        for candidate in [*prefixed_candidates, *name_candidates]:
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        if not candidates:
            self.var_crm_path.set("Mangler klientnummer for CRM-oppslag.")
            self._clear_crm_values()
            self.var_status.set("Fant ikke noe klientnummer å bruke mot CRMSystem.")
            self._update_action_states()
            return

        self.var_crm_client_number.set(candidates[0])
        self._crm_lookup = load_materiality_from_crm(candidates)
        self.var_crm_path.set(
            str(self._crm_lookup.db_path) if self._crm_lookup.db_path is not None else "CRMSystem er ikke konfigurert."
        )

        record = self._crm_lookup.record
        if record is None:
            self._clear_crm_values()
            self.var_status.set(self._crm_lookup.error or "Fant ingen vesentlighetsverdier for klienten i CRMSystem.")
            self._update_action_states()
            return

        match_text = record.client_number or self._crm_lookup.matched_client_number or "-"
        if self._crm_lookup.matched_client_number and record.client_number and self._crm_lookup.matched_client_number != record.client_number:
            match_text = f"{self._crm_lookup.matched_client_number} -> {record.client_number}"

        self.var_crm_match.set(match_text)
        self.var_crm_year.set(str(record.engagement_year or "-"))
        self.var_crm_materiality.set(_fmt_amount(record.materiality))
        self.var_crm_pmateriality.set(_fmt_amount(record.pmateriality))
        self.var_crm_trivial.set(_fmt_amount(record.clearly_triv))
        self.var_crm_source_updated.set(record.source_updated_at or "-")
        self.var_crm_synced.set(record.last_synced_at_utc or "-")
        if not str(self._state.get("crm_client_number") or "").strip():
            remembered = record.client_number or self._crm_lookup.matched_client_number
            if remembered:
                self._state = merge_state(self._client, self._year, {"crm_client_number": remembered})
                self.var_crm_client_number.set(remembered)
        self.var_status.set("Verdier lest fra CRMSystem.")
        self._update_action_states()

    def _clear_crm_values(self) -> None:
        self.var_crm_match.set("-")
        self.var_crm_year.set("-")
        self.var_crm_materiality.set("-")
        self.var_crm_pmateriality.set("-")
        self.var_crm_trivial.set("-")
        self.var_crm_source_updated.set("-")
        self.var_crm_synced.set("-")

    def _current_calc_payload(self) -> dict[str, Any] | None:
        benchmark_key = self._benchmark_key()
        amount = abs(float(self._benchmark_amounts.get(benchmark_key) or 0.0))
        if amount <= 0.0:
            return None

        default_om_pct, default_pm_pct, default_trivial_pct = get_default_percentages(benchmark_key)
        pm_pct = _parse_float(self.var_pm_pct.get(), default_pm_pct)
        trivial_pct = _parse_float(self.var_trivial_pct.get(), default_trivial_pct)
        selected_om = _parse_float(self.var_selected_om.get(), 0.0)
        calc = calculate_materiality(
            benchmark_key,
            amount,
            om_pct=default_om_pct,
            pm_pct=pm_pct,
            trivial_pct=trivial_pct,
            selected_om=selected_om if selected_om > 0.0 else None,
        )
        return {
            "source": "local_calculation",
            "benchmark_key": calc.benchmark_key,
            "benchmark_label": BENCHMARK_LABELS.get(calc.benchmark_key, calc.benchmark_key),
            "benchmark_amount": calc.benchmark_amount,
            "om_pct": calc.om_pct,
            "pm_pct": calc.pm_pct,
            "trivial_pct": calc.trivial_pct,
            "reference_pct_low": calc.reference_pct_low,
            "reference_pct_high": calc.reference_pct_high,
            "reference_amount_low": calc.reference_amount_low,
            "reference_amount_high": calc.reference_amount_high,
            "overall_materiality": calc.om,
            "performance_materiality": calc.pm,
            "clearly_trivial": calc.trivial,
        }

    def _save_local_calculation(self) -> None:
        payload = self._current_calc_payload()
        if payload is None or not self._client or not self._year:
            self.var_status.set("Kunne ikke lagre beregningen ennå.")
            return

        updates = {
            "crm_client_number": str(self.var_crm_client_number.get() or "").strip(),
            "last_local_calculation": payload,
            "active_materiality": payload,
        }
        self._state = merge_state(self._client, self._year, updates)
        self._set_active_materiality(payload)
        self.var_status.set("Lokal beregning er lagret som aktiv vesentlighet.")
        self._notify_utvalg_materiality_updated()
        self._update_action_states()

    def _adopt_crm_values(self) -> None:
        record = self._crm_lookup.record if self._crm_lookup is not None else None
        if record is None or not self._client or not self._year:
            self.var_status.set("Det finnes ingen CRM-verdier å aktivere.")
            return

        payload = {
            "source": "crmsystem",
            "matched_client_number": self._crm_lookup.matched_client_number,
            "client_number": record.client_number,
            "client_name": record.client_name,
            "engagement_year": record.engagement_year,
            "overall_materiality": round(float(record.materiality or 0.0)) if record.materiality is not None else None,
            "performance_materiality": round(float(record.pmateriality or 0.0)) if record.pmateriality is not None else None,
            "clearly_trivial": round(float(record.clearly_triv or 0.0)) if record.clearly_triv is not None else None,
            "source_updated_at": record.source_updated_at,
            "last_synced_at_utc": record.last_synced_at_utc,
        }
        updates = {
            "crm_client_number": str(self.var_crm_client_number.get() or "").strip(),
            "active_materiality": payload,
        }
        self._state = merge_state(self._client, self._year, updates)
        self._set_active_materiality(payload)
        self.var_status.set("CRMSystem-verdier er lagret som aktiv vesentlighet.")
        self._notify_utvalg_materiality_updated()
        self._update_action_states()

    def _notify_utvalg_materiality_updated(self) -> None:
        try:
            root = self.winfo_toplevel()
        except Exception:
            root = None
        page_utvalg = getattr(root, "page_utvalg", None) if root is not None else None
        refresh = getattr(page_utvalg, "refresh_materiality", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass

    def _set_active_materiality(self, payload: object) -> None:
        threshold_label = get_selection_threshold_label((self._state or {}).get("selection_threshold_key"))
        threshold_amount = "-"
        if not self._client or not self._year:
            threshold_label = "-"
            threshold_amount = "-"

        if isinstance(payload, dict):
            threshold_label, threshold_amount = _resolve_active_threshold_display(
                payload,
                (self._state or {}).get("selection_threshold_key"),
            )

        if not isinstance(payload, dict):
            self.var_active_source.set("-")
            self.var_active_om.set("-")
            self.var_active_pm.set("-")
            self.var_active_trivial.set("-")
            self.var_active_saved.set((self._state or {}).get("updated_at_utc") or "-")
            self.var_active_threshold.set(threshold_label)
            self.var_active_threshold_amount.set(threshold_amount)
            return

        self.var_active_source.set(_source_text(payload))
        self.var_active_om.set(_fmt_amount(payload.get("overall_materiality")))
        self.var_active_pm.set(_fmt_amount(payload.get("performance_materiality")))
        self.var_active_trivial.set(_fmt_amount(payload.get("clearly_trivial")))
        self.var_active_saved.set((self._state or {}).get("updated_at_utc") or "-")
        self.var_active_threshold.set(threshold_label)
        self.var_active_threshold_amount.set(threshold_amount)

    def _export_workpaper(self) -> None:
        if not self._client or not self._year:
            messagebox.showinfo("Vesentlighet", "Last inn klient og år før du eksporterer arbeidspapiret.", parent=self)
            return

        default_dir = materiality_dir(self._client, self._year)
        initialfile = f"Vesentlighetsarbeidspapir {_safe_filename_part(self._client)} {self._year}.xlsx"
        path_str = filedialog.asksaveasfilename(
            title="Eksporter vesentlighetsarbeidspapir",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialdir=str(default_dir),
            initialfile=initialfile,
            parent=self,
        )
        if not path_str:
            return

        try:
            exported = export_materiality_workpaper(
                path_str,
                client=self._client,
                year=self._year,
                active_materiality=self._state.get("active_materiality"),
                selection_threshold_label=get_selection_threshold_label(self._state.get("selection_threshold_key")),
                state_updated_at=str(self._state.get("updated_at_utc") or ""),
                crm_client_number=str(self.var_crm_client_number.get() or "").strip(),
                crm_lookup=self._crm_lookup,
                calculation_payload=self._current_calc_payload(),
                benchmark_amounts=self._benchmark_amounts,
            )
        except Exception as exc:
            self.var_status.set("Kunne ikke eksportere arbeidspapiret.")
            messagebox.showerror("Vesentlighet", f"Kunne ikke eksportere arbeidspapiret.\n\n{exc}", parent=self)
            return

        self.var_status.set(f"Eksporterte arbeidspapir til {Path(exported).name}.")
        messagebox.showinfo("Vesentlighet", f"Arbeidspapiret er eksportert til:\n{exported}", parent=self)

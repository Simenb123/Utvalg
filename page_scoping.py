"""Scoping-fane — vesentlighetsbasert scoping per regnskapslinje.

Viser auto-klassifisering (vesentlig/moderat/ikke vesentlig) basert på
beløp vs PM/SUM-grenser, med mulighet for manuell scoping (inn/ut) og
begrunnelse. Aggregeringskontroll nederst.
"""

from __future__ import annotations

import logging
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Optional

log = logging.getLogger(__name__)


class ScopingPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook) -> None:
        super().__init__(parent, padding=0)
        self.columnconfigure(0, weight=1)
        # Ny layout:
        #   rad 0: OM/PM/SUM + status + Oppdater
        #   rad 1: metric-kort (PL/BS) + Lås + Eksporter
        #   rad 2: filtrene
        #   rad 3: tree  ← vokser
        #   rad 4: input-rad (Ut av scope + Begrunnelse + Revisjonshandling)
        self.rowconfigure(3, weight=1)

        self._client: str | None = None
        self._year: str | None = None
        self._result: Any = None  # ScopingResult

        self.var_status = tk.StringVar(value="Last inn klient for å se scoping.")
        self.var_filter_class = tk.StringVar(value="Alle")
        self.var_filter_type = tk.StringVar(value="Alle")
        self.var_filter_scoping = tk.StringVar(value="Alle")
        self.var_hide_summary = tk.BooleanVar(value=True)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── Top bar: vesentlighetsgrenser ──
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        top.columnconfigure(10, weight=1)

        self._lbl_om = ttk.Label(top, text="OM: —", font=("", 9, "bold"))
        self._lbl_om.grid(row=0, column=0, sticky="w", padx=(0, 16))
        self._lbl_pm = ttk.Label(top, text="PM: —", font=("", 9, "bold"))
        self._lbl_pm.grid(row=0, column=1, sticky="w", padx=(0, 16))
        self._lbl_sum = ttk.Label(top, text="SUM: —", font=("", 9, "bold"))
        self._lbl_sum.grid(row=0, column=2, sticky="w", padx=(0, 16))

        ttk.Label(top, textvariable=self.var_status, foreground="#667085").grid(
            row=0, column=10, sticky="e"
        )
        ttk.Button(top, text="Oppdater", command=self._refresh).grid(
            row=0, column=11, sticky="e", padx=(6, 0)
        )

        # ── Metric-kort: Resultat (PL) + Balanse (BS) + Lås + Eksport ──
        # Flyttet hit fra bunnen — gir brukeren umiddelbar oversikt over
        # scopet-ut totalt per gruppe, med fargekodet OK/ADVARSEL.
        agg = ttk.Frame(self)
        agg.grid(row=1, column=0, sticky="ew", padx=8, pady=(2, 4))
        agg.columnconfigure(2, weight=1)

        self._card_pl_var = tk.StringVar(value="Resultat (PL)\n—")
        self._card_bs_var = tk.StringVar(value="Balanse (BS)\n—")
        self._card_pl = ttk.Label(
            agg, textvariable=self._card_pl_var,
            font=("Segoe UI", 9),
            padding=(10, 6),
            relief="solid", borderwidth=1,
            background="#F5F7FA", foreground="#1F2937",
            justify="left",
        )
        self._card_pl.grid(row=0, column=0, sticky="w")
        self._card_bs = ttk.Label(
            agg, textvariable=self._card_bs_var,
            font=("Segoe UI", 9),
            padding=(10, 6),
            relief="solid", borderwidth=1,
            background="#F5F7FA", foreground="#1F2937",
            justify="left",
        )
        self._card_bs.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self._var_scoping_locked = tk.BooleanVar(value=False)
        self._chk_lock = ttk.Checkbutton(
            agg, text="Lås scoping",
            variable=self._var_scoping_locked,
            command=self._on_lock_toggled,
        )
        self._chk_lock.grid(row=0, column=3, sticky="e", padx=(8, 0))

        ttk.Button(agg, text="Eksporter Excel", command=self._export_excel).grid(
            row=0, column=4, sticky="e", padx=(8, 0),
        )

        # Bakoverkompat-alias brukt av eldre kode/tester
        self._agg_var = tk.StringVar(value="")
        self._agg_label = self._card_pl

        # ── Filters ──
        filt = ttk.Frame(self)
        filt.grid(row=2, column=0, sticky="ew", padx=8, pady=(2, 4))

        ttk.Label(filt, text="Klassifisering:").pack(side="left")
        cb_class = ttk.Combobox(
            filt, textvariable=self.var_filter_class, state="readonly",
            values=["Alle", "Vesentlig", "Moderat", "Ikke vesentlig", "Manuell"], width=14,
        )
        cb_class.pack(side="left", padx=(2, 12))
        cb_class.bind("<<ComboboxSelected>>", lambda _: self._apply_filter())

        ttk.Label(filt, text="Type:").pack(side="left")
        # Radio-bokser (ikke kombiboks) for Type — tre valg: Alle /
        # Resultat (PL) / Balanse (BS). "Resultat" og "Balanse" er
        # internt BS/PL, men vises med tydelige norske labels.
        for label, value in (("Alle", "Alle"), ("Resultat", "PL"), ("Balanse", "BS")):
            ttk.Radiobutton(
                filt, text=label,
                variable=self.var_filter_type, value=value,
                command=self._apply_filter,
            ).pack(side="left", padx=(2, 4))
        ttk.Frame(filt, width=8).pack(side="left")  # liten spacer

        ttk.Label(filt, text="Scoping:").pack(side="left")
        for label in ("Alle", "I scope", "Ut av scope"):
            ttk.Radiobutton(
                filt, text=label,
                variable=self.var_filter_scoping, value=label,
                command=self._apply_filter,
            ).pack(side="left", padx=(2, 4))
        ttk.Frame(filt, width=8).pack(side="left")

        ttk.Checkbutton(
            filt, text="Skjul sumposter", variable=self.var_hide_summary,
            command=self._apply_filter,
        ).pack(side="left", padx=(4, 0))

        # ── Treeview ──
        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 0))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        cols = (
            "regnr", "regnskapslinje", "type", "ub", "ub_fjor", "endring",
            "endring_pct", "pct_pm", "klassifisering", "scoping", "revisjon", "handlinger",
        )
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")

        self._tree.heading("regnr", text="Regnr")
        self._tree.heading("regnskapslinje", text="Regnskapslinje")
        self._tree.heading("type", text="Type")
        self._tree.heading("ub", text="UB")
        self._tree.heading("ub_fjor", text="UB i fjor")
        self._tree.heading("endring", text="Endring")
        self._tree.heading("endring_pct", text="Endring %")
        self._tree.heading("pct_pm", text="% av PM")
        self._tree.heading("klassifisering", text="Klassifisering")
        self._tree.heading("scoping", text="Scoping")
        self._tree.heading("revisjon", text="Revisjonshandling")
        self._tree.heading("handlinger", text="Handl.")

        self._tree.column("regnr", width=50, minwidth=40, anchor="e")
        self._tree.column("regnskapslinje", width=200, minwidth=120)
        self._tree.column("type", width=45, minwidth=35, anchor="center")
        self._tree.column("ub", width=100, minwidth=70, anchor="e")
        self._tree.column("ub_fjor", width=100, minwidth=70, anchor="e")
        self._tree.column("endring", width=100, minwidth=70, anchor="e")
        self._tree.column("endring_pct", width=85, minwidth=60, anchor="e")
        self._tree.column("pct_pm", width=65, minwidth=50, anchor="e")
        self._tree.column("klassifisering", width=100, minwidth=80, anchor="center")
        self._tree.column("scoping", width=70, minwidth=50, anchor="center")
        self._tree.column("revisjon", width=160, minwidth=80)
        self._tree.column("handlinger", width=50, minwidth=40, anchor="center")
        self._tree.configure(
            displaycolumns=(
                "regnr",
                "regnskapslinje",
                "type",
                "ub",
                "pct_pm",
                "klassifisering",
                "scoping",
                "revisjon",
                "handlinger",
            )
        )

        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=yscroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Button-3>", self._on_right_click)
        self._tree.bind("<Control-a>", self._select_all)
        self._tree.bind("<Control-A>", self._select_all)
        self._tree.bind("<Delete>", self._on_key_remove_scoping)
        self._tree.bind("<BackSpace>", self._on_key_remove_scoping)
        self._tree.bind("<u>", self._on_key_scope_ut)
        self._tree.bind("<U>", self._on_key_scope_ut)
        self._tree.bind("<Escape>", self._on_escape)
        self._tree.bind("<Control-e>", lambda _: self._export_excel())
        self._tree.bind("<Control-E>", lambda _: self._export_excel())

        # Sortering via kolonneheader
        try:
            from ui_treeview_sort import enable_treeview_sorting
            enable_treeview_sorting(self._tree)
        except Exception:
            pass

        # Tagging for fargekoding
        self._tree.tag_configure("vesentlig", background="#fde8e8")
        self._tree.tag_configure("moderat", background="#fef3c7")
        self._tree.tag_configure("ikke_vesentlig", background="#d1fae5")
        self._tree.tag_configure("manuell", background="#dbeafe")
        self._tree.tag_configure("summary", foreground="#9ca3af")
        self._tree.tag_configure("stripe", background="#f8f9fa")

        # ── Input-rad for valgt linje: Ut av scope + Begrunnelse + Revisjonshandling ──
        # Den tidligere "Detaljer"-LabelFramen med duplikat tekst-info
        # er fjernet — radgrid-visningen over inneholder alt brukeren
        # trenger. Kun inputfeltene for manuell overstyring beholdes i
        # en flat rad under treet.
        scope_frame = ttk.Frame(self, padding=(8, 4))
        scope_frame.grid(row=4, column=0, sticky="ew", padx=8, pady=(2, 2))

        # Stringvar-alias for bakoverkompat (tester/oppdaterings­funksjoner
        # som tidligere skrev til _detail_var).
        self._detail_var = tk.StringVar(value="")
        self._detail_label = None  # fjernet; beholder attributt for kompat

        self._scope_var = tk.BooleanVar(value=False)
        self._chk_scope_ut = ttk.Checkbutton(
            scope_frame, text="Ut av scope", variable=self._scope_var,
            command=self._on_scope_changed,
        )
        self._chk_scope_ut.pack(side="left", padx=(0, 12))

        ttk.Label(scope_frame, text="Begrunnelse:").pack(side="left")
        self._rationale_var = tk.StringVar(value="")
        self._ent_rationale = ttk.Entry(scope_frame, textvariable=self._rationale_var, width=30)
        self._ent_rationale.pack(side="left", padx=(2, 12))
        self._ent_rationale.bind("<FocusOut>", self._on_rationale_changed)
        self._ent_rationale.bind("<Return>", self._on_rationale_changed)

        ttk.Label(scope_frame, text="Revisjonshandling:").pack(side="left")
        self._audit_action_var = tk.StringVar(value="")
        self._ent_audit_action = ttk.Entry(scope_frame, textvariable=self._audit_action_var, width=30)
        self._ent_audit_action.pack(side="left", padx=(2, 6))
        self._ent_audit_action.bind("<FocusOut>", self._on_audit_action_changed)
        self._ent_audit_action.bind("<Return>", self._on_audit_action_changed)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def on_client_changed(self, client: str | None, year: str | None) -> None:
        self._client = client
        self._year = year
        self._refresh()

    def _refresh(self) -> None:
        if not self._client or not self._year:
            self._result = None
            self._tree.delete(*self._tree.get_children())
            self.var_status.set("Last inn klient for å se scoping.")
            self._detail_var.set("")
            self._agg_var.set("")
            self._lbl_om.configure(text="OM: —")
            self._lbl_pm.configure(text="PM: —")
            self._lbl_sum.configure(text="SUM: —")
            return

        self.var_status.set("Beregner scoping ...")
        self.update_idletasks()

        try:
            result = self._build_scoping_data()
        except Exception as exc:
            log.warning("Scoping feilet: %s", exc, exc_info=True)
            self.var_status.set(f"Feil: {exc}")
            return

        self._result = result

        # Oppdater vesentlighetsvisning
        self._lbl_om.configure(text=f"OM: {_fmt(result.om)}")
        self._lbl_pm.configure(text=f"PM: {_fmt(result.pm)}")
        self._lbl_sum.configure(text=f"SUM: {_fmt(result.sum_threshold)}")

        self._configure_tree_columns()
        self._apply_filter()
        self._update_aggregation()

        non_sum = [l for l in result.lines if not l.is_summary]
        n = len(non_sum)
        vesentlige = sum(1 for l in non_sum if l.classification == "vesentlig")
        self.var_status.set(f"{n} regnskapslinjer — {vesentlige} vesentlige")

    def _build_scoping_data(self) -> Any:
        """Samle data fra eksisterende moduler og kjør scoping-motor."""
        import session as _session
        from page_analyse_rl import build_rl_pivot, load_rl_config, load_sb_for_session

        import materiality_store
        import previous_year_comparison
        import regnskap_client_overrides as _rco
        from scoping_engine import build_scoping

        # Regnskapslinjer og mapping
        intervals, regnskapslinjer = load_rl_config()
        if intervals is None or regnskapslinjer is None:
            from scoping_engine import ScopingResult
            return ScopingResult()

        # HB-data fra session
        df_hb = getattr(_session, "dataset", None)

        # SB-data
        sb_df = load_sb_for_session()
        sb_prev_df = previous_year_comparison.load_previous_year_sb(self._client, self._year)

        account_overrides = {}
        prior_year_overrides = None
        try:
            account_overrides = _rco.load_account_overrides(self._client, self._year)
        except Exception:
            account_overrides = {}
        try:
            prior_year_overrides = _rco.load_prior_year_overrides(self._client, self._year)
        except Exception:
            prior_year_overrides = None

        # Bygg RL-pivot
        rl_pivot = build_rl_pivot(
            df_hb, intervals, regnskapslinjer,
            sb_df=sb_df,
            sb_prev_df=sb_prev_df,
            account_overrides=account_overrides,
            prior_year_overrides=prior_year_overrides,
        )

        # Vesentlighet
        materiality = materiality_store.load_state(self._client, self._year)

        # CRM-handlinger (valgfritt)
        action_counts = self._load_action_counts(rl_pivot)

        # IB/UB-avvik (valgfritt)
        ib_ub_avvik = self._load_ib_ub_avvik(df_hb, sb_df, intervals)

        # Manuelle overstyringer
        import scoping_store
        overrides = scoping_store.load_overrides(self._client, self._year)

        # Beregn auto-scope-ut-forslag fra scoping-motoren. Brukes for
        # linjer uten manuell override. Hoppes over hvis scoping er
        # låst — da holdes forrige resultat uendret.
        auto_suggestions: dict[str, str] = {}
        if not self._is_scoping_locked():
            # Bygg foreløpig ScopingLine-liste for auto-algoritmen.
            # Vi kaller build_scoping én gang uten auto_suggestions for
            # å få ordentlig line_type (PL/BS) + is_summary-klassifisering,
            # deretter beregner vi auto og kjører build_scoping en gang
            # til med auto. Det er to kall men de er billige på ren logikk.
            from scoping_engine import compute_auto_scope_out

            preliminary = build_scoping(
                rl_pivot, materiality,
                action_counts=action_counts,
                ib_ub_avvik=ib_ub_avvik,
                overrides=overrides,
            )
            auto_suggestions = compute_auto_scope_out(
                preliminary.lines,
                pm=preliminary.pm,
            )

        return build_scoping(
            rl_pivot, materiality,
            action_counts=action_counts,
            ib_ub_avvik=ib_ub_avvik,
            overrides=overrides,
            auto_suggestions=auto_suggestions,
        )

    def _is_scoping_locked(self) -> bool:
        """Returnerer True hvis bruker har låst scoping for aktuell klient/år."""
        if not self._client or not self._year:
            return False
        try:
            import preferences
            key = f"scoping.locked.{self._client}.{self._year}"
            return bool(preferences.get(key, False))
        except Exception:
            return False

    def _set_scoping_locked(self, locked: bool) -> None:
        if not self._client or not self._year:
            return
        try:
            import preferences
            key = f"scoping.locked.{self._client}.{self._year}"
            preferences.set(key, bool(locked))
        except Exception:
            pass

    def _resolve_year_int(self) -> int | None:
        try:
            return int(self._year) if self._year is not None else None
        except (TypeError, ValueError):
            return None

    def _has_previous_year_data(self) -> bool:
        if not self._result:
            return False
        return any(line.amount_prior is not None for line in self._result.lines)

    def _configure_tree_columns(self) -> None:
        year = self._resolve_year_int()
        ub_label = f"UB {year}" if year is not None else "UB"
        ub_fjor_label = f"UB {year - 1}" if year is not None else "UB i fjor"

        self._tree.heading("ub", text=ub_label)
        self._tree.heading("ub_fjor", text=ub_fjor_label)
        self._tree.heading("endring", text="Endring")
        self._tree.heading("endring_pct", text="Endring %")

        if self._has_previous_year_data():
            self._tree.configure(
                displaycolumns=(
                    "regnr",
                    "regnskapslinje",
                    "type",
                    "ub",
                    "ub_fjor",
                    "endring",
                    "endring_pct",
                    "pct_pm",
                    "klassifisering",
                    "scoping",
                    "revisjon",
                    "handlinger",
                )
            )
        else:
            self._tree.configure(
                displaycolumns=(
                    "regnr",
                    "regnskapslinje",
                    "type",
                    "ub",
                    "pct_pm",
                    "klassifisering",
                    "scoping",
                    "revisjon",
                    "handlinger",
                )
            )

    def _display_column_id(self, column_name: str) -> str | None:
        display = self._tree.cget("displaycolumns")
        if display == "#all":
            columns = list(self._tree["columns"])
        else:
            columns = list(display)
        try:
            idx = columns.index(column_name)
        except ValueError:
            return None
        return f"#{idx + 1}"

    def _load_action_counts(self, rl_pivot) -> dict[str, int]:
        """Hent antall CRM-handlinger per regnr."""
        try:
            from crmsystem_action_matching import (
                RegnskapslinjeInfo,
                group_by_regnskapslinje,
                match_actions_to_regnskapslinjer,
            )
            from crmsystem_actions import load_audit_actions
            from regnskap_config import load_regnskapslinjer

            result = load_audit_actions(self._client, self._year)
            if result.error or not result.actions:
                return {}

            df = load_regnskapslinjer()
            rl_list = [
                RegnskapslinjeInfo(nr=str(row["nr"]).strip(), regnskapslinje=str(row["regnskapslinje"]).strip())
                for _, row in df.iterrows()
            ]
            matches = match_actions_to_regnskapslinjer(result.actions, rl_list)
            groups = group_by_regnskapslinje(matches)
            return {regnr: len(items) for regnr, items in groups.items() if regnr}
        except Exception:
            return {}

    def _load_ib_ub_avvik(self, df_hb, sb_df, intervals) -> set[str]:
        """Finn regnr med IB/UB-avvik."""
        try:
            from ib_ub_control import build_account_reconciliation, build_rl_reconciliation
            from regnskap_config import load_regnskapslinjer

            if sb_df is None or df_hb is None:
                return set()

            acct_recon = build_account_reconciliation(sb_df, df_hb, "Konto", "Beløp")
            regnskapslinjer = load_regnskapslinjer()
            rl_recon = build_rl_reconciliation(acct_recon, intervals, regnskapslinjer)
            if rl_recon is None or rl_recon.empty:
                return set()

            avvik = rl_recon.loc[rl_recon.get("har_avvik", False) == True]
            return {str(int(r)) for r in avvik["regnr"].dropna()}
        except Exception:
            return set()

    # ------------------------------------------------------------------
    # Filter / display
    # ------------------------------------------------------------------

    def _apply_filter(self) -> None:
        self._tree.delete(*self._tree.get_children())
        if not self._result:
            return

        class_filter = self.var_filter_class.get()
        type_filter = self.var_filter_type.get()
        scoping_filter = self.var_filter_scoping.get()

        class_map = {
            "Vesentlig": "vesentlig",
            "Moderat": "moderat",
            "Ikke vesentlig": "ikke_vesentlig",
            "Manuell": "manuell",
        }

        class_labels = {
            "vesentlig": "Vesentlig",
            "moderat": "Moderat",
            "ikke_vesentlig": "Ikke vesentlig",
            "manuell": "Manuell",
        }

        hide_summary = self.var_hide_summary.get()
        row_idx = 0

        for line in self._result.lines:
            if line.is_summary and hide_summary:
                continue
            if not line.is_summary:
                if class_filter != "Alle" and line.classification != class_map.get(class_filter, ""):
                    continue
                if type_filter != "Alle" and line.line_type != type_filter:
                    continue
                if scoping_filter == "Ut av scope" and line.scoping != "ut":
                    continue
                if scoping_filter == "I scope" and line.scoping == "ut":
                    continue
            else:
                if type_filter != "Alle" and line.line_type != type_filter:
                    continue

            if line.is_summary:
                tags = ("summary",)
            else:
                cls_tag = line.classification if line.classification in ("vesentlig", "moderat", "ikke_vesentlig", "manuell") else ""
                tags = (cls_tag, "stripe") if (row_idx % 2 == 1 and not cls_tag) else (cls_tag,) if cls_tag else ("stripe",) if row_idx % 2 == 1 else ()

            self._tree.insert("", "end", iid=line.regnr, values=(
                line.regnr,
                line.regnskapslinje,
                line.line_type,
                _fmt(line.amount),
                _fmt_optional(line.amount_prior),
                _fmt_optional(line.change_amount),
                _fmt_pct(line.change_pct),
                "" if line.is_summary else f"{line.pct_of_pm:.0f}%",
                class_labels.get(line.classification, ""),
                "Ut" if line.scoping == "ut" else "",
                line.audit_action if not line.is_summary else "",
                str(line.action_count) if line.action_count else "",
            ), tags=tags)
            row_idx += 1

    def _on_select(self, _event: tk.Event | None = None) -> None:
        sel = self._tree.selection()
        if not sel or not self._result:
            self._detail_var.set("")
            self._scope_var.set(False)
            self._rationale_var.set("")
            self._audit_action_var.set("")
            return

        # Multi-select: vis oppsummering, deaktiver enkelt-redigering
        if len(sel) > 1:
            selected_lines = [l for l in self._result.lines if l.regnr in sel and not l.is_summary]
            n_ut = sum(1 for l in selected_lines if l.scoping == "ut")
            total = sum(abs(l.amount) for l in selected_lines)
            self._detail_var.set(
                f"{len(selected_lines)} linjer valgt  |  "
                f"Sum beløp: {_fmt(total)}  |  Ut av scope: {n_ut}\n"
                f"Høyreklikk for å scope ut / fjerne fra ut."
            )
            self._scope_var.set(False)
            self._rationale_var.set("")
            self._audit_action_var.set("")
            self._chk_scope_ut.configure(state="disabled")
            self._ent_rationale.configure(state="disabled")
            self._ent_audit_action.configure(state="disabled")
            return

        regnr = sel[0]
        line = next((l for l in self._result.lines if l.regnr == regnr), None)
        if not line:
            return

        lines = [f"{line.regnr} {line.regnskapslinje}  ({line.line_type})"]

        if line.is_summary:
            lines.append(_detail_amount_line(self._resolve_year_int(), line))
            lines.append("(sumpost - ikke del av scoping)")
            self._detail_var.set("\n".join(lines))
            self._scope_var.set(False)
            self._rationale_var.set("")
            self._audit_action_var.set("")
            self._chk_scope_ut.configure(state="disabled")
            self._ent_rationale.configure(state="disabled")
            self._ent_audit_action.configure(state="disabled")
            return

        lines.append(_detail_amount_line(self._resolve_year_int(), line))

        auto_label = {"vesentlig": "Vesentlig", "moderat": "Moderat", "ikke_vesentlig": "Ikke vesentlig"}.get(line.auto_classification, "")
        curr_label = {"vesentlig": "Vesentlig", "moderat": "Moderat", "ikke_vesentlig": "Ikke vesentlig", "manuell": "Manuell"}.get(line.classification, "")
        if line.classification != line.auto_classification:
            lines.append(f"Klassifisering: {curr_label} (manuelt overstyrt, auto: {auto_label})")
        else:
            lines.append(f"Klassifisering: {curr_label} (auto)")

        lines.append(f"% av PM: {line.pct_of_pm:.1f}%")

        if line.action_count:
            lines.append(f"CRM-handlinger: {line.action_count}")
        if line.has_ib_ub_avvik:
            lines.append("IB/UB-kontroll: AVVIK")
        else:
            lines.append("IB/UB-kontroll: OK")

        self._detail_var.set("\n".join(lines))

        # Oppdater scoping-kontroller
        self._chk_scope_ut.configure(state="normal")
        self._ent_rationale.configure(state="normal")
        self._ent_audit_action.configure(state="normal")
        self._scope_var.set(line.scoping == "ut")
        self._rationale_var.set(line.rationale)
        self._audit_action_var.set(line.audit_action)

    def _on_double_click(self, event: tk.Event) -> None:
        """Dobbeltklikk på scoping-kolonne → toggle ut/i scope."""
        region = self._tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self._tree.identify_column(event.x)
        scoping_col = self._display_column_id("scoping")
        if col != scoping_col:
            return

        sel = self._tree.selection()
        if not sel or not self._result:
            return

        # Multiselect double-click: toggle all selected
        for regnr in sel:
            line = next((l for l in self._result.lines if l.regnr == regnr), None)
            if not line or line.is_summary:
                continue
            new_scoping = "" if line.scoping == "ut" else "ut"
            self._save_scoping_silent(regnr, scoping=new_scoping)

        self._apply_filter()
        self._update_aggregation()
        # Re-select
        for regnr in sel:
            if self._tree.exists(regnr):
                self._tree.selection_add(regnr)
        self._on_select()

    def _on_scope_changed(self) -> None:
        sel = self._tree.selection()
        if not sel or not self._result:
            return
        new_scoping = "ut" if self._scope_var.get() else ""
        for regnr in sel:
            line = next((l for l in self._result.lines if l.regnr == regnr), None)
            if not line or line.is_summary:
                continue
            self._save_scoping_silent(regnr, scoping=new_scoping)
        self._apply_filter()
        self._update_aggregation()
        for regnr in sel:
            if self._tree.exists(regnr):
                self._tree.selection_add(regnr)
        self._on_select()

    def _on_rationale_changed(self, _event: tk.Event | None = None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        regnr = sel[0]
        self._save_scoping(regnr, rationale=self._rationale_var.get())

    def _on_audit_action_changed(self, _event: tk.Event | None = None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        regnr = sel[0]
        self._save_scoping(regnr, audit_action=self._audit_action_var.get())

    def _save_scoping_silent(self, regnr: str, *, scoping: str | None = None, rationale: str | None = None, audit_action: str | None = None) -> None:
        """Lagre scoping-endring uten å oppdatere UI (for batch-operasjoner)."""
        if not self._client or not self._year:
            return
        try:
            import scoping_store
            scoping_store.update_line(
                self._client, self._year, regnr,
                scoping=scoping, rationale=rationale, audit_action=audit_action,
            )
        except Exception as exc:
            log.warning("Feil ved lagring av scoping: %s", exc)
            return
        if self._result:
            line = next((l for l in self._result.lines if l.regnr == regnr), None)
            if line:
                if scoping is not None:
                    line.scoping = scoping
                if rationale is not None:
                    line.rationale = rationale
                if audit_action is not None:
                    line.audit_action = audit_action

    def _save_scoping(self, regnr: str, *, scoping: str | None = None, rationale: str | None = None, audit_action: str | None = None) -> None:
        """Lagre scoping-endring og oppdater visningen."""
        self._save_scoping_silent(regnr, scoping=scoping, rationale=rationale, audit_action=audit_action)
        self._apply_filter()
        self._update_aggregation()
        if self._tree.exists(regnr):
            self._tree.selection_set(regnr)
            self._on_select()

    # ------------------------------------------------------------------
    # Right-click menu
    # ------------------------------------------------------------------

    def _on_right_click(self, event: tk.Event) -> None:
        if not self._result:
            return

        # Legg til klikket rad i seleksjon om den ikke allerede er valgt
        item = self._tree.identify_row(event.y)
        if item and item not in self._tree.selection():
            self._tree.selection_set(item)
            self._on_select()

        sel = self._tree.selection()
        menu = tk.Menu(self, tearoff=0)

        # Valgte linjer (ekskluder sumposter)
        selected_lines = [
            l for l in self._result.lines if l.regnr in sel and not l.is_summary
        ]

        if selected_lines:
            n = len(selected_lines)
            label_suffix = f" ({n} linjer)" if n > 1 else ""
            menu.add_command(
                label=f"Scope ut{label_suffix}",
                command=lambda: self._set_selected_scoping("ut"),
            )
            menu.add_command(
                label=f"Fjern fra ut{label_suffix}",
                command=lambda: self._set_selected_scoping(""),
            )
            menu.add_separator()

        # Bulk actions
        menu.add_command(
            label="Scope ut alle ikke-vesentlige",
            command=self._bulk_set_ikke_vesentlig_ut,
        )
        menu.add_separator()
        menu.add_command(
            label="Nullstill all scoping",
            command=self._bulk_reset_scoping,
        )

        menu.tk_popup(event.x_root, event.y_root)

    def _set_selected_scoping(self, scoping: str) -> None:
        """Sett scoping for alle valgte (ikke-sum) linjer."""
        sel = self._tree.selection()
        if not sel or not self._result or not self._client or not self._year:
            return
        for regnr in sel:
            line = next((l for l in self._result.lines if l.regnr == regnr), None)
            if not line or line.is_summary:
                continue
            self._save_scoping_silent(regnr, scoping=scoping)
        self._apply_filter()
        self._update_aggregation()
        for regnr in sel:
            if self._tree.exists(regnr):
                self._tree.selection_add(regnr)
        self._on_select()

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def _select_all(self, _event: tk.Event | None = None) -> str:
        """Ctrl+A — velg alle synlige rader."""
        all_items = self._tree.get_children()
        if all_items:
            self._tree.selection_set(all_items)
            self._on_select()
        return "break"

    def _on_key_scope_ut(self, _event: tk.Event | None = None) -> str:
        """U — scope ut valgte linjer."""
        self._set_selected_scoping("ut")
        return "break"

    def _on_key_remove_scoping(self, _event: tk.Event | None = None) -> str:
        """Delete/Backspace — fjern scoping fra valgte linjer."""
        self._set_selected_scoping("")
        return "break"

    def _on_escape(self, _event: tk.Event | None = None) -> str:
        """Escape — fjern seleksjon."""
        self._tree.selection_remove(*self._tree.selection())
        self._on_select()
        return "break"

    def _bulk_set_ikke_vesentlig_ut(self) -> None:
        if not self._result or not self._client or not self._year:
            return
        for line in self._result.lines:
            if line.is_summary:
                continue
            if line.classification == "ikke_vesentlig":
                self._save_scoping_silent(line.regnr, scoping="ut")
        self._apply_filter()
        self._update_aggregation()

    def _bulk_reset_scoping(self) -> None:
        if not self._result or not self._client or not self._year:
            return
        if not messagebox.askyesno("Nullstill", "Nullstille all scoping for denne klienten?"):
            return
        import scoping_store
        overrides = scoping_store.load_overrides(self._client, self._year)
        for line in self._result.lines:
            if line.is_summary:
                continue
            line.scoping = ""
            entry = overrides.get(line.regnr, {})
            entry.pop("scoping", None)
            if not entry:
                overrides.pop(line.regnr, None)
            else:
                overrides[line.regnr] = entry
        scoping_store.save_overrides(self._client, self._year, overrides)
        self._apply_filter()
        self._update_aggregation()

    # ------------------------------------------------------------------
    # Excel export
    # ------------------------------------------------------------------

    def _export_excel(self) -> None:
        if not self._result:
            messagebox.showinfo("Eksport", "Ingen scoping-data å eksportere.")
            return

        client = self._client or ""
        year = self._year or ""
        safe_client = "".join(
            ch if ch.isalnum() or ch in {" ", "_", "-"} else "_" for ch in client
        ).strip()
        base_name = f"Scoping {safe_client} {year}".strip()

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Eksporter scoping-arbeidspapir",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
            initialfile=base_name + ".xlsx",
        )
        if not path:
            return

        try:
            from scoping_export import export_scoping
            export_scoping(
                self._result, path,
                client_name=client, year=year,
            )
        except Exception as exc:
            log.error("Scoping-eksport feilet: %s", exc, exc_info=True)
            messagebox.showerror("Eksport", f"Feil ved eksport: {exc}")
            return

        # Åpne filen
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f"open '{path}'")
            else:
                os.system(f"xdg-open '{path}' >/dev/null 2>&1 &")
        except Exception:
            pass

    def _update_aggregation(self) -> None:
        # Synk lås-sjekkboks med lagret tilstand (gjøres her så det skjer
        # ved hver refresh, uten at sjekkboks-klikket trigger loop).
        try:
            self._var_scoping_locked.set(self._is_scoping_locked())
        except Exception:
            pass

        if not self._result:
            self._card_pl_var.set("Resultat (PL)\n—")
            self._card_bs_var.set("Balanse (BS)\n—")
            self._set_card_status(self._card_pl, None)
            self._set_card_status(self._card_bs, None)
            return

        from scoping_engine import scoped_out_totals_by_group
        totals = scoped_out_totals_by_group(self._result.lines)
        pm = self._result.pm

        non_sum = [l for l in self._result.lines if not l.is_summary]
        n_ut = sum(1 for l in non_sum if l.scoping == "ut")
        n_in = len(non_sum) - n_ut

        # PL-kort
        pl_out = totals.get("PL", 0.0)
        pl_pct = round(pl_out / pm * 100, 1) if pm > 0 else 0
        pl_ok = pm <= 0 or pl_out <= pm
        pl_n = sum(1 for l in non_sum if (l.line_type or "").upper() == "PL" and l.scoping == "ut")
        pl_text = (
            f"Resultat (PL)          {n_label(pl_n)}\n"
            f"Scopet ut: {_fmt(pl_out)}  av PM {_fmt(pm) if pm > 0 else '—'}"
            + (f"  ({pl_pct}%)" if pm > 0 else "")
        )
        self._card_pl_var.set(pl_text)
        self._set_card_status(self._card_pl, pl_ok if pm > 0 else None)

        # BS-kort
        bs_out = totals.get("BS", 0.0)
        bs_pct = round(bs_out / pm * 100, 1) if pm > 0 else 0
        bs_ok = pm <= 0 or bs_out <= pm
        bs_n = sum(1 for l in non_sum if (l.line_type or "").upper() == "BS" and l.scoping == "ut")
        bs_text = (
            f"Balanse (BS)           {n_label(bs_n)}\n"
            f"Scopet ut: {_fmt(bs_out)}  av PM {_fmt(pm) if pm > 0 else '—'}"
            + (f"  ({bs_pct}%)" if pm > 0 else "")
        )
        self._card_bs_var.set(bs_text)
        self._set_card_status(self._card_bs, bs_ok if pm > 0 else None)

        # Bakoverkompat: behold _agg_var for evt. lesere
        total_out = pl_out + bs_out
        self._agg_var.set(
            f"PL: {_fmt(pl_out)} / PM {_fmt(pm)}  |  "
            f"BS: {_fmt(bs_out)} / PM {_fmt(pm)}  |  "
            f"I scope: {n_in}  Ut: {n_ut}  Total ut: {_fmt(total_out)}"
        )

    def _set_card_status(self, card: ttk.Label, ok: bool | None) -> None:
        """Fargelegg metric-kortet basert på om det er OK, advarsel eller nøytralt."""
        try:
            if ok is None:
                card.configure(background="#F5F7FA", foreground="#1F2937")
            elif ok:
                card.configure(background="#E6F4EA", foreground="#065F46")
            else:
                card.configure(background="#FDECEA", foreground="#9F1A1A")
        except Exception:
            pass

    def _on_lock_toggled(self) -> None:
        locked = bool(self._var_scoping_locked.get())
        self._set_scoping_locked(locked)
        self._refresh()


def n_label(n: int) -> str:
    """Formater antall som 'n linje(r)' for metric-kortene."""
    return f"{n} linje{'r' if n != 1 else ''}"


def _fmt(value: float) -> str:
    """Formater tall med tusenskilletegn."""
    if abs(value) < 0.5:
        return "0"
    return f"{value:,.0f}".replace(",", " ")


def _fmt_optional(value: float | None) -> str:
    if value is None:
        return ""
    return _fmt(value)


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:+.1f}%"


def _detail_amount_line(year: int | None, line: Any) -> str:
    ub_label = f"UB {year}" if year is not None else "UB"
    if line.amount_prior is None:
        return f"{ub_label}: {_fmt(line.amount)}"

    ub_fjor_label = f"UB {year - 1}" if year is not None else "UB i fjor"
    endring_txt = _fmt_optional(line.change_amount)
    endring_pct_txt = _fmt_pct(line.change_pct)
    suffix = f"   Endring %: {endring_pct_txt}" if endring_pct_txt else ""
    return (
        f"{ub_label}: {_fmt(line.amount)}   "
        f"{ub_fjor_label}: {_fmt_optional(line.amount_prior)}   "
        f"Endring: {endring_txt}{suffix}"
    )

from __future__ import annotations

from typing import Any, Callable

import pandas as pd

import src.shared.regnskap.config as regnskap_config
import regnskapslinje_suggest

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore

from page_admin_helpers import (
    _clean_text,
    _int_list,
    _multiline_text,
    _normalize_regnskapslinje_rulebook_document,
    _saved_status_text,
    _string_list,
)
from page_admin_rl_models import (
    LINJETYPE_SUMPOST,
    LINJETYPE_VANLIG,
    RL_FILTER_ALLE,
    RL_FILTER_MED_FIN,
    RL_FILTER_SUMPOST,
    RL_FILTER_UTEN_FIN,
    RL_FILTER_VALUES,
    RL_FILTER_VANLIG,
    RLBaselineRow,
    _LINJETYPE_VALUES,
    _format_baseline_source_line,
    _format_kontointervall_text,
    _format_overlay_source_line,
    _format_sumtilknytning_text,
    _parse_kontointervall_text,
    _raw_cell_text,
    _rl_row_matches_filter,
    build_rl_baseline_rows,
)


class _RegnskapslinjeEditor(ttk.Frame):  # type: ignore[misc]
    TREE_COLUMNS: tuple[str, ...] = (
        "Regnr",
        "Regnskapslinje",
        "Linjetype",
        "Kontointervall",
        "Hierarki",
        "Finjustering",
    )

    def __init__(
        self,
        master: Any,
        *,
        title: str,
        loader: Callable[[], tuple[Any, str]],
        saver: Callable[[Any], str],
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._title = title
        self._loader = loader
        self._saver = saver
        self._on_saved = on_saved
        self._document: dict[str, Any] = {"rules": {}}
        self._baseline_doc = regnskap_config.RLBaselineDocument()
        self._baseline_by_regnr: dict[str, regnskap_config.RLBaselineLine] = {}
        self._intervals_by_regnr: dict[str, list[tuple[int, int]]] = {}
        self._selected_regnr = ""
        # Selection-guard: når True skal _handle_tree_select ignorere event-et.
        # Brukes rundt programmatisk selection_set/focus/see slik at rebuild og
        # reselection ikke trigger kaskader av TreeviewSelect-behandling.
        self._suspend_tree_select: bool = False
        # Sideeffekt fra _commit_form: True hvis den nettopp commitede raden
        # endret verdier som vises i treet (eller fikk nytt regnr).
        self._last_commit_changed_row: bool = False
        self._baseline_path_var = tk.StringVar(value="") if tk is not None else None
        self._overlay_path_var = tk.StringVar(value="") if tk is not None else None
        self._search_var = tk.StringVar(value="") if tk is not None else None
        self._filter_var = tk.StringVar(value=RL_FILTER_ALLE) if tk is not None else None
        self._status_var = tk.StringVar(value="") if tk is not None else None
        # Baseline vars (editable)
        self._regnr_var = tk.StringVar(value="") if tk is not None else None
        self._line_var = tk.StringVar(value="") if tk is not None else None
        self._linjetype_var = tk.StringVar(value=LINJETYPE_VANLIG) if tk is not None else None
        self._baseline_rb_var = tk.StringVar(value="") if tk is not None else None
        self._baseline_formel_var = tk.StringVar(value="") if tk is not None else None
        self._baseline_delsumnr_var = tk.StringVar(value="") if tk is not None else None
        self._baseline_sumnr_var = tk.StringVar(value="") if tk is not None else None
        self._baseline_sumnr2_var = tk.StringVar(value="") if tk is not None else None
        self._baseline_sluttsumnr_var = tk.StringVar(value="") if tk is not None else None
        # Baseline vars (read-only, derived)
        self._baseline_hierarki_var = tk.StringVar(value="") if tk is not None else None
        # Overlay vars (editable)
        self._balance_hint_var = tk.StringVar(value=regnskapslinje_suggest.NORMAL_BALANCE_AUTO) if tk is not None else None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        btn_row = ttk.Frame(self, padding=(8, 8, 8, 4))
        btn_row.grid(row=0, column=0, sticky="e")
        ttk.Button(btn_row, text="Ny linje", command=self._handle_new_line).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Ny sumpost", command=self._handle_new_sumpost).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Slett valgt", command=self._handle_delete_selected).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="Nullstill valgt", command=self.clear_selected_rule).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Last på nytt", command=self.reload).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Lagre", command=self.save).pack(side="left")

        ttk.Label(
            self,
            textvariable=self._status_var,
            style="Muted.TLabel",
            padding=(8, 0, 8, 4),
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=2, column=0, sticky="nsew")

        list_host = ttk.Frame(body, padding=(8, 0, 4, 8))
        list_host.columnconfigure(0, weight=1)
        list_host.rowconfigure(1, weight=1)
        body.add(list_host, weight=4)

        search_row = ttk.Frame(list_host)
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="Søk:").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(search_row, textvariable=self._search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Label(search_row, text="Filter:").grid(row=0, column=2, sticky="w")
        filter_combo = ttk.Combobox(
            search_row,
            textvariable=self._filter_var,
            values=RL_FILTER_VALUES,
            state="readonly",
            width=20,
        )
        filter_combo.grid(row=0, column=3, sticky="w", padx=(6, 0))
        try:
            search_entry.bind("<KeyRelease>", lambda _event: self._refresh_tree(), add="+")
        except Exception:
            pass
        try:
            filter_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_tree(), add="+")
        except Exception:
            pass

        tree = ttk.Treeview(list_host, columns=self.TREE_COLUMNS, show="headings", selectmode="browse")
        tree.grid(row=1, column=0, sticky="nsew")
        self._tree = tree
        for column, width, anchor in (
            ("Regnr", 70, "w"),
            ("Regnskapslinje", 240, "w"),
            ("Linjetype", 100, "w"),
            ("Kontointervall", 150, "w"),
            ("Hierarki", 260, "w"),
            ("Finjustering", 90, "w"),
        ):
            tree.heading(column, text=column)
            tree.column(column, width=width, anchor=anchor)
        try:
            tree.tag_configure(
                "sumpost",
                font=("TkDefaultFont", 0, "bold"),
                background="#eaf1fb",
                foreground="#1f3b66",
            )
        except Exception:
            pass
        y_scroll = ttk.Scrollbar(list_host, orient="vertical", command=tree.yview)
        y_scroll.grid(row=1, column=1, sticky="ns")
        tree.configure(yscrollcommand=y_scroll.set)
        try:
            tree.bind("<<TreeviewSelect>>", lambda _event: self._handle_tree_select(), add="+")
        except Exception:
            pass

        detail_host = ttk.Frame(body, padding=(4, 0, 8, 8))
        detail_host.columnconfigure(0, weight=1)
        body.add(detail_host, weight=3)

        baseline_frame = ttk.LabelFrame(detail_host, text="Felles baseline", padding=(8, 6, 8, 8))
        baseline_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        baseline_frame.columnconfigure(1, weight=1)

        row_idx = 0
        top_row = ttk.Frame(baseline_frame)
        top_row.grid(row=row_idx, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(top_row, text="Regnr").pack(side="left", padx=(0, 6))
        ttk.Entry(top_row, textvariable=self._regnr_var, width=10).pack(side="left", padx=(0, 16))
        ttk.Label(top_row, text="Linjetype", style="Section.TLabel").pack(side="left", padx=(0, 6))
        self._linjetype_combo = ttk.Combobox(
            top_row,
            textvariable=self._linjetype_var,
            values=_LINJETYPE_VALUES,
            state="readonly",
            width=16,
        )
        self._linjetype_combo.pack(side="left")
        try:
            self._linjetype_combo.bind(
                "<<ComboboxSelected>>", lambda _event: self._apply_linjetype_toggle(), add="+"
            )
        except Exception:
            pass
        row_idx += 1
        line_row = ttk.Frame(baseline_frame)
        line_row.grid(row=row_idx, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        line_row.columnconfigure(1, weight=3)
        line_row.columnconfigure(3, weight=1)
        ttk.Label(line_row, text="Regnskapslinje").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(line_row, textvariable=self._line_var).grid(row=0, column=1, sticky="ew", padx=(0, 12))
        ttk.Label(line_row, text="Resultat/Balanse").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(line_row, textvariable=self._baseline_rb_var).grid(row=0, column=3, sticky="ew")
        row_idx += 1
        ttk.Label(baseline_frame, text="Formel").grid(row=row_idx, column=0, sticky="w", padx=(0, 6), pady=(0, 2))
        self._formel_entry = ttk.Entry(baseline_frame, textvariable=self._baseline_formel_var)
        self._formel_entry.grid(row=row_idx, column=1, sticky="ew", pady=(0, 2))
        row_idx += 1

        ttk.Label(baseline_frame, text="Kontointervall").grid(row=row_idx, column=0, sticky="nw", padx=(0, 6), pady=(0, 2))
        self._intervall_text = tk.Text(baseline_frame, height=3, wrap="none", undo=True)
        self._intervall_text.grid(row=row_idx, column=1, sticky="ew", pady=(0, 2))
        row_idx += 1

        hierarki_header = ttk.Frame(baseline_frame)
        hierarki_header.grid(row=row_idx, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        ttk.Label(hierarki_header, text="Hierarki", style="Section.TLabel").pack(side="left")
        row_idx += 1
        hierarki_row = ttk.Frame(baseline_frame)
        hierarki_row.grid(row=row_idx, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        for label, variable in (
            ("DelsumNr", self._baseline_delsumnr_var),
            ("SumNr", self._baseline_sumnr_var),
            ("SumNr2", self._baseline_sumnr2_var),
            ("SluttsumNr", self._baseline_sluttsumnr_var),
        ):
            ttk.Label(hierarki_row, text=label).pack(side="left", padx=(0, 4))
            ttk.Entry(hierarki_row, textvariable=variable, width=8).pack(side="left", padx=(0, 12))
        row_idx += 1

        ttk.Label(baseline_frame, text="Hierarki (avledet)").grid(
            row=row_idx, column=0, sticky="w", padx=(0, 6), pady=(6, 2)
        )
        ttk.Entry(
            baseline_frame, textvariable=self._baseline_hierarki_var, state="readonly"
        ).grid(row=row_idx, column=1, sticky="ew", pady=(6, 2))

        overlay_frame = ttk.LabelFrame(detail_host, text="Finjustering", padding=(8, 6, 8, 8))
        overlay_frame.grid(row=1, column=0, sticky="nsew")
        overlay_frame.columnconfigure(1, weight=1)
        detail_host.rowconfigure(1, weight=1)

        balance_row = ttk.Frame(overlay_frame)
        balance_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(balance_row, text="Fortegn-hint").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            balance_row,
            textvariable=self._balance_hint_var,
            values=(
                regnskapslinje_suggest.NORMAL_BALANCE_AUTO,
                regnskapslinje_suggest.NORMAL_BALANCE_DEBET,
                regnskapslinje_suggest.NORMAL_BALANCE_KREDIT,
                regnskapslinje_suggest.NORMAL_BALANCE_NEUTRAL,
            ),
            state="readonly",
            width=18,
        ).grid(row=0, column=1, sticky="w", padx=(6, 0))

        ttk.Label(overlay_frame, text="Aliaser").grid(row=1, column=0, sticky="w")
        ttk.Label(overlay_frame, text="én verdi per linje", style="Muted.TLabel").grid(row=1, column=1, sticky="e")
        self._aliases_text = tk.Text(overlay_frame, height=8, wrap="word", undo=True)
        self._aliases_text.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(overlay_frame, text="Ekskluder aliaser").grid(row=3, column=0, sticky="w")
        self._exclude_text = tk.Text(overlay_frame, height=4, wrap="word", undo=True)
        self._exclude_text.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(overlay_frame, text="Brukssignaler").grid(row=5, column=0, sticky="w")
        self._usage_text = tk.Text(overlay_frame, height=4, wrap="word", undo=True)
        self._usage_text.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        ttk.Label(overlay_frame, text="Finjustering-kontointervall").grid(row=7, column=0, sticky="w")
        self._ranges_text = tk.Text(overlay_frame, height=4, wrap="word", undo=True)
        self._ranges_text.grid(row=8, column=0, columnspan=2, sticky="nsew", pady=(0, 8))

        overlay_frame.rowconfigure(2, weight=3)
        overlay_frame.rowconfigure(4, weight=1)
        overlay_frame.rowconfigure(6, weight=1)
        overlay_frame.rowconfigure(8, weight=2)

        self.reload()

    # --- tekst/widget-hjelpere -------------------------------------------------

    def _set_text_widget(self, widget: Any, value: str) -> None:
        try:
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
        except Exception:
            return

    def _get_text_widget(self, widget: Any) -> str:
        try:
            return widget.get("1.0", "end").strip()
        except Exception:
            return ""

    def _rules(self) -> dict[str, dict[str, Any]]:
        rules = self._document.get("rules", {})
        if isinstance(rules, dict):
            return rules
        self._document["rules"] = {}
        return self._document["rules"]

    # --- baseline-state --------------------------------------------------------

    def _rebuild_baseline_lookups(self) -> None:
        self._baseline_by_regnr = {line.regnr: line for line in self._baseline_doc.lines}
        intervals_by_regnr: dict[str, list[tuple[int, int]]] = {}
        for iv in self._baseline_doc.intervals:
            intervals_by_regnr.setdefault(iv.regnr, []).append((int(iv.fra), int(iv.til)))
        for key in intervals_by_regnr:
            intervals_by_regnr[key].sort()
        self._intervals_by_regnr = intervals_by_regnr

    def _hierarki_text(self, line: regnskap_config.RLBaselineLine | None) -> str:
        if line is None:
            return ""
        chain: list[str] = []
        for nr in (line.delsumnr, line.sumnr, line.sumnr2, line.sluttsumnr):
            nr_text = _clean_text(nr)
            if not nr_text:
                continue
            ref = self._baseline_by_regnr.get(nr_text)
            label = ref.regnskapslinje if ref else ""
            chain.append(f"{nr_text} {label}".strip() if label else nr_text)
        return " → ".join(chain)

    # --- form <-> state --------------------------------------------------------

    def _current_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        aliases = _string_list(self._get_text_widget(self._aliases_text))
        if aliases:
            payload["aliases"] = aliases
        exclude_aliases = _string_list(self._get_text_widget(self._exclude_text))
        if exclude_aliases:
            payload["exclude_aliases"] = exclude_aliases
        usage_keywords = _string_list(self._get_text_widget(self._usage_text))
        if usage_keywords:
            payload["usage_keywords"] = usage_keywords
        account_ranges = _string_list(self._get_text_widget(self._ranges_text))
        if account_ranges:
            payload["account_ranges"] = account_ranges
        balance_hint = _clean_text(self._balance_hint_var.get() if self._balance_hint_var is not None else "")
        if balance_hint and balance_hint != regnskapslinje_suggest.NORMAL_BALANCE_AUTO:
            payload["normal_balance_hint"] = balance_hint
        line_name = _clean_text(self._line_var.get() if self._line_var is not None else "")
        if line_name:
            payload["label"] = line_name
        return payload

    def _load_form(self, regnr: str) -> None:
        payload = self._rules().get(regnr, {})
        baseline = self._baseline_by_regnr.get(regnr)
        if self._regnr_var is not None:
            self._regnr_var.set(regnr)
        if self._line_var is not None:
            self._line_var.set(baseline.regnskapslinje if baseline else "")
        if self._linjetype_var is not None:
            self._linjetype_var.set(
                LINJETYPE_SUMPOST if (baseline and baseline.sumpost) else LINJETYPE_VANLIG
            )
        if self._baseline_rb_var is not None:
            self._baseline_rb_var.set(baseline.resultat_balanse if baseline else "")
        if self._baseline_formel_var is not None:
            self._baseline_formel_var.set(baseline.formel if baseline else "")
        if self._baseline_delsumnr_var is not None:
            self._baseline_delsumnr_var.set(baseline.delsumnr if baseline else "")
        if self._baseline_sumnr_var is not None:
            self._baseline_sumnr_var.set(baseline.sumnr if baseline else "")
        if self._baseline_sumnr2_var is not None:
            self._baseline_sumnr2_var.set(baseline.sumnr2 if baseline else "")
        if self._baseline_sluttsumnr_var is not None:
            self._baseline_sluttsumnr_var.set(baseline.sluttsumnr if baseline else "")
        intervals = self._intervals_by_regnr.get(regnr, [])
        self._set_text_widget(
            self._intervall_text,
            "\n".join(
                (f"{fra}-{til}" if fra != til else str(fra)) for fra, til in intervals
            ),
        )
        if self._baseline_hierarki_var is not None:
            self._baseline_hierarki_var.set(self._hierarki_text(baseline))
        if self._balance_hint_var is not None:
            self._balance_hint_var.set(
                _clean_text(payload.get("normal_balance_hint")) or regnskapslinje_suggest.NORMAL_BALANCE_AUTO
            )
        self._set_text_widget(self._aliases_text, _multiline_text(payload.get("aliases")))
        self._set_text_widget(self._exclude_text, _multiline_text(payload.get("exclude_aliases")))
        self._set_text_widget(self._usage_text, _multiline_text(payload.get("usage_keywords")))
        self._set_text_widget(self._ranges_text, _multiline_text(payload.get("account_ranges")))
        self._apply_linjetype_toggle()
        if self._status_var is not None:
            self._status_var.set(
                "Rediger baseline og finjustering, og trykk Lagre når du er ferdig."
            )

    def _clear_form(self) -> None:
        for var in (
            self._regnr_var,
            self._line_var,
            self._baseline_rb_var,
            self._baseline_formel_var,
            self._baseline_delsumnr_var,
            self._baseline_sumnr_var,
            self._baseline_sumnr2_var,
            self._baseline_sluttsumnr_var,
            self._baseline_hierarki_var,
        ):
            if var is not None:
                var.set("")
        if self._linjetype_var is not None:
            self._linjetype_var.set(LINJETYPE_VANLIG)
        if self._balance_hint_var is not None:
            self._balance_hint_var.set(regnskapslinje_suggest.NORMAL_BALANCE_AUTO)
        for widget in (
            self._intervall_text,
            self._aliases_text,
            self._exclude_text,
            self._usage_text,
            self._ranges_text,
        ):
            self._set_text_widget(widget, "")
        self._apply_linjetype_toggle()

    def _apply_linjetype_toggle(self) -> None:
        """Aktiver/deaktiver Formel og Kontointervall basert på linjetype.

        Sumpost: Formel er aktiv, Kontointervall er deaktivert.
        Vanlig linje: Kontointervall er aktiv, Formel er deaktivert.
        """

        is_sumpost = (
            self._linjetype_var is not None
            and _clean_text(self._linjetype_var.get()) == LINJETYPE_SUMPOST
        )
        try:
            self._formel_entry.configure(state=("normal" if is_sumpost else "disabled"))
        except Exception:
            pass
        try:
            self._intervall_text.configure(state=("disabled" if is_sumpost else "normal"))
        except Exception:
            pass

    # --- commit / migrasjon ----------------------------------------------------

    def _commit_form(self, *, show_errors: bool) -> bool:
        """Lagre formfeltene inn i baseline- og overlay-state. Returnerer False ved feil.

        Som sideeffekt settes ``self._last_commit_changed_row`` til True hvis
        commit faktisk endret verdier som vises i treet (eller migrerte regnr).
        Kallere kan bruke det for å avgjøre om en full `_refresh_tree` er
        nødvendig, eller om det holder å bytte selection + `_load_form`.
        """

        self._last_commit_changed_row = False
        prev_regnr = _clean_text(self._selected_regnr)
        if not prev_regnr:
            return True
        if prev_regnr not in self._baseline_by_regnr:
            return True

        new_regnr = _clean_text(self._regnr_var.get() if self._regnr_var is not None else prev_regnr)
        if not new_regnr:
            if show_errors and messagebox is not None:
                messagebox.showerror(self._title, "Regnr kan ikke være tomt.")
            return False
        try:
            new_regnr = str(int(new_regnr))
        except ValueError:
            if show_errors and messagebox is not None:
                messagebox.showerror(self._title, f"Regnr må være et tall: '{new_regnr}'.")
            return False

        line_name = _clean_text(self._line_var.get() if self._line_var is not None else "")
        if not line_name:
            if show_errors and messagebox is not None:
                messagebox.showerror(self._title, "Regnskapslinje er påkrevd.")
            return False

        is_sumpost = (
            self._linjetype_var is not None
            and _clean_text(self._linjetype_var.get()) == LINJETYPE_SUMPOST
        )

        # Parse kontointervall; sumposter kan ikke ha kontointervall
        raw_intervall_text = self._get_text_widget(self._intervall_text)
        parsed_intervals, parse_errors = _parse_kontointervall_text(raw_intervall_text)
        if parse_errors:
            if show_errors and messagebox is not None:
                messagebox.showerror(
                    self._title,
                    "Kontointervall har ugyldige verdier: " + ", ".join(parse_errors),
                )
            return False
        if is_sumpost and parsed_intervals:
            if show_errors and messagebox is not None:
                messagebox.showerror(
                    self._title,
                    "Sumpost kan ikke ha kontointervall. Fjern intervallene eller endre linjetype.",
                )
            return False

        # Hvis regnr endres: sjekk at nytt regnr ikke allerede finnes
        if new_regnr != prev_regnr and new_regnr in self._baseline_by_regnr:
            if show_errors and messagebox is not None:
                messagebox.showerror(
                    self._title, f"Regnr {new_regnr} finnes fra før — velg et annet."
                )
            return False

        # Snapshot av rad-verdier FØR mutasjon, for å kunne se om en full
        # tree-rebuild faktisk er nødvendig.
        before_values = self._compute_tree_row_values(self._baseline_by_regnr[prev_regnr])

        # Oppdater baseline-linjen
        line = self._baseline_by_regnr[prev_regnr]
        line.regnr = new_regnr
        line.regnskapslinje = line_name
        line.sumpost = is_sumpost
        line.resultat_balanse = _clean_text(self._baseline_rb_var.get() if self._baseline_rb_var is not None else "")
        line.formel = _clean_text(self._baseline_formel_var.get() if self._baseline_formel_var is not None else "") if is_sumpost else ""
        line.delsumnr = _clean_text(self._baseline_delsumnr_var.get() if self._baseline_delsumnr_var is not None else "")
        line.sumnr = _clean_text(self._baseline_sumnr_var.get() if self._baseline_sumnr_var is not None else "")
        line.sumnr2 = _clean_text(self._baseline_sumnr2_var.get() if self._baseline_sumnr2_var is not None else "")
        line.sluttsumnr = _clean_text(self._baseline_sluttsumnr_var.get() if self._baseline_sluttsumnr_var is not None else "")

        # Migrasjon: hvis regnr endret, flytt intervaller + overlay
        if new_regnr != prev_regnr:
            for iv in self._baseline_doc.intervals:
                if iv.regnr == prev_regnr:
                    iv.regnr = new_regnr
            # flytt også hierarki-referanser i andre linjer
            for other in self._baseline_doc.lines:
                if other is line:
                    continue
                if other.delsumnr == prev_regnr:
                    other.delsumnr = new_regnr
                if other.sumnr == prev_regnr:
                    other.sumnr = new_regnr
                if other.sumnr2 == prev_regnr:
                    other.sumnr2 = new_regnr
                if other.sluttsumnr == prev_regnr:
                    other.sluttsumnr = new_regnr
            rules = self._rules()
            if prev_regnr in rules:
                rules[new_regnr] = rules.pop(prev_regnr)
            self._selected_regnr = new_regnr

        # Erstatt intervaller for denne linjen med det som er i formfeltet
        self._baseline_doc.intervals = [
            iv for iv in self._baseline_doc.intervals if iv.regnr != line.regnr
        ]
        if not is_sumpost:
            for fra, til in parsed_intervals:
                self._baseline_doc.intervals.append(
                    regnskap_config.RLBaselineInterval(fra=fra, til=til, regnr=line.regnr)
                )

        # Overlay for denne regnr
        payload = self._current_payload()
        rules = self._rules()
        if payload:
            rules[line.regnr] = payload
        else:
            rules.pop(line.regnr, None)

        self._rebuild_baseline_lookups()

        # Avgjør om commit krever full tree-rebuild. Regnr-migrasjon påvirker
        # både denne raden og hierarki-kolonnen på andre rader.
        if new_regnr != prev_regnr:
            self._last_commit_changed_row = True
        else:
            after_line = self._baseline_by_regnr.get(line.regnr)
            if after_line is None:
                self._last_commit_changed_row = True
            else:
                after_values = self._compute_tree_row_values(after_line)
                self._last_commit_changed_row = before_values != after_values
        return True

    # --- tree ------------------------------------------------------------------

    def _select_tree_item(self, regnr: str | None) -> None:
        """Sett selection programmatisk uten å trigge _handle_tree_select."""

        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        previous = self._suspend_tree_select
        self._suspend_tree_select = True
        try:
            if not regnr:
                try:
                    tree.selection_set(())
                except Exception:
                    pass
                return
            if not tree.exists(regnr):
                return
            try:
                tree.selection_set(regnr)
                tree.focus(regnr)
                tree.see(regnr)
            except Exception:
                pass
        finally:
            self._suspend_tree_select = previous

    def _compute_tree_row_values(
        self, line: regnskap_config.RLBaselineLine
    ) -> tuple[str, ...]:
        has_overlay = line.regnr in self._rules()
        linjetype_text = LINJETYPE_SUMPOST if line.sumpost else LINJETYPE_VANLIG
        intervall_text = _format_kontointervall_text(
            self._intervals_by_regnr.get(line.regnr, [])
        )
        hierarki_text = self._hierarki_text(line)
        finjustering_text = "Ja" if has_overlay else ""
        return (
            line.regnr,
            line.regnskapslinje,
            linjetype_text,
            intervall_text,
            hierarki_text,
            finjustering_text,
        )

    def _refresh_tree(self, *, preserve_selection: str | None = None) -> None:
        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        if preserve_selection is not None:
            target = _clean_text(preserve_selection)
        else:
            target = _clean_text(self._selected_regnr)
        search_text = _clean_text(self._search_var.get() if self._search_var is not None else "").casefold()
        filter_mode = _clean_text(self._filter_var.get() if self._filter_var is not None else RL_FILTER_ALLE) or RL_FILTER_ALLE
        previous_guard = self._suspend_tree_select
        self._suspend_tree_select = True
        try:
            try:
                for item in tree.get_children(""):
                    tree.delete(item)
            except Exception:
                pass
            rules = self._rules()
            for line in self._baseline_doc.lines:
                has_overlay = line.regnr in rules
                if not _rl_row_matches_filter(
                    sumpost=line.sumpost, has_overlay=has_overlay, mode=filter_mode
                ):
                    continue
                values = self._compute_tree_row_values(line)
                haystack = " ".join(str(v) for v in values).casefold()
                if search_text and search_text not in haystack:
                    continue
                tags = ("sumpost",) if line.sumpost else ()
                try:
                    tree.insert("", "end", iid=line.regnr, values=values, tags=tags)
                except Exception:
                    continue
        finally:
            self._suspend_tree_select = previous_guard
        if target and tree.exists(target):
            self._selected_regnr = target
            self._select_tree_item(target)

    def _handle_tree_select(self) -> None:
        if self._suspend_tree_select:
            return
        tree = getattr(self, "_tree", None)
        if tree is None:
            return
        try:
            selection = list(tree.selection())
        except Exception:
            selection = []
        if not selection:
            return
        next_key = _clean_text(selection[0])
        if next_key == self._selected_regnr:
            return
        if not self._commit_form(show_errors=True):
            # Revert til forrige valg uten å trigge ny handling
            if self._selected_regnr:
                self._select_tree_item(self._selected_regnr)
            return
        changed = self._last_commit_changed_row
        # Oppdater state FØR evt. rebuild, slik at programmatisk reselection
        # ikke triggrer ny runde med _handle_tree_select.
        self._selected_regnr = next_key
        if changed:
            self._refresh_tree(preserve_selection=next_key)
        self._load_form(next_key)

    # --- handlinger ------------------------------------------------------------

    def _next_regnr(self) -> str:
        used: set[int] = set()
        for line in self._baseline_doc.lines:
            try:
                used.add(int(line.regnr))
            except Exception:
                pass
        nxt = (max(used) if used else 0) + 10
        while nxt in used:
            nxt += 1
        return str(nxt)

    def _add_line(self, *, sumpost: bool) -> None:
        if not self._commit_form(show_errors=True):
            return
        regnr = self._next_regnr()
        line = regnskap_config.RLBaselineLine(
            regnr=regnr,
            regnskapslinje="",
            sumpost=sumpost,
        )
        self._baseline_doc.lines.append(line)
        self._rebuild_baseline_lookups()
        self._selected_regnr = regnr
        self._refresh_tree(preserve_selection=regnr)
        self._load_form(regnr)
        if self._status_var is not None:
            kind = "sumpost" if sumpost else "vanlig linje"
            self._status_var.set(
                f"Ny {kind} lagt til (regnr {regnr}). Fyll inn Regnskapslinje og lagre."
            )

    def _handle_new_line(self) -> None:
        self._add_line(sumpost=False)

    def _handle_new_sumpost(self) -> None:
        self._add_line(sumpost=True)

    def _handle_delete_selected(self) -> None:
        regnr = _clean_text(self._selected_regnr)
        if not regnr or regnr not in self._baseline_by_regnr:
            return
        referents = [
            other.regnr
            for other in self._baseline_doc.lines
            if other.regnr != regnr
            and regnr in {other.delsumnr, other.sumnr, other.sumnr2, other.sluttsumnr}
        ]
        if referents:
            if messagebox is not None:
                messagebox.showerror(
                    self._title,
                    "Kan ikke slette linjen: den er referert fra hierarkiet i regnr "
                    + ", ".join(referents)
                    + ".",
                )
            return
        if messagebox is not None:
            if not messagebox.askyesno(
                self._title,
                f"Slette regnskapslinje {regnr}? Dette fjerner også tilhørende kontointervaller og finjustering.",
            ):
                return
        self._baseline_doc.lines = [l for l in self._baseline_doc.lines if l.regnr != regnr]
        self._baseline_doc.intervals = [iv for iv in self._baseline_doc.intervals if iv.regnr != regnr]
        self._rules().pop(regnr, None)
        self._rebuild_baseline_lookups()
        self._selected_regnr = ""
        self._clear_form()
        self._refresh_tree()
        tree = getattr(self, "_tree", None)
        children = tree.get_children("") if tree is not None else ()
        if children:
            first = str(children[0])
            self._selected_regnr = first
            self._select_tree_item(first)
            self._load_form(first)
        if self._status_var is not None:
            self._status_var.set(f"Regnskapslinje {regnr} er slettet.")

    def clear_selected_rule(self) -> None:
        selected = _clean_text(self._selected_regnr)
        if not selected:
            return
        self._rules().pop(selected, None)
        self._load_form(selected)
        self._refresh_tree()

    # --- validering ------------------------------------------------------------

    def _validate_document(self) -> list[str]:
        errors: list[str] = []
        seen: dict[str, int] = {}
        for line in self._baseline_doc.lines:
            if not _clean_text(line.regnr):
                errors.append("En linje mangler regnr.")
                continue
            try:
                int(line.regnr)
            except ValueError:
                errors.append(f"Regnr må være et tall: '{line.regnr}'.")
            seen[line.regnr] = seen.get(line.regnr, 0) + 1
            if not _clean_text(line.regnskapslinje):
                errors.append(f"Regnskapslinje mangler for regnr {line.regnr}.")
        for regnr, count in seen.items():
            if count > 1:
                errors.append(f"Regnr {regnr} forekommer {count} ganger.")
        regnr_set = {line.regnr for line in self._baseline_doc.lines}
        for line in self._baseline_doc.lines:
            for label, ref in (
                ("DelsumNr", line.delsumnr),
                ("SumNr", line.sumnr),
                ("SumNr2", line.sumnr2),
                ("SluttsumNr", line.sluttsumnr),
            ):
                ref = _clean_text(ref)
                if not ref:
                    continue
                if ref not in regnr_set:
                    errors.append(
                        f"{label} {ref} på regnr {line.regnr} peker ikke til en eksisterende linje."
                    )
        return errors

    # --- kilde-labels + lifecycle ---------------------------------------------

    def _refresh_path_vars(self, overlay_path_text: str) -> None:
        try:
            status = regnskap_config.get_status()
        except Exception:
            status = None
        if self._baseline_path_var is not None:
            self._baseline_path_var.set(_format_baseline_source_line(status))
        if self._overlay_path_var is not None:
            self._overlay_path_var.set(_format_overlay_source_line(overlay_path_text))

    def reload(self) -> None:
        document, path_text = self._loader()
        self._document = _normalize_regnskapslinje_rulebook_document(document)
        try:
            self._baseline_doc = regnskap_config.load_rl_baseline_document()
        except Exception:
            self._baseline_doc = regnskap_config.RLBaselineDocument()
        self._rebuild_baseline_lookups()
        self._refresh_path_vars(path_text)
        self._selected_regnr = ""
        self._clear_form()
        self._refresh_tree()
        tree = getattr(self, "_tree", None)
        children = tree.get_children("") if tree is not None else ()
        if children:
            first = str(children[0])
            self._selected_regnr = first
            self._load_form(first)
            self._select_tree_item(first)
        elif self._status_var is not None:
            self._status_var.set(
                "Fant ingen felles mapping. Kontroller regnskapslinjer og kontoplanmapping i datamappen."
            )

    def save(self) -> None:
        if not self._commit_form(show_errors=True):
            return
        errors = self._validate_document()
        if errors:
            if messagebox is not None:
                messagebox.showerror(self._title, "Kan ikke lagre:\n" + "\n".join(errors))
            return
        try:
            regnskap_config.save_rl_baseline_document(self._baseline_doc)
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror(self._title, f"Kunne ikke lagre baseline: {exc}")
            return
        try:
            saved_path = self._saver(_normalize_regnskapslinje_rulebook_document(self._document))
        except Exception as exc:
            if messagebox is not None:
                messagebox.showerror(self._title, f"Kunne ikke lagre finjustering: {exc}")
            return
        self._refresh_path_vars(saved_path)
        self.reload()
        if self._status_var is not None:
            self._status_var.set(_saved_status_text(saved_path))
        if self._on_saved is not None:
            self._on_saved()

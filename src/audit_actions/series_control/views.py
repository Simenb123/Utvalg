from __future__ import annotations

import bisect
from typing import Any, Iterable, Sequence

import pandas as pd
import tkinter as tk
from tkinter import ttk

from . import AUTO_FIELD_KEY, analyze_series, list_series_field_options


def _unique_nonempty(values: Iterable[object]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
    return out


def _compact_join(values: Iterable[object], *, limit: int = 4) -> str:
    uniq = _unique_nonempty(values)
    if not uniq:
        return ""
    if len(uniq) <= limit:
        return ", ".join(uniq)
    remaining = len(uniq) - limit
    return ", ".join(uniq[:limit]) + f" (+{remaining})"


def _period_text(values: Iterable[object]) -> str:
    dates = pd.to_datetime(pd.Series(list(values)), errors="coerce").dropna().sort_values()
    if dates.empty:
        return ""
    first = dates.iloc[0].strftime("%Y-%m-%d")
    last = dates.iloc[-1].strftime("%Y-%m-%d")
    return first if first == last else f"{first} - {last}"


def _map_regnskapslinje_labels(values: Iterable[object], konto_regnskapslinje_map: dict[str, str] | None) -> str:
    if not konto_regnskapslinje_map:
        return ""
    labels = []
    for value in values:
        konto = str(value or "").strip()
        if not konto:
            continue
        label = str(konto_regnskapslinje_map.get(konto, "") or "").strip()
        if label:
            labels.append(label)
    return _compact_join(labels)


def build_nr_series_scope_text(
    *,
    scope_mode: str,
    scope_items: Sequence[str] | None,
    selected_accounts: Sequence[str] | None,
    df_scope: pd.DataFrame | None,
) -> str:
    scope_kind = "regnskapslinjer" if str(scope_mode or "").strip().lower().startswith("regn") else "kontoer"
    scope_value = _compact_join(scope_items or selected_accounts or ())
    scope_txt = scope_value if scope_value else "ingen eksplisitt avgrensning"
    row_count = len(df_scope.index) if isinstance(df_scope, pd.DataFrame) else 0
    account_count = len(_unique_nonempty(selected_accounts or ()))
    return f"Scope ({scope_kind}): {scope_txt} | Kontoer: {account_count} | Linjer i scope: {row_count}"


def build_nr_series_scope_context_df(
    *,
    scope_rows_df: pd.DataFrame,
    df_scope: pd.DataFrame,
    family_key: str,
    konto_regnskapslinje_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    if (
        not isinstance(scope_rows_df, pd.DataFrame)
        or scope_rows_df.empty
        or not isinstance(df_scope, pd.DataFrame)
        or df_scope.empty
    ):
        return pd.DataFrame(columns=["number", "raw_value", "Bilag", "Dato", "Konto", "Regnskapslinje", "Tekst"])

    base = df_scope.reset_index().rename(columns={"index": "row_index"})
    merged = scope_rows_df.merge(base, on="row_index", how="left", suffixes=("", "_src"))
    if family_key:
        merged = merged.loc[merged["family_key"] == family_key].copy()
    if merged.empty:
        return pd.DataFrame(columns=["number", "raw_value", "Bilag", "Dato", "Konto", "Regnskapslinje", "Tekst"])

    for col in ("Bilag", "Konto", "Tekst"):
        if col not in merged.columns:
            merged[col] = ""
        merged[col] = merged[col].fillna("").astype(str)

    if "Dato" not in merged.columns:
        merged["Dato"] = pd.NaT
    else:
        merged["Dato"] = pd.to_datetime(merged["Dato"], errors="coerce")
    merged["Regnskapslinje"] = merged["Konto"].map(
        lambda konto: str((konto_regnskapslinje_map or {}).get(str(konto).strip(), "") or "").strip()
    )
    return merged.sort_values(["number", "Dato", "Bilag"], kind="mergesort", ignore_index=True)


def build_nr_series_gap_overview(
    gaps_df: pd.DataFrame,
    hits_df: pd.DataFrame,
    *,
    scope_context_df: pd.DataFrame | None = None,
    konto_regnskapslinje_map: dict[str, str] | None = None,
    only_with_hits: bool = False,
) -> pd.DataFrame:
    base = (
        gaps_df[["number"]]
        .drop_duplicates()
        .rename(columns={"number": "Nummer"})
        .sort_values("Nummer", kind="mergesort")
        .reset_index(drop=True)
        if isinstance(gaps_df, pd.DataFrame) and not gaps_df.empty
        else pd.DataFrame(columns=["Nummer"])
    )
    if base.empty:
        return pd.DataFrame(
            columns=[
                "Nummer",
                "Status",
                "Treff i HB",
                "Regnskapslinjer",
                "Kontoer",
                "Periode",
                "Forrige i scope",
                "Neste i scope",
            ]
        )

    if not isinstance(hits_df, pd.DataFrame) or hits_df.empty or "gap_number" not in hits_df.columns:
        out = base.copy()
        out["Status"] = "Ikke funnet i HB"
        out["Treff i HB"] = 0
        out["Regnskapslinjer"] = ""
        out["Kontoer"] = ""
        out["Periode"] = ""
    else:
        work = hits_df.copy()
        for col in ("Konto", "Bilag", "Dato"):
            if col not in work.columns:
                work[col] = ""

        work["Regnskapslinje"] = work["Konto"].map(
            lambda konto: str((konto_regnskapslinje_map or {}).get(str(konto).strip(), "") or "").strip()
        )

        grouped = (
            work.groupby("gap_number", dropna=False)
            .agg(
                treff=("gap_number", "size"),
                kontoer=("Konto", lambda s: _compact_join(s)),
                regnskapslinjer=("Regnskapslinje", lambda s: _compact_join(s)),
                periode=("Dato", _period_text),
            )
            .reset_index()
            .rename(
                columns={
                    "gap_number": "Nummer",
                    "treff": "Treff i HB",
                    "kontoer": "Kontoer",
                    "regnskapslinjer": "Regnskapslinjer",
                    "periode": "Periode",
                }
            )
        )

        out = base.merge(grouped, how="left", on="Nummer")
        out["Treff i HB"] = pd.to_numeric(out.get("Treff i HB"), errors="coerce").fillna(0).astype(int)
        out["Status"] = out["Treff i HB"].map(lambda n: "Funnet i HB" if int(n) > 0 else "Ikke funnet i HB")
        for col in ("Regnskapslinjer", "Kontoer", "Periode"):
            out[col] = out.get(col, "").fillna("").astype(str)

    prev_map: dict[int, str] = {}
    next_map: dict[int, str] = {}
    if isinstance(scope_context_df, pd.DataFrame) and not scope_context_df.empty and "number" in scope_context_df.columns:
        scope_summary = (
            scope_context_df.groupby("number", dropna=False)
            .agg(periode=("Dato", _period_text))
            .reset_index()
            .sort_values("number", kind="mergesort")
        )
        scope_numbers = [int(v) for v in scope_summary["number"].tolist()]
        period_map = {int(row.number): str(row.periode or "") for row in scope_summary.itertuples(index=False)}

        def _neighbor_label(number: int) -> str:
            period = str(period_map.get(int(number), "") or "").strip()
            return f"{int(number)} ({period})" if period else str(int(number))

        for gap_number in out["Nummer"].astype(int).tolist():
            pos = bisect.bisect_left(scope_numbers, int(gap_number))
            prev_number = scope_numbers[pos - 1] if pos > 0 else None
            next_number = scope_numbers[pos] if pos < len(scope_numbers) else None
            prev_map[int(gap_number)] = _neighbor_label(prev_number) if prev_number is not None else ""
            next_map[int(gap_number)] = _neighbor_label(next_number) if next_number is not None else ""

    out["Forrige i scope"] = out["Nummer"].astype(int).map(prev_map).fillna("")
    out["Neste i scope"] = out["Nummer"].astype(int).map(next_map).fillna("")

    if only_with_hits:
        out = out.loc[out["Treff i HB"] > 0].copy()

    return out[
        [
            "Nummer",
            "Status",
            "Treff i HB",
            "Regnskapslinjer",
            "Kontoer",
            "Periode",
            "Forrige i scope",
            "Neste i scope",
        ]
    ].reset_index(drop=True)


class NrSeriesControlView(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        df_scope: pd.DataFrame,
        *,
        df_all: pd.DataFrame | None = None,
        selected_accounts: Sequence[str] | None = None,
        scope_mode: str = "konto",
        scope_items: Sequence[str] | None = None,
        konto_regnskapslinje_map: dict[str, str] | None = None,
        analysis_jump_callback: Any | None = None,
        initial_field_key: str = AUTO_FIELD_KEY,
        initial_family_key: str | None = None,
    ) -> None:
        super().__init__(master)
        self.title("Nr.-seriekontroll")
        self.geometry("1180x760")

        self._df_scope = df_scope if isinstance(df_scope, pd.DataFrame) else pd.DataFrame()
        self._df_all = df_all if isinstance(df_all, pd.DataFrame) else self._df_scope
        self._selected_accounts = tuple(_unique_nonempty(selected_accounts or ()))
        self._scope_mode = str(scope_mode or "konto")
        self._scope_items = tuple(_unique_nonempty(scope_items or ()))
        self._konto_regnskapslinje_map = {
            str(k).strip(): str(v).strip()
            for k, v in (konto_regnskapslinje_map or {}).items()
            if str(k).strip() and str(v).strip()
        }
        self._analysis_jump_callback = analysis_jump_callback
        self._initial_family_key = str(initial_family_key or "")
        self._result = None
        self._family_rows: list[dict[str, object]] = []
        self._family_key_by_label: dict[str, str] = {}
        self._gap_number_by_iid: dict[str, int] = {}
        self._detail_bilag_by_iid: dict[str, str] = {}
        self._selected_gap_number: int | None = None
        self._gap_overview_df = pd.DataFrame()
        self._scope_context_df = pd.DataFrame()
        self._suspend_selection_events = False

        self._field_options = tuple(list_series_field_options(self._df_scope))
        self._field_label_by_key = {str(opt.key): str(opt.label) for opt in self._field_options}
        self._field_key_by_label = {str(opt.label): str(opt.key) for opt in self._field_options}

        initial_key = initial_field_key if initial_field_key in self._field_label_by_key else AUTO_FIELD_KEY
        initial_label = self._field_label_by_key.get(initial_key, "Auto")

        self._field_var = tk.StringVar(value=initial_label)
        self._family_var = tk.StringVar(value="")
        self._text_fallback_var = tk.BooleanVar(value=False)
        self._only_hits_var = tk.BooleanVar(value=False)
        self._status_var = tk.StringVar(value="")
        self._gap_summary_var = tk.StringVar(value="Velg et hull for å se treff i HB og nærmeste kontekst i scope.")
        self._scope_var = tk.StringVar(
            value=build_nr_series_scope_text(
                scope_mode=self._scope_mode,
                scope_items=self._scope_items,
                selected_accounts=self._selected_accounts,
                df_scope=self._df_scope,
            )
        )

        self._build_ui()
        self._refresh_analysis(preset_family_key=self._initial_family_key)

    def _build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=10, pady=10)

        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text="Nr.-seriekontroll", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(header, textvariable=self._scope_var).pack(anchor="w", pady=(2, 0))
        ttk.Label(header, textvariable=self._status_var).pack(anchor="w", pady=(2, 8))
        ttk.Label(header, textvariable=self._gap_summary_var, wraplength=1120, justify="left").pack(anchor="w", pady=(0, 8))

        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=(0, 8))

        ttk.Label(controls, text="Seriefelt:").grid(row=0, column=0, sticky="w")
        self._cmb_field = ttk.Combobox(
            controls,
            textvariable=self._field_var,
            values=[str(opt.label) for opt in self._field_options] or ["Auto"],
            width=20,
            state="readonly",
        )
        self._cmb_field.grid(row=0, column=1, sticky="w", padx=(4, 12))

        ttk.Label(controls, text="Serie:").grid(row=0, column=2, sticky="w")
        self._cmb_family = ttk.Combobox(
            controls,
            textvariable=self._family_var,
            values=[],
            width=42,
            state="readonly",
        )
        self._cmb_family.grid(row=0, column=3, sticky="w", padx=(4, 12))

        self._chk_text = ttk.Checkbutton(
            controls,
            text="Suppler med tekstsøk i hele HB",
            variable=self._text_fallback_var,
            command=self._refresh_analysis,
        )
        self._chk_text.grid(row=0, column=4, sticky="w")

        self._chk_only_hits = ttk.Checkbutton(
            controls,
            text="Kun hull med treff i HB",
            variable=self._only_hits_var,
            command=self._rerender_gap_views,
        )
        self._chk_only_hits.grid(row=0, column=5, sticky="w", padx=(12, 0))

        ttk.Button(controls, text="Oppdater", command=self._refresh_analysis).grid(row=0, column=6, sticky="e", padx=(12, 0))
        ttk.Button(controls, text="Vis i Analyse", command=self._open_in_analysis).grid(row=0, column=7, sticky="e", padx=(8, 0))
        controls.grid_columnconfigure(8, weight=1)

        self._cmb_field.bind("<<ComboboxSelected>>", lambda _e: self._refresh_analysis(reset_family=True))
        self._cmb_family.bind("<<ComboboxSelected>>", lambda _e: self._refresh_analysis())

        content = ttk.Frame(root)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)
        content.rowconfigure(3, weight=1)
        content.rowconfigure(5, weight=1)

        ttk.Label(content, text="Serieoversikt").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self._tree_families = self._build_tree(
            content,
            columns=("Serie", "Kilde", "Fra", "Til", "Antall", "Hull", "Duplikater", "Score"),
            row=1,
        )

        ttk.Label(content, text="Hull i valgt serie").grid(row=2, column=0, sticky="w", pady=(8, 2))
        self._tree_gaps = self._build_tree(
            content,
            columns=("Nummer", "Status", "Treff i HB", "Regnskapslinjer", "Kontoer", "Periode", "Forrige i scope", "Neste i scope"),
            row=3,
        )

        ttk.Label(content, text="Detaljer").grid(row=4, column=0, sticky="w", pady=(8, 2))
        self._tree_details = self._build_tree(
            content,
            columns=("Type", "Nr", "Kildeverdi", "Bilag", "Dato", "Konto", "Regnskapslinje", "Tekst"),
            row=5,
        )

        self._tree_families.bind("<<TreeviewSelect>>", self._on_family_selected)
        self._tree_gaps.bind("<<TreeviewSelect>>", self._on_gap_selected)
        self._tree_details.bind("<Double-1>", self._open_selected_bilag)
        self._tree_details.bind("<Return>", self._open_selected_bilag)

    def _build_tree(self, master: Any, *, columns: Sequence[str], row: int):
        frame = ttk.Frame(master)
        frame.grid(row=row, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        tree = ttk.Treeview(frame, columns=tuple(columns), show="headings", selectmode="browse")
        tree.grid(row=0, column=0, sticky="nsew")

        yscroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=yscroll.set)

        widths = {
            "Serie": 210,
            "Kilde": 120,
            "Fra": 80,
            "Til": 80,
            "Antall": 80,
            "Hull": 70,
            "Duplikater": 90,
            "Score": 70,
            "Nummer": 90,
            "Status": 130,
            "Treff i HB": 90,
            "Regnskapslinjer": 240,
            "Kontoer": 220,
            "Periode": 160,
            "Forrige i scope": 170,
            "Neste i scope": 170,
            "Bilag": 150,
            "Dato": 100,
            "Type": 120,
            "Nr": 90,
            "Kildeverdi": 120,
            "Tekst": 420,
            "Konto": 90,
            "Regnskapslinje": 220,
        }

        for col in columns:
            tree.heading(col, text=str(col))
            tree.column(col, width=widths.get(str(col), 120), stretch=True, anchor="w")
        return tree

    def _requested_field_key(self) -> str:
        label = str(self._field_var.get() or "").strip()
        return self._field_key_by_label.get(label, AUTO_FIELD_KEY)

    def _refresh_analysis(self, *_args: Any, reset_family: bool = False, preset_family_key: str | None = None) -> None:
        requested_field_key = self._requested_field_key()
        family_key = str(preset_family_key or "")
        if not family_key and not reset_family:
            family_key = self._family_key_by_label.get(str(self._family_var.get() or "").strip(), "")

        self._result = analyze_series(
            self._df_scope,
            self._df_all,
            field_key=requested_field_key,
            family_key=family_key,
            include_text_fallback=bool(self._text_fallback_var.get()),
        )
        self._render_all(requested_field_key=requested_field_key)

    def _render_all(self, *, requested_field_key: str) -> None:
        result = self._result
        if result is None:
            return

        actual_label = str(result.selected_field_label or "")
        if requested_field_key == AUTO_FIELD_KEY:
            field_text = f"Auto valgte: {actual_label or 'ingen serie funnet'}"
        else:
            requested_label = self._field_label_by_key.get(requested_field_key, requested_field_key)
            field_text = f"Seriefelt: {requested_label}"

        if result.families_df.empty:
            self._status_var.set(f"{field_text} | Fant ingen sammenhengende nummerserie i valgt scope.")
        else:
            self._status_var.set(
                f"{field_text} | Familier: {len(result.families_df.index)} | Hull: {len(result.gaps_df.index)} | Treff i hele HB: {len(result.hits_df.index)}"
            )

        self._scope_context_df = build_nr_series_scope_context_df(
            scope_rows_df=result.scope_rows_df,
            df_scope=self._df_scope,
            family_key=str(getattr(result, "selected_family_key", "") or ""),
            konto_regnskapslinje_map=self._konto_regnskapslinje_map,
        )
        self._suspend_selection_events = True
        try:
            self._render_families()
            self._render_family_choices()
            self._rerender_gap_views()
        finally:
            self._suspend_selection_events = False

    def _clear_tree(self, tree: Any) -> None:
        try:
            tree.delete(*tree.get_children(""))
        except Exception:
            pass

    def _render_families(self) -> None:
        self._clear_tree(self._tree_families)
        self._family_rows = []
        result = self._result
        if result is None or result.families_df.empty:
            return

        for idx, row in result.families_df.reset_index(drop=True).iterrows():
            family_key = str(row.get("family_key", "") or "")
            iid = f"family:{idx}"
            self._family_rows.append({"iid": iid, "family_key": family_key})
            self._tree_families.insert(
                "",
                "end",
                iid=iid,
                values=(
                    str(row.get("label", "") or ""),
                    str(row.get("source_column", "") or ""),
                    str(row.get("min_number", "") or ""),
                    str(row.get("max_number", "") or ""),
                    str(int(row.get("count_distinct", 0) or 0)),
                    str(int(row.get("gap_count", 0) or 0)),
                    str(int(row.get("duplicate_count", 0) or 0)),
                    f"{float(row.get('score', 0.0) or 0.0):.1f}",
                ),
            )

        selected_family = str(getattr(result, "selected_family_key", "") or "")
        for item in self._family_rows:
            if item["family_key"] == selected_family:
                self._tree_families.selection_set(item["iid"])
                self._tree_families.focus(item["iid"])
                break

    def _render_family_choices(self) -> None:
        result = self._result
        values: list[str] = []
        self._family_key_by_label = {}
        if result is not None and not result.families_df.empty:
            for row in result.families_df.itertuples(index=False):
                label = f"{str(row.label)} ({int(row.count_distinct)} nr, {int(row.gap_count)} hull)"
                family_key = str(row.family_key)
                values.append(label)
                self._family_key_by_label[label] = family_key

        try:
            self._cmb_family.configure(values=values)
        except Exception:
            pass

        selected_family_key = str(getattr(result, "selected_family_key", "") or "")
        selected_label = next((label for label, key in self._family_key_by_label.items() if key == selected_family_key), "")
        try:
            self._family_var.set(selected_label)
        except Exception:
            pass

    def _render_gaps(self) -> None:
        self._clear_tree(self._tree_gaps)
        self._gap_number_by_iid = {}

        result = self._result
        overview = build_nr_series_gap_overview(
            result.gaps_df if result is not None else pd.DataFrame(),
            result.hits_df if result is not None else pd.DataFrame(),
            scope_context_df=self._scope_context_df,
            konto_regnskapslinje_map=self._konto_regnskapslinje_map,
            only_with_hits=bool(self._only_hits_var.get()),
        )
        self._gap_overview_df = overview.copy()
        if overview.empty:
            self._selected_gap_number = None
            self._update_gap_summary()
            return

        previous_gap = self._selected_gap_number
        selected_iid = ""
        for idx, row in overview.iterrows():
            gap_number = int(row["Nummer"])
            iid = f"gap:{idx}"
            self._gap_number_by_iid[iid] = gap_number
            self._tree_gaps.insert(
                "",
                "end",
                iid=iid,
                values=(
                    str(gap_number),
                    str(row["Status"] or ""),
                    str(int(row["Treff i HB"])),
                    str(row["Regnskapslinjer"] or ""),
                    str(row["Kontoer"] or ""),
                    str(row["Periode"] or ""),
                    str(row["Forrige i scope"] or ""),
                    str(row["Neste i scope"] or ""),
                ),
            )
            if previous_gap is not None and gap_number == previous_gap:
                selected_iid = iid

        if not selected_iid:
            selected_iid = next(iter(self._gap_number_by_iid.keys()), "")

        if selected_iid:
            self._selected_gap_number = self._gap_number_by_iid.get(selected_iid)
            self._tree_gaps.selection_set(selected_iid)
            self._tree_gaps.focus(selected_iid)
        self._update_gap_summary()

    def _rerender_gap_views(self) -> None:
        self._render_gaps()
        self._render_details()

    def _gap_overview_row(self, gap_number: int | None) -> dict[str, object] | None:
        if gap_number is None or self._gap_overview_df.empty or "Nummer" not in self._gap_overview_df.columns:
            return None
        match = self._gap_overview_df.loc[self._gap_overview_df["Nummer"] == int(gap_number)]
        if match.empty:
            return None
        return dict(match.iloc[0].to_dict())

    def _update_gap_summary(self) -> None:
        gap_number = self._selected_gap_number
        row = self._gap_overview_row(gap_number)
        if row is None:
            self._gap_summary_var.set("Velg et hull for å se treff i HB og nærmeste kontekst i scope.")
            return

        status = str(row.get("Status", "") or "").strip() or "Ukjent status"
        period = str(row.get("Periode", "") or "").strip()
        kontoer = str(row.get("Kontoer", "") or "").strip()
        regnskapslinjer = str(row.get("Regnskapslinjer", "") or "").strip()
        prev_txt = str(row.get("Forrige i scope", "") or "").strip()
        next_txt = str(row.get("Neste i scope", "") or "").strip()
        summary = f"Hull {int(gap_number)}: {status}."
        if int(row.get("Treff i HB", 0) or 0) > 0:
            summary += f" Treff i HB: {int(row.get('Treff i HB', 0) or 0)}."
        if period:
            summary += f" Periode: {period}."
        if kontoer:
            summary += f" Kontoer: {kontoer}."
        if regnskapslinjer:
            summary += f" Regnskapslinjer: {regnskapslinjer}."
        if prev_txt or next_txt:
            summary += f" Nærmeste i scope: {prev_txt or 'ingen forrige'} -> {next_txt or 'ingen neste'}."
        self._gap_summary_var.set(summary)

    def _gap_context_rows(self, gap_number: int) -> list[dict[str, object]]:
        if self._scope_context_df.empty or "number" not in self._scope_context_df.columns:
            return []

        distinct_numbers = sorted({int(v) for v in self._scope_context_df["number"].dropna().tolist()})
        if not distinct_numbers:
            return []

        pos = bisect.bisect_left(distinct_numbers, int(gap_number))
        targets: list[tuple[str, int]] = []
        if pos > 0:
            targets.append(("Forrige i scope", distinct_numbers[pos - 1]))
        if pos < len(distinct_numbers):
            targets.append(("Neste i scope", distinct_numbers[pos]))

        rows: list[dict[str, object]] = []
        for row_type, number in targets:
            subset = self._scope_context_df.loc[self._scope_context_df["number"] == int(number)].copy()
            if subset.empty:
                continue
            for row in subset.sort_values(["Dato", "Bilag"], kind="mergesort").head(8).itertuples(index=False):
                rows.append(
                    {
                        "Type": row_type,
                        "Nr": int(getattr(row, "number", 0) or 0),
                        "Kildeverdi": str(getattr(row, "raw_value", "") or ""),
                        "Bilag": str(getattr(row, "Bilag", "") or ""),
                        "Dato": getattr(row, "Dato", None),
                        "Konto": str(getattr(row, "Konto", "") or ""),
                        "Regnskapslinje": str(getattr(row, "Regnskapslinje", "") or ""),
                        "Tekst": str(getattr(row, "Tekst", "") or ""),
                    }
                )
        return rows

    def _render_details(self) -> None:
        self._clear_tree(self._tree_details)
        self._detail_bilag_by_iid = {}

        result = self._result
        gap_number = self._selected_gap_number
        detail_rows: list[dict[str, object]] = []

        if result is not None and isinstance(result.hits_df, pd.DataFrame) and not result.hits_df.empty:
            df = result.hits_df.copy()
            if gap_number is not None and "gap_number" in df.columns:
                df = df.loc[df["gap_number"] == gap_number].copy()
            if not df.empty:
                for row in df.reset_index(drop=True).itertuples(index=False):
                    detail_rows.append(
                        {
                            "Type": "Treff i HB",
                            "Nr": int(getattr(row, "gap_number", 0) or 0),
                            "Kildeverdi": str(getattr(row, "raw_value", "") or ""),
                            "Bilag": str(getattr(row, "Bilag", "") or ""),
                            "Dato": getattr(row, "Dato", None),
                            "Konto": str(getattr(row, "Konto", "") or ""),
                            "Regnskapslinje": str(
                                self._konto_regnskapslinje_map.get(str(getattr(row, "Konto", "") or "").strip(), "") or ""
                            ),
                            "Tekst": str(getattr(row, "Tekst", "") or ""),
                        }
                    )

        if gap_number is not None:
            detail_rows.extend(self._gap_context_rows(int(gap_number)))

        if not detail_rows:
            return

        for idx, row in enumerate(detail_rows):
            iid = f"detail:{idx}"
            bilag = str(row.get("Bilag", "") or "")
            self._detail_bilag_by_iid[iid] = bilag
            dato = pd.to_datetime(row.get("Dato"), errors="coerce")
            dato_txt = "" if pd.isna(dato) else dato.strftime("%Y-%m-%d")
            self._tree_details.insert(
                "",
                "end",
                iid=iid,
                values=(
                    str(row.get("Type", "") or ""),
                    str(int(row.get("Nr", 0) or 0)),
                    str(row.get("Kildeverdi", "") or ""),
                    bilag,
                    dato_txt,
                    str(row.get("Konto", "") or ""),
                    str(row.get("Regnskapslinje", "") or ""),
                    str(row.get("Tekst", "") or ""),
                ),
            )

    @staticmethod
    def _regnr_from_label(value: object) -> int | None:
        text = str(value or "").strip()
        if not text:
            return None
        head = text.split(" ", 1)[0].strip()
        try:
            return int(head)
        except Exception:
            return None

    def _build_analysis_context(self) -> dict[str, object]:
        base = pd.DataFrame()
        result = self._result
        gap_number = self._selected_gap_number

        if result is not None and isinstance(result.hits_df, pd.DataFrame) and not result.hits_df.empty and gap_number is not None:
            base = result.hits_df.loc[result.hits_df["gap_number"] == gap_number].copy()

        if base.empty:
            base = self._scope_context_df.copy()

        accounts = _unique_nonempty(base.get("Konto", pd.Series(dtype=str)).tolist()) if not base.empty else list(self._selected_accounts)
        dates = pd.to_datetime(base.get("Dato", pd.Series(dtype=object)), errors="coerce").dropna() if not base.empty else pd.Series(dtype="datetime64[ns]")
        period_from = ""
        period_to = ""
        if not dates.empty:
            period_from = str(int(dates.min().month))
            period_to = str(int(dates.max().month))

        regnr_values: list[int] = []
        if not base.empty:
            labels = _unique_nonempty(base.get("Regnskapslinje", pd.Series(dtype=str)).tolist())
            for label in labels:
                regnr = self._regnr_from_label(label)
                if regnr is not None and regnr not in regnr_values:
                    regnr_values.append(regnr)

        if not regnr_values:
            for konto in accounts:
                regnr = self._regnr_from_label(self._konto_regnskapslinje_map.get(konto, ""))
                if regnr is not None and regnr not in regnr_values:
                    regnr_values.append(regnr)

        return {
            "accounts": accounts,
            "period_from": period_from,
            "period_to": period_to,
            "regnr_values": regnr_values,
            "gap_number": gap_number,
        }

    def _open_in_analysis(self) -> None:
        callback = self._analysis_jump_callback
        if not callable(callback):
            return
        try:
            callback(self._build_analysis_context())
        except Exception:
            pass

    def _on_family_selected(self, _event=None) -> None:
        if self._suspend_selection_events:
            return
        selection = list(self._tree_families.selection())
        if not selection:
            return
        selected_iid = selection[0]
        family_key = next((str(item["family_key"]) for item in self._family_rows if item["iid"] == selected_iid), "")
        if not family_key:
            return
        if family_key == str(getattr(self._result, "selected_family_key", "") or ""):
            return
        label = next((label for label, key in self._family_key_by_label.items() if key == family_key), "")
        if label:
            self._family_var.set(label)
        self._refresh_analysis(preset_family_key=family_key)

    def _on_gap_selected(self, _event=None) -> None:
        if self._suspend_selection_events:
            return
        selection = list(self._tree_gaps.selection())
        if not selection:
            self._selected_gap_number = None
            self._update_gap_summary()
            self._render_details()
            return
        self._selected_gap_number = self._gap_number_by_iid.get(selection[0])
        self._update_gap_summary()
        self._render_details()

    def _open_selected_bilag(self, _event=None) -> str:
        selection = list(self._tree_details.selection())
        if not selection:
            return "break"
        bilag = self._detail_bilag_by_iid.get(selection[0], "")
        if not bilag:
            return "break"
        callback = getattr(self.master, "_open_bilag_drilldown_for_bilag", None)
        if callable(callback):
            try:
                callback(bilag)
            except Exception:
                pass
        return "break"


def show_nr_series_control(
    master: tk.Misc,
    df_scope: pd.DataFrame | None = None,
    *,
    scope_df: pd.DataFrame | None = None,
    df_all: pd.DataFrame | None = None,
    all_df: pd.DataFrame | None = None,
    selected_accounts: Sequence[str] | None = None,
    accounts: Sequence[str] | None = None,
    scope_mode: str | None = None,
    scope_items: Sequence[str] | None = None,
    konto_regnskapslinje_map: dict[str, str] | None = None,
    analysis_jump_callback: Any | None = None,
    initial_field_key: str = AUTO_FIELD_KEY,
    initial_family_key: str | None = None,
    **_: Any,
) -> None:
    scope = df_scope if df_scope is not None else scope_df
    if scope is None:
        raise TypeError("show_nr_series_control: mangler dataframe (df_scope/scope_df)")
    if not isinstance(scope, pd.DataFrame) or scope.empty:
        return

    NrSeriesControlView(
        master,
        scope,
        df_all=df_all if df_all is not None else all_df,
        selected_accounts=selected_accounts if selected_accounts is not None else accounts,
        scope_mode=str(scope_mode or "konto"),
        scope_items=scope_items,
        konto_regnskapslinje_map=konto_regnskapslinje_map,
        analysis_jump_callback=analysis_jump_callback,
        initial_field_key=initial_field_key,
        initial_family_key=initial_family_key,
    )


_show_nr_series_control = show_nr_series_control


__all__ = [
    "NrSeriesControlView",
    "build_nr_series_gap_overview",
    "build_nr_series_scope_text",
    "show_nr_series_control",
    "_show_nr_series_control",
]

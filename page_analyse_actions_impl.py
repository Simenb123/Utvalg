"""page_analyse_actions_impl.py

Handlinger / actions på Analyse-fanen.

Flyttet ut av page_analyse.py for å holde UI-koden liten og mer testbar.

Inneholder:
- Motpostanalyse (scope bilag fra valgte kontoer)
- Nr.-seriekontroll (valgt konto-/RL-scope)
- Overstyring (åpne transaksjonsanalyser)
- Bilagsdrilldown (for valgt bilag)

Alle funksjoner er defensive: GUI skal ikke krasje ved manglende moduler
eller uventede signaturer.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import pandas as pd

import session
from konto_utils import konto_to_str


def _show_info(messagebox: Any, title: str, msg: str) -> None:
    if messagebox is None:
        return
    try:
        messagebox.showinfo(title, msg)
    except Exception:
        pass


def _show_error(messagebox: Any, title: str, msg: str) -> None:
    if messagebox is None:
        return
    try:
        messagebox.showerror(title, msg)
    except Exception:
        pass


def _normalized_bilag_key_series(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .replace({"nan": "", "None": ""})
    )


def _prepare_motpost_frame(df: pd.DataFrame) -> pd.DataFrame:
    work = df

    if "Bilag_str" not in work.columns:
        if work is df:
            work = work.copy()
        work["Bilag_str"] = _normalized_bilag_key_series(work["Bilag"])

    if "Konto_str" not in work.columns:
        if work is df:
            work = work.copy()
        work["Konto_str"] = work["Konto"].map(konto_to_str)

    if "Beløp_num" not in work.columns:
        if work is df:
            work = work.copy()
        work["Beløp_num"] = pd.to_numeric(work["Beløp"], errors="coerce").fillna(0.0)

    return work


def _cached_motpost_frame(page: Any, df: pd.DataFrame) -> pd.DataFrame:
    cache = getattr(page, "_motpost_prepared_frames", None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(page, "_motpost_prepared_frames", cache)

    key = (id(df), tuple(df.columns), len(df))
    hit = cache.get(key)
    if isinstance(hit, pd.DataFrame):
        return hit

    prepared = _prepare_motpost_frame(df)

    if len(cache) >= 6:
        cache.clear()
    cache[key] = prepared
    return prepared


def _build_rl_scope_context(*, page: Any, df_scope: pd.DataFrame) -> dict[str, Any]:
    try:
        agg_var = getattr(page, "_var_aggregering", None)
        agg_mode = str(agg_var.get()) if agg_var is not None else ""
    except Exception:
        agg_mode = ""

    if agg_mode != "Regnskapslinje":
        return {}

    try:
        import page_analyse_rl
        selected_rows = page_analyse_rl.get_selected_rl_rows(page=page)
    except Exception:
        selected_rows = []

    if not selected_rows:
        return {}

    scope_items = [f"{int(regnr)} {str(navn or '').strip()}".strip() for regnr, navn in selected_rows]

    konto_regnskapslinje_map: dict[str, str] = {}
    try:
        intervals = getattr(page, "_rl_intervals", None)
        regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
        if (
            isinstance(df_scope, pd.DataFrame)
            and not df_scope.empty
            and intervals is not None
            and regnskapslinjer is not None
            and "Konto" in df_scope.columns
        ):
            from regnskap_mapping import apply_account_overrides, apply_interval_mapping, normalize_regnskapslinjer

            konto_values = df_scope["Konto"].dropna().map(konto_to_str)
            konto_values = [k for k in pd.unique(konto_values) if k]
            probe = pd.DataFrame({"konto": konto_values})
            mapped = apply_interval_mapping(probe, intervals, konto_col="konto").mapped

            try:
                account_overrides = page_analyse_rl._load_current_client_account_overrides()
            except Exception:
                account_overrides = None
            mapped = apply_account_overrides(mapped, account_overrides, konto_col="konto")

            regn = normalize_regnskapslinjer(regnskapslinjer)[["regnr", "regnskapslinje"]].copy()
            regn["regnr"] = regn["regnr"].astype(int)
            regn["rl_label"] = regn["regnr"].map(str) + " " + regn["regnskapslinje"].fillna("").astype(str).str.strip()
            name_map = {
                int(row.regnr): str(row.rl_label).strip()
                for row in regn.itertuples(index=False)
            }
            for row in mapped.itertuples(index=False):
                konto = str(getattr(row, "konto", "") or "").strip()
                regnr = getattr(row, "regnr", None)
                if not konto or pd.isna(regnr):
                    continue
                try:
                    konto_regnskapslinje_map[konto] = name_map.get(int(regnr), str(int(regnr)))
                except Exception:
                    continue
    except Exception:
        konto_regnskapslinje_map = {}

    return {
        "scope_mode": "regnskapslinje",
        "scope_items": scope_items,
        "konto_regnskapslinje_map": konto_regnskapslinje_map,
    }


def _resolve_all_dataset(page: Any) -> Optional[pd.DataFrame]:
    df_all: Optional[pd.DataFrame] = None
    if isinstance(getattr(page, "dataset", None), pd.DataFrame):
        df_all = page.dataset

    if df_all is None or df_all.empty:
        if isinstance(getattr(session, "dataset", None), pd.DataFrame):
            df_all = session.dataset

    return df_all


def _resolve_scope_source(page: Any, df_all: pd.DataFrame) -> pd.DataFrame:
    df_filtered = getattr(page, "_df_filtered", None)
    if isinstance(df_filtered, pd.DataFrame) and not df_filtered.empty:
        return df_filtered
    return df_all


def open_motpost(
    *,
    page: Any,
    messagebox: Any,
    show_motpost_konto: Any,
) -> None:
    """Åpne en enkel motpostanalyse for valgte kontoer.

    Prinsipp:
    - Bruk *gjeldende filter* for å finne hvilke bilag som inngår (scope)
    - Når bilagene er identifisert, hentes alle linjer for disse bilagene
      fra full datasett slik at motposter alltid blir med.
    """

    accounts = []
    try:
        accounts = list(page._get_selected_accounts())
    except Exception:
        accounts = []

    if not accounts:
        _show_info(messagebox, "Motpost", "Velg minst én konto i pivot-listen først.")
        return

    # Fullt datasett
    df_all: Optional[pd.DataFrame] = None
    if isinstance(getattr(page, "dataset", None), pd.DataFrame):
        df_all = page.dataset

    if df_all is None or df_all.empty:
        if isinstance(getattr(session, "dataset", None), pd.DataFrame):
            df_all = session.dataset

    if df_all is None or df_all.empty:
        _show_error(messagebox, "Motpost", "Fant ingen datasett (dataset) å analysere.")
        return

    # Minimumskrav
    required_cols = {"Bilag", "Konto", "Beløp"}
    missing = [c for c in required_cols if c not in df_all.columns]
    if missing:
        _show_error(messagebox, "Motpost", "Datasettet mangler nødvendige kolonner: " + ", ".join(missing))
        return

    df_filtered = getattr(page, "_df_filtered", None)
    if not isinstance(df_filtered, pd.DataFrame):
        df_filtered = None

    df_all_prepared = _cached_motpost_frame(page, df_all)
    df_filtered_prepared = (
        _cached_motpost_frame(page, df_filtered)
        if df_filtered is not None and not df_filtered.empty
        else None
    )

    df_scope_source = (
        df_filtered_prepared
        if df_filtered_prepared is not None and not df_filtered_prepared.empty
        else df_all_prepared
    )

    accounts_set = {konto_to_str(a) for a in accounts}
    mask_sel = df_scope_source["Konto_str"].isin(accounts_set)

    bilag_list = [
        str(b).strip()
        for b in pd.unique(df_scope_source.loc[mask_sel, "Bilag_str"])
        if str(b).strip()
    ]

    if not bilag_list:
        _show_info(messagebox, "Motpost", "Fant ingen bilag for valgte kontoer i gjeldende filter.")
        return

    # Scope-datasett: alle linjer for scope-bilagene fra full datasett
    df_scope = df_all_prepared.loc[df_all_prepared["Bilag_str"].isin(set(bilag_list))].copy()

    if df_scope.empty:
        _show_info(messagebox, "Motpost", "Fant ingen transaksjoner i scope for valgt(e) bilag.")
        return

    if show_motpost_konto is None:
        _show_error(messagebox, "Motpost", "Motpostanalyse er ikke tilgjengelig (mangler GUI-støtte).")
        return

    extra_context = _build_rl_scope_context(page=page, df_scope=df_scope)

    try:
        show_motpost_konto(
            master=page,
            df_transactions=df_scope,
            konto_list=accounts,
            selected_direction=getattr(page, "_var_direction").get(),
            **extra_context,
        )
    except Exception as e:
        _show_error(messagebox, "Motpost", f"Kunne ikke åpne motpostanalyse.\n\n{e}")


def open_nr_series_control(
    *,
    page: Any,
    messagebox: Any,
    show_nr_series_control: Any,
) -> None:
    """Åpne nummerseriekontroll for valgt konto-/RL-scope."""

    try:
        accounts = list(page._get_selected_accounts())
    except Exception:
        accounts = []

    if not accounts:
        _show_info(messagebox, "Nr.-seriekontroll", "Velg minst én konto eller regnskapslinje i pivot-listen først.")
        return

    df_all = _resolve_all_dataset(page)
    if df_all is None or df_all.empty:
        _show_error(messagebox, "Nr.-seriekontroll", "Fant ingen datasett (dataset) å analysere.")
        return

    if "Konto" not in df_all.columns:
        _show_error(messagebox, "Nr.-seriekontroll", "Datasettet mangler nødvendig kolonne: Konto")
        return

    df_scope_source = _resolve_scope_source(page, df_all)
    accounts_set = {konto_to_str(a) for a in accounts}
    try:
        konto_scope = df_scope_source["Konto"].map(konto_to_str)
    except Exception:
        konto_scope = df_scope_source["Konto"].astype(str).str.strip()

    df_scope = df_scope_source.loc[konto_scope.isin(accounts_set)].copy()
    if df_scope.empty:
        _show_info(messagebox, "Nr.-seriekontroll", "Fant ingen transaksjoner i valgt scope.")
        return

    if show_nr_series_control is None:
        _show_error(messagebox, "Nr.-seriekontroll", "Nr.-seriekontroll er ikke tilgjengelig (mangler GUI-støtte).")
        return

    extra_context = _build_rl_scope_context(page=page, df_scope=df_scope)
    scope_mode = str(extra_context.get("scope_mode") or "konto")
    scope_items = list(extra_context.get("scope_items") or [konto_to_str(a) for a in accounts])

    try:
        show_nr_series_control(
            master=page,
            df_scope=df_scope,
            df_all=df_all,
            selected_accounts=accounts,
            scope_mode=scope_mode,
            scope_items=scope_items,
            konto_regnskapslinje_map=extra_context.get("konto_regnskapslinje_map"),
            analysis_jump_callback=getattr(page, "_jump_to_nr_series_context", None),
        )
    except Exception as e:
        _show_error(messagebox, "Nr.-seriekontroll", f"Kunne ikke åpne nr.-seriekontroll.\n\n{e}")


def open_override_checks(
    *,
    page: Any,
    messagebox: Any,
) -> None:
    """Åpne transaksjonsanalyser for revisjonsrisiko – ledelsens overstyring."""

    # Fullt datasett
    df_all: Optional[pd.DataFrame] = None
    if isinstance(getattr(page, "dataset", None), pd.DataFrame):
        df_all = page.dataset

    if df_all is None or df_all.empty:
        if isinstance(getattr(session, "dataset", None), pd.DataFrame):
            df_all = session.dataset

    if df_all is None or df_all.empty:
        _show_info(messagebox, "Transaksjonsanalyser", "Ingen datasett lastet.")
        return

    # Scope (valgte kontoer / gjeldende filter) brukes kun til markering i drilldown
    df_scope: Optional[pd.DataFrame] = None
    try:
        if isinstance(getattr(page, "_df_filtered", None), pd.DataFrame) and not page._df_filtered.empty:
            df_scope = page._df_filtered
    except Exception:
        df_scope = None

    # Prøv å hente Columns-mapping (hvis satt av importen)
    cols_obj = None
    try:
        _df_sess, cols_obj = session.get_dataset()
    except Exception:
        cols_obj = None

    try:
        from views_override_checks import open_override_checks_popup
    except Exception as e:
        _show_error(messagebox, "Transaksjonsanalyser", f"Kunne ikke laste modul for transaksjonsanalyser:\n{e}")
        return

    try:
        open_override_checks_popup(page, df_all=df_all, df_scope=df_scope, cols=cols_obj)
    except Exception as e:
        _show_error(messagebox, "Transaksjonsanalyser", f"Kunne ikke åpne analysevindu.\n\n{e}")


def open_bilag_drilldown_for_bilag(
    *,
    page: Any,
    bilag_value: str,
    open_bilag_drill_dialog: Any,
    messagebox: Any,
) -> None:
    """Åpne bilagsdrill for gitt bilag.

    - df_base: transaksjoner for valgte kontoer (markeres som "I kontoutvalg")
    - df_all: hele datasettet (slik at motposter kommer med)
    """

    if open_bilag_drill_dialog is None:
        _show_info(
            messagebox,
            "Bilagsdrill",
            "Bilagsdrill er ikke tilgjengelig (mangler selection_studio_drill).",
        )
        return

    df_all = getattr(page, "dataset", None) if isinstance(getattr(page, "dataset", None), pd.DataFrame) else None
    df_filtered = getattr(page, "_df_filtered", None) if isinstance(getattr(page, "_df_filtered", None), pd.DataFrame) else None

    if df_all is None:
        df_all = df_filtered
    if df_filtered is None:
        df_filtered = df_all

    if df_all is None or df_filtered is None or not isinstance(df_all, pd.DataFrame) or df_all.empty:
        _show_info(messagebox, "Bilagsdrill", "Ingen data tilgjengelig for drilldown.")
        return

    df_base = df_filtered
    try:
        sel_accounts = page._get_selected_accounts()
    except Exception:
        sel_accounts = []

    if sel_accounts and "Konto" in df_filtered.columns:
        try:
            df_base = df_filtered[df_filtered["Konto"].isin(sel_accounts)].copy()
            if df_base.empty:
                df_base = df_filtered
        except Exception:
            df_base = df_filtered

    # Kjør dialogen – robust mot flere signaturvarianter (bakoverkompat)
    try:
        open_bilag_drill_dialog(
            page,
            df_base=df_base,
            df_all=df_all,
            bilag_value=bilag_value,
            bilag_col="Bilag",
        )
        return
    except TypeError:
        pass
    except Exception as e:
        _show_error(messagebox, "Bilagsdrill", f"Kunne ikke åpne bilagsdrill.\n\n{e}")
        return

    # Eldre aliaser (historiske kall)
    try:
        open_bilag_drill_dialog(
            page,
            df_base=df_base,
            df_all=df_all,
            preset_bilag=bilag_value,
            bilag_col="Bilag",
        )
        return
    except TypeError:
        pass
    except Exception as e:
        _show_error(messagebox, "Bilagsdrill", f"Kunne ikke åpne bilagsdrill.\n\n{e}")
        return

    # Eldste signatur (posisjonelle)
    try:
        open_bilag_drill_dialog(page, df_base, df_all, bilag_value)
    except Exception as e:
        _show_error(messagebox, "Bilagsdrill", f"Kunne ikke åpne bilagsdrill.\n\n{e}")


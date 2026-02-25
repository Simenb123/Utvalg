"""page_analyse_actions_impl.py

Handlinger / actions på Analyse-fanen.

Flyttet ut av page_analyse.py for å holde UI-koden liten og mer testbar.

Inneholder:
- Motpostanalyse (scope bilag fra valgte kontoer)
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

    df_scope_source = df_filtered if df_filtered is not None and not df_filtered.empty else df_all

    accounts_set = {konto_to_str(a) for a in accounts}
    konto_norm = df_scope_source["Konto"].map(konto_to_str)
    mask_sel = konto_norm.isin(accounts_set)

    bilag_keys = (
        df_scope_source.loc[mask_sel, "Bilag"]
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .replace({"nan": "", "None": ""})
    )
    bilag_list = [b for b in bilag_keys.unique().tolist() if b]

    if not bilag_list:
        _show_info(messagebox, "Motpost", "Fant ingen bilag for valgte kontoer i gjeldende filter.")
        return

    # Scope-datasett: alle linjer for scope-bilagene fra full datasett
    bilag_all = (
        df_all["Bilag"]
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .replace({"nan": "", "None": ""})
    )
    df_scope = df_all.loc[bilag_all.isin(set(bilag_list))].copy()

    if df_scope.empty:
        _show_info(messagebox, "Motpost", "Fant ingen transaksjoner i scope for valgt(e) bilag.")
        return

    if show_motpost_konto is None:
        _show_error(messagebox, "Motpost", "Motpostanalyse er ikke tilgjengelig (mangler GUI-støtte).")
        return

    try:
        show_motpost_konto(
            master=page,
            df_transactions=df_scope,
            konto_list=accounts,
            selected_direction=getattr(page, "_var_direction").get(),
        )
    except Exception as e:
        _show_error(messagebox, "Motpost", f"Kunne ikke åpne motpostanalyse.\n\n{e}")


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


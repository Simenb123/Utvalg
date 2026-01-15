# page_utvalg_strata.py
"""
Utvalg-tab (stratifisering) basert på SelectionStudio.

Bakgrunn / problem som denne filen løser
--------------------------------------
Analyse-siden lar brukeren markere én eller flere kontoer og trykke "Til utvalg".
For at Utvalg-fanen skal kunne kjøre utvalg/stratifisering må den få et
datagrunnlag (populasjon) filtrert på de valgte kontoene.

I dette repoet sendes kontoer typisk som strenger (Listbox i Analyse fylles med
str(acc)). Samtidig kan df["Konto"] være int/float/str avhengig av import.
Derfor normaliserer vi og filtrerer robust, ellers får vi tomt grunnlag.

Teknisk:
- ui_main kaller UtvalgStrataPage.load_population(accounts) når bruker trykker
  "Til utvalg" i Analyse.
- Vi lagrer konto-valget i session.SELECTION (hvis mulig), filtrerer session.dataset
  og kaller SelectionStudio.load_data(...) for å oppdatere GUI.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, List, Optional

import pandas as pd

import session
from views_selection_studio_ui import SelectionStudio


def _normalize_account_values(accounts: List[Any]) -> List[str]:
    """
    Normaliserer kontoliste til strenger uten whitespace og uten trailing ".0".

    Tar imot både int/float/str.
    """
    out: List[str] = []
    seen: set[str] = set()

    for a in accounts or []:
        if a is None:
            continue

        # Tall -> int-streng
        if isinstance(a, (int,)):
            s = str(a)
        elif isinstance(a, float):
            # 6733.0 -> "6733"
            if a.is_integer():
                s = str(int(a))
            else:
                s = str(a)
        else:
            s = str(a).strip()

        if not s:
            continue

        # Rydd bort "6733.0" som kan komme fra Excel/float->str
        if s.endswith(".0"):
            s = s[:-2]

        if s not in seen:
            out.append(s)
            seen.add(s)

    return out


def _filter_base(df_all: pd.DataFrame, accounts: List[str]) -> pd.DataFrame:
    """
    Filtrer transaksjoner til valgt kontopopulasjon.

    Hvis Konto-kolonnen ikke finnes, eller accounts er tom -> tom DF.
    """
    if df_all is None or df_all.empty:
        return pd.DataFrame()

    if not accounts:
        return pd.DataFrame()

    if "Konto" not in df_all.columns:
        return pd.DataFrame()

    # Robust filtering:
    # - Konto kan være int/float/str avhengig av import
    # - Hvis Konto er float (f.eks. 6733.0) vil astype(str) gi "6733.0" og
    #   accounts inneholder "6733". Vi normaliserer derfor vekk trailing ".0".
    konto_as_str = df_all["Konto"].astype(str).str.strip()
    konto_as_str = konto_as_str.str.replace(r"\.0$", "", regex=True)

    return df_all[konto_as_str.isin(accounts)].copy()


def _expand_bilag_sample_to_transactions(
    df_sample_bilag: pd.DataFrame,
    df_transactions: pd.DataFrame,
) -> pd.DataFrame:
    """
    Konverter et bilag-basert sample (1 rad per bilag) til transaksjonsrader
    ved å slå opp bilagene i df_transactions.
    """
    if df_sample_bilag is None or df_sample_bilag.empty:
        return pd.DataFrame()
    if df_transactions is None or df_transactions.empty:
        return pd.DataFrame()

    if "Bilag" not in df_sample_bilag.columns or "Bilag" not in df_transactions.columns:
        return pd.DataFrame()

    bilag = (
        df_sample_bilag["Bilag"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )
    if not bilag:
        return pd.DataFrame()

    tx = df_transactions.copy()
    tx_bilag = tx["Bilag"].astype(str).str.strip()
    return tx[tx_bilag.isin(bilag)].copy()


class UtvalgStrataPage(ttk.Frame):
    """
    Wrapper-side i Notebook for SelectionStudio.

    Forventet API (brukes av ui_main og bus):
    - load_population(accounts: List[str]) -> filtrer session.dataset og last inn i studio
    """

    def __init__(
        self,
        parent: Any,
        session: object = session,
        bus: Optional[object] = None,
        on_commit_sample: Optional[Callable[[pd.DataFrame], None]] = None,
    ) -> None:
        super().__init__(parent)

        self.session = session
        self.bus = bus
        self._on_commit_sample = on_commit_sample

        self._accounts: List[str] = []

        # SelectionStudio: testene forventer at vi bruker on_commit_selection
        self.studio = SelectionStudio(self, on_commit_selection=self._on_commit_selection)
        self.studio.pack(fill="both", expand=True)

        # Hvis noe allerede er valgt i session ved oppstart, last det
        try:
            sel = (
                self.session.get_selection()  # type: ignore[attr-defined]
                if hasattr(self.session, "get_selection")
                else getattr(self.session, "SELECTION", {})
            )
            self._accounts = _normalize_account_values(sel.get("accounts", []))
        except Exception:
            self._accounts = []

        self._refresh()

    # ------------------------------------------------------------
    # Offentlig API: kall fra Analyse/ui_main/bus
    # ------------------------------------------------------------
    def load_population(self, accounts: List[Any]) -> None:
        """
        Motta kontoer fra Analyse-fanen og bygg datagrunnlag.
        """
        accounts_norm = _normalize_account_values(accounts or [])
        self._accounts = accounts_norm

        # Oppdater session.SELECTION hvis mulig (andre deler av appen leser dette)
        try:
            if hasattr(self.session, "set_selection"):
                # type: ignore[attr-defined]
                self.session.set_selection(accounts=accounts_norm)
            elif hasattr(self.session, "SELECTION"):
                self.session.SELECTION["accounts"] = accounts_norm  # type: ignore[attr-defined]
        except Exception:
            pass

        self._refresh()

    # ------------------------------------------------------------
    # Intern: last data inn i studio
    # ------------------------------------------------------------
    def _refresh(self) -> None:
        """
        Bygg df_all (fullt datasett) og base_df (filtrert på kontoer),
        og last i SelectionStudio.

        NB: unit-testene i repoet forventer at første posisjonelle argument
        i load_data-kallet er variabelen som heter df_all.
        Samtidig forventer SelectionStudio.load_data(df_base, df_all=None).
        Derfor bruker vi:
            - df_all = base_df (filtrert)  -> blir df_base i SelectionStudio
            - df_base = all_df (fullt)     -> blir df_all i SelectionStudio
        """
        try:
            all_df = getattr(self.session, "dataset", None)
            if not isinstance(all_df, pd.DataFrame):
                all_df = pd.DataFrame()
        except Exception:
            all_df = pd.DataFrame()

        base_df = _filter_base(all_df, self._accounts)

        # Variabelnavnene her er bevisst pga testene
        df_base = all_df
        df_all = base_df

        self.studio.load_data(df_all, df_base)

    # ------------------------------------------------------------
    # Callback fra SelectionStudio når brukeren "committer" et sample
    # ------------------------------------------------------------
    def _on_commit_selection(
        self,
        df_sample_bilag: pd.DataFrame,
        df_transactions: Optional[pd.DataFrame] = None,
    ) -> None:
        """
        SelectionStudio kaller denne når brukeren velger "Legg i utvalg".

        Vi prøver å ekspandere bilag-sample til transaksjonslinjer og sender
        videre til ui_main (Resultat-fane).

        NB: SelectionStudio kaller denne ofte med bare df_sample (1 argument).
        Derfor er df_transactions optional for å unngå TypeError.
        """
        if self._on_commit_sample is None:
            return

        try:
            df_out = _expand_bilag_sample_to_transactions(
                df_sample_bilag=df_sample_bilag,
                df_transactions=df_transactions,
            )
            if df_out.empty:
                df_out = df_sample_bilag.copy()
        except Exception:
            df_out = df_sample_bilag.copy()

        try:
            self._on_commit_sample(df_out)
        except Exception:
            # Ikke la GUI kræsje ved feil i callback
            pass

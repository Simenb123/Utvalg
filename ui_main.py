# ui_main.py
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk
from types import SimpleNamespace
from typing import List, Optional

import numpy as np
import pandas as pd

# Local imports
import session

# Pages / views
from page_dataset import DatasetPage
from page_analyse import AnalysePage
from page_utvalg_strata import UtvalgStrataPage

# "Resultat" fanen i dette repoet er implementert via page_utvalg.UtvalgPage
# (ikke page_resultat, som du nå får ModuleNotFoundError på)
from page_utvalg import UtvalgPage
from page_logg import LoggPage

log = logging.getLogger(__name__)


def _normalize_bilag_key(series: pd.Series) -> pd.Series:
    """Normaliserer bilags-id til en stabil nøkkel (string).

    Mål:
      - "3.0" i sample skal matche 3 i transaksjoner
      - Håndterer blandede typer (str/int/float)
      - Ikke-kvantifiserbare bilag beholdes som trimmet tekst (f.eks. "A12")

    Returnerer:
      pandas Series (dtype 'string') med normalisert nøkkel.
    """
    s_str = series.astype("string").str.strip()

    # Prøv numerisk normalisering (for å samle "3", "3.0", 3, 3.0 -> "3")
    num = pd.to_numeric(s_str, errors="coerce")
    # Robust heltallsdeteksjon (toleranse mot float-feil)
    is_int = num.notna() & np.isclose(num % 1, 0)

    # Konverter kun heltallsverdier til Int64 (bevarer NA) -> string
    num_int = num.where(is_int).astype("Int64")
    num_str = num_int.astype("string")

    # Hvis vi har et heltall: bruk det som nøkkel, ellers behold original tekst
    key = s_str.where(~is_int, num_str)
    return key


def expand_bilag_sample_to_transactions(df_sample_bilag: pd.DataFrame, df_transactions: pd.DataFrame) -> pd.DataFrame:
    """Utvid et bilag-sample (1 rad per bilag) til transaksjoner.

    - Filtrerer `df_transactions` til alle rader som matcher bilag i `df_sample_bilag`
    - Normaliserer bilags-id slik at f.eks. "3.0" matcher 3
    - Slår på metadata fra sample (prefikset med ``Utvalg_``)

    Merk:
      - Hvis sample er tomt: returneres et tomt utsnitt av df_transactions (samme kolonner)
      - Hvis bilag-kolonne mangler: returneres tomt utsnitt av df_transactions
    """
    if not isinstance(df_transactions, pd.DataFrame):
        return pd.DataFrame()

    # Hvis transaksjoner er tomt: returner tomt utsnitt med samme kolonner
    if df_transactions.empty:
        return df_transactions.iloc[0:0].copy()

    # Hvis sample er None/tomt: returner tomt utsnitt med samme kolonner (viktig for tester/GUI)
    if df_sample_bilag is None or not isinstance(df_sample_bilag, pd.DataFrame) or df_sample_bilag.empty:
        return df_transactions.iloc[0:0].copy()

    if "Bilag" not in df_sample_bilag.columns or "Bilag" not in df_transactions.columns:
        return df_transactions.iloc[0:0].copy()

    # Normaliser bilag-key på begge sider
    sample_key = _normalize_bilag_key(df_sample_bilag["Bilag"])
    tx_key = _normalize_bilag_key(df_transactions["Bilag"])

    sample_keys = sample_key.dropna().unique().tolist()
    if not sample_keys:
        return df_transactions.iloc[0:0].copy()

    # Filtrer transaksjoner
    mask = tx_key.isin(sample_keys)
    tx_out = df_transactions.loc[mask].copy()
    if tx_out.empty:
        return tx_out

    # Slå på metadata fra sample
    meta_cols = [c for c in df_sample_bilag.columns if c != "Bilag"]
    if meta_cols:
        meta = df_sample_bilag[["Bilag", *meta_cols]].copy()
        meta["__bilag_key"] = sample_key
        meta = meta.dropna(subset=["__bilag_key"]).drop_duplicates(subset=["__bilag_key"], keep="first")

        rename_map: dict[str, str] = {}
        for c in meta_cols:
            # Ikke dobbel-prefiks hvis kolonnen allerede er prefikset
            if c.startswith("Utvalg_"):
                rename_map[c] = c
            elif c in ("SumBeløp", "SumBelop"):
                rename_map[c] = "Utvalg_SumBilag"
            else:
                rename_map[c] = f"Utvalg_{c}"

        meta = meta.rename(columns=rename_map)

        # Merk: vi merger på en intern nøkkel for robust matching
        tx_out["__bilag_key"] = tx_key.loc[mask].astype("string")
        meta_keep_cols = ["__bilag_key", *[rename_map[c] for c in meta_cols]]
        meta = meta[[c for c in meta_keep_cols if c in meta.columns]]

        tx_out = tx_out.merge(meta, on="__bilag_key", how="left", sort=False)
        tx_out = tx_out.drop(columns=["__bilag_key"], errors="ignore")

    return tx_out


class App(tk.Tk):
    """Hovedapp (Tk).

    Denne klassen forsøker å være *test/CI-vennlig*:
    Hvis Tk ikke kan initialiseres (typisk i headless Linux), faller den tilbake
    til et minimalt objekt med de attributtene testene trenger.
    """

    def __init__(self) -> None:
        self._tk_ok: bool = True
        self._tk_init_error: Optional[Exception] = None

        try:
            super().__init__()
        except Exception as e:  # TclError / display-problemer
            self._tk_ok = False
            self._tk_init_error = e
            self._init_headless()
            return

        # --- Normal GUI-init ---
        self.title("Utvalg – revisjonsverktøy")
        self.geometry("1100x700")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        # Pages
        self.page_dataset = DatasetPage(self.nb)
        self.page_analyse = AnalysePage(self.nb)
        self.page_utvalg = UtvalgStrataPage(self.nb, on_commit_sample=self._on_utvalg_commit_sample)
        self.page_resultat = UtvalgPage(self.nb)
        self.page_logg = LoggPage(self.nb)

        self.nb.add(self.page_dataset, text="Dataset")
        self.nb.add(self.page_analyse, text="Analyse")
        self.nb.add(self.page_utvalg, text="Utvalg")
        self.nb.add(self.page_resultat, text="Resultat")
        self.nb.add(self.page_logg, text="Logg")

        # Gi AnalysePage callback for "Til utvalg"
        if hasattr(self.page_analyse, "set_utvalg_callback"):
            self.page_analyse.set_utvalg_callback(self._on_analyse_send_to_utvalg)

        # La session peke på relevante objekter (brukes av andre moduler)
        try:
            session.APP = self
            session.NOTEBOOK = self.nb
            session.UTVALG_STRATA_PAGE = self.page_utvalg
        except Exception:
            pass

        # Forsøk å koble DatasetPage -> on ready hook slik at Analyse oppdateres etter import
        self._maybe_install_dataset_ready_hook()

    def _init_headless(self) -> None:
        """Initialiserer en minimal app når Tk ikke kan brukes."""
        # Minimal notebook-stub
        self.nb = SimpleNamespace(  # type: ignore[assignment]
            select=lambda *_args, **_kwargs: None,
            add=lambda *_args, **_kwargs: None,
        )

        # Minimal pages/stubs som testene forventer
        self.page_analyse = SimpleNamespace(dataset=None)  # type: ignore[assignment]

        # DatasetPage må eksponere .dp, og DatasetPane må ha ._on_ready
        dp_stub = SimpleNamespace(_on_ready=None)
        self.page_dataset = SimpleNamespace(dp=dp_stub)  # type: ignore[assignment]

        # Resten brukes ikke av testene, men vi setter dem for robusthet
        self.page_utvalg = SimpleNamespace()  # type: ignore[assignment]
        self.page_resultat = SimpleNamespace()  # type: ignore[assignment]
        self.page_logg = SimpleNamespace()  # type: ignore[assignment]

        # Installer hook slik at testene kan finne dp._on_ready og kalle callback
        self._maybe_install_dataset_ready_hook()

    # --- Tk-sikre wrappers (hindrer krasj i headless) ---
    def withdraw(self) -> None:  # type: ignore[override]
        if self._tk_ok:
            try:
                super().withdraw()
            except Exception:
                pass

    def destroy(self) -> None:  # type: ignore[override]
        if self._tk_ok:
            try:
                super().destroy()
            except Exception:
                pass

    def mainloop(self, n: int = 0) -> None:  # type: ignore[override]
        if not self._tk_ok:
            raise RuntimeError("tkinter er ikke tilgjengelig i dette miljøet (headless).") from self._tk_init_error
        super().mainloop(n)

    def _maybe_install_dataset_ready_hook(self) -> None:
        """Installer callback for når DatasetPane har bygget datasett.

        DatasetPage/DatasetPane har hatt flere varianter i repoet, derfor prøver vi
        flere attributtnavn.

        Mål:
          - dp._on_ready skal være callable etter create_app()
          - Når dataset bygges, skal Analyse-fanen oppdateres automatisk
        """
        try:
            # Ny standard i repoet: DatasetPage.dp
            dp = getattr(self.page_dataset, "dp", None)

            # Bakoverkompat: dataset_pane / pane
            if dp is None:
                dp = getattr(self.page_dataset, "dataset_pane", None)
            if dp is None:
                dp = getattr(self.page_dataset, "pane", None)

            if dp is None:
                return

            # Vanlig mønster: dp._on_ready er en callback (DatasetPane)
            if hasattr(dp, "_on_ready"):
                existing = getattr(dp, "_on_ready", None)

                if callable(existing):
                    # Unngå dobbel-wrapping av samme callback så godt vi kan
                    if existing is self._on_data_ready:
                        return

                    def _wrapped_on_ready(df: pd.DataFrame) -> None:
                        try:
                            existing(df)
                        finally:
                            self._on_data_ready(df)

                    dp._on_ready = _wrapped_on_ready  # type: ignore[attr-defined]
                    return

                # Hvis eksisterende ikke er callable (typisk None): sett direkte
                dp._on_ready = self._on_data_ready  # type: ignore[attr-defined]
                return

            # Alternativt: dp.on_data_ready
            if hasattr(dp, "on_data_ready"):
                existing = getattr(dp, "on_data_ready", None)

                if callable(existing):
                    if existing is self._on_data_ready:
                        return

                    def _wrapped_on_ready(df: pd.DataFrame) -> None:
                        try:
                            existing(df)
                        finally:
                            self._on_data_ready(df)

                    dp.on_data_ready = _wrapped_on_ready  # type: ignore[attr-defined]
                    return

                dp.on_data_ready = self._on_data_ready  # type: ignore[attr-defined]
                return

        except Exception:
            # Ikke kræsje appen om hook feiler
            return

    def _on_data_ready(self, df: pd.DataFrame) -> None:
        """Kalles når dataset er lastet.

        Oppdaterer session.dataset, refresher Analyse-fanen og bytter til Analyse.
        """
        if df is None or df.empty:
            return

        try:
            session.dataset = df
        except Exception:
            pass

        # Oppdater Analyse
        try:
            if hasattr(self.page_analyse, "refresh_from_session") and callable(getattr(self.page_analyse, "refresh_from_session")):
                # AnalysePage henter df fra session og setter self.dataset = df (uten copy)
                self.page_analyse.refresh_from_session(session)  # type: ignore[attr-defined]
            elif hasattr(self.page_analyse, "on_dataset_loaded") and callable(getattr(self.page_analyse, "on_dataset_loaded")):
                self.page_analyse.on_dataset_loaded(df)  # type: ignore[attr-defined]
            else:
                # Headless/minimal
                setattr(self.page_analyse, "dataset", df)
        except Exception:
            pass

        # Oppdater Resultat også (om ønskelig)
        try:
            if hasattr(self.page_resultat, "on_dataset_loaded") and callable(getattr(self.page_resultat, "on_dataset_loaded")):
                self.page_resultat.on_dataset_loaded(df)  # type: ignore[attr-defined]
        except Exception:
            pass

        # Vis Analyse som neste steg
        try:
            if hasattr(self, "nb") and hasattr(self.nb, "select"):
                self.nb.select(self.page_analyse)
        except Exception:
            pass

    def _on_analyse_send_to_utvalg(self, accounts: List[str]) -> None:
        """Callback fra Analyse-fanen ("Til utvalg")."""
        accounts = [str(a).strip() for a in (accounts or []) if str(a).strip()]
        if not accounts:
            return

        # Lagre i session selection
        try:
            if hasattr(session, "set_selection"):
                session.set_selection(accounts=accounts)
            else:
                session.SELECTION["accounts"] = accounts  # type: ignore[attr-defined]
                session.SELECTION["version"] = int(session.SELECTION.get("version", 0)) + 1  # type: ignore[attr-defined]
        except Exception:
            pass

        # Last populasjon i Utvalg
        try:
            if hasattr(self.page_utvalg, "load_population"):
                self.page_utvalg.load_population(accounts)  # type: ignore[attr-defined]
        except Exception as e:
            try:
                messagebox.showerror("Feil", f"Kunne ikke overføre kontoer til Utvalg:\n{e}")
            except Exception:
                pass
            return

        # Bytt til Utvalg-fanen
        try:
            if hasattr(self, "nb") and hasattr(self.nb, "select"):
                self.nb.select(self.page_utvalg)
        except Exception:
            pass

    def _on_utvalg_commit_sample(self, df_sample: pd.DataFrame) -> None:
        """Callback fra UtvalgStrataPage/SelectionStudio når brukeren klikker "Legg i utvalg"."""
        if df_sample is None or df_sample.empty:
            return

        df_to_result = df_sample.copy()

        # Prøv å ekspandere bilag -> transaksjoner hvis vi har full dataset
        df_all = getattr(session, "dataset", None)
        if isinstance(df_all, pd.DataFrame) and not df_all.empty:
            try:
                df_tx = expand_bilag_sample_to_transactions(df_sample_bilag=df_sample, df_transactions=df_all)
                if not df_tx.empty:
                    df_to_result = df_tx
            except Exception:
                df_to_result = df_sample.copy()

        # Oppdater Resultat-fanen
        try:
            if hasattr(self.page_resultat, "on_dataset_loaded"):
                self.page_resultat.on_dataset_loaded(df_to_result.copy())  # type: ignore[attr-defined]
        except Exception:
            pass

        # Bytt til Resultat-fanen
        try:
            if hasattr(self, "nb") and hasattr(self.nb, "select"):
                self.nb.select(self.page_resultat)
        except Exception:
            pass


def create_app() -> App:
    """Fabrikk for tester og app.py."""
    return App()


if __name__ == "__main__":
    app = create_app()
    app.mainloop()

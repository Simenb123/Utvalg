from __future__ import annotations

"""page_utvalg_strata.py

Utvalg-fanen (stratifisering og trekk) – embedder SelectionStudio.

Historikk:
- Repoet har både en "ny" session.dataset (DataFrame) og en eldre
  session.get_dataset() -> (df, cols).
- Flere GUI-deler (DatasetPane/AnalysePage) bruker session.dataset direkte.

Denne siden er derfor skrevet defensivt:
- den henter primært DataFrame via session.dataset,
- men kan falle tilbake til session.get_dataset()[0] om nødvendig.
"""

from typing import Callable, List, Optional

import pandas as pd
import tkinter as tk
from tkinter import ttk

import session
from views_selection_studio import SelectionStudio


class UtvalgStrataPage(tk.Frame):
    """Utvalg-fane: stratifisering + trekk (SelectionStudio)."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_commit_sample: Optional[Callable[[pd.DataFrame], None]] = None,
        **_: object,
    ) -> None:
        super().__init__(master)
        self._on_commit_sample = on_commit_sample

        # Lokal (ev. filtrert) populasjon – hvis None bruker vi full session.dataset
        self.dataset: Optional[pd.DataFrame] = None

        # Header
        self.header_lbl = ttk.Label(self, text="")
        self.header_lbl.pack(anchor="w", padx=10, pady=(10, 0))

        # Studio: start med tomt datasett (oppdateres når session/delpopulasjon finnes)
        # Bakoverkompat: SelectionStudio bruker keyword `on_commit_selection`.
        # Tidligere kode sendte inn `on_commit` + et dummy-DataFrame som pos-arg.
        # Det krasjer nå etter refaktor. Vi oppretter derfor studio uten data her,
        # og laster data i `_refresh()` via `load_data()`.
        self.studio = SelectionStudio(self, on_commit_selection=self._handle_commit)
        self.studio.pack(fill="both", expand=True, padx=10, pady=10)

        # Last tilgjengelig dataset ved oppstart
        self._refresh()

    # ---- Public API -------------------------------------------------

    def refresh_from_session(self) -> None:
        """Oppdater visningen basert på gjeldende session."""
        self._refresh()

    def load_population(self, accounts: List[str]) -> None:
        """Filtrer populasjonen til gitte konti og oppdater studio.

        Brukes når Analyse-fanen sender over et utvalg av kontoer.
        """
        accounts = [str(a).strip() for a in (accounts or []) if str(a).strip()]

        df_all = self._get_session_df()
        if df_all is None or df_all.empty:
            self.dataset = None
            self._refresh()
            return

        # Hvis ingen kontoer er gitt, eller vi mangler Konto-kolonne, bruk hele datasettet.
        if not accounts or "Konto" not in df_all.columns:
            self.dataset = df_all
            self._refresh()
            return

        # Sørg for sammenlignbare strenger
        konto_str = df_all["Konto"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        self.dataset = df_all.loc[konto_str.isin(accounts)].copy()
        self._refresh()

    # ---- Internal ---------------------------------------------------

    def _get_session_df(self) -> Optional[pd.DataFrame]:
        """Hent DataFrame fra session på en robust måte."""
        # 1) Foretrukket: session.dataset
        try:
            df = getattr(session, "dataset", None)
        except Exception:
            df = None
        if isinstance(df, pd.DataFrame):
            return df

        # 2) Fallback: eldre API session.get_dataset() -> (df, cols)
        try:
            df2, _cols = session.get_dataset()  # type: ignore[misc]
            if isinstance(df2, pd.DataFrame):
                return df2
        except Exception:
            pass

        return None

    def _refresh(self) -> None:
        df_all = self._get_session_df()
        df_base = self.dataset if isinstance(self.dataset, pd.DataFrame) else df_all
        df_all_for_studio = df_all if isinstance(df_all, pd.DataFrame) else df_base

        if df_base is None or not isinstance(df_base, pd.DataFrame) or df_base.empty:
            self.header_lbl.config(text="Ingen dataset.")
            try:
                # Hold studioet "tomt" uten å kræsje
                empty = pd.DataFrame()
                # Ny signatur (foretrukket): load_data(df_all, df_base=None)
                try:
                    self.studio.load_data(empty, None)
                except TypeError:
                    # Eldre signatur (fallback): load_data(df_all) eller omvendt rekkefølge
                    try:
                        self.studio.load_data(empty)
                    except Exception:
                        try:
                            self.studio.load_data(None, empty)
                        except Exception:
                            pass
            except Exception:
                pass
            return

        total_sum = (
            pd.to_numeric(df_base.get("Beløp", pd.Series(dtype=float)), errors="coerce")
            .fillna(0.0)
            .sum()
        )

        header_txt = f"Grunnlag: {len(df_base):,} rader | Sum: {float(total_sum):,.2f}"
        header_txt = header_txt.replace(",", " ").replace(".", ",")
        self.header_lbl.config(text=header_txt)

        # Oppdater studioet med nytt grunnlag. Vi sender også med df_all slik at
        # valgfrie summeringer "alle kontoer" kan brukes.
        try:
            # Ny signatur (foretrukket): load_data(df_all, df_base=None)
            self.studio.load_data(df_all_for_studio, df_base)
        except TypeError:
            # Eldre signatur (fallback): load_data(df_base, df_all)
            try:
                self.studio.load_data(df_base, df_all_for_studio)
            except Exception:
                pass
        except Exception:
            pass

    def _handle_commit(self, sample_df: pd.DataFrame) -> None:
        """Kalles av SelectionStudio når bruker legger til i utvalg."""
        if callable(self._on_commit_sample):
            self._on_commit_sample(sample_df)

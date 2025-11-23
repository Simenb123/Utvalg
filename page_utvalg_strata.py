"""page_utvalg_strata.py

Utvalg-fanen: stratifisering og utvalgsverktøy.

Denne siden embedder SelectionStudio (stratifiserings-UI) i en ttk.Frame.
Analyse-fanen kan sende inn en populasjon (liste av kontonumre) via load_population().
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, List

import pandas as pd

import session  # type: ignore[import]
from views_selection_studio import SelectionStudio


class UtvalgStrataPage(ttk.Frame):
    """
    Fane for utvalgsarbeid (stratifisering).

    - Viser SelectionStudio (stratifiseringsverktøyet) som en del av fanen.
    - load_population(accounts) brukes for å laste inn ny populasjon.
    - on_commit_sample(df) kan brukes til å sende sample videre til Resultat-fanen.
    """

    def __init__(
        self,
        parent: tk.Misc,
        on_commit_sample: Optional[Callable[[pd.DataFrame], None]] = None,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(parent, *args, **kwargs)
        self.pack(fill="both", expand=True)

        self._on_commit_sample = on_commit_sample
        self._studio: Optional[SelectionStudio] = None

        # Start med tomt grunnlag – dette vil bli erstattet når Analyse sender inn populasjon
        empty = pd.DataFrame()
        self._studio = SelectionStudio(self, empty, self._handle_commit, df_all=None)
        self._studio.pack(fill="both", expand=True)

    # ---------------- API for Analyse/bus ----------------

    def load_population(self, accounts: List[str]) -> None:
        """
        Last inn en ny kontopopulasjon i Utvalg-fanen.

        accounts: liste av kontonumre (som strenger eller tall) valgt i Analyse-fanen.
        """
        df_all = getattr(session, "dataset", None)
        if not isinstance(df_all, pd.DataFrame) or df_all.empty:
            return

        if "Konto" not in df_all.columns:
            return

        accounts_str = [str(a) for a in accounts]
        df_base = df_all[df_all["Konto"].astype(str).isin(accounts_str)].copy()
        if df_base.empty:
            # Ingen rader for disse kontoene – ikke gjør noe
            return

        if self._studio is not None:
            self._studio.load_data(df_base, df_all)

    # ---------------- Intern callback ----------------

    def _handle_commit(self, df_sample: pd.DataFrame) -> None:
        """
        Callback fra SelectionStudio når brukeren klikker "Legg i utvalg".
        """
        if self._on_commit_sample is not None and df_sample is not None and not df_sample.empty:
            self._on_commit_sample(df_sample)

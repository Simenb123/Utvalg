"""
ui_main.py

Hovedvindu for Utvalg-prosjektet.

Fanestruktur:

- Dataset   : innlesing / bygging av hovedbokdatasett
- Analyse   : pivot / kontoanalyse og valg av populasjon (kontoer)
- Utvalg    : stratifisering og utvalgsarbeid (SelectionStudio som fane)
- Resultat  : transaksjonsvisning av valgt utvalg (tidligere Utvalg-fane)
- Logg      : logg / meldinger
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Optional, List

import pandas as pd

# Faner / sider
try:
    from page_dataset import DatasetPage
except Exception:  # pragma: no cover - fallback hvis modul mangler
    DatasetPage = ttk.Frame  # type: ignore[misc]

try:
    from page_analyse import AnalysePage
except Exception:  # pragma: no cover
    AnalysePage = ttk.Frame  # type: ignore[misc]

try:
    from page_utvalg_strata import UtvalgStrataPage
except Exception:  # pragma: no cover
    UtvalgStrataPage = ttk.Frame  # type: ignore[misc]

try:
    # Denne brukes som Resultat-fane (transaksjonsvisning)
    from page_utvalg import UtvalgPage
except Exception:  # pragma: no cover
    UtvalgPage = ttk.Frame  # type: ignore[misc]

try:
    from page_logg import LoggPage
except Exception:  # pragma: no cover
    LoggPage = ttk.Frame  # type: ignore[misc]

try:
    import session  # type: ignore[import]
except Exception:  # pragma: no cover
    session = None  # type: ignore[assignment]


class App(tk.Tk):
    """
    Hoved-application med Notebook og faner for Dataset, Analyse, Utvalg, Resultat og Logg.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.title("Utvalg – revisjonsverktøy")
        self.geometry("1280x800")

        # Notebook som holder fanene
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        # Dataset-fane
        self.page_dataset = DatasetPage(self.nb)
        self.nb.add(self.page_dataset, text="Dataset")
        # Når DatasetPane er ferdig med å bygge datasettet, vil vi gjerne
        # oppdatere Analyse-fanen automatisk. DatasetPane støtter en
        # on_dataset_ready-callback gjennom et privat attributt. Her
        # registrerer vi en lokal callback som gjør tre ting:
        #   1) Lagre datasettet til session (defensivt, DatasetPane gjør dette selv).
        #   2) Kalle AnalysePage.refresh_from_session() slik at pivoten
        #      blir bygget og vist.
        #   3) Bytte til Analyse-fanen i notebooken for å vise resultatet.
        try:
            dp = getattr(self.page_dataset, "dp", None)
            if dp is not None:
                def _on_data_ready(df: pd.DataFrame) -> None:
                    # Oppdater session med datasettet hvis modulen er importert
                    try:
                        if session is not None:
                            session.dataset = df  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    # Oppdater Analyse-fanen
                    try:
                        if hasattr(self.page_analyse, "refresh_from_session"):
                            # type: ignore[call-arg]
                            self.page_analyse.refresh_from_session(session)  # type: ignore[arg-type]
                    except Exception:
                        pass
                    # Bytt til Analyse-fanen for å vise pivoten
                    try:
                        self.nb.select(self.page_analyse)
                    except Exception:
                        pass
                # type: ignore[assignment]
                dp._on_ready = _on_data_ready  # registrer callback
        except Exception:
            # Hvis datasetpanelet mangler dp eller setting feiler, gjør ingenting
            pass

        # Analyse-fane
        self.page_analyse = AnalysePage(self.nb)
        self.nb.add(self.page_analyse, text="Analyse")

        # Utvalg-fane (stratifisering / SelectionStudio som Frame)
        self.page_utvalg = UtvalgStrataPage(
            self.nb,
            on_commit_sample=self._on_utvalg_commit_sample,
        )
        self.nb.add(self.page_utvalg, text="Utvalg")

        # Resultat-fane (gammel Utvalg-fane – transaksjonsliste)
        self.page_resultat = UtvalgPage(self.nb)
        self.nb.add(self.page_resultat, text="Resultat")

        # Logg-fane
        self.page_logg = LoggPage(self.nb)
        self.nb.add(self.page_logg, text="Logg")

        # Eksponer noen referanser i session for enkel tilgang fra andre moduler
        if session is not None:
            try:
                session.APP = self                  # type: ignore[attr-defined]
                session.NOTEBOOK = self.nb          # type: ignore[attr-defined]
                session.UTVALG_STRATA_PAGE = self.page_utvalg  # type: ignore[attr-defined]
                session.RESULTAT_PAGE = self.page_resultat     # type: ignore[attr-defined]
            except Exception:
                # Hvis session-modul ikke har disse feltene fra før, gjør vi ingenting ekstra
                pass

        # Valgfritt: hvis AnalysePage har støtte for å registrere callback, koble den til her.
        # Da kan "Til utvalg"-knappen i Analyse kalle tilbake hit.
        try:
            if hasattr(self.page_analyse, "set_utvalg_callback"):
                # type: ignore[call-arg]
                self.page_analyse.set_utvalg_callback(self._on_analyse_send_to_utvalg)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Dataflyt mellom Utvalg (stratifisering) og Resultat
    # ------------------------------------------------------------------

    def _on_utvalg_commit_sample(self, df_sample: pd.DataFrame) -> None:
        """
        Callback brukt av UtvalgStrataPage/SelectionStudio når brukeren klikker "Legg i utvalg".

        Vi legger da sample i Resultat-fanen og bytter tab dit.
        """
        if df_sample is None or df_sample.empty:
            return

        # UtvalgPage (Resultat) har allerede en on_dataset_loaded-metode som kan gjenbrukes
        try:
            if hasattr(self.page_resultat, "on_dataset_loaded"):
                # type: ignore[call-arg]
                self.page_resultat.on_dataset_loaded(df_sample.copy())
        except Exception:
            # Vi vil ikke krasje hele appen om noe feiler her
            pass

        # Bytt til Resultat-fanen
        try:
            self.nb.select(self.page_resultat)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Callback fra Analyse-fanen for å sende kontopopulasjon til Utvalg
    # ------------------------------------------------------------------

    def _on_analyse_send_to_utvalg(self, accounts: List[str]) -> None:
        """
        Callback som Analyse-fanen kan bruke for å sende kontopopulasjon
        direkte til Utvalg-fanen (stratifisering).

        Forventes at accounts er en liste med kontonumre (str eller tall).
        """
        accounts = [str(a) for a in (accounts or [])]
        if not accounts:
            return

        # Oppdater session.SELECTION for bakoverkompatibilitet / andre moduler
        if session is not None:
            try:
                sel = getattr(session, "SELECTION", {}) or {}
                sel["accounts"] = accounts
                sel["version"] = int(sel.get("version", 0)) + 1
                session.SELECTION = sel  # type: ignore[attr-defined]
            except Exception:
                pass

        # Last populasjonen inn i UtvalgStrataPage (stratifisering)
        try:
            if hasattr(self.page_utvalg, "load_population"):
                # type: ignore[call-arg]
                self.page_utvalg.load_population(accounts)
        except Exception:
            pass

        # Bytt til Utvalg-fanen
        try:
            self.nb.select(self.page_utvalg)
        except Exception:
            pass


def create_app() -> App:
    """
    Fabrikkfunksjon for å opprette App. Kan brukes i tester.
    """
    return App()


if __name__ == "__main__":
    app = create_app()
    app.mainloop()
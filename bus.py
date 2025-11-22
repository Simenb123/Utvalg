"""
En veldig enkel "event-bus" for Utvalg-prosjektet.

Hovedformål nå:
- Koble Analyse-fanen (page_analyse) mot Utvalg-fanen (page_utvalg)
  via SELECTION_SET_ACCOUNTS-eventet.
- Gi UtvalgPage mulighet til å registrere seg (set_utvalg_page/get_utvalg_page).
- Åpne stratifiseringsvinduet (SelectionStudio) automatisk når Analyse sender kontoer
  til utvalg.

Når Analyse kaller:

    emit("SELECTION_SET_ACCOUNTS", {"accounts": accounts})

vil vi:
- be UtvalgPage om å oppdatere filtrene (apply_filters), og
- automatisk åpne stratifiseringsvinduet (SelectionStudio) for videre arbeid.
"""

from __future__ import annotations

from typing import Any, Optional

# Global referanse til UtvalgPage (registreres fra page_utvalg.UtvalgPage.__init__)
_UTVALG_PAGE: Optional[object] = None


def set_utvalg_page(page: object) -> None:
    """
    Registrer UtvalgPage-instansen slik at bus kan nå den.

    Kalles fra page_utvalg.UtvalgPage.__init__.
    """
    global _UTVALG_PAGE
    _UTVALG_PAGE = page


def get_utvalg_page() -> Optional[object]:
    """Returner sist registrerte UtvalgPage, eller None hvis ingen er satt."""
    return _UTVALG_PAGE


def emit(event_name: str, data: Any = None) -> None:
    """
    Enkelt event-kall.

    Kjente events:
    - "UTVALG_PAGE_READY": (page_utvalg) – vi sørger for at UtvalgPage er registrert.
    - "SELECTION_SET_ACCOUNTS": (page_analyse) – når kontoer er valgt og sendt til utvalg.

    Alle andre events ignoreres stille (no-op) for bakoverkompatibilitet.
    """
    # Utvalg-fanen er klar – sørg for at den er registrert
    if event_name == "UTVALG_PAGE_READY":
        if data is not None:
            set_utvalg_page(data)
        return

    # Analyse har sendt kontoer til utvalg (definert populasjon)
    # -> oppdater Utvalg-fanen og åpne stratifisering direkte.
    if event_name == "SELECTION_SET_ACCOUNTS":
        _handle_selection_set_accounts(data)
        return

    # Ukjente events: ikke gjør noe (bevisst no-op)
    return


def _handle_selection_set_accounts(data: Any) -> None:
    """
    Håndterer SELECTION_SET_ACCOUNTS-eventet.

    data forventes å være et dict med minst nøkkelen "accounts".
    """
    try:
        accounts = []
        if isinstance(data, dict):
            accounts = data.get("accounts") or []
        # normaliser til strenger
        accounts = [str(a) for a in accounts]
    except Exception:
        accounts = []

    # 1) Oppdater Utvalg-fanen (hvis den finnes)
    page = get_utvalg_page()

    def _update_utvalg_and_open() -> None:
        # Oppdater Utvalg-fanen sitt grunnlag
        try:
            if page is not None and hasattr(page, "apply_filters"):
                page.apply_filters()  # type: ignore[call-arg]
        except Exception:
            # Feil i UtvalgPage skal ikke krasje hele GUI-et
            pass

        # 2) Åpne SelectionStudio direkte på valgt kontopopulasjon
        try:
            import tkinter as tk
            import pandas as pd
            import session  # type: ignore[import]

            from views_selection_studio import SelectionStudio  # type: ignore[import]

            df_all = getattr(session, "dataset", None)
            if not isinstance(df_all, pd.DataFrame) or not len(df_all):
                return

            if not accounts:
                return

            if "Konto" not in df_all.columns:
                return

            df_base = df_all[df_all["Konto"].astype(str).isin(accounts)].copy()
            if df_base.empty:
                return

            # Bruk hovedvinduet (Tk root) som master, evt. UtvalgPage hvis root mangler
            master = tk._default_root or page  # type: ignore[attr-defined]
            if master is None:
                return

            SelectionStudio(master, df_base, on_commit=None, df_all=df_all)

        except Exception:
            # Alle feil i denne delen vises uansett som messagebox i SelectionStudio,
            # eller ignoreres hvis import feiler. Vi vil ikke krasje hele appen.
            pass

    # Kjører vi i en Tk-widget, bruk after() for å kjøre i GUI-tråden
    if page is not None and hasattr(page, "after"):
        try:
            page.after(0, _update_utvalg_and_open)  # type: ignore[attr-defined]
        except Exception:
            _update_utvalg_and_open()
    else:
        _update_utvalg_and_open()

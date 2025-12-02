"""
bus.py

En veldig enkel "event-bus" for Utvalg-prosjektet.

Hovedformål nå:
- Koble Analyse-fanen mot Utvalg-fanen via SELECTION_SET_ACCOUNTS-eventet.
- Gi UtvalgPage (Resultat) mulighet til å registrere seg (set_utvalg_page/get_utvalg_page)
  for eventuell senere bruk.

Når Analyse kaller:

    emit("SELECTION_SET_ACCOUNTS", {"accounts": accounts})

vil vi:
- oppdatere session.SELECTION med kontolisten,
- be UtvalgStrataPage (Utvalg-fanen) om å laste inn populasjonen,
- og automatisk bytte til Utvalg-fanen.
"""

from __future__ import annotations

from typing import Any, Optional, List

# Global referanse til (gamle) UtvalgPage/Resultat, hvis noen vil bruke den
_UTVALG_PAGE: Optional[object] = None


def set_utvalg_page(page: object) -> None:
    """
    Registrer UtvalgPage-instansen slik at bus kan nå den.

    Kalles typisk fra page_utvalg.UtvalgPage.__init__.
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
    if event_name == "UTVALG_PAGE_READY":
        # Enkel måte for UtvalgPage (Resultat) å si "her er jeg"
        if data is not None:
            set_utvalg_page(data)
        return

    if event_name == "SELECTION_SET_ACCOUNTS":
        _handle_selection_set_accounts(data)
        return

    # Ukjente events: bevisst no-op
    return


def _handle_selection_set_accounts(data: Any) -> None:
    """
    Håndterer SELECTION_SET_ACCOUNTS-eventet.

    data forventes å være et dict med minst nøkkelen "accounts".
    Vi forsøker å være robuste ved feil typer/innhold.
    """
    try:
        accounts: List[str] = []
        if isinstance(data, dict):
            raw = data.get("accounts") or []
            accounts = [str(a) for a in raw]
    except Exception:
        accounts = []

    if not accounts:
        # Ingen kontoer å jobbe med
        return

    # Vi trenger session for å:
    # - oppdatere SELECTION (for bakoverkomp / logging)
    # - finne UTVALG_STRATA_PAGE (Utvalg-fanen) og NOTEBOOK (tab-kontroll)
    try:
        import session  # type: ignore[import]
    except Exception:
        session = None  # type: ignore[assignment]

    # 1) Oppdater session.SELECTION
    if session is not None:
        try:
            sel = getattr(session, "SELECTION", {}) or {}
            sel["accounts"] = accounts
            sel["version"] = int(sel.get("version", 0)) + 1
            session.SELECTION = sel  # type: ignore[attr-defined]
        except Exception:
            # Vi svelger feil her – SELECTION er kun informativt
            pass

    # 2) Last populasjonen inn i Utvalg-fanen (stratifisering)
    utvalg_strata_page = None
    nb = None

    if session is not None:
        try:
            utvalg_strata_page = getattr(session, "UTVALG_STRATA_PAGE", None)
        except Exception:
            utvalg_strata_page = None
        try:
            nb = getattr(session, "NOTEBOOK", None)
        except Exception:
            nb = None

    def _do_update() -> None:
        # Be UtvalgStrataPage laste inn populasjonen
        try:
            if utvalg_strata_page is not None and hasattr(utvalg_strata_page, "load_population"):
                # type: ignore[call-arg]
                utvalg_strata_page.load_population(accounts)
        except Exception:
            # Vi vil ikke krasje hele appen hvis noe går galt her
            pass

        # Bytt til Utvalg-fanen
        try:
            if nb is not None and utvalg_strata_page is not None:
                nb.select(utvalg_strata_page)  # type: ignore[arg-type]
        except Exception:
            pass

    # Hvis vi har en Tk-widget (f.eks. UtvalgStrataPage), bruk after() for å kjøre i GUI-tråden
    if utvalg_strata_page is not None and hasattr(utvalg_strata_page, "after"):
        try:
            # type: ignore[attr-defined]
            utvalg_strata_page.after(0, _do_update)
        except Exception:
            _do_update()
    else:
        _do_update()

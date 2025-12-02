"""
Tester grunnegenskaper ved Analyse-siden uten å være avhengig av
detaljert GUI‑oppførsel.

Målet er å sikre at:
* det finnes en AnalysePage‑klasse i page_analyse‑modulen
* den eksponerer en metode refresh_from_session(session)
  slik at vi kan bruke sesjonsobjektet til å oppdatere analysen.

Disse testene er bevisst "lette" – de verifiserer interface / kontrakt,
ikke hele funksjonaliteten i GUI-et.
"""

from __future__ import annotations

import inspect
import types
from typing import Any


def _get_module(name: str) -> types.ModuleType:
    """Liten hjelpefunksjon for å gi litt hyggeligere feilmeldinger."""
    try:
        module = __import__(name)
    except Exception as exc:  # pragma: no cover - bare feilrapportering
        raise AssertionError(f"Kunne ikke importere modulen {name!r}: {exc}") from exc
    return module


def test_analysepage_class_exists() -> None:
    """Sjekk at page_analyse.AnalysePage finnes."""
    page_analyse = _get_module("page_analyse")

    assert hasattr(
        page_analyse, "AnalysePage"
    ), "Forventer en klasse 'AnalysePage' i page_analyse.py"

    AnalysePage = getattr(page_analyse, "AnalysePage")
    assert inspect.isclass(AnalysePage), "AnalysePage må være en klasse"


def test_analysepage_has_refresh_from_session_method() -> None:
    """
    AnalysePage skal ha en metode refresh_from_session(self, session).

    Vi sjekker signaturen på metoden – ikke selve logikken – for å unngå
    å gjøre testen skjør mot detaljer i GUI‑implementasjonen.
    """
    page_analyse = _get_module("page_analyse")
    AnalysePage = getattr(page_analyse, "AnalysePage")

    assert hasattr(
        AnalysePage, "refresh_from_session"
    ), "AnalysePage mangler refresh_from_session(self, session)"

    fn = getattr(AnalysePage, "refresh_from_session")
    # På klasse‑nivå får vi ut funksjonsobjektet (ikke bound method)
    assert inspect.isfunction(fn), "refresh_from_session bør være en vanlig metode"

    sig = inspect.signature(fn)
    params = list(sig.parameters.values())

    # Typisk: (self, session)
    assert (
        len(params) >= 2
    ), "refresh_from_session bør minst ta self og session som argumenter"

    # Første param er 'self'-lignende navn, det bryr vi oss ikke om.
    second: Any = params[1]
    assert second.name in {
        "session",
        "sess",
    }, "Andre parameter på refresh_from_session bør hete 'session' (eller lignende)"


def test_analysepage_refresh_from_session_is_callable(monkeypatch) -> None:
    """
    Vi verifiserer at refresh_from_session kan kalles med et sesjonsobjekt.

    Selve session‑klassen kan utvikles videre over tid, så vi bruker et
    minimalt dummy‑objekt her. Poenget er at metoden ikke skal kaste
    exception i normal bruk.
    """

    class DummySession:
        """Minimal stand‑in for session.Session i dette testscenariet."""

        def __init__(self) -> None:
            # Mange implementasjoner forventer et eller flere attributter;
            # vi kan enkelt legge til flere her etter behov.
            self.dataset = None

    page_analyse = _get_module("page_analyse")
    AnalysePage = getattr(page_analyse, "AnalysePage")

    # Vi instansierer uten å binde oss til hvordan Tk‑hierarkiet ser ut:
    # parent-argumentet kan være None, forutsatt at implementasjonen håndterer det.
    page = AnalysePage(None)  # type: ignore[arg-type]

    session = DummySession()

    # Selve kallet – testen vil feile hvis dette kaster unntak.
    page.refresh_from_session(session)

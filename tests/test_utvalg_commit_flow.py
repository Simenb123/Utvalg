"""
Tester grunnegenskaper ved Utvalg‑stratifiseringsfanen (page_utvalg_strata).

Hensikt:
* Det skal finnes en klasse UtvalgStrataPage i page_utvalg_strata.py.
* Klassen skal ha minst én "commit"-relatert metode på klassens namespace
  (f.eks. _on_commit_sample, handle_commit, commit_selection el.l.).
* Vi sjekker hovedsakelig interface / overflate – ikke hele GUI‑logikken –
  slik at testen er robust mot interne endringer i Tkinter‑strukturen.
"""

from __future__ import annotations

import inspect
import types


def _get_module(name: str) -> types.ModuleType:
    try:
        module = __import__(name)
    except Exception as exc:  # pragma: no cover - ren feilrapportering
        raise AssertionError(f"Kunne ikke importere modulen {name!r}: {exc}") from exc
    return module


def test_utvalgstratapage_class_exists() -> None:
    """Sjekk at page_utvalg_strata.UtvalgStrataPage finnes og er en klasse."""
    mod = _get_module("page_utvalg_strata")

    assert hasattr(
        mod, "UtvalgStrataPage"
    ), "Forventer en klasse 'UtvalgStrataPage' i page_utvalg_strata.py"

    cls = getattr(mod, "UtvalgStrataPage")
    assert inspect.isclass(cls), "UtvalgStrataPage må være en klasse"


def test_utvalgstratapage_init_signature_is_reasonable() -> None:
    """
    __init__ skal i det minste ta parent‑argumentet.

    Mange implementasjoner vil også ta f.eks. session, bus eller callbacks,
    men de detaljene ønsker vi ikke å hardkode i testen (for å unngå
    unødvendige breaking changes når GUI-et utvikles videre).
    """
    mod = _get_module("page_utvalg_strata")
    cls = getattr(mod, "UtvalgStrataPage")

    sig = inspect.signature(cls.__init__)
    params = list(sig.parameters.values())

    # Typisk: (self, parent, ...)
    # Vi sjekker bare at det finnes minst self + én til.
    assert (
        len(params) >= 2
    ), "__init__ til UtvalgStrataPage bør minst ta (self, parent, ...)"


def test_utvalgstratapage_has_some_commit_like_method() -> None:
    """
    UtvalgStrataPage skal eksponere minst én metode som har 'commit' i navnet.

    Dette sikrer at det finnes en tydelig "vei ut" fra stratifiseringsvinduet
    der et sample/utvalg kan sendes videre til resten av applikasjonen
    (f.eks. via bus eller direkte callback).
    """
    mod = _get_module("page_utvalg_strata")
    cls = getattr(mod, "UtvalgStrataPage")

    commit_like = [
        name
        for name in dir(cls)
        if "commit" in name.lower() and not name.startswith("__")
    ]

    assert (
        commit_like
    ), "UtvalgStrataPage bør ha minst én commit‑relatert metode på klassens namespace"

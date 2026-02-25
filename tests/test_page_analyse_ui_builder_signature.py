from __future__ import annotations

import inspect


def test_build_ui_accepts_injected_modules() -> None:
    """Regression test.

    AnalysePage bygger UI ved å kalle page_analyse_ui.build_ui(..., tk=..., ttk=...).
    Dette skal ikke kaste TypeError ("unexpected keyword argument") på plattformer
    der Tk er tilgjengelig (typisk Windows).

    Vi verifiserer kun signaturen her for å unngå å måtte starte et faktisk
    Tk-vindu i testmiljøet.
    """

    import page_analyse_ui

    sig = inspect.signature(page_analyse_ui.build_ui)

    # build_ui skal støtte injisering av tk/ttk-moduler og dir_options.
    assert "tk" in sig.parameters
    assert "ttk" in sig.parameters
    assert "dir_options" in sig.parameters

    # Og vi skal kunne binde keyword-argumentene uten TypeError.
    sig.bind_partial(page=None, tk=None, ttk=None, dir_options=None)

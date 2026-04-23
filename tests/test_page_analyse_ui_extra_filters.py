from __future__ import annotations

from tests.test_page_analyse_ui_regressions import DummyPage, DummyTkModule, DummyTtkModule, _DirOpt


def test_build_ui_exposes_period_filters() -> None:
    """Periode-filterne skal fortsatt være bundet i toolbaren.

    NB: Bilag- og Motpart-feltene er fjernet fra toolbaren (sjelden brukt i
    Analyse-fanen). StringVars beholdes for filter-logikken, men det finnes
    ikke entry-widgets å binde Enter på lenger.
    """
    import page_analyse_ui

    page = DummyPage()

    page_analyse_ui.build_ui(
        page=page,
        tk=DummyTkModule,
        ttk=DummyTtkModule,
        dir_options=[_DirOpt("Alle"), _DirOpt("Debet"), _DirOpt("Kredit")],
    )

    assert "<Return>" in page._ent_date_from.bindings
    assert "<Return>" in page._ent_date_to.bindings
    assert "<<ComboboxSelected>>" in page._ent_date_from.bindings
    assert "<<ComboboxSelected>>" in page._ent_date_to.bindings
    assert list(page._ent_date_from.kwargs.get("values", ())) == ["", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
    assert list(page._ent_date_to.kwargs.get("values", ())) == ["", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]

    page._ent_date_from.bindings["<<ComboboxSelected>>"](None)
    assert page.calls.get("apply_now", 0) >= 1

    assert page._var_date_from.trace_calls
    assert page._var_date_to.trace_calls


def test_bilag_motpart_widgets_no_longer_in_toolbar() -> None:
    """Bilag/Motpart-widgetene er fjernet — page._ent_bilag/_ent_motpart skal være None."""
    import page_analyse_ui

    page = DummyPage()

    page_analyse_ui.build_ui(
        page=page,
        tk=DummyTkModule,
        ttk=DummyTtkModule,
        dir_options=[_DirOpt("Alle"), _DirOpt("Debet"), _DirOpt("Kredit")],
    )

    assert page._ent_bilag is None
    assert page._ent_motpart is None
    # StringVars beholdes så filter-logikken kan lese dem (no-op når tomme)
    assert page._var_bilag is not None
    assert page._var_motpart is not None


def test_advanced_filter_widgets_moved_out_of_toolbar() -> None:
    """MVA-kode, Min/Maks beløp er flyttet til 'Mer filter…'-popup."""
    import page_analyse_ui

    page = DummyPage()

    page_analyse_ui.build_ui(
        page=page,
        tk=DummyTkModule,
        ttk=DummyTtkModule,
        dir_options=[_DirOpt("Alle"), _DirOpt("Debet"), _DirOpt("Kredit")],
    )

    # Toolbar skal ikke lenger eksponere disse widgetene direkte.
    assert page._cmb_mva_code is None
    assert page._cmb_mva is None
    # Underliggende StringVars finnes fortsatt, og refresh_mva_codes m.fl. funker.
    assert page._var_mva_code is not None
    assert page._var_min is not None
    assert page._var_max is not None

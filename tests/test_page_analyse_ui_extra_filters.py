from __future__ import annotations

from tests.test_page_analyse_ui_regressions import DummyPage, DummyTkModule, DummyTtkModule, _DirOpt


def test_build_ui_exposes_bilag_motpart_and_period_filters() -> None:
    import page_analyse_ui

    page = DummyPage()

    page_analyse_ui.build_ui(
        page=page,
        tk=DummyTkModule,
        ttk=DummyTtkModule,
        dir_options=[_DirOpt("Alle"), _DirOpt("Debet"), _DirOpt("Kredit")],
    )

    assert "<Return>" in page._ent_bilag.bindings
    assert "<Return>" in page._ent_motpart.bindings
    assert "<Return>" in page._ent_date_from.bindings
    assert "<Return>" in page._ent_date_to.bindings
    assert "<<ComboboxSelected>>" in page._ent_date_from.bindings
    assert "<<ComboboxSelected>>" in page._ent_date_to.bindings
    assert list(page._ent_date_from.kwargs.get("values", ())) == ["", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
    assert list(page._ent_date_to.kwargs.get("values", ())) == ["", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]

    page._ent_bilag.bindings["<Return>"](None)
    page._ent_motpart.bindings["<Return>"](None)
    page._ent_date_from.bindings["<<ComboboxSelected>>"](None)
    assert page.calls.get("apply_now", 0) >= 2

    assert page._var_bilag.trace_calls
    assert page._var_motpart.trace_calls
    assert page._var_date_from.trace_calls
    assert page._var_date_to.trace_calls

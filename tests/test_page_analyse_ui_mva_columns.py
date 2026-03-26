from __future__ import annotations

from tests.test_page_analyse_ui_regressions import DummyPage, DummyTkModule, DummyTtkModule, _DirOpt


def test_build_ui_exposes_column_button_and_mva_filters() -> None:
    import page_analyse_ui

    page = DummyPage()
    page._mva_code_values = ["Alle", "1", "3", "25"]

    page_analyse_ui.build_ui(
        page=page,
        tk=DummyTkModule,
        ttk=DummyTtkModule,
        dir_options=[_DirOpt("Alle"), _DirOpt("Debet"), _DirOpt("Kredit")],
    )

    assert page._btn_columns.kwargs.get("state") == "normal"
    page._btn_columns.kwargs["command"]()
    assert page.calls.get("columns", 0) == 1

    assert "<Return>" in page._ent_mva.bindings
    page._ent_mva.bindings["<Return>"](None)
    assert page.calls.get("apply_now", 0) >= 1
    assert page._cmb_mva_code.kwargs.get("state") == "readonly"
    assert list(page._cmb_mva_code.kwargs.get("values", ())) == ["Alle", "1", "3", "25"]

    assert page._cmb_mva.kwargs.get("state") == "readonly"
    assert list(page._cmb_mva.kwargs.get("values", ())) == [
        "Alle",
        "Med MVA-kode",
        "Uten MVA-kode",
        "Med MVA-beløp",
        "Uten MVA-beløp",
        "MVA-avvik",
    ]

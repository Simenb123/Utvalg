from __future__ import annotations

from tests.test_page_analyse_ui_regressions import DummyPage, DummyTkModule, DummyTtkModule, _DirOpt


def test_build_ui_exposes_column_button() -> None:
    """Kolonner-knappen skal være aktiv og kalle riktig command.

    NB: MVA-kode og MVA-filter-comboboxene er flyttet ut av toolbar til
    "Mer filter…"-popup-dialogen. StringVars deles, og MVA_FILTER_OPTIONS-
    listen er fortsatt tilgjengelig som klassevariabel for popup-bygging.
    """
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

    # Toolbar har ikke lenger MVA-kode eller MVA-filter direkte.
    assert page._cmb_mva_code is None
    assert page._cmb_mva is None
    assert page._ent_mva is None

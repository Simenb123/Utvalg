from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_build_a07_overview_df_marks_ok_avvik_unmapped_and_excluded() -> None:
    a07_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1000.0},
            {"Kode": "bonus", "Navn": "Bonus", "Belop": 500.0},
            {"Kode": "aga", "Navn": "AGA", "Belop": 100.0},
        ]
    )
    reconcile_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "WithinTolerance": True, "AntallKontoer": 1, "Kontoer": "5000"},
            {"Kode": "bonus", "WithinTolerance": False, "AntallKontoer": 1, "Kontoer": "5090"},
        ]
    )

    out = page_a07.build_a07_overview_df(a07_df, reconcile_df)

    assert out.loc[out["Kode"] == "fastloenn", "Status"].iloc[0] == "OK"
    assert out.loc[out["Kode"] == "bonus", "Status"].iloc[0] == "Avvik"
    assert out.loc[out["Kode"] == "aga", "Status"].iloc[0] == "Ekskludert"

def test_count_unsolved_a07_codes_ignores_ok_and_excluded() -> None:
    overview_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Status": "OK"},
            {"Kode": "bonus", "Status": "Avvik"},
            {"Kode": "aga", "Status": "Ekskludert"},
            {"Kode": "feriepenger", "Status": "Ikke mappet"},
        ]
    )

    out = page_a07.count_unsolved_a07_codes(overview_df)

    assert out == 2

def test_filter_a07_overview_df_supports_unsolved_and_specific_statuses() -> None:
    overview_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Status": "OK"},
            {"Kode": "bonus", "Status": "Avvik"},
            {"Kode": "aga", "Status": "Ekskludert"},
            {"Kode": "feriepenger", "Status": "Ikke mappet"},
        ]
    )

    unresolved = page_a07.filter_a07_overview_df(overview_df, "uloste")
    only_deviation = page_a07.filter_a07_overview_df(overview_df, "avvik")
    only_unmapped = page_a07.filter_a07_overview_df(overview_df, "ikke_mappet")

    assert unresolved["Kode"].tolist() == ["bonus", "feriepenger"]
    assert only_deviation["Kode"].tolist() == ["bonus"]
    assert only_unmapped["Kode"].tolist() == ["feriepenger"]

def test_build_mapping_history_details_compares_current_and_previous_accounts() -> None:
    out = page_a07.build_mapping_history_details(
        "fastloenn",
        mapping_current={"5000": "fastloenn", "5090": "bonus"},
        mapping_previous={"5000": "fastloenn", "5001": "fastloenn"},
        previous_year="2024",
    )

    assert "fastloenn |" in out
    assert "I år: 5000" in out
    assert "2024: 5000, 5001" in out
    assert "Avviker fra historikk." in out

def test_safe_previous_accounts_for_code_requires_available_nonconflicting_accounts() -> None:
    gl_df = pd.DataFrame([{"Konto": "6990"}, {"Konto": "5940"}])

    out_ready = page_a07.safe_previous_accounts_for_code(
        "telefon",
        mapping_current={},
        mapping_previous={"6990": "telefon"},
        gl_df=gl_df,
    )
    out_conflict = page_a07.safe_previous_accounts_for_code(
        "pensjon",
        mapping_current={"5940": "annet"},
        mapping_previous={"5940": "pensjon"},
        gl_df=gl_df,
    )
    out_missing = page_a07.safe_previous_accounts_for_code(
        "fastloenn",
        mapping_current={},
        mapping_previous={"5000": "fastloenn"},
        gl_df=gl_df,
    )

    assert out_ready == ["6990"]
    assert out_conflict == []
    assert out_missing == []

def test_build_history_comparison_df_marks_same_ready_conflict_and_missing() -> None:
    a07_df = pd.DataFrame(
        [
            {"Kode": "bonus", "Navn": "Bonus"},
            {"Kode": "telefon", "Navn": "Telefon"},
            {"Kode": "pensjon", "Navn": "Pensjon"},
            {"Kode": "fastloenn", "Navn": "Fastloenn"},
            {"Kode": "feriepenger", "Navn": "Feriepenger"},
        ]
    )
    gl_df = pd.DataFrame(
        [
            {"Konto": "5090"},
            {"Konto": "6990"},
            {"Konto": "5940"},
        ]
    )

    out = page_a07.build_history_comparison_df(
        a07_df,
        gl_df,
        mapping_current={"5090": "bonus", "5940": "annet"},
        mapping_previous={
            "5090": "bonus",
            "6990": "telefon",
            "5940": "pensjon",
            "5000": "fastloenn",
        },
    )

    assert out.loc[out["Kode"] == "bonus", "Status"].iloc[0] == "Samme"
    assert out.loc[out["Kode"] == "telefon", "Status"].iloc[0] == "Klar fra historikk"
    assert bool(out.loc[out["Kode"] == "telefon", "KanBrukes"].iloc[0]) is True
    assert out.loc[out["Kode"] == "pensjon", "Status"].iloc[0] == "Konflikt"
    assert out.loc[out["Kode"] == "fastloenn", "Status"].iloc[0] == "Mangler konto"
    assert out.loc[out["Kode"] == "feriepenger", "Status"].iloc[0] == "Ingen historikk"

def test_select_safe_history_codes_returns_unique_ready_codes_only() -> None:
    history_df = pd.DataFrame(
        [
            {"Kode": "telefon", "KanBrukes": True},
            {"Kode": "telefon", "KanBrukes": True},
            {"Kode": "pensjon", "KanBrukes": False},
            {"Kode": "fastloenn", "KanBrukes": True},
        ]
    )

    out = page_a07.select_safe_history_codes(history_df)

    assert out == ["telefon", "fastloenn"]

def test_best_suggestion_row_for_code_returns_first_matching_row() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "bonus", "ForslagKontoer": "5000", "WithinTolerance": True},
            {"Kode": "bonus", "ForslagKontoer": "5001", "WithinTolerance": False},
            {"Kode": "telefon", "ForslagKontoer": "6990", "WithinTolerance": True},
        ]
    )

    out = page_a07.best_suggestion_row_for_code(suggestions_df, "bonus")

    assert out is not None
    assert str(out["ForslagKontoer"]) == "5000"

def test_build_control_suggestion_summary_includes_a07_and_gl_amounts() -> None:
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "feriepenger",
                "ForslagKontoer": "2932,2940",
                "ForslagVisning": "2932 Feriepenger mertid + 2940 Skyldig feriepenger",
                "A07_Belop": Decimal("862608.92"),
                "GL_Sum": Decimal("862608.92"),
                "Diff": Decimal("0"),
                "WithinTolerance": True,
                "SuggestionGuardrail": "accepted",
            },
        ]
    )

    out = page_a07.build_control_suggestion_summary("feriepenger", suggestions_df, suggestions_df.iloc[0])

    assert "A07 862 608,92" in out
    assert "SB forslag 862 608,92" in out
    assert "Diff 0,00" in out

def test_build_control_suggestion_effect_summary_describes_new_mapping() -> None:
    row = pd.Series({"ForslagKontoer": "5000,5001", "Diff": Decimal("12.50"), "WithinTolerance": True})

    out = page_a07.build_control_suggestion_effect_summary("bonus", [], row)
    diff_text = page_a07._format_picker_amount(Decimal("12.50"))

    assert out == f"Vil mappe 5000,5001 til bonus | Må vurderes | Diff {diff_text}"

def test_control_next_action_label_prioritizes_history_then_safe_suggestion() -> None:
    best_row = pd.Series({"WithinTolerance": True})
    weak_row = pd.Series({"WithinTolerance": False})

    assert (
        page_a07.control_next_action_label("Ikke mappet", has_history=True, best_suggestion=best_row)
        == "Se forslag for valgt kode."
    )
    assert (
        page_a07.control_next_action_label("Ikke mappet", has_history=False, best_suggestion=best_row)
        == "Se forslag for valgt kode."
    )
    assert (
        page_a07.control_next_action_label("Avvik", has_history=False, best_suggestion=weak_row)
        == "Se forslag for valgt kode."
    )
    assert (
        page_a07.control_next_action_label("OK", has_history=True, best_suggestion=best_row)
        == "Ingen handling nødvendig."
    )

def test_build_control_queue_df_summarizes_mapping_history_and_best_suggestion() -> None:
    overview_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1000.0, "Status": "Ikke mappet"},
            {"Kode": "telefon", "Navn": "Telefon", "Belop": 500.0, "Status": "Ikke mappet"},
            {"Kode": "bonus", "Navn": "Bonus", "Belop": 250.0, "Status": "OK"},
        ]
    )
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "telefon", "ForslagKontoer": "6990", "WithinTolerance": True, "Diff": 0.0},
            {"Kode": "bonus", "ForslagKontoer": "5090", "WithinTolerance": True, "Diff": 0.0},
        ]
    )
    gl_df = pd.DataFrame([{"Konto": "5000"}, {"Konto": "6990"}, {"Konto": "5090"}])

    out = page_a07.build_control_queue_df(
        overview_df,
        suggestions_df,
        mapping_current={"5090": "bonus"},
        mapping_previous={"5000": "fastloenn"},
        gl_df=gl_df,
        code_profile_state={"bonus": {"source": "manual"}},
    )

    assert out.loc[out["Kode"] == "fastloenn", "A07Post"].iloc[0] == "Fastloenn"
    assert out.loc[out["Kode"] == "fastloenn", "Anbefalt"].iloc[0] == "Se historikk"
    assert out.loc[out["Kode"] == "fastloenn", "NesteHandling"].iloc[0] == "Åpne historikk for valgt kode."
    assert out.loc[out["Kode"] == "fastloenn", "Status"].iloc[0] == "Har historikk"
    assert out.loc[out["Kode"] == "fastloenn", "GuidetStatus"].iloc[0] == "Har historikk"
    assert out.loc[out["Kode"] == "telefon", "Anbefalt"].iloc[0] == "Se forslag"
    assert out.loc[out["Kode"] == "telefon", "NesteHandling"].iloc[0] == "Belop uten stotte"
    assert out.loc[out["Kode"] == "telefon", "Status"].iloc[0] == "Har forslag"
    assert out.loc[out["Kode"] == "telefon", "GuidetStatus"].iloc[0] == "Har forslag"
    assert out.loc[out["Kode"] == "telefon", "SuggestionGuardrail"].iloc[0] == "review"
    assert out.loc[out["Kode"] == "fastloenn", "Arbeidsstatus"].iloc[0] == "Forslag"
    assert out.loc[out["Kode"] == "telefon", "Arbeidsstatus"].iloc[0] == "Forslag"
    assert out.loc[out["Kode"] == "bonus", "DagensMapping"].iloc[0] == "5090"
    assert out.loc[out["Kode"] == "bonus", "Status"].iloc[0] == "Kontroller kobling"
    assert out.loc[out["Kode"] == "bonus", "GuidetStatus"].iloc[0] == "Kontroller kobling"
    assert out.loc[out["Kode"] == "bonus", "Arbeidsstatus"].iloc[0] == "Manuell"
    assert out.loc[out["Kode"] == "bonus", "NesteHandling"].iloc[0] == "Kontroller dagens kobling."

def test_preferred_rf1022_overview_group_prioritizes_unknown_then_largest_diff() -> None:
    overview = pd.DataFrame(
        [
            {"GroupId": "100_loenn_ol", "A07": 100.0, "Diff": 500.0},
            {"GroupId": "uavklart_rf1022", "A07": 25.0, "Diff": 25.0},
            {"GroupId": "112_pensjon", "A07": 0.0, "Diff": 1000.0},
        ]
    )

    assert a07_control_data.preferred_rf1022_overview_group(overview, ["100_loenn_ol", "uavklart_rf1022"]) == "uavklart_rf1022"
    no_unknown_amount = overview.copy()
    no_unknown_amount.loc[no_unknown_amount["GroupId"] == "uavklart_rf1022", ["A07", "Diff"]] = 0.0

    assert (
        a07_control_data.preferred_rf1022_overview_group(
            no_unknown_amount,
            ["100_loenn_ol", "uavklart_rf1022", "112_pensjon"],
        )
        == "112_pensjon"
    )

def test_filter_a07_overview_df_keeps_custom_columns_for_control_queue() -> None:
    control_df = pd.DataFrame(
        [
            {"Kode": "bonus", "Status": "Avvik", "NesteHandling": "Map manuelt."},
            {"Kode": "aga", "Status": "Ekskludert", "NesteHandling": "Ingen handling nÃ¸dvendig."},
        ]
    )

    out = page_a07.filter_a07_overview_df(control_df, "uloste")

    assert out.columns.tolist() == ["Kode", "Status", "NesteHandling"]
    assert out["Kode"].tolist() == ["bonus"]

def test_select_batch_suggestion_rows_picks_only_safe_top_suggestions() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "ForslagKontoer": "5000", "WithinTolerance": True, "Score": 0.93, "SuggestionGuardrail": "accepted"},
            {"Kode": "fastloenn", "ForslagKontoer": "5001", "WithinTolerance": True, "Score": 0.92, "SuggestionGuardrail": "review"},
            {"Kode": "bonus", "ForslagKontoer": "5090", "WithinTolerance": True, "Score": 0.91, "Explain": "regel=bonus"},
            {"Kode": "feriepenger", "ForslagKontoer": "5000", "WithinTolerance": True, "Score": 0.95, "SuggestionGuardrail": "accepted"},
            {"Kode": "telefon", "ForslagKontoer": "6990", "WithinTolerance": False, "Score": 0.99},
            {"Kode": "pensjon", "ForslagKontoer": "5940", "WithinTolerance": True, "Score": 0.70},
        ]
    )

    out = page_a07.select_batch_suggestion_rows(suggestions_df, {"5100": "annet"}, min_score=0.85)

    assert out == [0]

def test_select_magic_wand_suggestion_rows_uses_within_tolerance_without_score_gate() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "ForslagKontoer": "5000", "WithinTolerance": True, "Score": 0.61, "SuggestionGuardrail": "review"},
            {"Kode": "fastloenn", "ForslagKontoer": "5001", "WithinTolerance": True, "Score": 0.95, "SuggestionGuardrail": "accepted"},
            {"Kode": "telefon", "ForslagKontoer": "6990", "WithinTolerance": True, "Score": 0.40, "HistoryAccounts": "6990"},
            {"Kode": "bonus", "ForslagKontoer": "6990", "WithinTolerance": True, "Score": 0.97, "SuggestionGuardrail": "review"},
            {"Kode": "pensjon", "ForslagKontoer": "5940", "WithinTolerance": False, "Score": 0.99, "SuggestionGuardrail": "accepted"},
        ]
    )

    out = page_a07.select_magic_wand_suggestion_rows(
        suggestions_df,
        {"5100": "annet"},
        unresolved_codes=["fastloenn", "telefon", "bonus", "pensjon"],
    )

    assert out == [1]

def test_build_control_suggestion_effect_summary_describes_replacement() -> None:
    row = pd.Series({"ForslagKontoer": "5000,5001", "Diff": Decimal("100.00"), "WithinTolerance": False})

    out = page_a07.build_control_suggestion_effect_summary("bonus", ["5090"], row)
    diff_text = page_a07._format_picker_amount(Decimal("100.00"))

    assert out == f"Vil erstatte 5090 med 5000,5001 | Må vurderes | Diff {diff_text}"

def test_build_control_suggestion_effect_summary_handles_matching_current_mapping() -> None:
    row = pd.Series({"ForslagKontoer": "5001,5000", "Diff": Decimal("0"), "WithinTolerance": True})

    out = page_a07.build_control_suggestion_effect_summary("bonus", ["5000", "5001"], row)
    diff_text = page_a07._format_picker_amount(Decimal("0"))

    assert out == f"Matcher dagens mapping: 5001,5000 | Må vurderes | Diff {diff_text}"

def test_build_control_accounts_summary_handles_empty_state() -> None:
    assert (
        page_a07.build_control_accounts_summary(pd.DataFrame(), "fastloenn")
            == "Ingen kontoer er koblet til fastloenn ennå. Velg kontoer til venstre og trykk ->."
    )
    assert (
        page_a07.build_control_accounts_summary(pd.DataFrame(), None)
            == "Velg A07-kode til høyre for å se hva som er koblet nå."
    )

def test_sync_control_alternative_view_updates_history_mode_and_summary_without_widget_routing() -> None:
    class _Var:
        def __init__(self, value: str) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

        def set(self, value: str) -> None:
            self.value = value

    class _Notebook:
        def __init__(self, selected):
            self.selected_widget = selected

        def select(self):
            return "current"

        def nametowidget(self, _name):
            return self.selected_widget

    suggestions_frame = object()
    history_frame = object()
    summary_var = _Var("")
    mode_var = _Var("")
    mode_label_var = _Var("")
    dummy = SimpleNamespace(
        _selected_control_alternative_mode=lambda: "history",
        _active_support_tab_key=page_a07.A07Page._active_support_tab_key,
        _control_details_visible=True,
        control_support_nb=_Notebook(history_frame),
        tab_suggestions=suggestions_frame,
        tab_history=history_frame,
        control_alternative_mode_var=mode_var,
        control_alternative_mode_label_var=mode_label_var,
        history_details_var=_Var("Historikk finnes for valgt kode."),
        control_suggestion_summary_var=_Var("Beste forslag"),
        control_alternative_summary_var=summary_var,
    )

    page_a07.A07Page._sync_control_alternative_view(dummy)

    assert mode_var.get() == "history"
    assert mode_label_var.get() == page_a07._CONTROL_ALTERNATIVE_MODE_LABELS["history"]
    assert summary_var.get() == "Historikk finnes for valgt kode."


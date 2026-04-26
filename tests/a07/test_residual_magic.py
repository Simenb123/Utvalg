from __future__ import annotations

from .shared import *  # noqa: F401,F403
from a07_feature.suggest.residual_display import residual_analysis_to_suggestions_df
from a07_feature.suggest.residual_models import REVIEW_EXACT, ResidualAnalysis, ResidualGroupScenario
from a07_feature.suggest.residual_solver import analyze_a07_residuals


def test_apply_magic_wand_suggestions_only_applies_exact_zero_diff_rows() -> None:
    workspace = SimpleNamespace(
        suggestions=pd.DataFrame(
            [
                {
                    "Kode": "bonus",
                    "ForslagKontoer": "5000",
                    "WithinTolerance": True,
                    "Score": 0.40,
                    "SuggestionGuardrail": "accepted",
                    "Diff": 0.0,
                },
                {
                    "Kode": "telefon",
                    "ForslagKontoer": "6990",
                    "WithinTolerance": True,
                    "Score": 0.40,
                    "SuggestionGuardrail": "accepted",
                    "Diff": 0.50,
                },
            ]
        ),
        mapping={},
        locks=set(),
    )
    dummy = SimpleNamespace(
        workspace=workspace,
        _effective_mapping=lambda: workspace.mapping,
        _strict_auto_amount_is_exact=lambda row: abs(float(row.get("Diff") or 0.0)) <= 0.01,
    )

    applied_codes, applied_accounts, skipped_codes = page_a07.A07Page._apply_magic_wand_suggestions(
        dummy,
        ["bonus", "telefon"],
    )

    assert (applied_codes, applied_accounts, skipped_codes) == (1, 1, 1)
    assert workspace.mapping == {"5000": "bonus"}


def test_magic_match_clicked_uses_only_unresolved_codes_and_keeps_zero_diff_codes() -> None:
    calls: list[object] = []
    workspace = SimpleNamespace(
        a07_df=pd.DataFrame([{"Kode": "bonus"}]),
        gl_df=pd.DataFrame([{"Konto": "5000", "Endring": 100.0}]),
        suggestions=pd.DataFrame(
            [
                {
                    "Kode": "bonus",
                    "ForslagKontoer": "5000",
                    "WithinTolerance": True,
                    "Score": 0.40,
                    "SuggestionGuardrail": "accepted",
                    "Diff": 0.0,
                },
                {
                    "Kode": "feriepenger",
                    "ForslagKontoer": "2940",
                    "WithinTolerance": True,
                    "Score": 0.99,
                    "SuggestionGuardrail": "accepted",
                    "Diff": 0.0,
                },
            ]
        ),
        mapping={},
        locks=set(),
    )
    dummy = SimpleNamespace(
        workspace=workspace,
        control_gl_df=pd.DataFrame(
            [
                {"Konto": "5000", "Navn": "Bonus", "Endring": 100.0, "Kode": "", "MappingAuditStatus": ""},
                {"Konto": "2940", "Navn": "Feriepenger", "Endring": 100.0, "Kode": "feriepenger", "MappingAuditStatus": "Trygg"},
            ]
        ),
        a07_overview_df=pd.DataFrame(
            [
                {"Kode": "bonus", "Status": "Avvik", "Diff": 100.0},
                {"Kode": "feriepenger", "Status": "OK", "Diff": 0.0},
            ]
        ),
        status_var=SimpleNamespace(set=lambda value: calls.append(("status", value))),
        details_var=SimpleNamespace(set=lambda value: calls.append(("details", value))),
        tree_a07=object(),
        tree_control_suggestions=object(),
        _safe_auto_matching_enabled=lambda: True,
        _selected_control_work_level=lambda: "a07",
        _selected_control_code=lambda: "bonus",
        _effective_mapping=lambda: workspace.mapping,
        _strict_auto_amount_is_exact=lambda row: abs(float(row.get("Diff") or 0.0)) <= 0.01,
        _autosave_mapping=lambda **_kwargs: True,
        _refresh_core=lambda **kwargs: calls.append(("refresh", kwargs)),
        _focus_control_code=lambda code: calls.append(("focus", code)),
        _select_primary_tab=lambda: calls.append("primary"),
        _notify_inline=lambda message, **_kwargs: calls.append(("notify", message)),
        _sync_active_trial_balance=lambda **_kwargs: calls.append("sync"),
    )
    dummy._build_magic_wand_residual_analysis = lambda: page_a07.A07Page._build_magic_wand_residual_analysis(dummy)
    dummy._apply_magic_wand_residual_changes = lambda analysis: page_a07.A07Page._apply_magic_wand_residual_changes(
        dummy,
        analysis,
    )
    dummy._run_magic_wand_residual_flow = lambda: page_a07.A07Page._run_magic_wand_residual_flow(dummy)

    page_a07.A07Page._magic_match_clicked(dummy)

    assert workspace.mapping == {"5000": "bonus"}
    assert "2940" not in workspace.mapping
    assert ("refresh", {"focus_code": "bonus"}) in calls
    assert ("focus", "bonus") in calls


def test_magic_match_clicked_reports_residual_review_without_applying() -> None:
    calls: list[object] = []
    workspace = SimpleNamespace(
        a07_df=pd.DataFrame([{"Kode": "annet"}]),
        gl_df=pd.DataFrame([{"Konto": "5310", "Endring": 55_120.0}]),
        suggestions=pd.DataFrame(),
        mapping={"5310": "annet"},
        locks=set(),
        basis_col="Endring",
    )
    dummy = SimpleNamespace(
        workspace=workspace,
        control_gl_df=pd.DataFrame(
            [
                {
                    "Konto": "5310",
                    "Navn": "Gruppelivsforsikring",
                    "Endring": 55_120.0,
                    "Kode": "annet",
                    "MappingAuditStatus": "Feil",
                }
            ]
        ),
        a07_overview_df=pd.DataFrame(
            [
                {"Kode": "annet", "Diff": 16_395.08},
                {"Kode": "skattepliktigDelForsikringer", "Diff": -57_892.00},
                {"Kode": "trekkILoennForFerie+overtidsgodtgjoerelse+timeloenn", "Diff": -13_623.08},
            ]
        ),
        status_var=SimpleNamespace(set=lambda value: calls.append(("status", value))),
        details_var=SimpleNamespace(set=lambda value: calls.append(("details", value))),
        tree_a07=object(),
        tree_control_suggestions=object(),
        _safe_auto_matching_enabled=lambda: True,
        _selected_control_work_level=lambda: "a07",
        _selected_control_code=lambda: "annet",
        _effective_mapping=lambda: workspace.mapping,
        _autosave_mapping=lambda **_kwargs: calls.append("autosave"),
        _refresh_core=lambda **kwargs: calls.append(("refresh", kwargs)),
        _focus_control_code=lambda code: calls.append(("focus", code)),
        _select_primary_tab=lambda: calls.append("primary"),
        _select_support_tab_key=lambda *args, **kwargs: calls.append(("support", args, kwargs)),
        _notify_inline=lambda message, **_kwargs: calls.append(("notify", message)),
        _sync_active_trial_balance=lambda **_kwargs: calls.append("sync"),
    )
    dummy._build_magic_wand_residual_analysis = lambda: page_a07.A07Page._build_magic_wand_residual_analysis(dummy)
    dummy._show_magic_wand_residual_review = lambda analysis: page_a07.A07Page._show_magic_wand_residual_review(
        dummy,
        analysis,
    )
    dummy._run_magic_wand_residual_flow = lambda: page_a07.A07Page._run_magic_wand_residual_flow(dummy)

    page_a07.A07Page._magic_match_clicked(dummy)

    assert workspace.mapping == {"5310": "annet"}
    assert not any(call == "autosave" for call in calls)
    assert "SuggestionSource" in workspace.suggestions.columns
    assert set(workspace.suggestions["SuggestionSource"]) == {"residual_solver"}
    assert "Mistenkelig rest" in set(workspace.suggestions["Forslagsstatus"])
    messages = [
        str(call[1])
        for call in calls
        if isinstance(call, tuple) and len(call) >= 2 and call[0] in {"notify", "details"}
    ]
    assert any("5310" in message for message in messages)


def test_residual_analysis_to_suggestions_marks_5310_as_compact_review_row() -> None:
    overview = pd.DataFrame(
        [
            {"Kode": "annet", "Diff": 16_395.08},
            {"Kode": "skattepliktigDelForsikringer", "Diff": -57_892.00},
            {"Kode": "trekkILoennForFerie+overtidsgodtgjoerelse+timeloenn", "Diff": -13_623.08},
        ]
    )
    control_gl = pd.DataFrame(
        [
            {
                "Konto": "5310",
                "Navn": "Gruppelivsforsikring",
                "Endring": 55_120.0,
                "Kode": "annet",
                "MappingAuditStatus": "Feil",
            }
        ]
    )

    analysis = analyze_a07_residuals(
        overview,
        control_gl,
        {"5310": "annet"},
        basis_col="Endring",
    )

    suggestions = residual_analysis_to_suggestions_df(analysis)

    row = suggestions.loc[suggestions["Forslagsstatus"] == "Mistenkelig rest"].iloc[0]
    assert row["Kode"] == "annet"
    assert row["ForslagKontoer"] == "5310"
    assert row["HvorforKort"] == "Forklarer samlet rest"
    assert row["SuggestionGuardrail"] == "review"


def test_residual_group_suggestion_is_compact_and_actionable() -> None:
    overview = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Diff": 70.0},
            {"Kode": "timeloenn", "Diff": 30.0},
        ]
    )
    control_gl = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Navn": "Lonn ansatte",
                "Endring": 100.0,
                "Kode": "",
                "MappingAuditStatus": "",
            }
        ]
    )

    analysis = analyze_a07_residuals(overview, control_gl, {}, basis_col="Endring")
    suggestions = residual_analysis_to_suggestions_df(analysis)

    row = suggestions.loc[suggestions["ResidualAction"] == "group_review"].iloc[0]
    assert row["ResidualGroupCodes"] == "fastloenn,timeloenn"
    assert row["ResidualGroupAccounts"] == "5000"
    assert row["ForslagVisning"] == "Gruppe: fastloenn, timeloenn"
    assert row["HvorforKort"] == "Opprett gruppeforslag"


def test_magic_match_clicked_renders_residual_review_rows_in_suggestions_tree() -> None:
    calls: list[object] = []
    filled: list[pd.DataFrame] = []

    class _Tree:
        def get_children(self):
            return ()

    workspace = SimpleNamespace(
        a07_df=pd.DataFrame([{"Kode": "annet"}]),
        gl_df=pd.DataFrame([{"Konto": "5310", "Endring": 55_120.0}]),
        suggestions=pd.DataFrame(),
        mapping={"5310": "annet"},
        locks=set(),
        basis_col="Endring",
    )
    dummy = SimpleNamespace(
        workspace=workspace,
        control_gl_df=pd.DataFrame(
            [
                {
                    "Konto": "5310",
                    "Navn": "Gruppelivsforsikring",
                    "Endring": 55_120.0,
                    "Kode": "annet",
                    "MappingAuditStatus": "Feil",
                }
            ]
        ),
        a07_overview_df=pd.DataFrame(
            [
                {"Kode": "annet", "Diff": 16_395.08},
                {"Kode": "skattepliktigDelForsikringer", "Diff": -57_892.00},
                {"Kode": "trekkILoennForFerie+overtidsgodtgjoerelse+timeloenn", "Diff": -13_623.08},
            ]
        ),
        status_var=SimpleNamespace(set=lambda value: calls.append(("status", value))),
        details_var=SimpleNamespace(set=lambda value: calls.append(("details", value))),
        suggestion_details_var=SimpleNamespace(set=lambda value: calls.append(("suggestion_details", value))),
        control_suggestion_summary_var=SimpleNamespace(set=lambda value: calls.append(("summary", value))),
        control_alternative_summary_var=SimpleNamespace(set=lambda value: calls.append(("alt_summary", value))),
        control_suggestion_effect_var=SimpleNamespace(set=lambda value: calls.append(("effect", value))),
        tree_a07=object(),
        tree_control_suggestions=_Tree(),
        _safe_auto_matching_enabled=lambda: True,
        _selected_control_work_level=lambda: "a07",
        _selected_control_code=lambda: "annet",
        _effective_mapping=lambda: workspace.mapping,
        _fill_tree=lambda _tree, df, _columns, **_kwargs: filled.append(df.copy()),
        _reconfigure_tree_columns=lambda *_args, **_kwargs: calls.append("columns"),
        _notify_inline=lambda message, **_kwargs: calls.append(("notify", message)),
        _select_support_tab_key=lambda *args, **kwargs: calls.append(("support", args, kwargs)),
        _sync_active_trial_balance=lambda **_kwargs: calls.append("sync"),
    )
    dummy._build_magic_wand_residual_analysis = lambda: page_a07.A07Page._build_magic_wand_residual_analysis(dummy)
    dummy._show_magic_wand_residual_review = lambda analysis: page_a07.A07Page._show_magic_wand_residual_review(
        dummy,
        analysis,
    )
    dummy._run_magic_wand_residual_flow = lambda: page_a07.A07Page._run_magic_wand_residual_flow(dummy)

    page_a07.A07Page._magic_match_clicked(dummy)

    assert filled
    assert "Mistenkelig rest" in set(filled[0]["Forslagsstatus"])
    assert any(call == ("summary", "Ingen trygg 0-diff-løsning. Mistenkelig konto: 5310.") for call in calls)
    assert ("suggestion_details", "Tryllestav-resultat: velg rad for manuell vurdering.") in calls


def test_magic_wand_group_review_details_point_to_group_action() -> None:
    calls: list[object] = []
    filled: list[pd.DataFrame] = []

    class _Tree:
        def get_children(self):
            return ()

    analysis = ResidualAnalysis(
        status=REVIEW_EXACT,
        auto_safe=False,
        changes=(),
        total_diff_before_cents=15_000,
        total_diff_after_cents=0,
        affected_codes=(),
        explanation="",
        code_results=(),
        group_scenarios=(
            ResidualGroupScenario(
                codes=("bonus", "telefon"),
                diff_cents=15_000,
                accounts=("5990",),
                amount_cents=15_000,
                diff_after_cents=0,
                reason="Åpne koder kan vurderes samlet som gruppe.",
            ),
        ),
    )
    dummy = SimpleNamespace(
        workspace=SimpleNamespace(suggestions=pd.DataFrame()),
        tree_control_suggestions=_Tree(),
        suggestion_details_var=SimpleNamespace(set=lambda value: calls.append(("suggestion_details", value))),
        control_suggestion_summary_var=SimpleNamespace(set=lambda value: calls.append(("summary", value))),
        control_alternative_summary_var=None,
        control_suggestion_effect_var=None,
        btn_control_best=None,
        _fill_tree=lambda _tree, df, _columns, **_kwargs: filled.append(df.copy()),
        _reconfigure_tree_columns=lambda *_args, **_kwargs: None,
        _update_a07_action_button_state=lambda: None,
    )

    page_a07.A07Page._show_magic_wand_residual_review(dummy, analysis)

    assert filled
    assert ("suggestion_details", "Tryllestav-resultat: velg gruppeforslag og trykk Opprett gruppeforslag.") in calls
    assert ("summary", "Ingen trygg 0-diff-løsning. 1 gruppeforslag må vurderes.") in calls


def test_apply_selected_residual_group_review_creates_group_without_mapping_autosave() -> None:
    calls: list[object] = []
    row = pd.Series(
        {
            "Kode": "fastloenn + timeloenn",
            "ResidualGroupCodes": "fastloenn,timeloenn",
            "ResidualGroupAccounts": "5000",
            "ForslagKontoer": "5000",
            "WithinTolerance": True,
            "SuggestionGuardrail": "review",
            "SuggestionSource": "residual_solver",
            "ResidualAction": "group_review",
            "Forslagsstatus": "Krever gruppe",
        }
    )
    workspace = SimpleNamespace(
        suggestions=pd.DataFrame([dict(row)]),
        mapping={},
        groups={},
        locks=set(),
    )
    dummy = SimpleNamespace(
        workspace=workspace,
        tree_a07=object(),
        tree_control_suggestions=object(),
        status_var=SimpleNamespace(set=lambda value: calls.append(("status", value))),
        _selected_control_work_level=lambda: "a07",
        _selected_suggestion_row=lambda: row,
        _selected_control_code=lambda: "fastloenn",
        _create_group_from_codes=lambda codes: calls.append(("create_group", list(codes))) or "A07_GROUP:fastloenn+timeloenn",
        _open_groups_popup=lambda group_id=None: calls.append(("groups_popup", group_id)),
        _focus_mapping_account=lambda account: calls.append(("focus_account", account)),
        _autosave_mapping=lambda **_kwargs: calls.append("autosave"),
        _refresh_core=lambda **kwargs: calls.append(("refresh", kwargs)),
        _focus_control_code=lambda code: calls.append(("focus_code", code)),
        _select_primary_tab=lambda: calls.append("primary"),
        _notify_inline=lambda message, **_kwargs: calls.append(("notify", message)),
    )
    dummy._residual_group_codes_from_row = (
        lambda selected_row: page_a07.A07Page._residual_group_codes_from_row(dummy, selected_row)
    )
    dummy._create_residual_group_from_suggestion = (
        lambda selected_row: page_a07.A07Page._create_residual_group_from_suggestion(dummy, selected_row)
    )

    page_a07.A07Page._apply_selected_suggestion(dummy)

    assert ("create_group", ["fastloenn", "timeloenn"]) in calls
    assert ("groups_popup", "A07_GROUP:fastloenn+timeloenn") in calls
    assert ("focus_account", "5000") in calls
    assert "autosave" not in calls


def test_residual_group_review_relabels_primary_suggestion_button() -> None:
    class _Button:
        def __init__(self) -> None:
            self.text = ""
            self.states: list[tuple[str, ...]] = []

        def configure(self, **kwargs) -> None:
            self.text = str(kwargs.get("text", self.text))

        def state(self, states) -> None:
            self.states.append(tuple(states))

    button = _Button()
    row = pd.Series(
        {
            "Kode": "fastloenn + timeloenn",
            "ResidualGroupCodes": "fastloenn,timeloenn",
            "SuggestionSource": "residual_solver",
            "ResidualAction": "group_review",
            "SuggestionGuardrail": "review",
        }
    )
    dummy = SimpleNamespace(
        tree_control_suggestions=object(),
        btn_control_best=button,
        btn_control_batch_suggestions=None,
        btn_control_magic=None,
        a07_overview_df=pd.DataFrame(),
        _selected_control_work_level=lambda: "a07",
        _selected_suggestion_row_from_tree=lambda _tree: row,
        _locked_codes=lambda: set(),
        _safe_auto_matching_enabled=lambda: True,
        get_global_auto_plan_summary=lambda: {"actionable": 0},
    )

    page_a07.A07Page._update_a07_action_button_state(dummy)

    assert button.text == "Opprett gruppeforslag"
    assert button.states[-1] == ("!disabled",)


def test_apply_selected_residual_review_opens_manual_mapping_without_autosave() -> None:
    calls: list[object] = []
    row = pd.Series(
        {
            "Kode": "annet",
            "ForslagKontoer": "5310",
            "WithinTolerance": False,
            "SuggestionGuardrail": "review",
            "SuggestionSource": "residual_solver",
            "Forslagsstatus": "Mistenkelig rest",
        }
    )
    workspace = SimpleNamespace(
        suggestions=pd.DataFrame([dict(row)]),
        mapping={"5310": "annet"},
    )
    dummy = SimpleNamespace(
        workspace=workspace,
        tree_a07=object(),
        tree_control_suggestions=object(),
        _selected_control_work_level=lambda: "a07",
        _selected_suggestion_row=lambda: row,
        _selected_control_code=lambda: "annet",
        _open_manual_mapping_clicked=lambda **kwargs: calls.append(("manual", kwargs)),
        _autosave_mapping=lambda **_kwargs: calls.append("autosave"),
        _refresh_core=lambda **kwargs: calls.append(("refresh", kwargs)),
        _focus_control_code=lambda code: calls.append(("focus", code)),
        _select_primary_tab=lambda: calls.append("primary"),
        _notify_inline=lambda message, **_kwargs: calls.append(("notify", message)),
    )

    page_a07.A07Page._apply_selected_suggestion(dummy)

    assert calls == [("manual", {"initial_account": "5310", "initial_code": "annet"})]

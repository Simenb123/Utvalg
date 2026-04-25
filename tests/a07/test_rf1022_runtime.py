from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_apply_selected_suggestion_uses_selected_rf1022_candidate() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _selected_control_work_level=lambda: "rf1022",
        _apply_selected_rf1022_candidate=lambda: calls.append("candidate"),
    )

    page_a07.A07Page._apply_selected_suggestion(dummy)

    assert calls == ["candidate"]

def test_apply_selected_rf1022_candidate_requires_auto_plan_apply() -> None:
    statuses: list[str] = []
    assigned: list[tuple[list[str], str]] = []

    class _Tree:
        def selection(self):
            return ("5000",)

    class DummyPage:
        tree_control_suggestions = _Tree()
        rf1022_candidate_df = pd.DataFrame(
            [
                {
                    "Konto": "5000",
                    "Navn": "Lonn ansatte",
                    "Kode": "fastloenn",
                    "Rf1022GroupId": "100_loenn_ol",
                    "Matchgrunnlag": "Regelbok/alias",
                    "Belopsgrunnlag": "",
                    "Forslagsstatus": "Maa vurderes",
                }
            ]
        )

        def _current_rf1022_candidate_df(self):
            return self.rf1022_candidate_df

        def _selected_rf1022_candidate_row(self):
            return page_a07.A07Page._selected_rf1022_candidate_row(self)

        def _build_global_auto_mapping_plan(self, _candidates):
            return pd.DataFrame(
                [
                    {
                        "Konto": "5000",
                        "Kode": "fastloenn",
                        "Action": "review",
                        "Status": "Maa vurderes",
                        "Reason": "Mangler belopsstotte.",
                    }
                ]
            )

        def _assign_accounts_to_a07_code(self, accounts, code, **_kwargs):
            assigned.append((list(accounts), code))

        def _notify_inline(self, message, **_kwargs):
            statuses.append(message)

    page_a07.A07Page._apply_selected_rf1022_candidate(DummyPage())

    assert assigned == []
    assert statuses == ["Kandidaten kan ikke brukes automatisk (Maa vurderes): Mangler belopsstotte."]

def test_auto_apply_strict_a07_suggestions_applies_exact_accepted_rows() -> None:
    saves: list[tuple[str, float]] = []
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "skattepliktigDelForsikringer",
                "ForslagKontoer": "5250",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "Diff": 0.0,
                "SuggestionGuardrail": "accepted",
                "UsedRulebook": True,
            },
            {
                "Kode": "yrkebilTjenstligbehovListepris",
                "ForslagKontoer": "5200",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "Diff": 0.0,
                "SuggestionGuardrail": "review",
                "UsedRulebook": True,
            },
        ]
    )

    class DummyPage:
        workspace = SimpleNamespace(mapping={}, suggestions=suggestions, locks=set(), membership={})

        def _ensure_suggestion_display_fields(self):
            return self.workspace.suggestions

        def _effective_mapping(self):
            return self.workspace.mapping

        def _locked_codes(self):
            return set()

        def _autosave_mapping(self, *, source="manual", confidence=1.0):
            saves.append((source, confidence))
            return True

    page = DummyPage()
    result = page_a07.A07Page._auto_apply_strict_a07_suggestions(page)

    assert result["accounts"] == ["5250"]
    assert result["codes"] == ["skattepliktigDelForsikringer"]
    assert result["autosaved"] is True
    assert saves == [("auto", 1.0)]
    assert page.workspace.mapping == {"5250": "skattepliktigDelForsikringer"}

def test_auto_apply_strict_a07_suggestions_adds_residual_special_add_accounts() -> None:
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "feriepenger",
                "ForslagKontoer": "2932,2940",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "Diff": 0.0,
                "SuggestionGuardrail": "accepted",
                "UsedRulebook": True,
                "UsedSpecialAdd": True,
            },
        ]
    )

    class DummyPage:
        workspace = SimpleNamespace(
            mapping={"5020": "feriepenger", "5096": "feriepenger"},
            suggestions=suggestions,
            locks=set(),
            membership={},
        )

        def _ensure_suggestion_display_fields(self):
            return self.workspace.suggestions

        def _effective_mapping(self):
            return self.workspace.mapping

        def _locked_codes(self):
            return set()

        def _autosave_mapping(self, *, source="manual", confidence=1.0):
            return True

    page = DummyPage()
    result = page_a07.A07Page._auto_apply_strict_a07_suggestions(page)

    assert set(result["accounts"]) == {"2932", "2940"}
    assert page.workspace.mapping == {
        "5020": "feriepenger",
        "5096": "feriepenger",
        "2932": "feriepenger",
        "2940": "feriepenger",
    }

def test_apply_batch_suggestions_clicked_uses_rf1022_candidates_in_rf_mode() -> None:
    calls: list[tuple[str, object]] = []
    statuses: list[str] = []
    candidate_df = pd.DataFrame(
        [
            {
                "Konto": "2940",
                "Navn": "Skyldig feriepenger",
                "Kode": "feriepenger",
                "Rf1022GroupId": "100_loenn_ol",
                "BelopAktiv": -100.0,
                "Matchgrunnlag": "special_add",
                "Belopsgrunnlag": "Tilleggsregel",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "5000",
                "Navn": "Lonn ansatte",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "BelopAktiv": 1000.0,
                "Matchgrunnlag": "Regelbok/alias",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "5001",
                "Navn": "Lonn ansatte",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "BelopAktiv": 1000.0,
                "Matchgrunnlag": "Regelbok/alias",
                "Belopsgrunnlag": "",
                "Forslagsstatus": "Maa vurderes",
            },
        ]
    )

    class DummyPage:
        tree_control_suggestions = object()
        workspace = SimpleNamespace(mapping={}, locks=set(), membership={})
        control_gl_df = pd.DataFrame(
            [
                {"Konto": "2940", "Navn": "Skyldig feriepenger", "Endring": -100.0, "UB": -500.0, "BelopAktiv": -100.0},
                {"Konto": "5000", "Navn": "Lonn ansatte", "Endring": 1000.0, "UB": 1000.0, "BelopAktiv": 1000.0},
                {"Konto": "5001", "Navn": "Lonn ansatte", "Endring": 1000.0, "UB": 1000.0, "BelopAktiv": 1000.0},
            ]
        )
        rf1022_candidate_df = candidate_df
        rf1022_all_candidate_df = candidate_df

        def __init__(self) -> None:
            self.status_var = SimpleNamespace(set=lambda value: statuses.append(value))

        def _selected_control_work_level(self):
            return "rf1022"

        def _apply_rf1022_candidate_suggestions(self):
            return page_a07.A07Page._apply_rf1022_candidate_suggestions(self)

        def _safe_auto_matching_enabled(self):
            return True

        def _current_rf1022_candidate_df(self):
            return page_a07.A07Page._current_rf1022_candidate_df(self)

        def _all_rf1022_candidate_df(self):
            return self.rf1022_all_candidate_df.copy()

        def _effective_mapping(self):
            return {}

        def _autosave_mapping(self):
            return False

        def _refresh_core(self, *, focus_code=None):
            calls.append(("refresh", focus_code))

        def _focus_mapping_account(self, account):
            calls.append(("account", account))

        def _focus_control_code(self, code):
            calls.append(("code", code))

        def _select_primary_tab(self):
            calls.append(("tab", "primary"))

        def _notify_inline(self, message, **_kwargs):
            statuses.append(message)

    page = DummyPage()

    page_a07.A07Page._apply_batch_suggestions_clicked(page)

    assert page.workspace.mapping == {"2940": "feriepenger", "5000": "fastloenn"}
    assert calls == [
        ("refresh", "feriepenger"),
        ("account", "2940"),
        ("code", "feriepenger"),
        ("tab", "primary"),
    ]
    assert statuses == ["Trygg auto-matching: brukte 2 sikre forslag (1 post(er), 1 maa vurderes)."]

def test_apply_rf1022_candidate_suggestions_uses_all_groups_not_only_visible_group() -> None:
    calls: list[tuple[str, object]] = []
    statuses: list[str] = []
    visible_df = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Navn": "Lonn ansatte",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "BelopAktiv": 1000.0,
                "Matchgrunnlag": "Regelbok/alias",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            }
        ]
    )
    all_df = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Navn": "Lonn ansatte",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "BelopAktiv": 1000.0,
                "Matchgrunnlag": "Regelbok/alias",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "5940",
                "Navn": "Pensjon",
                "Kode": "tilskuddOgPremieTilPensjon",
                "Rf1022GroupId": "112_pensjon",
                "BelopAktiv": 200.0,
                "Matchgrunnlag": "Regelbok/alias",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
        ]
    )

    class DummyPage:
        tree_control_suggestions = object()
        workspace = SimpleNamespace(mapping={}, locks=set(), membership={})
        control_gl_df = pd.DataFrame(
            [
                {"Konto": "5000", "Navn": "Lonn ansatte", "Endring": 1000.0, "UB": 1000.0, "BelopAktiv": 1000.0},
                {"Konto": "5940", "Navn": "Pensjon", "Endring": 200.0, "UB": 200.0, "BelopAktiv": 200.0},
            ]
        )
        rf1022_candidate_df = visible_df
        rf1022_all_candidate_df = all_df

        def __init__(self) -> None:
            self.status_var = SimpleNamespace(set=lambda value: statuses.append(value))

        def _all_rf1022_candidate_df(self):
            return self.rf1022_all_candidate_df.copy()

        def _effective_mapping(self):
            return {}

        def _autosave_mapping(self):
            return False

        def _refresh_core(self, *, focus_code=None):
            calls.append(("refresh", focus_code))

        def _focus_mapping_account(self, account):
            calls.append(("account", account))

        def _focus_control_code(self, code):
            calls.append(("code", code))

        def _select_primary_tab(self):
            calls.append(("tab", "primary"))

        def _notify_inline(self, message, **_kwargs):
            statuses.append(message)

    page = DummyPage()

    page_a07.A07Page._apply_rf1022_candidate_suggestions(page)

    assert page.workspace.mapping == {"5000": "fastloenn", "5940": "tilskuddOgPremieTilPensjon"}
    assert calls[0] == ("refresh", "fastloenn")
    assert statuses == ["Trygg auto-matching: brukte 2 sikre forslag (2 post(er))."]


def test_apply_rf1022_candidate_suggestions_skips_codes_that_are_already_zero_diff() -> None:
    calls: list[tuple[str, object]] = []
    statuses: list[str] = []
    all_df = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Navn": "Lonn ansatte",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "BelopAktiv": 1000.0,
                "Matchgrunnlag": "Regelbok/alias",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "5940",
                "Navn": "Pensjon",
                "Kode": "tilskuddOgPremieTilPensjon",
                "Rf1022GroupId": "112_pensjon",
                "BelopAktiv": 200.0,
                "Matchgrunnlag": "Regelbok/alias",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
        ]
    )

    class DummyPage:
        tree_control_suggestions = object()
        workspace = SimpleNamespace(mapping={}, locks=set(), membership={}, basis_col="Endring")
        control_gl_df = pd.DataFrame(
            [
                {"Konto": "5000", "Navn": "Lonn ansatte", "Endring": 1000.0, "UB": 1000.0, "BelopAktiv": 1000.0},
                {"Konto": "5940", "Navn": "Pensjon", "Endring": 200.0, "UB": 200.0, "BelopAktiv": 200.0},
            ]
        )
        a07_overview_df = pd.DataFrame(
            [
                {"Kode": "fastloenn", "Diff": 0.0},
                {"Kode": "tilskuddOgPremieTilPensjon", "Diff": 200.0},
            ]
        )
        rf1022_all_candidate_df = all_df

        def __init__(self) -> None:
            self.status_var = SimpleNamespace(set=lambda value: statuses.append(value))

        def _all_rf1022_candidate_df(self):
            return self.rf1022_all_candidate_df.copy()

        def _auto_matching_protected_codes(self):
            return page_a07.A07Page._auto_matching_protected_codes(self)

        def _build_global_auto_mapping_plan(self, candidates):
            return page_a07.A07Page._build_global_auto_mapping_plan(self, candidates)

        def _effective_mapping(self):
            return {}

        def _autosave_mapping(self):
            return False

        def _refresh_core(self, *, focus_code=None):
            calls.append(("refresh", focus_code))

        def _focus_mapping_account(self, account):
            calls.append(("account", account))

        def _focus_control_code(self, code):
            calls.append(("code", code))

        def _select_primary_tab(self):
            calls.append(("tab", "primary"))

        def _notify_inline(self, message, **_kwargs):
            statuses.append(message)

    page = DummyPage()

    page_a07.A07Page._apply_rf1022_candidate_suggestions(page)

    assert page.workspace.mapping == {"5940": "tilskuddOgPremieTilPensjon"}
    assert calls == [
        ("refresh", "tilskuddOgPremieTilPensjon"),
        ("account", "5940"),
        ("code", "tilskuddOgPremieTilPensjon"),
        ("tab", "primary"),
    ]
    assert statuses == ["Trygg auto-matching: brukte 1 sikre forslag (1 post(er), 1 allerede ferdig)."]

def test_apply_rf1022_candidate_suggestions_rebuilds_fresh_candidates() -> None:
    calls: list[tuple[str, object]] = []
    statuses: list[str] = []
    stale_df = pd.DataFrame(
        [
            {
                "Konto": "5001",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "Forslagsstatus": "Trygt forslag",
            }
        ]
    )
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "fastloenn",
                "KodeNavn": "Fastlonn",
                "A07_Belop": 1000.0,
                "ForslagKontoer": "5000",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "SuggestionGuardrail": "accepted",
                "UsedRulebook": True,
                "HitTokens": "lonn",
            }
        ]
    )

    class DummyPage:
        tree_control_suggestions = object()
        workspace = SimpleNamespace(mapping={}, locks=set(), membership={}, basis_col="Endring")
        control_gl_df = pd.DataFrame(
            [{"Konto": "5000", "Navn": "Fast lonn", "Endring": 1000.0, "BelopAktiv": 1000.0}]
        )
        rf1022_all_candidate_df = stale_df

        def __init__(self) -> None:
            self.status_var = SimpleNamespace(set=lambda value: statuses.append(value))

        def _all_rf1022_candidate_df(self):
            return page_a07.A07Page._all_rf1022_candidate_df(self)

        def _rf1022_group_menu_choices(self):
            return [("100_loenn_ol", "Lonn")]

        def _ensure_suggestion_display_fields(self):
            return suggestions_df

        def _effective_mapping(self):
            return {}

        def _autosave_mapping(self):
            return False

        def _refresh_core(self, *, focus_code=None):
            calls.append(("refresh", focus_code))

        def _focus_mapping_account(self, account):
            calls.append(("account", account))

        def _focus_control_code(self, code):
            calls.append(("code", code))

        def _select_primary_tab(self):
            calls.append(("tab", "primary"))

        def _notify_inline(self, message, **_kwargs):
            statuses.append(message)

    page = DummyPage()

    page_a07.A07Page._apply_rf1022_candidate_suggestions(page)

    assert page.workspace.mapping == {"5000": "fastloenn"}
    assert "5001" not in page.workspace.mapping
    assert calls[0] == ("refresh", "fastloenn")

def test_on_rf1022_selection_changed_does_not_move_support_or_list_focus() -> None:
    calls: list[str] = []
    workspace = SimpleNamespace(selected_code=None)
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _is_tree_selection_suppressed=lambda _tree: False,
        tree_a07=object(),
        workspace=workspace,
        _selected_control_work_level=lambda: "rf1022",
        _selected_rf1022_group=lambda: "100_loenn_ol",
        _selected_control_code=lambda: "fastloenn",
        _update_history_details_from_selection=lambda: calls.append("history"),
        _update_selected_code_status_message=lambda: calls.append("status"),
        _update_control_panel=lambda: calls.append("panel"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _sync_groups_panel_visibility=lambda: calls.append("groups"),
        _refresh_in_progress=False,
        _control_details_visible=True,
        _schedule_control_selection_followup=lambda: calls.append("followup"),
        _select_support_tab_key=lambda *_args, **_kwargs: calls.append("tab"),
        _set_tree_selection=lambda *_args, **_kwargs: calls.append("tree_selection"),
        _focus_selected_control_account_in_gl=lambda: calls.append("gl_focus"),
    )

    page_a07.A07Page._on_control_selection_changed(dummy)

    assert dummy._selected_rf1022_group_id == "100_loenn_ol"
    assert workspace.selected_code == "fastloenn"
    assert calls == ["history", "panel", "buttons", "groups", "followup"]


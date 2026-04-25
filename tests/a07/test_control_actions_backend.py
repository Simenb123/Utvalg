from __future__ import annotations

import pytest
import pandas as pd

from src.pages.a07.backend.control_actions import (
    ASSIGN_A07,
    ASSIGN_RF1022,
    NOOP,
    PROMPT_A07_CODE,
    PROMPT_RF1022_GROUP,
    apply_accounts_to_code,
    clean_account_ids,
    plan_selected_control_gl_action,
    resolve_rf1022_target_code,
)


def test_clean_account_ids_deduplicates_and_skips_empty_values() -> None:
    assert clean_account_ids(["5000", "", None, "5000", " 5800 "]) == ("5000", "5800")


def test_plan_selected_control_gl_action_assigns_to_a07_code() -> None:
    plan = plan_selected_control_gl_action(
        accounts=["5000"],
        work_level="a07",
        selected_code="fastloenn",
        selected_rf1022_group="",
    )

    assert plan.action == ASSIGN_A07
    assert plan.accounts == ("5000",)
    assert plan.target_code == "fastloenn"


def test_plan_selected_control_gl_action_guides_when_a07_code_missing() -> None:
    plan = plan_selected_control_gl_action(
        accounts=["5000"],
        work_level="a07",
        selected_code="",
        selected_rf1022_group="",
    )

    assert plan.action == PROMPT_A07_CODE
    assert "A07-kode" in plan.message


def test_plan_selected_control_gl_action_assigns_to_rf1022_group() -> None:
    plan = plan_selected_control_gl_action(
        accounts=["5800"],
        work_level="rf1022",
        selected_code="sumAvgiftsgrunnlagRefusjon",
        selected_rf1022_group="100_refusjon",
    )

    assert plan.action == ASSIGN_RF1022
    assert plan.target_group == "100_refusjon"
    assert plan.source_label == "RF-1022-mapping"


def test_plan_selected_control_gl_action_guides_when_rf1022_group_missing() -> None:
    plan = plan_selected_control_gl_action(
        accounts=["5800"],
        work_level="rf1022",
        selected_code="sumAvgiftsgrunnlagRefusjon",
        selected_rf1022_group="",
    )

    assert plan.action == PROMPT_RF1022_GROUP
    assert "RF-1022-post" in plan.message


def test_plan_selected_control_gl_action_noops_without_accounts() -> None:
    plan = plan_selected_control_gl_action(
        accounts=[],
        work_level="a07",
        selected_code="fastloenn",
        selected_rf1022_group="",
    )

    assert plan.action == NOOP


def test_apply_accounts_to_code_updates_mapping_and_returns_assigned_accounts() -> None:
    mapping: dict[str, str] = {"2940": "feriepenger"}

    assigned = apply_accounts_to_code(mapping, ["5000", "5000", "5001"], "fastloenn")

    assert assigned == ["5000", "5001"]
    assert mapping == {"2940": "feriepenger", "5000": "fastloenn", "5001": "fastloenn"}


def test_apply_accounts_to_code_requires_code_and_accounts() -> None:
    with pytest.raises(ValueError, match="Mangler A07-kode"):
        apply_accounts_to_code({}, ["5000"], "")
    with pytest.raises(ValueError, match="Mangler konto"):
        apply_accounts_to_code({}, [], "fastloenn")


def test_resolve_rf1022_target_code_prefers_selected_allowed_code() -> None:
    out = resolve_rf1022_target_code(
        group_id="100_refusjon",
        accounts=["5800"],
        selected_code="sumAvgiftsgrunnlagRefusjon",
        effective_mapping={},
    )

    assert out == "sumAvgiftsgrunnlagRefusjon"


def test_resolve_rf1022_target_code_uses_existing_unique_mapping() -> None:
    out = resolve_rf1022_target_code(
        group_id="111_naturalytelser",
        accounts=["5210", "5211"],
        effective_mapping={"5210": "elektroniskKommunikasjon", "5211": "elektroniskKommunikasjon"},
    )

    assert out == "elektroniskKommunikasjon"


def test_resolve_rf1022_target_code_uses_strict_suggestion_overlap() -> None:
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "elektroniskKommunikasjon",
                "ForslagKontoer": "5210",
                "WithinTolerance": True,
                "Score": 0.9,
                "SuggestionGuardrail": "accepted",
            },
            {
                "Kode": "skattepliktigDelForsikringer",
                "ForslagKontoer": "5251",
                "WithinTolerance": True,
                "Score": 0.8,
                "SuggestionGuardrail": "accepted",
            },
        ]
    )

    out = resolve_rf1022_target_code(
        group_id="111_naturalytelser",
        accounts=["5251"],
        effective_mapping={},
        suggestions_df=suggestions,
    )

    assert out == "skattepliktigDelForsikringer"


def test_resolve_rf1022_target_code_uses_name_hints_but_avoids_broad_honorar() -> None:
    phone = resolve_rf1022_target_code(
        group_id="111_naturalytelser",
        accounts=["5210"],
        effective_mapping={},
        gl_df=pd.DataFrame([{"Konto": "5210", "Navn": "Fri telefon"}]),
    )
    broad_honorar = resolve_rf1022_target_code(
        group_id="100_loenn_ol",
        accounts=["6701"],
        effective_mapping={},
        gl_df=pd.DataFrame([{"Konto": "6701", "Navn": "Honorar revisjon"}]),
    )

    assert phone == "elektroniskKommunikasjon"
    assert broad_honorar is None

from __future__ import annotations

import pandas as pd

from src.pages.a07.backend.candidate_actions import (
    apply_rf1022_auto_plan_to_mapping,
    global_auto_plan_action_counts,
    rf1022_candidate_summary_counts,
)


def _strict_candidate(account: str, code: str, group: str) -> dict[str, object]:
    return {
        "Konto": account,
        "Kode": code,
        "Rf1022GroupId": group,
        "WithinTolerance": True,
        "SuggestionGuardrail": "accepted",
    }


def test_global_auto_plan_action_counts_counts_guarded_actions() -> None:
    plan = pd.DataFrame(
        [
            {"Action": "apply"},
            {"Action": "already"},
            {"Action": "review"},
            {"Action": "blocked"},
            {"Action": "invalid"},
            {"Action": "conflict"},
            {"Action": "locked"},
        ]
    )

    counts = global_auto_plan_action_counts(plan)

    assert counts == {
        "safe": 2,
        "actionable": 1,
        "review": 2,
        "invalid": 1,
        "already": 1,
        "conflict": 1,
        "locked": 1,
        "blocked": 1,
    }


def test_rf1022_candidate_summary_counts_classifies_precheck_states() -> None:
    candidates = pd.DataFrame(
        [
            _strict_candidate("5210", "elektroniskKommunikasjon", "111_naturalytelser"),
            _strict_candidate("5800", "sumAvgiftsgrunnlagRefusjon", "100_refusjon"),
            _strict_candidate("5945", "tilskuddOgPremieTilPensjon", "112_pensjon"),
            _strict_candidate("5251", "skattepliktigDelForsikringer", "111_naturalytelser"),
            _strict_candidate("5000", "fastloenn", "100_loenn_ol"),
            _strict_candidate("5252", "skattepliktigDelForsikringer", "100_refusjon"),
            {"Konto": "5330", "Kode": "styrehonorarOgGodtgjoerelseVerv", "Rf1022GroupId": "100_loenn_ol"},
            _strict_candidate("9999", "elektroniskKommunikasjon", "111_naturalytelser"),
        ]
    )

    counts = rf1022_candidate_summary_counts(
        candidates,
        locked_codes={"fastloenn"},
        solved_codes={"sumAvgiftsgrunnlagRefusjon"},
        current_mapping={
            "5945": "tilskuddOgPremieTilPensjon",
            "5251": "annet",
        },
        gl_accounts={"5210", "5800", "5945", "5251", "5000", "5252", "5330"},
    )

    assert counts == {
        "safe": 3,
        "actionable": 1,
        "review": 1,
        "invalid": 1,
        "already": 2,
        "conflict": 1,
        "locked": 1,
        "blocked": 1,
    }


def test_apply_rf1022_auto_plan_to_mapping_applies_only_safe_rows() -> None:
    mapping: dict[str, str] = {}
    plan = pd.DataFrame(
        [
            {"Konto": "5210", "Kode": "elektroniskKommunikasjon", "Action": "apply"},
            {"Konto": "", "Kode": "fastloenn", "Action": "apply"},
            {"Konto": "5251", "Kode": "skattepliktigDelForsikringer", "Action": "apply"},
            {"Konto": "5800", "Kode": "sumAvgiftsgrunnlagRefusjon", "Action": "apply"},
            {"Konto": "5330", "Kode": "styrehonorarOgGodtgjoerelseVerv", "Action": "review"},
        ]
    )

    result = apply_rf1022_auto_plan_to_mapping(
        mapping,
        plan,
        effective_mapping={"5251": "annet"},
        locked_conflicts_fn=lambda account, _code: account == "5800",
    )

    assert result.applied == (("5210", "elektroniskKommunikasjon"),)
    assert result.invalid == 1
    assert result.conflict == 1
    assert result.locked == 1
    assert result.skipped == 3
    assert mapping == {"5210": "elektroniskKommunikasjon"}

from __future__ import annotations

import pandas as pd

from a07_feature.suggest.residual_solver import (
    NO_SAFE_WHOLE_ACCOUNT_SOLUTION,
    REVIEW_EXACT,
    SAFE_EXACT,
    ResidualAccountCandidate,
    amount_to_cents,
    analyze_a07_residuals,
    exact_subset_sum,
)


def test_amount_to_cents_handles_norwegian_amount_text() -> None:
    assert amount_to_cents("16 395,08") == 1_639_508
    assert amount_to_cents("-57 892,00") == -5_789_200
    assert amount_to_cents("0,004") == 0


def test_exact_subset_sum_finds_deterministic_whole_account_solution() -> None:
    candidates = (
        ResidualAccountCandidate("5000", "Lonn", 12_500, "", "", "unmapped"),
        ResidualAccountCandidate("5001", "Bonus", 7_500, "", "", "unmapped"),
        ResidualAccountCandidate("5002", "Feil", 3_000, "", "", "unmapped"),
    )

    out = exact_subset_sum(candidates, 20_000)

    assert [candidate.account for candidate in out] == ["5000", "5001"]


def test_residual_solver_locks_zero_diff_and_does_not_move_trygg_mapping() -> None:
    overview = pd.DataFrame(
        [
            {"Kode": "bonus", "Diff": 100.0},
            {"Kode": "telefon", "Diff": 0.0},
        ]
    )
    control_gl = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Bonus", "Endring": 100.0, "Kode": "", "MappingAuditStatus": ""},
            {"Konto": "6990", "Navn": "Telefon", "Endring": 100.0, "Kode": "telefon", "MappingAuditStatus": "Trygg"},
        ]
    )

    analysis = analyze_a07_residuals(overview, control_gl, {"6990": "telefon"}, basis_col="Endring")

    assert analysis.status == SAFE_EXACT
    assert analysis.auto_safe is True
    assert [(change.account, change.to_code) for change in analysis.changes] == [("5000", "bonus")]
    assert "telefon" not in analysis.affected_codes


def test_residual_solver_uses_raw_audit_status_when_display_status_is_avstemt() -> None:
    overview = pd.DataFrame([{"Kode": "bonus", "Diff": 100.0}])
    control_gl = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Navn": "Bonus",
                "Endring": 100.0,
                "Kode": "annet",
                "MappingAuditStatus": "Avstemt",
                "MappingAuditRawStatus": "Feil",
            }
        ]
    )

    analysis = analyze_a07_residuals(overview, control_gl, {"5000": "annet"}, basis_col="Endring")

    assert analysis.code_results[0].exact_accounts == ("5000",)
    assert analysis.code_results[0].review_required is True


def test_residual_solver_does_not_auto_apply_partial_safe_solution() -> None:
    overview = pd.DataFrame(
        [
            {"Kode": "bonus", "Diff": 100.0},
            {"Kode": "telefon", "Diff": 25.0},
        ]
    )
    control_gl = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Bonus", "Endring": 100.0, "Kode": "", "MappingAuditStatus": ""},
        ]
    )

    analysis = analyze_a07_residuals(overview, control_gl, {}, basis_col="Endring")

    assert analysis.status == NO_SAFE_WHOLE_ACCOUNT_SOLUTION
    assert analysis.auto_safe is False
    assert [(change.account, change.to_code) for change in analysis.changes] == [("5000", "bonus")]
    assert analysis.total_diff_after_cents == 2_500


def test_residual_solver_treats_annet_exact_match_as_review_only() -> None:
    overview = pd.DataFrame([{"Kode": "annet", "Diff": 100.0}])
    control_gl = pd.DataFrame(
        [{"Konto": "5900", "Navn": "Gave", "Endring": 100.0, "Kode": "", "MappingAuditStatus": ""}]
    )

    analysis = analyze_a07_residuals(overview, control_gl, {}, basis_col="Endring")

    assert analysis.status == REVIEW_EXACT
    assert analysis.auto_safe is False
    assert analysis.changes == ()
    assert analysis.code_results[0].exact_accounts == ("5900",)
    assert analysis.code_results[0].review_required is True


def test_residual_solver_suggests_group_scenario_without_auto_apply() -> None:
    overview = pd.DataFrame(
        [
            {"Kode": "bonus", "Diff": 100.0},
            {"Kode": "telefon", "Diff": 50.0},
        ]
    )
    control_gl = pd.DataFrame(
        [
            {"Konto": "5990", "Navn": "Personalkost", "Endring": 150.0, "Kode": "", "MappingAuditStatus": ""},
        ]
    )

    analysis = analyze_a07_residuals(overview, control_gl, {}, basis_col="Endring")

    assert analysis.auto_safe is False
    assert analysis.changes == ()
    assert analysis.group_scenarios
    scenario = analysis.group_scenarios[0]
    assert scenario.codes == ("bonus", "telefon")
    assert scenario.accounts == ("5990",)
    assert scenario.diff_after_cents == 0


def test_residual_solver_uses_structured_suggestion_evidence_with_human_explain() -> None:
    overview = pd.DataFrame([{"Kode": "bonus", "Diff": 100.0}])
    control_gl = pd.DataFrame(
        [{"Konto": "5000", "Navn": "Bonus", "Endring": 100.0, "Kode": "", "MappingAuditStatus": ""}]
    )
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "bonus",
                "ForslagKontoer": "5000",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "SuggestionGuardrail": "accepted",
                "UsedRulebook": True,
                "HitTokens": "bonus",
                "AnchorSignals": "navnetreff,konto-intervall",
                "Explain": "Regelbok og kontonavn peker mot bonus.",
            }
        ]
    )

    analysis = analyze_a07_residuals(overview, control_gl, {}, basis_col="Endring", suggestions_df=suggestions)

    assert analysis.status == SAFE_EXACT
    assert analysis.auto_safe is True
    assert [(change.account, change.to_code) for change in analysis.changes] == [("5000", "bonus")]


def test_residual_solver_keeps_amount_only_exact_as_review_when_evidence_exists_elsewhere() -> None:
    overview = pd.DataFrame([{"Kode": "bonus", "Diff": 100.0}])
    control_gl = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Uforklart kostnad", "Endring": 100.0, "Kode": "", "MappingAuditStatus": ""},
            {"Konto": "5090", "Navn": "Bonus", "Endring": 90.0, "Kode": "", "MappingAuditStatus": ""},
        ]
    )
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "bonus",
                "ForslagKontoer": "5090",
                "WithinTolerance": False,
                "AmountEvidence": "near",
                "SuggestionGuardrail": "review",
                "UsedRulebook": True,
                "HitTokens": "bonus",
                "AnchorSignals": "navnetreff",
                "Explain": "Bonusnavn, men beløpet må vurderes.",
            }
        ]
    )

    analysis = analyze_a07_residuals(overview, control_gl, {}, basis_col="Endring", suggestions_df=suggestions)

    assert analysis.auto_safe is False
    assert analysis.changes == ()
    assert analysis.code_results[0].exact_accounts == ("5000",)
    assert analysis.code_results[0].review_required is True


def test_residual_solver_component_group_prefers_evidence_backed_account() -> None:
    overview = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Diff": 70.0},
            {"Kode": "timeloenn", "Diff": 30.0},
        ]
    )
    control_gl = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn ansatte", "Endring": 100.0, "Kode": "", "MappingAuditStatus": ""},
            {"Konto": "5999", "Navn": "Annen personalkost", "Endring": 100.0, "Kode": "", "MappingAuditStatus": ""},
        ]
    )
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "fastloenn",
                "ForslagKontoer": "5000",
                "WithinTolerance": False,
                "AmountEvidence": "near",
                "UsedRulebook": True,
                "HitTokens": "lonn",
                "AnchorSignals": "navnetreff",
            },
            {
                "Kode": "timeloenn",
                "ForslagKontoer": "5000",
                "WithinTolerance": False,
                "AmountEvidence": "near",
                "UsedRulebook": True,
                "HitTokens": "lonn",
                "AnchorSignals": "navnetreff",
            },
        ]
    )

    analysis = analyze_a07_residuals(overview, control_gl, {}, basis_col="Endring", suggestions_df=suggestions)

    assert analysis.auto_safe is False
    assert analysis.group_scenarios
    scenario = analysis.group_scenarios[0]
    assert scenario.codes == ("fastloenn", "timeloenn")
    assert scenario.accounts == ("5000",)
    assert "Strukturert evidens" in scenario.reason


def test_residual_solver_marks_5310_case_as_suspicious_without_forcing_zero() -> None:
    overview = pd.DataFrame(
        [
            {"Kode": "annet", "Diff": 16_395.08},
            {"Kode": "skattepliktigDelForsikringer", "Diff": -57_892.00},
            {"Kode": "trekkILoennForFerie+overtidsgodtgjoerelse+timeloenn", "Diff": -13_623.08},
            {"Kode": "feriepenger", "Diff": 0.0},
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
            },
            {
                "Konto": "5251",
                "Navn": "Gruppelivsforsikring",
                "Endring": 54_207.0,
                "Kode": "skattepliktigDelForsikringer",
                "MappingAuditStatus": "Uavklart",
            },
            {
                "Konto": "5280",
                "Navn": "Annen fordel",
                "Endring": 117_853.21,
                "Kode": "skattepliktigDelForsikringer",
                "MappingAuditStatus": "Uavklart",
            },
        ]
    )

    analysis = analyze_a07_residuals(
        overview,
        control_gl,
        {
            "5310": "annet",
            "5251": "skattepliktigDelForsikringer",
            "5280": "skattepliktigDelForsikringer",
        },
        basis_col="Endring",
    )

    assert analysis.status == NO_SAFE_WHOLE_ACCOUNT_SOLUTION
    assert analysis.auto_safe is False
    assert analysis.changes == ()
    assert [account.account for account in analysis.suspicious_accounts] == ["5310"]
    assert "5310" in analysis.explanation

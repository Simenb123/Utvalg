from __future__ import annotations

from a07_feature.suggest.residual_display import residual_analysis_to_suggestions_df
from a07_feature.suggest.residual_models import (
    REVIEW_EXACT,
    ResidualAnalysis,
    ResidualCodeResult,
    ResidualGroupScenario,
)


def _analysis(**overrides) -> ResidualAnalysis:
    payload = {
        "status": REVIEW_EXACT,
        "auto_safe": False,
        "changes": (),
        "total_diff_before_cents": 0,
        "total_diff_after_cents": 0,
        "affected_codes": (),
        "explanation": "",
        "code_results": (),
    }
    payload.update(overrides)
    return ResidualAnalysis(**payload)


def test_residual_display_shortens_long_account_lists_but_keeps_raw_accounts() -> None:
    analysis = _analysis(
        code_results=(
            ResidualCodeResult(
                code="annet",
                diff_cents=16_395_08,
                status=REVIEW_EXACT,
                exact_accounts=("7410", "8151", "7140", "7740", "7838"),
                review_required=True,
            ),
        ),
    )

    suggestions = residual_analysis_to_suggestions_df(analysis)

    row = suggestions.iloc[0]
    assert row["ForslagVisning"] == "7410, 8151, 7140 +2"
    assert row["ForslagKontoer"] == "7410,8151,7140,7740,7838"
    assert row["Forslagsstatus"] == "Må vurderes"
    assert row["HvorforKort"] == "Treffer beløp, men kode er annet"


def test_residual_display_renders_group_scenario_as_review_only() -> None:
    analysis = _analysis(
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

    suggestions = residual_analysis_to_suggestions_df(analysis)

    row = suggestions.iloc[0]
    assert row["Kode"] == "bonus + telefon"
    assert row["ForslagKontoer"] == "5990"
    assert row["Forslagsstatus"] == "Krever gruppe"
    assert row["SuggestionGuardrail"] == "review"
    assert row["ResidualAction"] == "group_review"

from __future__ import annotations

import pandas as pd

from a07_feature.control_matching import (
    build_control_suggestion_summary,
    build_smartmapping_fallback,
    decorate_suggestions_for_display,
    preferred_support_tab_key,
)


def test_preferred_support_tab_prefers_mapping_then_history_then_suggestions() -> None:
    assert preferred_support_tab_key(current_accounts=["5000"], history_accounts=[], best_row=None) == "mapping"
    assert (
        preferred_support_tab_key(
            current_accounts=[],
            history_accounts=["5000"],
            best_row=pd.Series({"ForslagKontoer": "5092", "Diff": 10.0, "Score": 0.91}),
        )
        == "suggestions"
    )
    assert preferred_support_tab_key(current_accounts=[], history_accounts=["5000"], best_row=None) == "history"


def test_build_smartmapping_fallback_points_user_to_best_candidate() -> None:
    fallback = build_smartmapping_fallback(
        code="feriepenger",
        current_accounts=[],
        history_accounts=[],
        best_row=pd.Series({"ForslagKontoer": "5092", "Diff": 0.0, "Score": 0.95}),
    )

    assert fallback.preferred_tab == "suggestions"
    assert "Beste kandidat er 5092" in fallback.message


def test_decorate_suggestions_for_display_adds_account_names() -> None:
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "feriepenger",
                "ForslagKontoer": "5092,2940",
                "HistoryAccounts": "5092",
                "WithinTolerance": True,
                "Score": 0.91,
            }
        ]
    )
    gl_df = pd.DataFrame(
        [
            {"Konto": "5092", "Navn": "Feriepenger"},
            {"Konto": "2940", "Navn": "Skyldige feriepenger"},
        ]
    )

    out = decorate_suggestions_for_display(suggestions, gl_df)

    assert out.iloc[0]["ForslagVisning"] == "5092 Feriepenger + 2940 Skyldige feriepenger"
    assert out.iloc[0]["HistoryAccountsVisning"] == "5092 Feriepenger"
    assert out.iloc[0]["Forslagsstatus"] == "Trygg auto"
    assert out.iloc[0]["HvorforKort"] == "Samme som historikk"


def test_decorate_suggestions_backfills_evidence_fields_for_legacy_frames() -> None:
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "feriepenger",
                "ForslagKontoer": "5092",
                "HistoryAccounts": "",
                "HitTokens": "",
                "WithinTolerance": True,
                "Diff": 0.0,
                "Score": 0.95,
                "Explain": "basis=UB | regel=kontonr",
            }
        ]
    )

    out = decorate_suggestions_for_display(suggestions, pd.DataFrame(columns=["Konto", "Navn"]))

    for column in (
        "UsedRulebook",
        "UsedHistory",
        "UsedUsage",
        "UsedSpecialAdd",
        "UsedResidual",
        "AmountEvidence",
        "AmountDiffAbs",
        "AnchorSignals",
    ):
        assert column in out.columns

    row = out.iloc[0]
    assert bool(row["UsedRulebook"]) is True
    assert bool(row["UsedHistory"]) is False
    assert str(row["AmountEvidence"]) == "exact"
    assert row["Forslagsstatus"] == "Trygg auto"
    assert row["HvorforKort"] == "Belop passer mot regelbok"


def test_decorate_suggestions_uses_structured_fields_over_explain() -> None:
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "fastloenn",
                "ForslagKontoer": "5000",
                "HistoryAccounts": "",
                "HitTokens": "loenn",
                "WithinTolerance": False,
                "Score": 0.80,
                "Diff": 500.0,
                "Explain": "basis=UB | navn=loenn",
                "UsedRulebook": False,
                "UsedUsage": True,
                "UsedHistory": False,
                "UsedSpecialAdd": False,
                "UsedResidual": False,
                "AmountEvidence": "near",
                "AmountDiffAbs": 500.0,
                "AnchorSignals": "navnetreff,kontobruk",
            }
        ]
    )

    out = decorate_suggestions_for_display(suggestions, pd.DataFrame(columns=["Konto", "Navn"]))
    row = out.iloc[0]
    assert row["Forslagsstatus"] == "Svak kandidat" or row["Forslagsstatus"] == "Maa vurderes"
    # AmountEvidence=near + not within → neither rulebook nor usage+fits → navnetreff wins
    assert row["HvorforKort"] == "Treff paa navn"


def test_build_control_suggestion_summary_prefers_human_display_when_available() -> None:
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "feriepenger",
                "ForslagKontoer": "5092,2940",
                "ForslagVisning": "5092 Feriepenger + 2940 Skyldige feriepenger",
                "Diff": 0.0,
                "WithinTolerance": True,
            }
        ]
    )

    out = build_control_suggestion_summary("feriepenger", suggestions_df, suggestions_df.iloc[0])

    assert "Beste forslag for feriepenger" in out
    assert "5092 Feriepenger + 2940 Skyldige feriepenger" in out

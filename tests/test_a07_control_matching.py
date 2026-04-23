from __future__ import annotations

import pandas as pd

from a07_feature.control.data import (
    a07_suggestion_is_strict_auto,
    build_global_auto_mapping_plan,
    build_rf1022_candidate_df,
)
from a07_feature.control_matching import (
    best_suggestion_row_for_code,
    build_control_suggestion_summary,
    build_smartmapping_fallback,
    decorate_suggestions_for_display,
    evaluate_current_mapping_suspicion,
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


def test_decorate_suggestions_for_display_adds_account_names_and_guardrail_labels() -> None:
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
    assert out.iloc[0]["Forslagsstatus"] == "God kandidat"
    assert out.iloc[0]["HvorforKort"] == "Treff paa historikk"
    assert out.iloc[0]["SuggestionGuardrail"] == "accepted"


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
    assert row["Forslagsstatus"] == "God kandidat"
    assert row["HvorforKort"] == "Treff paa regelbok"
    assert row["SuggestionGuardrail"] == "accepted"


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
    assert row["Forslagsstatus"] == "Maa vurderes"
    assert row["HvorforKort"] == "Treff paa kontobruk"
    assert row["SuggestionGuardrail"] == "review"


def test_best_suggestion_row_for_code_ignores_blocked_candidates() -> None:
    suggestions = pd.DataFrame(
        [
            {
                "Kode": "tilskuddOgPremieTilPensjon",
                "KodeNavn": "Tilskudd og premie til pensjon",
                "ForslagKontoer": "6300",
                "ForslagVisning": "6300 Leie lokale",
                "WithinTolerance": True,
                "Score": 0.99,
                "Diff": 0.0,
                "Explain": "basis=UB",
                "UsedRulebook": False,
                "UsedHistory": False,
                "UsedUsage": False,
                "AmountEvidence": "exact",
            },
            {
                "Kode": "tilskuddOgPremieTilPensjon",
                "KodeNavn": "Tilskudd og premie til pensjon",
                "ForslagKontoer": "5420",
                "ForslagVisning": "5420 Innberetningspliktig pensjonskostnad",
                "WithinTolerance": True,
                "Score": 0.95,
                "Diff": 58318.21,
                "Explain": "regel=kontonr",
                "UsedRulebook": True,
                "UsedHistory": False,
                "UsedUsage": False,
                "AmountEvidence": "near",
            },
        ]
    )

    decorated = decorate_suggestions_for_display(
        suggestions,
        pd.DataFrame(
            [
                {"Konto": "6300", "Navn": "Leie lokale"},
                {"Konto": "5420", "Navn": "Innberetningspliktig pensjonskostnad"},
            ]
        ),
    )

    blocked = decorated.loc[decorated["ForslagKontoer"] == "6300"].iloc[0]
    accepted = decorated.loc[decorated["ForslagKontoer"] == "5420"].iloc[0]
    best = best_suggestion_row_for_code(decorated, "tilskuddOgPremieTilPensjon", locked_codes=set())

    assert blocked["SuggestionGuardrail"] == "blocked"
    assert accepted["SuggestionGuardrail"] == "accepted"
    assert best is not None
    assert str(best.get("ForslagKontoer") or "") == "5420"


def test_evaluate_current_mapping_suspicion_flags_semantic_mismatch_without_support() -> None:
    suspicious, reason = evaluate_current_mapping_suspicion(
        code="tilskuddOgPremieTilPensjon",
        code_name="Tilskudd og premie til pensjon",
        current_accounts=["6300"],
        history_accounts=[],
        gl_df=pd.DataFrame([{"Konto": "6300", "Navn": "Leie lokale"}]),
        profile_state={},
    )

    assert suspicious is True
    assert "Forventer pensjon" in reason


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


def test_build_rf1022_candidate_df_requires_group_anchor_and_amount_support() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Fast lonn", "Endring": 1000.0, "BelopAktiv": 1000.0},
            {"Konto": "5001", "Navn": "Diverse", "Endring": 1000.0, "BelopAktiv": 1000.0},
            {"Konto": "5002", "Navn": "Bonus", "Endring": 100.0, "BelopAktiv": 100.0},
            {"Konto": "5940", "Navn": "Pensjon", "Endring": 1000.0, "BelopAktiv": 1000.0},
        ]
    )
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "fastloenn",
                "ForslagKontoer": "5000",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "SuggestionGuardrail": "accepted",
                "UsedRulebook": True,
                "HitTokens": "lonn",
            },
            {
                "Kode": "fastloenn",
                "ForslagKontoer": "5001",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "SuggestionGuardrail": "review",
                "UsedUsage": True,
            },
            {
                "Kode": "fastloenn",
                "ForslagKontoer": "5002",
                "WithinTolerance": False,
                "AmountEvidence": "weak",
                "SuggestionGuardrail": "review",
                "UsedRulebook": True,
                "HitTokens": "bonus",
            },
            {
                "Kode": "tilskuddOgPremieTilPensjon",
                "ForslagKontoer": "5940",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "SuggestionGuardrail": "accepted",
                "UsedRulebook": True,
                "HitTokens": "pensjon",
            },
        ]
    )

    out = build_rf1022_candidate_df(control_gl_df, suggestions_df, "100_loenn_ol")

    assert out["Konto"].tolist() == ["5000"]
    row = out.iloc[0]
    assert row["Kode"] == "fastloenn"
    assert row["Rf1022GroupId"] == "100_loenn_ol"
    assert row["Forslagsstatus"] == "Trygt forslag"
    assert "Regelbok" in row["Matchgrunnlag"]
    assert row["Belopsgrunnlag"] == "Eksakt belop"


def test_generic_refund_is_review_not_strict_auto() -> None:
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "sumAvgiftsgrunnlagRefusjon",
                "KodeNavn": "Refusjon",
                "ForslagKontoer": "5890",
                "ForslagVisning": "5890 Annen refusjon",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "UsedRulebook": True,
                "HitTokens": "refusjon",
                "AnchorSignals": "konto-intervall,navnetreff",
            },
            {
                "Kode": "sumAvgiftsgrunnlagRefusjon",
                "KodeNavn": "Refusjon",
                "ForslagKontoer": "5800",
                "ForslagVisning": "5800 Refusjon av sykepenger",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "UsedRulebook": True,
                "HitTokens": "refusjon,sykepenger",
                "AnchorSignals": "konto-boost,navnetreff",
            },
        ]
    )

    out = decorate_suggestions_for_display(suggestions_df, pd.DataFrame())

    generic = out.loc[out["ForslagKontoer"] == "5890"].iloc[0]
    specific = out.loc[out["ForslagKontoer"] == "5800"].iloc[0]
    assert generic["SuggestionGuardrail"] == "review"
    assert "Generisk refusjon" in generic["SuggestionGuardrailReason"]
    assert not a07_suggestion_is_strict_auto(generic)
    assert specific["SuggestionGuardrail"] == "accepted"
    assert a07_suggestion_is_strict_auto(specific)


def test_strict_auto_requires_explicit_accepted_guardrail() -> None:
    assert a07_suggestion_is_strict_auto({"WithinTolerance": True, "SuggestionGuardrail": "accepted"})
    assert not a07_suggestion_is_strict_auto({"WithinTolerance": True})
    assert not a07_suggestion_is_strict_auto({"WithinTolerance": True, "SuggestionGuardrail": "review"})
    assert not a07_suggestion_is_strict_auto({"WithinTolerance": False, "SuggestionGuardrail": "accepted"})


def test_global_auto_plan_accepts_strict_a07_groups() -> None:
    candidates_df = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Navn": "Lonn til ansatte",
                "Kode": "A07_GROUP:fastloenn+timeloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "Belop": 1000.0,
                "Kol": "UB",
                "Forslagsstatus": "Trygt forslag",
                "SuggestionGuardrail": "accepted",
                "WithinTolerance": True,
                "UsedRulebook": True,
                "Matchgrunnlag": "Treff paa regelbok",
            }
        ]
    )
    gl_df = pd.DataFrame([{"Konto": "5000", "Navn": "Lonn til ansatte", "UB": 1000.0, "Endring": 1000.0}])

    out = build_global_auto_mapping_plan(candidates_df, gl_df, pd.DataFrame(), {})

    assert out.iloc[0]["Action"] == "apply"
    assert out.iloc[0]["Status"] == "Trygg"


def test_rf1022_candidates_include_a07_group_codes() -> None:
    control_gl_df = pd.DataFrame(
        [{"Konto": "5000", "Navn": "Lonn til ansatte", "Endring": 1000.0, "BelopAktiv": 1000.0}]
    )
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "A07_GROUP:fastloenn+timeloenn",
                "ForslagKontoer": "5000",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "SuggestionGuardrail": "accepted",
                "UsedRulebook": True,
                "HitTokens": "lonn",
            }
        ]
    )

    out = build_rf1022_candidate_df(control_gl_df, suggestions_df, "100_loenn_ol")

    assert out["Konto"].tolist() == ["5000"]
    assert out.iloc[0]["Kode"] == "A07_GROUP:fastloenn+timeloenn"


def test_rf1022_combo_amount_does_not_make_each_account_safe() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5800", "Navn": "Refusjon av sykepenger", "Endring": -465809.0, "BelopAktiv": -465809.0},
            {"Konto": "5890", "Navn": "Annen refusjon", "Endring": -58009.0, "BelopAktiv": -58009.0},
        ]
    )
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "sumAvgiftsgrunnlagRefusjon",
                "KodeNavn": "Refusjon",
                "A07_Belop": -523818.0,
                "ForslagKontoer": "5800,5890",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "SuggestionGuardrail": "accepted",
                "UsedRulebook": True,
                "HitTokens": "refusjon,sykepenger",
                "AnchorSignals": "konto-intervall,navnetreff",
            },
        ]
    )

    out = build_rf1022_candidate_df(control_gl_df, suggestions_df, "100_refusjon")

    assert "5890" not in set(out.get("Konto", []))
    if not out.empty:
        assert not (
            (out["Konto"].astype(str) == "5890")
            & (out["Forslagsstatus"].astype(str) == "Trygt forslag")
        ).any()


def test_rf1022_special_add_2940_survives_as_feriepenger_candidate() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "Endring": -4207.18, "BelopAktiv": -4207.18},
        ]
    )
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "feriepenger",
                "KodeNavn": "Feriepenger",
                "A07_Belop": 866816.0,
                "ForslagKontoer": "2940",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "SuggestionGuardrail": "accepted",
                "UsedRulebook": True,
                "UsedSpecialAdd": True,
                "HitTokens": "feriepenger",
                "AnchorSignals": "special_add,navnetreff",
            },
        ]
    )

    out = build_rf1022_candidate_df(control_gl_df, suggestions_df, "100_loenn_ol")

    assert out["Konto"].tolist() == ["2940"]
    assert out.iloc[0]["Forslagsstatus"] == "Trygt forslag"
    assert out.iloc[0]["Belopsgrunnlag"] == "Tilleggsregel"

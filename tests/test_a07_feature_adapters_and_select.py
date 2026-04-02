from __future__ import annotations

import pandas as pd

from a07_feature import (
    from_trial_balance,
    select_batch_suggestions,
    select_best_suggestion_for_code,
    select_magic_wand_suggestions,
)
from a07_feature.suggest import UiSuggestionRow


def test_from_trial_balance_adapts_utvalg_shape_to_a07_shape():
    tb_df = pd.DataFrame(
        [
            {"konto": "5000", "kontonavn": "Loenn", "ib": 10, "ub": 30, "netto": 20},
            {"konto": "5400", "kontonavn": "AGA", "ib": 0, "ub": 15, "netto": 15},
        ]
    )

    out = from_trial_balance(tb_df)

    assert list(out.columns) == ["Konto", "Navn", "IB", "UB", "Endring", "Belop"]
    assert out.loc[out["Konto"] == "5000", "Belop"].iloc[0] == 20
    assert out.loc[out["Konto"] == "5400", "Navn"].iloc[0] == "AGA"


def test_select_best_suggestion_prefers_score_then_lowest_abs_diff():
    suggestions = [
        UiSuggestionRow(
            kode="fastloenn",
            kode_navn="Fastloenn",
            a07_belop=100.0,
            gl_kontoer=["5000"],
            gl_sum=90.0,
            diff=10.0,
            score=0.80,
            within_tolerance=True,
        ),
        UiSuggestionRow(
            kode="fastloenn",
            kode_navn="Fastloenn",
            a07_belop=100.0,
            gl_kontoer=["5010"],
            gl_sum=95.0,
            diff=5.0,
            score=0.80,
            within_tolerance=True,
        ),
    ]

    best = select_best_suggestion_for_code(suggestions, "fastloenn")
    assert best is not None
    assert best.gl_kontoer == ["5010"]


def test_select_best_suggestion_filters_locked_and_group_tokens():
    suggestions = [
        UiSuggestionRow(
            kode="bonus",
            kode_navn="Bonus",
            a07_belop=100.0,
            gl_kontoer=["5012"],
            gl_sum=100.0,
            diff=0.0,
            score=0.9,
            within_tolerance=True,
            hit_tokens=["A07_GROUP:bonus+fastloenn"],
        ),
        UiSuggestionRow(
            kode="bonus",
            kode_navn="Bonus",
            a07_belop=100.0,
            gl_kontoer=["5014"],
            gl_sum=100.0,
            diff=0.0,
            score=0.7,
            within_tolerance=True,
        ),
        UiSuggestionRow(
            kode="bonus",
            kode_navn="Bonus",
            a07_belop=100.0,
            gl_kontoer=["5013"],
            gl_sum=130.0,
            diff=-30.0,
            score=0.95,
            within_tolerance=False,
        ),
    ]

    best = select_best_suggestion_for_code(suggestions, "bonus")
    assert best is not None
    assert best.gl_kontoer == ["5014"]

    assert select_best_suggestion_for_code(suggestions, "bonus", locked_codes={"bonus"}) is None

    best_any = select_best_suggestion_for_code(
        suggestions,
        "bonus",
        require_within_tolerance=False,
        exclude_hit_token_prefixes=("A07_GROUP:",),
    )
    assert best_any is not None
    assert best_any.gl_kontoer == ["5013"]


def test_select_batch_suggestions_uses_selector_and_respects_conflicts_and_locks():
    suggestions = [
        UiSuggestionRow(
            kode="fastloenn",
            kode_navn="Fastloenn",
            a07_belop=100.0,
            gl_kontoer=["5000"],
            gl_sum=100.0,
            diff=0.0,
            score=0.88,
            within_tolerance=True,
            source_index=0,
        ),
        UiSuggestionRow(
            kode="fastloenn",
            kode_navn="Fastloenn",
            a07_belop=100.0,
            gl_kontoer=["5001"],
            gl_sum=99.0,
            diff=1.0,
            score=0.91,
            within_tolerance=True,
            source_index=1,
        ),
        UiSuggestionRow(
            kode="bonus",
            kode_navn="Bonus",
            a07_belop=50.0,
            gl_kontoer=["5001"],
            gl_sum=50.0,
            diff=0.0,
            score=0.95,
            within_tolerance=True,
            source_index=2,
        ),
        UiSuggestionRow(
            kode="telefon",
            kode_navn="Telefon",
            a07_belop=25.0,
            gl_kontoer=["6990"],
            gl_sum=25.0,
            diff=0.0,
            score=0.82,
            within_tolerance=True,
            source_index=3,
        ),
    ]

    selected = select_batch_suggestions(suggestions, {"5001": "annet"}, locked_codes={"bonus"})

    assert [row.kode for row in selected] == []

    selected = select_batch_suggestions(suggestions, {}, locked_codes={"bonus"})

    assert [row.kode for row in selected] == ["fastloenn"]
    assert selected[0].gl_kontoer == ["5001"]


def test_select_magic_wand_suggestions_filters_unresolved_codes_and_conflicts():
    suggestions = [
        UiSuggestionRow(
            kode="fastloenn",
            kode_navn="Fastloenn",
            a07_belop=100.0,
            gl_kontoer=["5000"],
            gl_sum=100.0,
            diff=0.0,
            score=0.70,
            within_tolerance=True,
            source_index=0,
        ),
        UiSuggestionRow(
            kode="bonus",
            kode_navn="Bonus",
            a07_belop=40.0,
            gl_kontoer=["5000"],
            gl_sum=40.0,
            diff=0.0,
            score=0.95,
            within_tolerance=True,
            source_index=1,
        ),
        UiSuggestionRow(
            kode="telefon",
            kode_navn="Telefon",
            a07_belop=25.0,
            gl_kontoer=["6990"],
            gl_sum=25.0,
            diff=0.0,
            score=0.92,
            within_tolerance=True,
            source_index=2,
        ),
    ]

    selected = select_magic_wand_suggestions(
        suggestions,
        {},
        unresolved_codes=["fastloenn", "telefon"],
        locked_codes={"telefon"},
    )

    assert [row.kode for row in selected] == ["fastloenn"]

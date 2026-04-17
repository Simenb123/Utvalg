from __future__ import annotations

import pandas as pd

from motpost.combo_workflow import find_expected_combos_by_rule_set
from motpost.expected_rules import ExpectedRule, ExpectedRuleSet


def _sample_df() -> pd.DataFrame:
    """Tre bilag med valgt konto 3000 og varierende motposter."""
    return pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 2, 2, 3, 3],
            "Dato": ["2025-01-01"] * 7,
            "Konto": ["3000", "2700", "1500", "3000", "1500", "3000", "9999"],
            "Kontonavn": [
                "Salg",
                "MVA høy",
                "Kundefordr.",
                "Salg",
                "Kundefordr.",
                "Salg",
                "Ukjent",
            ],
            "Tekst": ["", "", "", "", "", "", ""],
            "Beløp": [-1000.0, 250.0, 750.0, -500.0, 500.0, -200.0, 200.0],
        }
    )


def _label_map() -> dict[str, str]:
    return {
        "3000": "10 Salgsinntekt",
        "2700": "790 Skyldig offentlige avgifter",
        "1500": "610 Kundefordringer",
        # 9999 bevisst umappet
    }


def test_account_mode_all_approves_combo_with_kontos_in_target_rl() -> None:
    df = _sample_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(target_regnr=610, account_mode="all"),
            ExpectedRule(target_regnr=790, account_mode="all"),
        ),
    )
    combos = ["1500, 2700", "1500"]
    result = find_expected_combos_by_rule_set(
        combos,
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert set(result) == {"1500, 2700", "1500"}


def test_account_mode_selected_whitelists_specific_accounts() -> None:
    df = _sample_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(
                target_regnr=610,
                account_mode="selected",
                allowed_accounts=("1501",),  # 1500 er IKKE i whitelist
            ),
        ),
    )
    result = find_expected_combos_by_rule_set(
        ["1500"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert result == []


def test_unmapped_account_blocks_expected() -> None:
    df = _sample_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(ExpectedRule(target_regnr=610, account_mode="all"),),
    )
    # Bilag 3 har motpost 9999 som ikke finnes i label_map
    result = find_expected_combos_by_rule_set(
        ["9999"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert result == []


def test_multiple_rules_allow_partial_presence() -> None:
    """En kombinasjon med kun 1500 er forventet selv om regel for 790 også finnes."""
    df = _sample_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(target_regnr=610, account_mode="all"),
            ExpectedRule(target_regnr=790, account_mode="all"),
        ),
    )
    result = find_expected_combos_by_rule_set(
        ["1500"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert result == ["1500"]


def test_mixed_allowed_and_unmapped_blocks_combo() -> None:
    """1500 er tillatt, men 9999 er umappet → kombo ikke forventet."""
    df = _sample_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(ExpectedRule(target_regnr=610, account_mode="all"),),
    )
    result = find_expected_combos_by_rule_set(
        ["1500, 9999"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert result == []


def test_empty_rule_set_returns_empty() -> None:
    df = _sample_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10, selected_direction="kredit", rules=()
    )
    result = find_expected_combos_by_rule_set(
        ["1500"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert result == []


def test_per_rule_netting_requires_each_rules_kontos_to_balance_alone() -> None:
    """Per-regel netting: kontoene EN regel tillater må alene balansere kilden.

    Kombo '1500': rule 610 matcher 1500. Bilag 2 har 3000=-500 + 1500=500 → 0. OK.
    Kombo '1500, 2700': rule 610 matcher 1500 og rule 790 matcher 2700 (hver regel
    kjøres separat). For rule 610 alene på bilag 1: 3000=-1000 + 1500=750 → residual
    -250, bryter toleranse 1.0. Kombo blokkeres.
    """
    df = _sample_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(
                target_regnr=610,
                account_mode="all",
                requires_netting=True,
                netting_tolerance=1.0,
            ),
            ExpectedRule(
                target_regnr=790,
                account_mode="all",
                requires_netting=True,
                netting_tolerance=1.0,
            ),
        ),
    )
    result = find_expected_combos_by_rule_set(
        ["1500, 2700", "1500"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert result == ["1500"]


def test_rule_without_netting_allows_combo_even_if_unbalanced() -> None:
    """Uten requires_netting=True skal godkjenning ikke kreve balanse."""
    df = _sample_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(target_regnr=610, account_mode="all"),
            ExpectedRule(target_regnr=790, account_mode="all"),
        ),
    )
    result = find_expected_combos_by_rule_set(
        ["1500, 2700", "1500"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert set(result) == {"1500, 2700", "1500"}


def test_netting_enabled_rejects_unbalanced_combo() -> None:
    """Bygg df hvor valgt-siden ikke balanserer motpost-siden."""
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1],
            "Dato": ["2025-01-01"] * 3,
            "Konto": ["3000", "1500", "1500"],
            "Kontonavn": ["Salg", "Kundefordr.", "Kundefordr."],
            "Tekst": ["", "", ""],
            "Beløp": [-1000.0, 500.0, 600.0],  # residual = -1000 + 1100 = 100
        }
    )
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(
                target_regnr=610,
                account_mode="all",
                requires_netting=True,
                netting_tolerance=1.0,
            ),
        ),
    )
    result = find_expected_combos_by_rule_set(
        ["1500"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map={"3000": "10 Salgsinntekt", "1500": "610 Kundefordringer"},
        selected_direction="Kredit",
    )
    assert result == []


def test_excluded_account_blocks_combo() -> None:
    """1500 er i target-RL 610, men skopet ut → kombo ikke forventet."""
    df = _sample_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(
                target_regnr=610,
                account_mode="all",
                excluded_accounts=("1500",),
            ),
        ),
    )
    result = find_expected_combos_by_rule_set(
        ["1500"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert result == []


def test_excluded_does_not_affect_other_kontos_in_same_rl() -> None:
    """Ekskluder 1501 — 1500 er fortsatt forventet under regel 610."""
    df = _sample_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(
                target_regnr=610,
                account_mode="all",
                excluded_accounts=("1501",),
            ),
        ),
    )
    result = find_expected_combos_by_rule_set(
        ["1500"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert result == ["1500"]


def test_combo_with_only_selected_accounts_is_not_expected() -> None:
    """Kombo som bare består av valgt konto (ingen motpost observert) skal ikke være forventet."""
    df = _sample_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(ExpectedRule(target_regnr=610, account_mode="all"),),
    )
    result = find_expected_combos_by_rule_set(
        ["3000"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert result == []

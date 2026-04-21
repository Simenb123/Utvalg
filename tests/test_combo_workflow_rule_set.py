from __future__ import annotations

import pandas as pd

from motpost.combo_workflow import find_expected_combos_by_rule_set
from motpost.expected_rules import BalancePair, ExpectedRule, ExpectedRuleSet


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


# ---------------------------------------------------------------------------
# BalancePair — parvis utligning mellom to motpost-RL-er
# ---------------------------------------------------------------------------


def _pair_df() -> pd.DataFrame:
    """Salg-bilag med Varekostnad/Varelager-par i tillegg.

    Bilag 1: Kunde+Salg+MVA+Varekost+Varelager — par matcher 1:1.
    Bilag 2: Kunde+Salg+MVA+Varekost alene (Varelager mangler) — orphan.
    Bilag 3: Kunde+Salg+MVA+Varekost+Varelager, par skjevt (500 vs 400 = 100 skjev).
    """
    return pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3],
            "Dato": ["2025-01-01"] * 14,
            "Konto": [
                "1500", "3000", "2700", "4300", "1400",
                "1500", "3000", "2700", "4300",
                "1500", "3000", "2700", "4300", "1400",
            ],
            "Kontonavn": ["x"] * 14,
            "Tekst": [""] * 14,
            "Beløp": [
                12500.0, -10000.0, -2500.0, 6000.0, -6000.0,
                6250.0, -5000.0, -1250.0, 3000.0,
                12500.0, -10000.0, -2500.0, 500.0, -400.0,
            ],
        }
    )


def _pair_label_map() -> dict[str, str]:
    return {
        "3000": "10 Salgsinntekt",
        "1500": "610 Kundefordringer",
        "2700": "790 Skyldig MVA",
        "4300": "30 Varekostnad",
        "1400": "110 Varelager",
    }


def test_balance_pair_accepts_matching_pair() -> None:
    df = _pair_df()[_pair_df()["Bilag"] == 1]
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(target_regnr=610),
            ExpectedRule(target_regnr=790),
            ExpectedRule(target_regnr=30),
            ExpectedRule(target_regnr=110),
        ),
        balance_pairs=(BalancePair(rl_a=30, rl_b=110, tolerance=100.0),),
    )
    result = find_expected_combos_by_rule_set(
        ["1400, 1500, 2700, 4300"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_pair_label_map(),
        selected_direction="Kredit",
    )
    assert result == ["1400, 1500, 2700, 4300"]


def test_balance_pair_rejects_orphan_pair_side() -> None:
    """Bilag med Varekost men uten Varelager → orphan → kombo avvist."""
    df = _pair_df()[_pair_df()["Bilag"] == 2]
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(target_regnr=610),
            ExpectedRule(target_regnr=790),
            ExpectedRule(target_regnr=30),
            ExpectedRule(target_regnr=110),
        ),
        balance_pairs=(BalancePair(rl_a=30, rl_b=110, tolerance=100.0),),
    )
    result = find_expected_combos_by_rule_set(
        ["1500, 2700, 4300"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_pair_label_map(),
        selected_direction="Kredit",
    )
    assert result == []


def test_balance_pair_rejects_skewed_pair() -> None:
    """Varekost +500, Varelager −400 → residual 100, tol 50 → avvises."""
    df = _pair_df()[_pair_df()["Bilag"] == 3]
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(target_regnr=610),
            ExpectedRule(target_regnr=790),
            ExpectedRule(target_regnr=30),
            ExpectedRule(target_regnr=110),
        ),
        balance_pairs=(BalancePair(rl_a=30, rl_b=110, tolerance=50.0),),
    )
    result = find_expected_combos_by_rule_set(
        ["1400, 1500, 2700, 4300"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_pair_label_map(),
        selected_direction="Kredit",
    )
    assert result == []


def test_balance_pair_tolerance_default_100_accepts_small_skew() -> None:
    """Samme skjeve bilag (residual 100) godkjennes med default tol 100."""
    df = _pair_df()[_pair_df()["Bilag"] == 3]
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(target_regnr=610),
            ExpectedRule(target_regnr=790),
            ExpectedRule(target_regnr=30),
            ExpectedRule(target_regnr=110),
        ),
        balance_pairs=(BalancePair(rl_a=30, rl_b=110),),  # default tol 100.0
    )
    result = find_expected_combos_by_rule_set(
        ["1400, 1500, 2700, 4300"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_pair_label_map(),
        selected_direction="Kredit",
    )
    assert result == ["1400, 1500, 2700, 4300"]


def test_balance_pair_small_amount_treated_as_absent() -> None:
    """Varekost 1,20 kr uten Varelager godkjennes (under tol 100 → effektivt null)."""
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1],
            "Dato": ["2025-01-01"] * 4,
            "Konto": ["3000", "1500", "2700", "4300"],
            "Kontonavn": ["Salg", "Kunde", "MVA", "Varekost"],
            "Tekst": [""] * 4,
            # Varekost på 1,20 kr — øre-avrunding, skal ignoreres
            "Beløp": [-1000.0, 1248.80, -250.0, 1.20],
        }
    )
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(target_regnr=610),
            ExpectedRule(target_regnr=790),
            ExpectedRule(target_regnr=30),
            ExpectedRule(target_regnr=110),
        ),
        balance_pairs=(BalancePair(rl_a=30, rl_b=110, tolerance=100.0),),
    )
    result = find_expected_combos_by_rule_set(
        ["1500, 2700, 4300"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_pair_label_map(),
        selected_direction="Kredit",
    )
    assert result == ["1500, 2700, 4300"]


def test_balance_pair_both_sides_small_skipped() -> None:
    """Begge par-sider ≤ tol → ingen utligning kreves → kombo godkjennes."""
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1, 1],
            "Dato": ["2025-01-01"] * 5,
            "Konto": ["3000", "1500", "2700", "4300", "1400"],
            "Kontonavn": ["Salg", "Kunde", "MVA", "Varekost", "Varelager"],
            "Tekst": [""] * 5,
            # Begge par-sider under 100 kr
            "Beløp": [-1000.0, 1248.50, -250.0, 2.00, -0.50],
        }
    )
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(target_regnr=610),
            ExpectedRule(target_regnr=790),
            ExpectedRule(target_regnr=30),
            ExpectedRule(target_regnr=110),
        ),
        balance_pairs=(BalancePair(rl_a=30, rl_b=110, tolerance=100.0),),
    )
    result = find_expected_combos_by_rule_set(
        ["1400, 1500, 2700, 4300"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_pair_label_map(),
        selected_direction="Kredit",
    )
    assert result == ["1400, 1500, 2700, 4300"]

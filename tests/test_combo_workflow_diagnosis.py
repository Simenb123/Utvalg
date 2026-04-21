from __future__ import annotations

import pandas as pd

from motpost.combo_workflow import (
    ComboDiagnosis,
    DIAG_EXPECTED,
    DIAG_NO_RULES,
    DIAG_REJECTED,
    diagnose_combos_against_rule_set,
)
from motpost.expected_rules import BalancePair, ExpectedRule, ExpectedRuleSet


def _base_df() -> pd.DataFrame:
    """Balansert Kunde+Salg+MVA-bilag pluss et bilag med umappet motpost."""
    return pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 2, 2, 3, 3],
            "Dato": ["2025-01-01"] * 7,
            "Konto": ["3000", "2700", "1500", "3000", "9999", "3000", "2400"],
            "Kontonavn": [
                "Salg",
                "MVA høy",
                "Kundefordr.",
                "Salg",
                "Ukjent",
                "Salg",
                "Leverandørgjeld",
            ],
            "Tekst": ["", "", "", "", "", "", ""],
            "Beløp": [-1000.0, 250.0, 750.0, -500.0, 500.0, -300.0, 300.0],
        }
    )


def _label_map() -> dict[str, str]:
    return {
        "3000": "10 Salgsinntekt",
        "2700": "790 Skyldig offentlige avgifter",
        "1500": "610 Kundefordringer",
        "2400": "560 Leverandørgjeld",
        # 9999 bevisst umappet
    }


def test_no_rules_returns_no_rules_status() -> None:
    df = _base_df()
    rule_set = ExpectedRuleSet(source_regnr=10, selected_direction="kredit", rules=())
    result = diagnose_combos_against_rule_set(
        ["1500", "9999"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    assert {k: v.status for k, v in result.items()} == {
        "1500": DIAG_NO_RULES,
        "9999": DIAG_NO_RULES,
    }


def test_approved_combo_status_expected_with_empty_reason() -> None:
    df = _base_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(target_regnr=610, account_mode="all"),
            ExpectedRule(target_regnr=790, account_mode="all"),
        ),
    )
    result = diagnose_combos_against_rule_set(
        ["1500, 2700"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    diag = result["1500, 2700"]
    assert diag.status == DIAG_EXPECTED
    assert diag.reason == ""


def test_unmapped_account_gives_specific_reason() -> None:
    df = _base_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(ExpectedRule(target_regnr=610, account_mode="all"),),
    )
    result = diagnose_combos_against_rule_set(
        ["9999"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    diag = result["9999"]
    assert diag.status == DIAG_REJECTED
    assert diag.reason == "Umappet konto: 9999"


def test_account_not_in_rule_set_gives_specific_reason() -> None:
    """Konto 2400 (RL 560) er mappet, men ingen regel dekker RL 560."""
    df = _base_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(ExpectedRule(target_regnr=610, account_mode="all"),),
    )
    result = diagnose_combos_against_rule_set(
        ["2400"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    diag = result["2400"]
    assert diag.status == DIAG_REJECTED
    assert diag.reason == "Ikke i regelsett: 2400"


def test_excluded_account_gives_scoped_out_reason() -> None:
    """Konto 1500 er i RL 610 men eksplisitt skopet ut i regelen."""
    df = _base_df()
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
    result = diagnose_combos_against_rule_set(
        ["1500"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    diag = result["1500"]
    assert diag.status == DIAG_REJECTED
    assert diag.reason == "Skopet ut: 1500"


def _pair_label_map() -> dict[str, str]:
    return {
        "3000": "10 Salgsinntekt",
        "1500": "610 Kundefordringer",
        "2700": "790 Skyldig MVA",
        "4300": "30 Varekostnad",
        "1400": "110 Varelager",
    }


def test_balance_pair_orphan_gives_specific_reason() -> None:
    """Bilag med Varekost men uten Varelager → reason nevner begge RL-navn."""
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1],
            "Dato": ["2025-01-01"] * 4,
            "Konto": ["3000", "1500", "2700", "4300"],
            "Kontonavn": ["Salg", "Kunde", "MVA", "Varekost"],
            "Tekst": [""] * 4,
            "Beløp": [-5000.0, 6250.0, -1250.0, 3000.0],
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
    result = diagnose_combos_against_rule_set(
        ["1500, 2700, 4300"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_pair_label_map(),
        selected_direction="Kredit",
    )
    diag = result["1500, 2700, 4300"]
    assert diag.status == DIAG_REJECTED
    assert diag.reason.startswith("Utligning mangler motpart:")
    assert "Varekostnad" in diag.reason
    assert "Varelager" in diag.reason
    assert diag.details["present_regnr"] == 30
    assert diag.details["missing_regnr"] == 110


def test_balance_pair_skew_gives_residual_reason() -> None:
    """Varekost +500, Varelager −400 → residual 100 > tol 50."""
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1, 1],
            "Dato": ["2025-01-01"] * 5,
            "Konto": ["3000", "1500", "2700", "4300", "1400"],
            "Kontonavn": ["Salg", "Kunde", "MVA", "Varekost", "Varelager"],
            "Tekst": [""] * 5,
            "Beløp": [-10000.0, 12500.0, -2500.0, 500.0, -400.0],
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
        balance_pairs=(BalancePair(rl_a=30, rl_b=110, tolerance=50.0),),
    )
    result = diagnose_combos_against_rule_set(
        ["1400, 1500, 2700, 4300"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_pair_label_map(),
        selected_direction="Kredit",
    )
    diag = result["1400, 1500, 2700, 4300"]
    assert diag.status == DIAG_REJECTED
    assert diag.reason.startswith("Utligning skjev:")
    assert "Varekostnad" in diag.reason
    assert "Varelager" in diag.reason
    assert diag.details["rl_a"] == 30
    assert diag.details["rl_b"] == 110
    assert abs(diag.details["residual"]) == 100.0
    assert diag.details["tolerance"] == 50.0


def test_combo_with_only_selected_accounts_gives_no_motposter() -> None:
    df = _base_df()
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(ExpectedRule(target_regnr=610, account_mode="all"),),
    )
    result = diagnose_combos_against_rule_set(
        ["3000"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_label_map(),
        selected_direction="Kredit",
    )
    diag = result["3000"]
    assert diag.status == DIAG_REJECTED
    assert diag.reason == "Ingen motposter"


def test_combo_diagnosis_dataclass_is_mutable_and_ordered() -> None:
    """ComboDiagnosis må kunne konstrueres standalone og ha default details={}."""
    d = ComboDiagnosis(status=DIAG_EXPECTED)
    assert d.reason == ""
    assert d.details == {}
    d.details["foo"] = 1
    assert d.details["foo"] == 1


def test_unmapped_or_out_of_ruleset_small_amount_ignored() -> None:
    """Konto utenfor regelsettet (f.eks. 7771 Øreavrunding) med kun småbeløp
    skal ikke avvise kombinasjonen.

    Dette matcher det typiske scenariet der øre-avrunding føres på en separat
    konto og dermed blir en del av kombinasjonsnøkkelen, selv om beløpet er
    revisjonsmessig uinteressant.
    """
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1, 2, 2, 2, 2],
            "Dato": ["2025-01-01"] * 8,
            "Konto": ["3000", "1500", "2700", "7771", "3000", "1500", "2700", "7771"],
            "Kontonavn": [
                "Salg", "Kunde", "MVA", "Øreavrunding",
                "Salg", "Kunde", "MVA", "Øreavrunding",
            ],
            "Tekst": [""] * 8,
            # 7771 har bare øre-beløp (-0.31 og +0.15) → effektivt fraværende
            "Beløp": [
                -1000.0, 1250.31, -250.0, -0.31,
                -2000.0, 2500.15, -500.0, 0.15,
            ],
        }
    )
    label_map = {
        "3000": "10 Salgsinntekt",
        "1500": "610 Kundefordringer",
        "2700": "790 Skyldig offentlige avgifter",
        "7771": "70 Annen driftskostnad",  # RL 70 er IKKE i regelsettet
    }
    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="kredit",
        rules=(
            ExpectedRule(target_regnr=610, account_mode="all"),
            ExpectedRule(target_regnr=790, account_mode="all"),
        ),
    )
    result = diagnose_combos_against_rule_set(
        ["1500, 2700, 7771"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=label_map,
        selected_direction="Kredit",
    )
    diag = result["1500, 2700, 7771"]
    assert diag.status == DIAG_EXPECTED
    assert diag.reason == ""


def test_balance_pair_small_amount_gives_expected() -> None:
    """Varekost 1,20 kr uten Varelager → diagnose returnerer DIAG_EXPECTED."""
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 1],
            "Dato": ["2025-01-01"] * 4,
            "Konto": ["3000", "1500", "2700", "4300"],
            "Kontonavn": ["Salg", "Kunde", "MVA", "Varekost"],
            "Tekst": [""] * 4,
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
    result = diagnose_combos_against_rule_set(
        ["1500, 2700, 4300"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=_pair_label_map(),
        selected_direction="Kredit",
    )
    diag = result["1500, 2700, 4300"]
    assert diag.status == DIAG_EXPECTED
    assert diag.reason == ""

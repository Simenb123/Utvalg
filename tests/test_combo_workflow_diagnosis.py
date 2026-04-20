from __future__ import annotations

import pandas as pd

from motpost.combo_workflow import (
    ComboDiagnosis,
    DIAG_EXPECTED,
    DIAG_NO_RULES,
    DIAG_REJECTED,
    diagnose_combos_against_rule_set,
)
from motpost.expected_rules import ExpectedRule, ExpectedRuleSet


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


def test_netting_residual_failure_gives_residual_reason() -> None:
    """SelectedNet + ExpectedNet = -100 → residual 100 > tol 1."""
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1],
            "Dato": ["2025-01-01"] * 3,
            "Konto": ["3000", "1500", "2700"],
            "Kontonavn": ["Salg", "Kundefordr.", "MVA"],
            "Tekst": ["", "", ""],
            "Beløp": [-1000.0, 600.0, 300.0],
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
            ExpectedRule(
                target_regnr=790,
                account_mode="all",
                requires_netting=True,
                netting_tolerance=1.0,
            ),
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
    assert diag.status == DIAG_REJECTED
    assert diag.reason.startswith("Netting feilet: residual ")
    assert "100" in diag.reason
    assert diag.details["residual_max"] == 100.0


def test_netting_other_net_outside_tolerance_gives_other_reason() -> None:
    """Expected balanseres, men en ikke-netting regelstyrt konto skaper OtherNetAbs > tol.

    Bilag: selected=-1000, 1500 (RL 610, netting aktiv)=+1000 → residual=0.
    4000 (RL 25, regel uten netting) har netto +50 → faller i other-bucket.
    """
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1],
            "Konto": ["3000", "1500", "4000"],
            "Beløp": [-1000.0, 1000.0, 50.0],
        }
    )
    label_map = {
        "3000": "10 Salgsinntekt",
        "1500": "610 Kundefordringer",
        "4000": "25 Annet",
    }
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
            # 4000 er «forventet» på konto-nivå men ikke med i netting-unionen.
            ExpectedRule(target_regnr=25, account_mode="all"),
        ),
    )
    result = diagnose_combos_against_rule_set(
        ["1500, 4000"],
        rule_set=rule_set,
        df_scope=df,
        selected_accounts=["3000"],
        konto_regnskapslinje_map=label_map,
        selected_direction="Kredit",
    )
    diag = result["1500, 4000"]
    assert diag.status == DIAG_REJECTED
    assert diag.reason.startswith("Utenfor netting:")
    assert "50" in diag.reason
    assert diag.details["other_net_max"] == 50.0


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

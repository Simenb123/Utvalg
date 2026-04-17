from __future__ import annotations

import pandas as pd

from motpost.expected_rules import ExpectedRule
from motpost.expected_rules_dialog import (
    accounts_in_target_rl,
    build_mva_group_map,
    build_rl_options,
    format_rule_summary,
    load_all_rl_options,
    mva_flagged_accounts,
)


def test_build_rl_options_unique_and_sorted() -> None:
    label_map = {
        "3000": "10 Salgsinntekt",
        "3001": "10 Salgsinntekt",  # duplikat RL
        "1500": "610 Kundefordringer",
        "2700": "790 Skyldig off.avg.",
    }
    options = build_rl_options(label_map)
    assert options == [
        (10, "10 Salgsinntekt"),
        (610, "610 Kundefordringer"),
        (790, "790 Skyldig off.avg."),
    ]


def test_build_rl_options_skips_malformed_labels() -> None:
    label_map = {"3000": "10 Salgsinntekt", "9999": "uten-regnr"}
    options = build_rl_options(label_map)
    assert options == [(10, "10 Salgsinntekt")]


def test_accounts_in_target_rl_filters_by_regnr() -> None:
    label_map = {
        "2700": "790 Skyldig off.avg.",
        "2740": "790 Skyldig off.avg.",
        "2770": "790 Skyldig off.avg.",
        "1500": "610 Kundefordringer",
    }
    assert accounts_in_target_rl(label_map, 790) == ["2700", "2740", "2770"]
    assert accounts_in_target_rl(label_map, 610) == ["1500"]
    assert accounts_in_target_rl(label_map, 999) == []


def test_mva_flagged_accounts_uses_group_names() -> None:
    group_map = {
        "2700": "Utgående MVA",
        "2740": "Inngående MVA",
        "2770": "Skyldig MVA",
        "1500": "Kundefordringer",  # ikke MVA
    }
    flagged = mva_flagged_accounts(group_map, ["2700", "2740", "2770", "1500", "9999"])
    assert flagged == {"2700", "2740", "2770"}


def test_build_mva_group_map_with_injected_loader() -> None:
    raw = {
        "2700": "Utgående MVA",
        "2740": "Inngående MVA",
        "1500": "Kundefordringer",
    }
    result = build_mva_group_map("Testklient", loader=lambda _c: raw)
    assert result == {"2700": "Utgående MVA", "2740": "Inngående MVA"}


def test_build_mva_group_map_returns_empty_without_client() -> None:
    assert build_mva_group_map(None) == {}


def test_format_rule_summary_account_mode_all() -> None:
    rule = ExpectedRule(target_regnr=610, account_mode="all")
    text = format_rule_summary(rule, regnr_to_label={610: "610 Kundefordringer"})
    assert "alle kontoer" in text
    assert "610 Kundefordringer" in text


def test_format_rule_summary_account_mode_selected_count() -> None:
    rule = ExpectedRule(
        target_regnr=790,
        account_mode="selected",
        allowed_accounts=("2740", "2770"),
    )
    text = format_rule_summary(rule, regnr_to_label={790: "790 Skyldig off.avg."})
    assert "kun 2 kontoer" in text


def test_format_rule_summary_all_with_excluded_accounts() -> None:
    rule = ExpectedRule(
        target_regnr=610,
        account_mode="all",
        excluded_accounts=("1520", "1530"),
    )
    text = format_rule_summary(rule, regnr_to_label={610: "610 Kundefordringer"})
    assert "alle kontoer" in text
    assert "2" in text
    assert "skopet ut" in text


def test_format_rule_summary_falls_back_to_regnr_when_label_missing() -> None:
    rule = ExpectedRule(target_regnr=999, account_mode="all")
    text = format_rule_summary(rule)
    assert text.startswith("999")


def test_load_all_rl_options_with_injected_loader() -> None:
    df = pd.DataFrame(
        {
            "regnr": [10, 610, 790, 10],  # duplikat for 10
            "regnskapslinje": [
                "Salgsinntekt",
                "Kundefordringer",
                "Skyldig off.avg.",
                "Salgsinntekt",
            ],
        }
    )
    result = load_all_rl_options(loader=lambda: df)
    assert result == [
        (10, "10 Salgsinntekt"),
        (610, "610 Kundefordringer"),
        (790, "790 Skyldig off.avg."),
    ]


def test_load_all_rl_options_excludes_source() -> None:
    df = pd.DataFrame(
        {"regnr": [10, 610], "regnskapslinje": ["Salgsinntekt", "Kundefordringer"]}
    )
    result = load_all_rl_options(loader=lambda: df, exclude_regnr=10)
    assert result == [(610, "610 Kundefordringer")]


def test_load_all_rl_options_returns_empty_on_loader_error() -> None:
    def broken_loader():
        raise RuntimeError("ingen fil")

    assert load_all_rl_options(loader=broken_loader) == []

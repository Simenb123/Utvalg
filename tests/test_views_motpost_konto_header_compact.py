from __future__ import annotations

import pandas as pd

import views_motpost_konto as vm
from motpost.konto_core import MotpostData


def _dummy_data(direction: str = "Alle") -> MotpostData:
    return MotpostData(
        selected_accounts=("3000", "3001", "3020"),
        bilag_count=42,
        selected_sum=-123.5,
        control_sum=0.0,
        df_motkonto=pd.DataFrame(),
        df_selected=pd.DataFrame(),
        df_scope=pd.DataFrame(),
        selected_direction=direction,
    )


def test_build_motpost_header_metrics_text_uses_direction_in_sum_label() -> None:
    data_all = _dummy_data("Alle")
    txt_all = vm.build_motpost_header_metrics_text(data_all)

    assert "Bilag i grunnlag: 42" in txt_all
    assert "Sum valgte kontoer" in txt_all
    assert "(kredit)" not in txt_all.lower()

    data_credit = _dummy_data("Kredit")
    txt_credit = vm.build_motpost_header_metrics_text(data_credit)

    assert "Bilag i grunnlag: 42" in txt_credit
    assert "sum valgte kontoer (kredit)" in txt_credit.lower()


def test_build_motpost_selected_accounts_label_and_value() -> None:
    data = _dummy_data()
    assert vm.build_motpost_selected_accounts_label(data) == "Valgte kontoer (3):"
    assert vm.build_motpost_selected_accounts_value(data) == "3000, 3001, 3020"


def test_build_motpost_scope_label_and_value_for_regnskapslinjer() -> None:
    items = ("10 Salgsinntekt", "40 LÃ¸nnskostnad")

    assert vm.build_motpost_scope_label(items, scope_mode="regnskapslinje") == "Valgte regnskapslinjer (2):"
    assert vm.build_motpost_scope_value(items) == "10 Salgsinntekt, 40 LÃ¸nnskostnad"


def test_build_motpost_rule_set_summary_text_uses_rule_list() -> None:
    from motpost.expected_rules import ExpectedRule, ExpectedRuleSet

    label_map = {
        "1500": "610 Kundefordringer",
        "2700": "790 Skyldig off.avg.",
    }
    empty_text = vm.build_motpost_rule_set_summary_text(
        ExpectedRuleSet(source_regnr=10, selected_direction="alle"),
        konto_regnskapslinje_map=label_map,
    )
    assert "ingen regler" in empty_text.lower()

    rule_set = ExpectedRuleSet(
        source_regnr=10,
        selected_direction="alle",
        rules=(
            ExpectedRule(target_regnr=610, account_mode="all"),
            ExpectedRule(
                target_regnr=790,
                account_mode="selected",
                allowed_accounts=("2740", "2770"),
                requires_netting=True,
                netting_tolerance=1.0,
            ),
        ),
    )
    text = vm.build_motpost_rule_set_summary_text(
        rule_set, konto_regnskapslinje_map=label_map
    )
    assert "Forventningsregler (2)" in text
    assert "610 Kundefordringer" in text
    assert "790 Skyldig off.avg." in text
    assert "utligning" in text


class DummyEntry:
    def __init__(self) -> None:
        self.bindings: dict[str, object] = {}
        self.selection_args: tuple[object, object] | None = None
        self.icursor_arg: object | None = None

    def bind(self, seq: str, fn, add: str | None = None):
        # We keep the last binding per sequence.
        self.bindings[seq] = fn

    def selection_range(self, a, b) -> None:
        self.selection_args = (a, b)

    def icursor(self, where) -> None:
        self.icursor_arg = where


def test_bind_entry_select_all_binds_ctrl_a_and_selects_all() -> None:
    ent = DummyEntry()
    vm.bind_entry_select_all(ent)

    assert "<Control-a>" in ent.bindings
    assert "<Control-A>" in ent.bindings

    res = ent.bindings["<Control-a>"](None)
    assert res == "break"
    assert ent.selection_args == (0, "end")
    assert ent.icursor_arg == "end"

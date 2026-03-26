from __future__ import annotations

import pandas as pd


def test_build_leaf_regnskapslinje_choices_returns_sorted_leaf_rows() -> None:
    from views_rl_account_drill import build_leaf_regnskapslinje_choices

    regnskapslinjer = pd.DataFrame(
        {
            "nr": [30, 10, 20],
            "regnskapslinje": ["Sumlinje", "Salg", "Varekostnad"],
            "sumpost": ["ja", "nei", "nei"],
            "Formel": ["10+20", "", ""],
        }
    )

    assert build_leaf_regnskapslinje_choices(regnskapslinjer) == [
        (10, "Salg"),
        (20, "Varekostnad"),
    ]


def test_format_and_parse_regnskapslinje_choice_roundtrip() -> None:
    from views_rl_account_drill import format_regnskapslinje_choice, parse_regnskapslinje_choice

    value = format_regnskapslinje_choice(610, "Kundefordringer")

    assert value == "610 - Kundefordringer"
    assert parse_regnskapslinje_choice(value) == 610
    assert parse_regnskapslinje_choice("610") == 610
    assert parse_regnskapslinje_choice("") is None

import pandas as pd

from views_selection_studio_ui import parse_custom_strata_bounds, stratify_values_custom_bounds


def test_parse_custom_strata_bounds_parses_semicolon_separated_norwegian_numbers() -> None:
    bounds = parse_custom_strata_bounds("100 000; 500000; 1 000 000")
    assert bounds == [100000.0, 500000.0, 1000000.0]


def test_parse_custom_strata_bounds_sorts_deduplicates_and_ignores_invalid() -> None:
    bounds = parse_custom_strata_bounds("500; 100; 100; foo\n300")
    assert bounds == [100.0, 300.0, 500.0]


def test_stratify_values_custom_bounds_creates_expected_groups_and_intervals() -> None:
    s = pd.Series([10, 50, 150, 250], index=["a", "b", "c", "d"])
    groups, interval_map, stats = stratify_values_custom_bounds(s, bounds=[100, 200])

    assert [g for g, _ in groups] == [1, 2, 3]
    assert "1" in interval_map and "2" in interval_map and "3" in interval_map
    assert "–" in interval_map["1"]

    mask1 = groups[0][1]
    mask2 = groups[1][1]
    mask3 = groups[2][1]
    assert set(mask1[mask1].index) == {"a", "b"}
    assert set(mask2[mask2].index) == {"c"}
    assert set(mask3[mask3].index) == {"d"}

    antall = stats.set_index("Gruppe")["Antall"].to_dict()
    assert antall == {1: 2, 2: 1, 3: 1}


def test_stratify_values_custom_bounds_handles_empty_bounds_as_single_group() -> None:
    s = pd.Series([1, 2, 3])
    groups, interval_map, stats = stratify_values_custom_bounds(s, bounds=[])

    assert [g for g, _ in groups] == [1]
    assert "1" in interval_map
    assert stats.iloc[0]["Antall"] == 3

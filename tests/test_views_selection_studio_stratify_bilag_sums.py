import pandas as pd

from views_selection_studio_ui import stratify_bilag_sums


def _assert_masks_cover_all(groups, index):
    combined = pd.Series(False, index=index)
    for _label, mask in groups:
        # same index
        assert list(mask.index) == list(index)
        # disjointness: no overlap
        assert not (combined & mask).any()
        combined = combined | mask
    assert combined.all()


def test_stratify_bilag_sums_quantile_basic_two_groups():
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], index=list("ABCDEFGHIJ"))
    groups, interval_map, stats_df = stratify_bilag_sums(s, method="quantile", k=2)

    assert len(groups) == 2
    _assert_masks_cover_all(groups, s.index)

    # labels start at 1
    assert [g for g, _m in groups] == [1, 2]
    assert set(interval_map.keys()) == {"1", "2"}

    # Stats columns
    assert set(["Gruppe", "Antall", "Sum", "Min", "Max"]).issubset(stats_df.columns)

    # Each group should have 5 entries for this simple monotonic series
    antall = stats_df.set_index("Gruppe")["Antall"].to_dict()
    assert antall[1] == 5
    assert antall[2] == 5

    # Interval text should be norwegian formatted (has dash and comma)
    assert "–" in interval_map["1"]
    assert "," in interval_map["1"]


def test_stratify_bilag_sums_equal_width_basic():
    s = pd.Series([0, 1, 2, 3], index=[10, 11, 12, 13])
    groups, interval_map, stats_df = stratify_bilag_sums(s, method="equal_width", k=2)

    assert len(groups) == 2
    _assert_masks_cover_all(groups, s.index)
    assert set(interval_map.keys()) == {"1", "2"}
    assert stats_df["Antall"].sum() == 4


def test_stratify_bilag_sums_quantile_all_equal_falls_back_to_one_group():
    s = pd.Series([5, 5, 5], index=["x", "y", "z"])
    groups, interval_map, stats_df = stratify_bilag_sums(s, method="quantile", k=3)

    assert len(groups) == 1
    label, mask = groups[0]
    assert label == 1
    assert mask.all()
    assert interval_map.get("1")
    assert stats_df["Antall"].iloc[0] == 3

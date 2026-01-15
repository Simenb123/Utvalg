import pandas as pd
import pytest

from views_selection_studio_ui import build_bilag_dataframe


def test_build_bilag_dataframe_happy_path_sums_per_bilag():
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 2],
            "Dato": ["01.01.2024", "01.01.2024", "02.01.2024"],
            "Tekst": ["A", "A2", "B"],
            "Beløp": [100.0, 50.0, -25.0],
        }
    )

    out = build_bilag_dataframe(df)

    assert list(out.columns) == ["Bilag", "Dato", "Tekst", "SumBeløp"]
    assert len(out) == 2

    v1 = out.loc[out["Bilag"] == 1, "SumBeløp"].iloc[0]
    v2 = out.loc[out["Bilag"] == 2, "SumBeløp"].iloc[0]
    assert v1 == pytest.approx(150.0)
    assert v2 == pytest.approx(-25.0)


def test_build_bilag_dataframe_accepts_already_aggregated_sum_column():
    df = pd.DataFrame(
        {
            "Bilag": [10, 11],
            "Dato": ["03.01.2024", "04.01.2024"],
            "Tekst": ["X", "Y"],
            "SumBeløp": [123.0, -456.0],
        }
    )

    out = build_bilag_dataframe(df)

    assert out["SumBeløp"].tolist() == [123.0, -456.0]


def test_build_bilag_dataframe_accepts_belop_without_norwegian_char():
    df = pd.DataFrame(
        {
            "Bilag": [1, 1],
            "Belop": [10, 20],
        }
    )

    out = build_bilag_dataframe(df)

    assert len(out) == 1
    assert out["SumBeløp"].iloc[0] == pytest.approx(30.0)
    # date/text filled in
    assert out["Dato"].iloc[0] in ("", None)
    assert out["Tekst"].iloc[0] in ("", None)


def test_build_bilag_dataframe_raises_keyerror_when_missing_bilag():
    df = pd.DataFrame({"Beløp": [1, 2, 3]})
    with pytest.raises(KeyError):
        build_bilag_dataframe(df)

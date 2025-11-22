import pandas as pd
import pytest

from selectionstudio_filters import filter_selectionstudio_dataframe


def _make_df():
    # Lite datasett som ligner på utvalg/stratifisering-grunnlag
    data = [
        {"Bilag": 1, "Beløp": 100.0},
        {"Bilag": 2, "Beløp": -50.0},
        {"Bilag": 3, "Beløp": 250.0},
        {"Bilag": 4, "Beløp": -300.0},
    ]
    return pd.DataFrame(data)


def test_filter_selectionstudio_debet_only():
    df_base = _make_df()

    df, summary = filter_selectionstudio_dataframe(
        df_base=df_base,
        direction="Debet",
        min_value="",
        max_value="",
        use_abs=False,
    )

    # Bare positive beløp skal være igjen
    assert set(df["Bilag"].tolist()) == {1, 3}
    assert summary["N"] == 2
    # Summen skal være sum av alle debetbeløp
    assert summary["S"] == pytest.approx(350.0)


def test_filter_selectionstudio_kredit_only():
    df_base = _make_df()

    df, summary = filter_selectionstudio_dataframe(
        df_base=df_base,
        direction="Kredit",
        min_value="",
        max_value="",
        use_abs=False,
    )

    # Bare negative beløp skal være igjen
    assert set(df["Bilag"].tolist()) == {2, 4}
    assert summary["N"] == 2
    assert summary["S"] == pytest.approx(-350.0)


def test_filter_selectionstudio_min_max_netto():
    df_base = _make_df()

    # direction Alle, min 0, max 200 → kun bilag 1 (100 ligger i intervallet, -50 gjør ikke det)
    df, summary = filter_selectionstudio_dataframe(
        df_base=df_base,
        direction="Alle",
        min_value="0",
        max_value="200",
        use_abs=False,
    )

    assert set(df["Bilag"].tolist()) == {1}
    # Netto sum: 100
    assert summary["S"] == pytest.approx(100.0)


def test_filter_selectionstudio_min_max_abs():
    df_base = _make_df()

    # abs=True, min 200 → bilag 3 (250) og 4 (|-300|)
    df, summary = filter_selectionstudio_dataframe(
        df_base=df_base,
        direction="Alle",
        min_value="200",
        max_value="",
        use_abs=True,
    )

    assert set(df["Bilag"].tolist()) == {3, 4}
    # Netto sum for 3 og 4: 250 - 300 = -50
    assert summary["S"] == pytest.approx(-50.0)


def test_filter_selectionstudio_handles_norwegian_numbers_and_empty():
    df_base = _make_df()

    # Norsk format med mellomrom og komma
    df, summary = filter_selectionstudio_dataframe(
        df_base=df_base,
        direction="Alle",
        min_value=" 1 0 0,0 ",
        max_value=" 3 0 0,0 ",
        use_abs=True,
    )

    # abs-beløp mellom 100 og 300 → bilag 1, 3 og 4
    assert set(df["Bilag"].tolist()) == {1, 3, 4}
    assert summary["N"] == 3

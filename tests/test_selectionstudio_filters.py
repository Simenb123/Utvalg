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


def test_filter_selectionstudio_excludes_zero_netto_bilag_when_min_amount_is_set():
    """Beløpsfilteret i Utvalg/Selection Studio skal virke på *bilagsnetto*.

    Hvis et bilag består av flere linjer som summerer til 0 (f.eks. korrigeringer),
    skal bilaget filtreres bort når min-beløp > 0.
    """

    df_base = pd.DataFrame(
        {
            "Bilag": [1, 1, 2],
            "Beløp": [100.0, -100.0, 50.0],
        }
    )

    df, summary = filter_selectionstudio_dataframe(
        df_base=df_base,
        direction="Alle",
        min_value="10",
        max_value="",
        use_abs=True,
    )

    assert set(df["Bilag"].tolist()) == {2}
    assert summary["N"] == 1
    assert summary["amount_filter_active"] is True
    assert summary["removed_by_amount_rows"] == 2
    assert summary["removed_by_amount_sum_net"] == 0.0
    assert summary["removed_by_amount_sum_abs"] == 200.0


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


def test_selectionstudio_filters_summary_includes_abs_removed_by_amount():
    """When using absolute amount filtering, we want net+abs sums for what is filtered out."""

    df = pd.DataFrame(
        {
            "Dato": ["2025-01-01", "2025-01-01", "2025-01-01"],
            "Beløp": [-50.0, 50.0, 200.0],
        }
    )

    df_f, summary = filter_selectionstudio_dataframe(
        df,
        direction="Alle",
        min_value="100",
        max_value="",
        use_abs=True,
    )

    assert df_f["Beløp"].tolist() == [200.0]
    assert summary["amount_filter_active"] is True
    assert summary["removed_by_amount_rows"] == 2
    # Net sum cancels out, but abs sum shows actual magnitude removed
    assert summary["removed_by_amount_sum_net"] == 0.0
    assert summary["removed_by_amount_sum_abs"] == 100.0


def test_selectionstudio_filters_date_range_filter():
    df = pd.DataFrame(
        {
            "Dato": ["2025-01-15", "2025-02-15", "2025-03-15"],
            "Beløp": [10.0, 20.0, 30.0],
        }
    )

    df_f, summary = filter_selectionstudio_dataframe(
        df,
        direction="Alle",
        min_value="",
        max_value="",
        use_abs=True,
        date_from="01.02.2025",
        date_to="28.02.2025",
    )

    assert df_f["Beløp"].tolist() == [20.0]
    assert summary["date_filter_active"] is True
    assert summary["removed_by_date_rows"] == 2


def test_filter_selectionstudio_min_amount_is_checked_on_bilag_net_sum_not_line_level():
    """Regresjonstest for beløpsfilteret:

    Beløpsfilteret skal sjekkes på *bilagsnetto* (sum Beløp pr bilag), ikke på linjenivå.

    Eksempel: Et bilag kan ha store debet/kredit-linjer som nesten utligner hverandre.
    Da kan hver linje være "stor" mens bilagsnetto er liten.

    Med min=100 skal bilag med netto 40 filtreres bort.
    """

    df_base = pd.DataFrame(
        {
            "Bilag": [1, 1, 2],
            "Beløp": [1000.0, -960.0, 150.0],
        }
    )

    df, summary = filter_selectionstudio_dataframe(
        df_base=df_base,
        direction="Alle",
        min_value="100",
        max_value="",
        use_abs=True,
    )

    assert set(df["Bilag"].tolist()) == {2}
    assert summary["N"] == 1
    assert summary["amount_filter_active"] is True
    assert summary["removed_by_amount_rows"] == 2
    assert summary["removed_by_amount_sum_net"] == pytest.approx(40.0)
    assert summary["removed_by_amount_sum_abs"] == pytest.approx(1960.0)

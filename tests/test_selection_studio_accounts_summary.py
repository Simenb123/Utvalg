import pandas as pd
import pytest

from src.pages.utvalg.selection_studio.ui_widget_actions import build_konto_summary_df


def test_build_konto_summary_df_happy_path_counts_and_sums_and_sorts() -> None:
    df = pd.DataFrame(
        {
            "Konto": [3000, 3000, 3100, 3200, 3200, 3200],
            "Kontonavn": ["Salg", "Salg", "Tjenester", "Annet", "Annet", "Annet"],
            "Bilag": [1, 1, 2, 3, 4, 4],
            "Beløp": [100.0, -20.0, 50.0, -200.0, 10.0, 5.0],
        }
    )

    out = build_konto_summary_df(df)

    assert set(out.columns) >= {"Konto", "Rader", "Bilag", "Sum"}

    # Konto 3000: 2 rows, 1 bilag, sum 80
    r3000 = out.loc[out["Konto"] == 3000].iloc[0]
    assert int(r3000["Rader"]) == 2
    assert int(r3000["Bilag"]) == 1
    assert float(r3000["Sum"]) == pytest.approx(80.0)

    # Konto 3200: 3 rows, 2 bilag (3 and 4), sum -185
    r3200 = out.loc[out["Konto"] == 3200].iloc[0]
    assert int(r3200["Rader"]) == 3
    assert int(r3200["Bilag"]) == 2
    assert float(r3200["Sum"]) == pytest.approx(-185.0)

    # Sorted by abs(sum) descending => konto 3200 (185) should come before 3000 (80)
    konto_order = out["Konto"].tolist()
    assert konto_order.index(3200) < konto_order.index(3000)


def test_build_konto_summary_df_raises_keyerror_when_missing_konto() -> None:
    df = pd.DataFrame({"Bilag": [1], "Beløp": [10.0]})
    with pytest.raises(KeyError):
        build_konto_summary_df(df)

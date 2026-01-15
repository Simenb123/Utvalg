import pandas as pd

from selection_studio_drill import (
    _resolve_drilldown_inputs,
    annotate_scope,
    extract_bilag_rows,
    konto_set_from_df,
    normalize_bilag_value,
)


def test_normalize_bilag_value_strips_trailing_dot_zero():
    assert normalize_bilag_value("101.0") == "101"
    assert normalize_bilag_value(101.0) == "101"
    assert normalize_bilag_value("  00101  ") == "00101"


def test_extract_bilag_rows_matches_numeric_and_string_variants():
    df = pd.DataFrame(
        {
            "Bilag": [101, 101.0, "101", "00101", 202],
            "Konto": [6200, 6200, 6300, 6400, 6500],
            "Beløp": [10, -10, 5, 5, 1],
        }
    )

    rows = extract_bilag_rows(df, "101")
    # 101 should match all four first rows (including '00101' via numeric comparison)
    assert len(rows) == 4
    assert set(rows["Konto"].tolist()) == {6200, 6300, 6400}

    rows2 = extract_bilag_rows(df, "202")
    assert len(rows2) == 1
    assert rows2.iloc[0]["Konto"] == 6500


def test_annotate_scope_marks_accounts_in_selection():
    df_base = pd.DataFrame({"Konto": [6200, "6300.0"]})
    konto_set = konto_set_from_df(df_base)

    df_rows = pd.DataFrame({"Konto": [6200, 6300, 6400]})
    out = annotate_scope(df_rows, konto_set)
    assert out["I kontoutvalg"].tolist() == [True, True, False]


def test_resolve_drilldown_inputs_accepts_aliases_for_bilag_value():
    master = object()
    df = pd.DataFrame({"Bilag": [1], "Konto": [1000], "Beløp": [10]})

    # bilag_value not given => should pick preset_bilag
    base, all_df, bilag, col = _resolve_drilldown_inputs(
        master,
        df_base=df,
        df_all=df,
        bilag_value=None,
        preset_bilag="101",
        bilag_col="Bilag",
    )
    assert bilag == "101"
    assert col == "Bilag"
    assert base is df
    assert all_df is df

    # bilag_value wins over aliases
    base2, all_df2, bilag2, _ = _resolve_drilldown_inputs(
        master,
        df_base=df,
        df_all=df,
        bilag_value="202",
        preset_bilag="101",
        bilag="303",
        bilag_id="404",
        selected_bilag="505",
        bilag_col="Bilag",
    )
    assert bilag2 == "202"
    assert base2 is df
    assert all_df2 is df


def test_resolve_drilldown_inputs_infers_df_base_from_master_when_missing():
    class DummyMaster:
        def __init__(self, df_base: pd.DataFrame) -> None:
            self._df_base = df_base

    df_base = pd.DataFrame({"Bilag": [1], "Konto": [1000], "Beløp": [10]})
    master = DummyMaster(df_base)

    base, all_df, bilag, col = _resolve_drilldown_inputs(
        master,
        df_base=None,
        df_all=None,
        bilag_value=None,
        preset_bilag=123,
        bilag_col=None,  # type: ignore[arg-type] - deliberate robustness test
    )
    assert isinstance(base, pd.DataFrame)
    assert base.equals(df_base)
    assert isinstance(all_df, pd.DataFrame)
    assert all_df.equals(df_base)
    assert bilag == 123
    assert col == "Bilag"

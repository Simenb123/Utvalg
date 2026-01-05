import pandas as pd

from selection_studio_drill import annotate_scope, extract_bilag_rows, konto_set_from_df, normalize_bilag_value


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

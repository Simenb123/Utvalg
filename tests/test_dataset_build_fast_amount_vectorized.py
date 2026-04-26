import pandas as pd


from src.pages.dataset.backend.build_fast import _coerce_amount_series


def test_coerce_amount_series_vectorized_parses_common_formats() -> None:
    s = pd.Series(
        [
            "1 234,50",
            "(34,50)",
            "100-",
            "1.234,50",
            "1,234.50",
            "1234",
            "-12,00",
        ]
    )
    out = _coerce_amount_series(s)
    assert out.tolist() == [1234.50, -34.50, -100.0, 1234.50, 1234.50, 1234.0, -12.0]


def test_coerce_amount_series_vectorized_handles_numeric_dtype_fastpath() -> None:
    s = pd.Series([1.5, 2.0, None])
    out = _coerce_amount_series(s)
    assert out.iloc[0] == 1.5
    assert out.iloc[1] == 2.0
    assert pd.isna(out.iloc[2])

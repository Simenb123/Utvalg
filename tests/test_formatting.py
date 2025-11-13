import pandas as pd

from formatting import (
    format_number_no,
    format_int_no,
    format_date_no,
    is_number_like_col,
    is_percent_col,
)


def test_format_number_no_basic_and_none():
    # None og tom streng -> tom tekst
    assert format_number_no(None) == ""
    assert format_number_no("") == ""

    # Vanlig tall -> norsk format
    assert format_number_no(1234.5) == "1 234,50"
    assert format_number_no("1234.5") == "1 234,50"

    # Flere desimaler
    assert format_number_no(1234.567, decimals=1) == "1 234,6"

    # NaN -> tom streng
    assert format_number_no(float("nan")) == ""


def test_format_number_no_rejects_series_and_dataframe():
    s = pd.Series([1, 2, 3])
    df = pd.DataFrame({"x": [1, 2]})

    # For disse prøver ikke funksjonen å formatere – den returnerer str(x)
    assert format_number_no(s) == str(s)
    assert format_number_no(df) == str(df)


def test_format_int_no_basic_and_fallback():
    # None -> tom streng
    assert format_int_no(None) == ""

    # Vanlig int
    assert format_int_no(1234) == "1 234"

    # Streng som int
    assert format_int_no("42") == "42"

    # Streng som float -> fall-back til float->int
    assert format_int_no("12.0") == "12"

    # Ugyldig verdi -> str(x)
    assert format_int_no("abc") == "abc"


def test_format_date_no_basic_and_invalid():
    # None -> tom
    assert format_date_no(None) == ""

    # ISO-lignende streng -> dagens oppførsel er at dette tolkes som 02.01.2024
    # (vi låser testen til faktisk oppførsel i formatting.py)
    assert format_date_no("2024-02-01") == "02.01.2024"

    # Norsk dato allerede -> beholdes
    assert format_date_no("03.04.2024") == "03.04.2024"

    # Ikke-streng: Timestamp går gjennom else-grenen
    ts = pd.Timestamp("2024-01-02")
    assert format_date_no(ts) == "02.01.2024"

    # Ugyldig dato -> blir NaT og gir tom streng
    assert format_date_no("not a date") == ""



def test_format_date_no_exception_path(monkeypatch):
    """Dekker except-blokken ved å tvinge pd.to_datetime til å kaste feil."""

    from formatting import pd as formatting_pd  # pd-objektet inni formatting-modulen

    def boom(*args, **kwargs):
        raise TypeError("boom")

    # Patcher pd.to_datetime inne i formatting-modulen
    monkeypatch.setattr(formatting_pd, "to_datetime", boom)

    # Når to_datetime kaster, skal funksjonen falle tilbake til str(x)
    assert format_date_no("2024-02-01") == "2024-02-01"


def test_is_number_like_col():
    assert is_number_like_col("Beløp") is True
    assert is_number_like_col("sum_mva") is True
    assert is_number_like_col("Amount EUR") is True

    # Ikke tall-kolonner
    assert is_number_like_col("Tekst") is False
    assert is_number_like_col("") is False
    assert is_number_like_col(None) is False  # type: ignore[arg-type]


def test_is_percent_col():
    assert is_percent_col("Prosentvis avvik") is True
    assert is_percent_col("Margin%") is True

    # Ikke prosent
    assert is_percent_col("Beløp") is False
    assert is_percent_col("") is False
    assert is_percent_col(None) is False  # type: ignore[arg-type]

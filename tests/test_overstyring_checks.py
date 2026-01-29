import pandas as pd

from override_checks import (
    build_voucher_summary,
    duplicate_lines_vouchers,
    large_vouchers,
    override_risk_vouchers,
    round_amount_vouchers,
)
from override_check_registry import run_override_check_by_id


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # Bilag 1: stort (én-linje) bilag
            {"Bilag": "1", "Konto": "1920", "Beløp": 2_000_000, "Dato": "2025-12-31", "Tekst": "Innbetaling", "Dokumentnr": "INV1"},
            # Bilag 2: runde beløp (balanserer)
            {"Bilag": "2", "Konto": "3000", "Beløp": 10_000, "Dato": "2025-01-15", "Tekst": "Salg", "Dokumentnr": "INV2"},
            {"Bilag": "2", "Konto": "1500", "Beløp": -10_000, "Dato": "2025-01-15", "Tekst": "Salg", "Dokumentnr": "INV2"},
            # Bilag 3: dupliserte linjer
            {"Bilag": "3", "Konto": "6100", "Beløp": 5_000, "Dato": "2025-02-01", "Tekst": "Kostnad", "Dokumentnr": "INV3"},
            {"Bilag": "3", "Konto": "6100", "Beløp": 5_000, "Dato": "2025-02-01", "Tekst": "Kostnad", "Dokumentnr": "INV3"},
            {"Bilag": "3", "Konto": "1920", "Beløp": -10_000, "Dato": "2025-02-01", "Tekst": "Kostnad", "Dokumentnr": "INV3"},
            # Bilag 4: risiko (keyword + mangler dokumentnr + månedsslutt)
            {"Bilag": "4", "Konto": "1230", "Beløp": 200_000, "Dato": "2025-03-31", "Tekst": "Kontant uttak private", "Dokumentnr": ""},
        ]
    )


def test_build_voucher_summary_has_expected_columns() -> None:
    df = _sample_df()
    summ = build_voucher_summary(df)

    expected_cols = {
        "Bilag",
        "AntallLinjer",
        "SumDebet",
        "SumKredit",
        "SumDebetAbs",
        "SumKreditAbs",
        "SumAbs",
        "Netto",
        "NettoAbs",
        "Max line abs",
        "DatoMin",
        "DatoMax",
        "KontoNunique",
        "TekstNunique",
        "DokumentnrNunique",
    }
    assert expected_cols.issubset(set(summ.columns))

    # Bilag 2 balanserer -> netto ca 0
    netto_2 = float(summ.loc[summ["Bilag"] == "2", "Netto"].iloc[0])
    assert abs(netto_2) < 1e-9


def test_large_vouchers_flags_big_single_line_voucher() -> None:
    df = _sample_df()
    res = large_vouchers(df, threshold=1_500_000)
    assert not res.summary_df.empty
    assert set(res.summary_df["Bilag"].astype(str).tolist()) == {"1"}


def test_round_amount_vouchers_flags_round_lines() -> None:
    df = _sample_df()
    res = round_amount_vouchers(df, round_base=10_000)
    assert not res.summary_df.empty
    assert "AntallRundeLinjer" in res.summary_df.columns
    assert "2" in set(res.summary_df["Bilag"].astype(str).tolist())


def test_duplicate_lines_vouchers_flags_duplicates() -> None:
    df = _sample_df()
    res = duplicate_lines_vouchers(df, min_count=2)
    assert not res.summary_df.empty
    assert "3" in set(res.summary_df["Bilag"].astype(str).tolist())
    assert "__IsDuplicate__" in res.lines_df.columns


def test_override_risk_vouchers_flags_keyword_and_missing_doc() -> None:
    df = _sample_df()
    res = override_risk_vouchers(df, min_score=1.5, min_abs_amount=100_000)
    assert not res.summary_df.empty
    assert "Risikoscore" in res.summary_df.columns
    assert "4" in set(res.summary_df["Bilag"].astype(str).tolist())


def test_registry_run_by_id() -> None:
    df = _sample_df()
    res = run_override_check_by_id(
        "round_amounts",
        df_all=df,
        params={"round_base": 10_000, "require_zero_cents": True, "top_n": 50},
    )
    assert not res.summary_df.empty

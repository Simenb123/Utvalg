from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_filter_control_gl_df_supports_search_and_only_unmapped() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Fast lonn", "IB": 0.0, "Endring": 1200.0, "UB": 1200.0, "Kode": "fastloenn"},
            {"Konto": "6990", "Navn": "Telefon", "IB": 0.0, "Endring": 250.0, "UB": 250.0, "Kode": ""},
            {"Konto": "7100", "Navn": "Bonus", "IB": 0.0, "Endring": 300.0, "UB": 300.0, "Kode": ""},
        ]
    )

    out = page_a07.filter_control_gl_df(control_gl_df, search_text="tele", only_unmapped=True)

    assert out["Konto"].tolist() == ["6990"]

def test_filter_control_gl_df_supports_active_only_and_keeps_mapped_rows() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "1000", "Navn": "Tom konto", "IB": 0.0, "Endring": 0.0, "UB": 0.0, "Kode": ""},
            {"Konto": "1020", "Navn": "Mapped nullkonto", "IB": 0.0, "Endring": 0.0, "UB": 0.0, "Kode": "fastloenn"},
            {"Konto": "5000", "Navn": "Lonn", "IB": 0.0, "Endring": 1200.0, "UB": 1200.0, "Kode": ""},
        ]
    )

    out = page_a07.filter_control_gl_df(control_gl_df, active_only=True)

    assert out["Konto"].tolist() == ["1020", "5000"]

def test_filter_control_gl_df_supports_multiple_account_series() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "1940", "Navn": "Bank", "IB": 10.0, "Endring": 0.0, "UB": 10.0, "Kode": ""},
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "IB": -100.0, "Endring": 20.0, "UB": -80.0, "Kode": "feriepenger"},
            {"Konto": "5000", "Navn": "Fast lonn", "IB": 0.0, "Endring": 1200.0, "UB": 1200.0, "Kode": "fastloenn"},
            {"Konto": "6000", "Navn": "Husleie", "IB": 0.0, "Endring": 250.0, "UB": 250.0, "Kode": ""},
        ]
    )

    out = page_a07.filter_control_gl_df(control_gl_df, account_series="2,5")

    assert out["Konto"].tolist() == ["2940", "5000"]

def test_filter_control_visible_codes_df_hides_non_matching_codes_for_this_view() -> None:
    control_df = pd.DataFrame(
        [
            {"Kode": "forskuddstrekk", "Navn": "Forskuddstrekk"},
            {"Kode": "aga", "Navn": "AGA"},
            {"Kode": "finansskattloenn", "Navn": "FinansskattLonn"},
            {"Kode": "feriepenger", "Navn": "Feriepenger"},
        ]
    )

    out = page_a07.filter_control_visible_codes_df(control_df)

    assert list(out["Kode"]) == ["feriepenger"]


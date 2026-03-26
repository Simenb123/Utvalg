from __future__ import annotations

from decimal import Decimal

import pandas as pd

from a07_feature import mapping_to_assigned_df, reconcile_a07_vs_gl, unmapped_accounts_df


def test_reconcile_happy_path_includes_counts_and_tolerance():
    a07_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": "1000"},
            {"Kode": "bonus", "Navn": "Bonus", "Belop": "200"},
        ]
    )
    gl_df = pd.DataFrame(
        [
            {"Konto": "3000", "Navn": "Loenn", "UB": "1000"},
            {"Konto": "3001", "Navn": "Bonus", "UB": "200"},
        ]
    )

    mapping = {"3000": "fastloenn", "3001": "bonus"}
    out = reconcile_a07_vs_gl(a07_df, gl_df, mapping, basis_col="UB")

    row_fast = out.loc[out["Kode"] == "fastloenn"].iloc[0]
    assert row_fast["AntallKontoer"] == 1
    assert row_fast["Kontoer"] == "3000"
    assert row_fast["Diff"] == Decimal("0.00")
    assert bool(row_fast["WithinTolerance"]) is True


def test_reconcile_filters_excluded_codes_by_default():
    a07_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": "1000"},
            {"Kode": "aga", "Navn": "AGA", "Belop": "141"},
            {"Kode": "forskuddstrekk", "Navn": "Forskuddstrekk", "Belop": "50"},
        ]
    )
    gl_df = pd.DataFrame(
        [
            {"Konto": "3000", "Navn": "Loenn", "UB": "1000"},
            {"Konto": "5400", "Navn": "AGA", "UB": "141"},
            {"Konto": "2770", "Navn": "Forskuddstrekk", "UB": "50"},
        ]
    )
    mapping = {"3000": "fastloenn", "5400": "aga", "2770": "forskuddstrekk"}

    out = reconcile_a07_vs_gl(a07_df, gl_df, mapping, basis_col="UB")

    assert "aga" not in out["Kode"].astype(str).tolist()
    assert "forskuddstrekk" not in out["Kode"].astype(str).tolist()
    assert "fastloenn" in out["Kode"].astype(str).tolist()


def test_unmapped_accounts_treats_excluded_codes_as_unmapped():
    gl_df = pd.DataFrame(
        [
            {"Konto": "3000", "Navn": "Loenn", "UB": "1000"},
            {"Konto": "5400", "Navn": "AGA", "UB": "141"},
        ]
    )
    mapping = {"3000": "fastloenn", "5400": "aga"}

    df = unmapped_accounts_df(gl_df, mapping, basis_col="UB")

    assert "5400" in df["Konto"].astype(str).tolist()
    assert df.loc[df["Konto"].astype(str) == "5400", "Kode"].iloc[0] == ""


def test_mapping_to_assigned_df_blanks_excluded_codes():
    gl_df = pd.DataFrame([{"Konto": "5400", "Navn": "AGA", "UB": "141"}])
    assigned = mapping_to_assigned_df({"5400": "aga"}, gl_df, include_empty=True)

    assert assigned.iloc[0]["Konto"] == "5400"
    assert assigned.iloc[0]["Kode"] == ""


def test_unmapped_accounts_supports_ib_minus_ub_basis():
    gl_df = pd.DataFrame([{"Konto": "2940", "Navn": "Skyldig feriepenger", "IB": "100", "UB": "140"}])
    df = unmapped_accounts_df(gl_df, {}, basis_col="IB-UB")

    assert df.loc[df["Konto"].astype(str) == "2940", "GL_Belop"].iloc[0] == Decimal("-40.00")

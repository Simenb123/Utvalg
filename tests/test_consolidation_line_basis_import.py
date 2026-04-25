from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.pages.consolidation.backend.line_basis_import import (
    export_line_basis_template,
    normalize_company_line_basis,
    validate_company_line_basis,
)


def _regnskapslinjer_df() -> pd.DataFrame:
    return pd.DataFrame({
        "regnr": [10, 11, 20],
        "regnskapslinje": ["Eiendeler", "Inntekter", "SUM"],
        "sumpost": [False, False, True],
        "formel": [None, None, "=10+11"],
    })


def test_validate_company_line_basis_normalizes_names_and_keeps_source_name() -> None:
    df = pd.DataFrame({
        "regnr": [10, 11],
        "regnskapslinje": ["Bankmidler", "Salg"],
        "ub": [100.0, -50.0],
    })

    normalized, warnings = validate_company_line_basis(df, regnskapslinjer=_regnskapslinjer_df())

    assert normalized["regnskapslinje"].tolist() == ["Eiendeler", "Inntekter"]
    assert normalized["source_regnskapslinje"].tolist() == ["Bankmidler", "Salg"]
    assert warnings


def test_validate_company_line_basis_blocks_unknown_regnr() -> None:
    df = pd.DataFrame({
        "regnr": [999],
        "regnskapslinje": ["Ukjent"],
        "ub": [100.0],
    })

    with pytest.raises(ValueError, match="Ukjente regnr"):
        validate_company_line_basis(df, regnskapslinjer=_regnskapslinjer_df())


def test_validate_company_line_basis_blocks_sumlines() -> None:
    df = pd.DataFrame({
        "regnr": [20],
        "regnskapslinje": ["SUM"],
        "ub": [100.0],
    })

    with pytest.raises(ValueError, match="Sumlinjer"):
        validate_company_line_basis(df, regnskapslinjer=_regnskapslinjer_df())


def test_validate_company_line_basis_blocks_duplicates() -> None:
    df = pd.DataFrame({
        "regnr": [10, 10],
        "regnskapslinje": ["Eiendeler", "Eiendeler"],
        "ub": [100.0, 50.0],
    })

    with pytest.raises(ValueError, match="Dupliserte regnr"):
        validate_company_line_basis(df, regnskapslinjer=_regnskapslinjer_df())


def test_normalize_company_line_basis_handles_optional_pdf_columns() -> None:
    df = pd.DataFrame({
        "Regnr": [10],
        "Regnskapslinje": ["Eiendeler"],
        "UB": ["1 234,50"],
        "source_page": [2],
        "confidence": [0.83],
        "review_status": ["approved"],
    })

    normalized = normalize_company_line_basis(df)

    assert int(normalized.iloc[0]["regnr"]) == 10
    assert float(normalized.iloc[0]["ub"]) == pytest.approx(1234.50)
    assert int(normalized.iloc[0]["source_page"]) == 2
    assert float(normalized.iloc[0]["confidence"]) == pytest.approx(0.83)


def test_export_line_basis_template_only_exports_leaf_lines(tmp_path: Path) -> None:
    target = tmp_path / "template.xlsx"
    saved = export_line_basis_template(target, regnskapslinjer=_regnskapslinjer_df())

    loaded = pd.read_excel(saved)

    assert loaded["regnr"].tolist() == [10, 11]
    assert loaded["regnskapslinje"].tolist() == ["Eiendeler", "Inntekter"]
    assert "ub" in loaded.columns

"""Tests for consolidation.tb_import — TB import wrapper."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from consolidation.tb_import import import_company_tb, _normalize_columns


class TestNormalizeColumns:
    def test_lowercase_passthrough(self):
        df = pd.DataFrame({
            "konto": ["1000", "2000"],
            "kontonavn": ["Bank", "Gjeld"],
            "ib": [100.0, 0.0],
            "ub": [200.0, -50.0],
            "netto": [100.0, -50.0],
        })
        result = _normalize_columns(df)
        assert list(result.columns) == ["konto", "kontonavn", "ib", "ub", "netto"]
        assert len(result) == 2

    def test_titlecase_saft_columns(self):
        """SAF-T reader returnerer Title Case kolonner."""
        df = pd.DataFrame({
            "Konto": ["1000", "2000"],
            "Kontonavn": ["Bank", "Gjeld"],
            "IB": [100.0, 0.0],
            "UB": [200.0, -50.0],
            "Netto": [100.0, -50.0],
        })
        result = _normalize_columns(df)
        assert list(result.columns) == ["konto", "kontonavn", "ib", "ub", "netto"]
        assert result.iloc[0]["konto"] == "1000"

    def test_missing_ib_gets_zero(self):
        df = pd.DataFrame({
            "konto": ["1000"],
            "kontonavn": ["Bank"],
            "ub": [200.0],
            "netto": [200.0],
        })
        result = _normalize_columns(df)
        assert "ib" in result.columns
        assert result.iloc[0]["ib"] == 0.0

    def test_empty_konto_rows_removed(self):
        df = pd.DataFrame({
            "konto": ["1000", "", "  ", "2000"],
            "kontonavn": ["A", "B", "C", "D"],
            "ib": [0.0, 0.0, 0.0, 0.0],
            "ub": [100.0, 0.0, 0.0, 200.0],
            "netto": [100.0, 0.0, 0.0, 200.0],
        })
        result = _normalize_columns(df)
        assert len(result) == 2
        assert list(result["konto"]) == ["1000", "2000"]

    def test_non_numeric_coerced(self):
        df = pd.DataFrame({
            "konto": ["1000"],
            "kontonavn": ["Test"],
            "ib": ["ikke-tall"],
            "ub": ["200"],
            "netto": [None],
        })
        result = _normalize_columns(df)
        assert result.iloc[0]["ib"] == 0.0
        assert result.iloc[0]["ub"] == 200.0
        assert result.iloc[0]["netto"] == 0.0


class TestImportCompanyTB:
    def test_import_excel(self, tmp_path):
        """Test import fra Excel-fil."""
        xlsx = tmp_path / "test_tb.xlsx"
        df = pd.DataFrame({
            "konto": ["1000", "3000", "4000"],
            "kontonavn": ["Bank", "Salg", "Kost"],
            "ib": [100000.0, 0.0, 0.0],
            "ub": [150000.0, -500000.0, 300000.0],
            "netto": [50000.0, -500000.0, 300000.0],
        })
        df.to_excel(xlsx, index=False)

        company, result_df, warnings = import_company_tb(xlsx, "Testselskap AS")

        assert company.name == "Testselskap AS"
        assert company.source_type == "excel"
        assert company.source_file == "test_tb.xlsx"
        assert company.row_count == 3
        assert company.has_ib is True
        assert len(result_df) == 3
        assert list(result_df.columns) == ["konto", "kontonavn", "ib", "ub", "netto"]

    def test_import_csv(self, tmp_path):
        """Test import fra CSV-fil."""
        csv_file = tmp_path / "test_tb.csv"
        csv_file.write_text(
            "konto,kontonavn,ib,ub,netto\n"
            "1000,Bank,0,50000,50000\n"
            "3000,Salg,0,-100000,-100000\n",
            encoding="utf-8",
        )

        company, result_df, warnings = import_company_tb(csv_file, "CSV Selskap")

        assert company.source_type == "csv"
        assert company.row_count == 2
        assert company.has_ib is False
        assert "Ingen IB-verdier" in warnings[0]

    def test_import_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            import_company_tb(tmp_path / "finnes_ikke.xlsx", "Test")

    def test_reader_strips_non_digit_konto(self, tmp_path):
        """trial_balance_reader normalizes non-digit konto to empty -> dropped."""
        xlsx = tmp_path / "weird.xlsx"
        df = pd.DataFrame({
            "konto": ["1000", "SUM", "3000"],
            "kontonavn": ["Bank", "Sum", "Salg"],
            "ib": [0.0, 0.0, 0.0],
            "ub": [100.0, 100.0, -100.0],
            "netto": [100.0, 100.0, -100.0],
        })
        df.to_excel(xlsx, index=False)

        company, result_df, warnings = import_company_tb(xlsx, "Weird")
        # SUM-raden fjernes av reader (non-digit konto -> "")
        assert company.row_count == 2
        assert "SUM" not in list(result_df["konto"])

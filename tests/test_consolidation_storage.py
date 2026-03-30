"""Tests for consolidation.storage — save/load project + parquet TB."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from consolidation.models import (
    CompanyTB,
    ConsolidationProject,
    EliminationJournal,
    EliminationLine,
    MappingConfig,
)
from consolidation import storage


@pytest.fixture
def _mock_years_dir(tmp_path, monkeypatch):
    """Redirect client_store.years_dir to tmp_path."""

    def fake_years_dir(display_name: str, *, year: str) -> Path:
        p = tmp_path / display_name / "years" / year
        p.mkdir(parents=True, exist_ok=True)
        return p

    monkeypatch.setattr(storage.client_store, "years_dir", fake_years_dir)
    return tmp_path


class TestProjectSaveLoad:
    def test_save_and_load_roundtrip(self, _mock_years_dir):
        proj = ConsolidationProject(
            project_id="p1",
            client="TestKlient",
            year="2025",
            companies=[
                CompanyTB(company_id="c1", name="Mor AS", source_file="mor.xlsx",
                          source_type="excel", row_count=42, has_ib=True),
            ],
            mapping_config=MappingConfig(company_overrides={"c1": {"1920": 1900}}),
            eliminations=[
                EliminationJournal(
                    journal_id="e1",
                    name="Internhandel",
                    lines=[
                        EliminationLine(regnr=3000, company_id="c1", amount=-100.0),
                        EliminationLine(regnr=4000, company_id="c1", amount=100.0),
                    ],
                ),
            ],
        )
        path = storage.save_project(proj)
        assert path.exists()
        assert path.name == "project.json"

        loaded = storage.load_project("TestKlient", "2025")
        assert loaded is not None
        assert loaded.project_id == "p1"
        assert loaded.client == "TestKlient"
        assert len(loaded.companies) == 1
        assert loaded.companies[0].name == "Mor AS"
        assert loaded.mapping_config.company_overrides == {"c1": {"1920": 1900}}
        assert len(loaded.eliminations) == 1
        assert loaded.eliminations[0].is_balanced

    def test_load_nonexistent_returns_none(self, _mock_years_dir):
        result = storage.load_project("Finnes Ikke", "2099")
        assert result is None

    def test_project_json_is_valid_json(self, _mock_years_dir):
        proj = ConsolidationProject(client="JsonTest", year="2025")
        path = storage.save_project(proj)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["schema_version"] == 2
        assert raw["client"] == "JsonTest"

    def test_delete_project(self, _mock_years_dir):
        proj = ConsolidationProject(client="Slett", year="2025")
        storage.save_project(proj)
        assert storage.load_project("Slett", "2025") is not None

        assert storage.delete_project("Slett", "2025") is True
        assert storage.load_project("Slett", "2025") is None

    def test_delete_nonexistent_returns_false(self, _mock_years_dir):
        assert storage.delete_project("Finnes Ikke", "2099") is False


class TestCompanyTBParquet:
    def test_save_and_load_tb(self, _mock_years_dir):
        df = pd.DataFrame({
            "konto": ["1920", "3000", "4000"],
            "kontonavn": ["Bankkonto", "Salgsinntekt", "Varekostnad"],
            "ib": [100000.0, 0.0, 0.0],
            "ub": [150000.0, -500000.0, 300000.0],
            "netto": [50000.0, -500000.0, 300000.0],
        })
        path = storage.save_company_tb("TestKlient", "2025", "c1", df)
        assert path.exists()
        assert path.suffix == ".csv"

        loaded = storage.load_company_tb("TestKlient", "2025", "c1")
        assert loaded is not None
        assert len(loaded) == 3
        assert list(loaded.columns) == ["konto", "kontonavn", "ib", "ub", "netto"]
        assert loaded.iloc[0]["konto"] == "1920"
        assert loaded.iloc[0]["ub"] == 150000.0

    def test_load_nonexistent_returns_none(self, _mock_years_dir):
        result = storage.load_company_tb("X", "2025", "nonexistent")
        assert result is None

    def test_delete_company_tb(self, _mock_years_dir):
        df = pd.DataFrame({"konto": ["1000"], "kontonavn": ["Test"],
                           "ib": [0.0], "ub": [100.0], "netto": [100.0]})
        storage.save_company_tb("Del", "2025", "c1", df)
        assert storage.delete_company_tb("Del", "2025", "c1") is True
        assert storage.load_company_tb("Del", "2025", "c1") is None
        assert storage.delete_company_tb("Del", "2025", "c1") is False


class TestProjectDir:
    def test_project_dir_created(self, _mock_years_dir, tmp_path):
        d = storage.project_dir("DirTest", "2025")
        assert d.exists()
        assert d.name == "consolidation"
        assert "DirTest" in str(d)

    def test_export_path(self, _mock_years_dir):
        p = storage.export_path("X", "2025", "run123")
        assert p.name == "run123_workbook.xlsx"
        assert "exports" in str(p)

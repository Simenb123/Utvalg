from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd


def _regnskapslinjer_df() -> pd.DataFrame:
    return pd.DataFrame({
        "regnr": [10, 11, 20],
        "regnskapslinje": ["Eiendeler", "Inntekter", "SUM"],
        "sumpost": [False, False, True],
        "formel": [None, None, "=10+11"],
    })


def test_finalize_line_basis_import_creates_company_and_persists(monkeypatch, tmp_path: Path) -> None:
    import client_store
    from src.pages.consolidation.backend import storage
    from src.pages.consolidation.backend.models import ConsolidationProject
    from src.pages.consolidation.frontend.page import ConsolidationPage

    monkeypatch.setattr(
        client_store,
        "years_dir",
        lambda client, year: tmp_path / client / "years" / year,
    )
    monkeypatch.setattr("src.pages.consolidation.frontend.page.messagebox", MagicMock())

    page = ConsolidationPage.__new__(ConsolidationPage)
    page._tk_ok = False
    page._project = ConsolidationProject(client="TestCo", year="2025")
    page._company_tbs = {}
    page._company_line_bases = {}
    page._mapped_tbs = {}
    page._mapping_pct = {}
    page._mapping_unmapped = {}
    page._regnskapslinjer = _regnskapslinjer_df()
    page._ensure_line_import_config = MagicMock(return_value=True)
    page._ensure_project = MagicMock(return_value=page._project)
    page._compute_mapping_status = MagicMock()
    page._refresh_company_tree = MagicMock()
    page._update_status = MagicMock()
    page._select_and_show_company = MagicMock()

    df = pd.DataFrame({
        "regnr": [10, 11],
        "regnskapslinje": ["Bankmidler", "Salg"],
        "ub": [100.0, -50.0],
    })
    source = tmp_path / "grunnlag.xlsx"
    source.touch()

    page._finalize_line_basis_import(df, "Rapporteringspakke AS", source, source_type="rl_excel")

    assert len(page._project.companies) == 1
    company = page._project.companies[0]
    assert company.basis_type == "regnskapslinje"
    assert company.source_type == "rl_excel"
    assert company.company_id in page._company_line_bases

    loaded = storage.load_company_line_basis("TestCo", "2025", company.company_id)
    assert loaded is not None
    assert loaded["regnskapslinje"].tolist() == ["Eiendeler", "Inntekter"]

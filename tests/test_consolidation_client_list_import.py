from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd


def _sample_tb() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "konto": ["1000", "3000"],
            "kontonavn": ["Bank", "Salg"],
            "ib": [10.0, 0.0],
            "ub": [100.0, -90.0],
            "netto": [90.0, -90.0],
        }
    )


def _make_page(project):
    from src.pages.consolidation.frontend.page import ConsolidationPage

    page = ConsolidationPage.__new__(ConsolidationPage)
    page._tk_ok = False
    page._project = project
    page._company_tbs = {}
    page._company_line_bases = {}
    page._mapped_tbs = {}
    page._mapping_pct = {}
    page._mapping_unmapped = {}
    page._compute_mapping_status = MagicMock()
    page._refresh_company_tree = MagicMock()
    page._update_status = MagicMock()
    page._select_and_show_company = MagicMock()
    page._invalidate_run_cache = MagicMock()
    return page


def test_import_company_from_client_list_creates_company(monkeypatch, tmp_path) -> None:
    import client_store
    from src.pages.consolidation.backend import storage
    from src.pages.consolidation.backend.models import ConsolidationProject

    monkeypatch.setattr(
        client_store,
        "years_dir",
        lambda client, year: tmp_path / client / "years" / year,
    )
    monkeypatch.setattr(client_store, "list_clients", lambda: ["Air Cargo Logistics AS"])
    monkeypatch.setattr(
        client_store,
        "get_active_version",
        lambda display_name, *, year, dtype: SimpleNamespace(
            path=str(tmp_path / "air_cargo_sb.xlsx"),
            filename="air_cargo_sb.xlsx",
            client_display=display_name,
            year=year,
            dtype=dtype,
        ),
    )
    monkeypatch.setattr("client_picker_dialog.open_client_picker", lambda *a, **kw: "Air Cargo Logistics AS")
    monkeypatch.setattr("trial_balance_reader.read_trial_balance", lambda _path: _sample_tb())
    monkeypatch.setattr("src.pages.consolidation.frontend.page.simpledialog.askstring", lambda *a, **kw: "Air Cargo Logistics AS")
    monkeypatch.setattr("src.pages.consolidation.frontend.page.messagebox", MagicMock())

    page = _make_page(ConsolidationProject(client="Air Management AS", year="2024"))

    page._on_import_company_from_client_list()

    assert len(page._project.companies) == 1
    company = page._project.companies[0]
    assert company.name == "Air Cargo Logistics AS"
    assert company.source_type == "client_store_sb"
    assert company.source_file == "air_cargo_sb.xlsx"
    assert company.company_id in page._company_tbs

    loaded = storage.load_company_tb("Air Management AS", "2024", company.company_id)
    assert loaded is not None
    assert loaded["konto"].tolist() == ["1000", "3000"]


def test_import_company_from_client_list_updates_existing_company_and_preserves_mapping(monkeypatch, tmp_path) -> None:
    import client_store
    from src.pages.consolidation.backend import storage
    from src.pages.consolidation.backend.models import CompanyTB, ConsolidationProject

    monkeypatch.setattr(
        client_store,
        "years_dir",
        lambda client, year: tmp_path / client / "years" / year,
    )
    monkeypatch.setattr(client_store, "list_clients", lambda: ["Air Cargo Logistics AS"])
    monkeypatch.setattr(
        client_store,
        "get_active_version",
        lambda display_name, *, year, dtype: SimpleNamespace(
            path=str(tmp_path / "air_cargo_sb.xlsx"),
            filename="air_cargo_sb.xlsx",
            client_display=display_name,
            year=year,
            dtype=dtype,
        ),
    )
    monkeypatch.setattr("client_picker_dialog.open_client_picker", lambda *a, **kw: "Air Cargo Logistics AS")
    monkeypatch.setattr("trial_balance_reader.read_trial_balance", lambda _path: _sample_tb())
    monkeypatch.setattr("src.pages.consolidation.frontend.page.simpledialog.askstring", lambda *a, **kw: "Air Cargo Logistics AS")
    monkeypatch.setattr("src.pages.consolidation.frontend.page.messagebox", MagicMock())

    existing = CompanyTB(company_id="dat1", name="Air Cargo Logistics AS", source_type="excel", source_file="old.xlsx")
    project = ConsolidationProject(client="Air Management AS", year="2024", companies=[existing])
    project.mapping_config.company_overrides["dat1"] = {"3000": 100}
    page = _make_page(project)

    page._on_import_company_from_client_list()

    assert len(page._project.companies) == 1
    company = page._project.companies[0]
    assert company.company_id == "dat1"
    assert company.source_type == "client_store_sb"
    assert project.mapping_config.company_overrides["dat1"] == {"3000": 100}
    pd.testing.assert_frame_equal(page._company_tbs["dat1"], _sample_tb())

    loaded = storage.load_company_tb("Air Management AS", "2024", "dat1")
    assert loaded is not None
    assert loaded["ub"].tolist() == [100.0, -90.0]


def test_import_company_from_client_list_shows_info_when_no_active_sb(monkeypatch) -> None:
    import client_store
    from src.pages.consolidation.backend.models import ConsolidationProject

    monkeypatch.setattr(client_store, "list_clients", lambda: ["Air Cargo Logistics AS"])
    monkeypatch.setattr(client_store, "get_active_version", lambda *a, **kw: None)
    monkeypatch.setattr("client_picker_dialog.open_client_picker", lambda *a, **kw: "Air Cargo Logistics AS")

    mock_messagebox = MagicMock()
    monkeypatch.setattr("src.pages.consolidation.frontend.page.messagebox", mock_messagebox)

    page = _make_page(ConsolidationProject(client="Air Management AS", year="2024"))

    page._on_import_company_from_client_list()

    assert page._project.companies == []
    mock_messagebox.showinfo.assert_called_once()
    assert "ingen aktiv saldobalanse" in mock_messagebox.showinfo.call_args[0][1].lower()

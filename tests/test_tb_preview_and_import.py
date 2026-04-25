"""Tests for TB preview dialog and consolidation import wiring.

Covers:
  1. TBPreviewDialog column detection and user mapping
  2. IB-only blocking
  3. Preview cancel → no side effects
  4. _finalize_import → company visible in tree with detail
  5. _import_saft_direct → company visible in tree with detail
  6. validate_tb consistency between preview and direct paths
  7. _select_and_show_company behaviour
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.pages.consolidation.backend.models import CompanyTB, ConsolidationProject
from src.pages.consolidation.backend.tb_import import _normalize_columns, validate_tb
from tb_preview_dialog import TBPreviewDialog, _NONE_CHOICE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name)


def _sample_tb_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Konto": ["1000", "3000", "4000"],
        "Kontonavn": ["Bank", "Salg", "Varekost"],
        "IB": [100.0, 0.0, 0.0],
        "UB": [150.0, -200.0, 80.0],
        "Netto": [50.0, -200.0, 80.0],
    })


def _sample_saldo_i_aar_df() -> pd.DataFrame:
    """TB with Norwegian 'Saldo i år/fjor' columns."""
    return pd.DataFrame({
        "Konto": ["1000", "3000"],
        "Kontonavn": ["Bank", "Salg"],
        "Saldo i fjor": [100.0, 0.0],
        "Saldo i år": [150.0, -200.0],
    })


def _sample_year_columns_df() -> pd.DataFrame:
    """TB with year-number columns (2024/2025)."""
    return pd.DataFrame({
        "Konto": ["1000", "3000"],
        "Kontonavn": ["Bank", "Salg"],
        "2024": [100.0, 0.0],
        "2025": [150.0, -200.0],
    })


def _sample_ib_only_df() -> pd.DataFrame:
    """TB with only IB column — no UB/netto."""
    return pd.DataFrame({
        "Konto": ["1000", "3000"],
        "Kontonavn": ["Bank", "Salg"],
        "IB": [100.0, 50.0],
    })


# ---------------------------------------------------------------------------
# 1. validate_tb — shared validation
# ---------------------------------------------------------------------------

class TestValidateTb:
    def test_warns_on_no_ib(self):
        df = pd.DataFrame({
            "konto": ["1000"], "kontonavn": ["Bank"],
            "ib": [0.0], "ub": [100.0], "netto": [100.0],
        })
        warnings = validate_tb(df)
        assert any("IB" in w for w in warnings)

    def test_warns_on_non_numeric_konto(self):
        df = pd.DataFrame({
            "konto": ["ABC", "1000"], "kontonavn": ["X", "Y"],
            "ib": [0.0, 0.0], "ub": [10.0, 20.0], "netto": [10.0, 20.0],
        })
        warnings = validate_tb(df)
        assert any("ikke-numerisk" in w for w in warnings)

    def test_warns_on_empty_kontonavn(self):
        df = pd.DataFrame({
            "konto": ["1000"], "kontonavn": [""],
            "ib": [0.0], "ub": [100.0], "netto": [100.0],
        })
        warnings = validate_tb(df)
        assert any("kontonavn" in w.lower() for w in warnings)

    def test_warns_on_majority_zero_rows(self):
        df = pd.DataFrame({
            "konto": [str(i) for i in range(10)],
            "kontonavn": ["X"] * 10,
            "ib": [0.0] * 10,
            "ub": [0.0] * 10,
            "netto": [0.0] * 10,
        })
        warnings = validate_tb(df)
        assert any("nullverdier" in w for w in warnings)

    def test_no_warnings_on_good_data(self):
        df = pd.DataFrame({
            "konto": ["1000", "3000"],
            "kontonavn": ["Bank", "Salg"],
            "ib": [100.0, 0.0],
            "ub": [150.0, -200.0],
            "netto": [50.0, -200.0],
        })
        warnings = validate_tb(df)
        assert warnings == []

    def test_both_paths_get_same_warnings(self, tmp_path):
        """Preview path and direct path should produce same warnings."""
        # Create a file with no-IB data
        tb = pd.DataFrame({
            "Konto": ["1000", "ABC"],
            "Kontonavn": ["Bank", ""],
            "UB": [100.0, 50.0],
            "Netto": [100.0, 50.0],
        })
        p = tmp_path / "test.xlsx"
        _write_xlsx(p, {"Saldobalanse": tb})

        # Direct path
        from src.pages.consolidation.backend.tb_import import import_company_tb
        _, df_direct, warnings_direct = import_company_tb(p, "TestCo")

        # Preview path: normalize + validate (same as _finalize_import)
        from trial_balance_reader import read_trial_balance
        df_preview_raw = read_trial_balance(p)
        df_preview = _normalize_columns(df_preview_raw)
        warnings_preview = validate_tb(df_preview)

        # Both should have the same set of warning types
        direct_types = {w.split(" ")[0] for w in warnings_direct}
        preview_types = {w.split(" ")[0] for w in warnings_preview}
        assert direct_types == preview_types


# ---------------------------------------------------------------------------
# 2. IB-only blocking in preview
# ---------------------------------------------------------------------------

class TestIbOnlyBlocking:
    def test_ib_only_file_detection(self):
        """infer_trial_balance_columns should fail on IB-only (no UB/netto)."""
        from trial_balance_reader import infer_trial_balance_columns

        df = _sample_ib_only_df()
        with pytest.raises(ValueError, match="UB|netto"):
            infer_trial_balance_columns(df)

    def test_preview_confirm_blocks_ib_only(self):
        """_on_confirm should block when only IB is selected."""
        # Create a mock dialog without Tk
        dlg = TBPreviewDialog.__new__(TBPreviewDialog)
        dlg._file_path = Path("fake.xlsx")
        dlg._result = None
        dlg._name_var = MagicMock()
        dlg._name_var.get.return_value = "TestCo"

        # Set up combos: only konto + ib selected
        dlg._combos = {
            "konto": MagicMock(get=MagicMock(return_value="Konto")),
            "kontonavn": MagicMock(get=MagicMock(return_value=_NONE_CHOICE)),
            "ib": MagicMock(get=MagicMock(return_value="IB")),
            "ub": MagicMock(get=MagicMock(return_value=_NONE_CHOICE)),
            "netto": MagicMock(get=MagicMock(return_value=_NONE_CHOICE)),
            "debet": MagicMock(get=MagicMock(return_value=_NONE_CHOICE)),
            "kredit": MagicMock(get=MagicMock(return_value=_NONE_CHOICE)),
        }

        cols = dlg._get_user_mapping()
        assert cols is not None
        assert cols.ib == "IB"
        assert cols.ub is None
        assert cols.netto is None

        # The confirm validation should block this
        has_value_col = (
            cols.ub is not None
            or cols.netto is not None
            or (cols.debet is not None and cols.kredit is not None)
        )
        assert not has_value_col, "IB-only should be blocked"


# ---------------------------------------------------------------------------
# 3. Preview cancel → no side effects
# ---------------------------------------------------------------------------

class TestPreviewCancel:
    def test_cancel_returns_none(self):
        """TBPreviewDialog._on_cancel sets result to None."""
        dlg = TBPreviewDialog.__new__(TBPreviewDialog)
        dlg._result = ("should be cleared",)

        # Mock Tk methods
        dlg.grab_release = MagicMock()
        dlg.destroy = MagicMock()

        dlg._on_cancel()

        assert dlg._result is None
        dlg.grab_release.assert_called_once()
        dlg.destroy.assert_called_once()

    def test_import_with_none_result_does_nothing(self, monkeypatch, tmp_path):
        """_on_import_company with cancelled preview should not create company."""
        import client_store
        from src.pages.consolidation.frontend.page import ConsolidationPage

        monkeypatch.setattr(
            client_store, "years_dir",
            lambda client, year: tmp_path / client / "years" / year,
        )

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = ConsolidationProject(client="Test", year="2025")
        page._company_tbs = {}
        page._mapped_tbs = {}

        initial_count = len(page._project.companies)

        # Simulate: file dialog returns path, preview returns None (cancel)
        monkeypatch.setattr(
            "src.pages.consolidation.frontend.page.filedialog",
            MagicMock(askopenfilename=MagicMock(
                return_value=str(tmp_path / "fake.xlsx"),
            )),
        )

        # Patch the preview import inside _on_import_company
        monkeypatch.setattr(
            "tb_preview_dialog.open_tb_preview",
            lambda *a, **kw: None,
        )

        page._on_import_company()

        # No company should have been added
        assert len(page._project.companies) == initial_count


# ---------------------------------------------------------------------------
# 4. _finalize_import → company visible
# ---------------------------------------------------------------------------

class TestFinalizeImport:
    def test_finalize_creates_company_and_persists(self, monkeypatch, tmp_path):
        """_finalize_import should create CompanyTB, save, and update tree."""
        import client_store
        from src.pages.consolidation.frontend.page import ConsolidationPage
        from src.pages.consolidation.backend import storage

        monkeypatch.setattr(
            client_store, "years_dir",
            lambda client, year: tmp_path / client / "years" / year,
        )

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = ConsolidationProject(client="TestCo", year="2025")
        page._company_tbs = {}
        page._mapped_tbs = {}
        page._mapping_pct = {}
        page._mapping_unmapped = {}

        # Stub UI methods
        page._compute_mapping_status = MagicMock()
        page._refresh_company_tree = MagicMock()
        page._update_status = MagicMock()
        page._select_and_show_company = MagicMock()

        # Mock messagebox for potential warnings
        monkeypatch.setattr(
            "src.pages.consolidation.frontend.page.messagebox",
            MagicMock(),
        )

        df = _sample_tb_df()
        source = tmp_path / "test.xlsx"
        source.touch()

        page._finalize_import(df, "Datterselskap AS", source)

        # Company created
        assert len(page._project.companies) == 1
        company = page._project.companies[0]
        assert company.name == "Datterselskap AS"
        assert company.source_file == "test.xlsx"
        assert company.row_count == 3

        # TB stored in memory
        assert company.company_id in page._company_tbs

        # Persisted to disk
        loaded = storage.load_company_tb("TestCo", "2025", company.company_id)
        assert loaded is not None
        assert len(loaded) == 3

        # UI updated
        page._select_and_show_company.assert_called_once_with(company.company_id)

    def test_finalize_shows_validation_warnings(self, monkeypatch, tmp_path):
        """_finalize_import should show warnings from validate_tb."""
        import client_store
        from src.pages.consolidation.frontend.page import ConsolidationPage

        monkeypatch.setattr(
            client_store, "years_dir",
            lambda client, year: tmp_path / client / "years" / year,
        )

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = ConsolidationProject(client="TestCo", year="2025")
        page._company_tbs = {}
        page._mapped_tbs = {}
        page._mapping_pct = {}
        page._mapping_unmapped = {}
        page._compute_mapping_status = MagicMock()
        page._refresh_company_tree = MagicMock()
        page._update_status = MagicMock()
        page._select_and_show_company = MagicMock()

        mock_msgbox = MagicMock()
        monkeypatch.setattr("src.pages.consolidation.frontend.page.messagebox", mock_msgbox)

        # DataFrame with no IB → should trigger warning
        df = pd.DataFrame({
            "Konto": ["1000"], "Kontonavn": ["Bank"],
            "IB": [0.0], "UB": [100.0], "Netto": [100.0],
        })
        source = tmp_path / "test.xlsx"
        source.touch()

        page._finalize_import(df, "TestCo", source)

        # Should have called showwarning with IB warning
        mock_msgbox.showwarning.assert_called_once()
        args = mock_msgbox.showwarning.call_args
        assert "IB" in args[0][1]


# ---------------------------------------------------------------------------
# 5. _select_and_show_company
# ---------------------------------------------------------------------------

class TestSelectAndShowCompany:
    def test_select_and_show_calls_tree_methods(self):
        """_select_and_show_company should set selection and show detail."""
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False

        mock_tree = MagicMock()
        page._tree_companies = mock_tree
        page._left_nb = MagicMock()

        # Mock _show_company_detail
        page._show_company_detail = MagicMock()

        # Stub the treeviews needed by _show_company_detail
        page._tree_detail = MagicMock()
        page._right_nb = MagicMock()
        page._mapped_tbs = {}
        page._company_tbs = {}
        page._mapping_unmapped = {}

        page._select_and_show_company("test-id-123")

        mock_tree.selection_set.assert_called_once_with("test-id-123")
        mock_tree.see.assert_called_once_with("test-id-123")
        page._show_company_detail.assert_called_once_with("test-id-123")
        page._left_nb.select.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# 6. _show_company_detail DataFrame truthiness fix
# ---------------------------------------------------------------------------

class TestShowCompanyDetailDfFix:
    def test_no_value_error_with_empty_mapped_tb(self):
        """_show_company_detail should not raise ValueError with empty mapped_tbs."""
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False

        mock_tree = MagicMock()
        mock_tree.get_children.return_value = []
        page._tree_detail = mock_tree
        page._right_nb = MagicMock()
        page._mapping_unmapped = {}
        page._regnr_to_name = {}
        page._regnskapslinjer = None
        page._mapping_tab = MagicMock()
        page._project = None
        page._current_detail_cid = None
        page._detail_hide_zero_var = MagicMock()
        page._detail_hide_zero_var.get.return_value = False  # show all
        page._detail_count_var = MagicMock()
        page._result_mode_var = MagicMock()
        page._result_mode_var.get.return_value = "Valgt selskap"
        page._hide_zero_var = MagicMock()
        page._hide_zero_var.get.return_value = True
        page._company_result_df = None
        page._consolidated_result_df = None
        page._preview_result_df = None
        page._preview_label_var = MagicMock()
        page._tree_result = MagicMock()

        # mapped_tbs has an empty DataFrame (previously would crash with `or`)
        empty_df = pd.DataFrame(columns=["konto", "kontonavn", "regnr", "ib", "ub", "netto"])
        page._mapped_tbs = {"cid": empty_df}
        page._company_tbs = {"cid": _sample_tb_df()}

        # Should NOT raise ValueError
        page._show_company_detail("cid")

        # Should have used the raw TB (since mapped was empty)
        assert mock_tree.insert.called

    def test_uses_mapped_tb_when_available(self):
        """_show_company_detail should prefer mapped_tbs when non-empty."""
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False

        mock_tree = MagicMock()
        mock_tree.get_children.return_value = []
        page._tree_detail = mock_tree
        page._right_nb = MagicMock()
        page._mapping_unmapped = {"cid": []}
        page._regnr_to_name = {100: "Driftsinntekter"}
        page._regnskapslinjer = None
        page._mapping_tab = MagicMock()
        page._project = None
        page._current_detail_cid = None
        page._detail_hide_zero_var = MagicMock()
        page._detail_hide_zero_var.get.return_value = False  # show all
        page._detail_count_var = MagicMock()
        page._result_mode_var = MagicMock()
        page._result_mode_var.get.return_value = "Valgt selskap"
        page._hide_zero_var = MagicMock()
        page._hide_zero_var.get.return_value = True
        page._company_result_df = None
        page._consolidated_result_df = None
        page._preview_result_df = None
        page._preview_label_var = MagicMock()
        page._tree_result = MagicMock()

        mapped_df = pd.DataFrame({
            "konto": ["1000"], "kontonavn": ["Bank"],
            "regnr": [100], "ib": [0.0], "ub": [50.0], "netto": [50.0],
        })
        page._mapped_tbs = {"cid": mapped_df}
        page._company_tbs = {"cid": _sample_tb_df()}

        page._show_company_detail("cid")

        # Should have inserted exactly 1 row (from mapped, not raw which has 3)
        assert mock_tree.insert.call_count == 1


# ---------------------------------------------------------------------------
# 7. Alias detection consistency
# ---------------------------------------------------------------------------

class TestAliasDetection:
    def test_saldo_i_aar_detected_in_preview_and_reader(self, tmp_path):
        """Both read_trial_balance and infer_columns_with_year_detection
        should handle 'Saldo i år/fjor' correctly."""
        from trial_balance_reader import (
            read_trial_balance,
            read_raw_trial_balance,
            infer_columns_with_year_detection,
        )

        df = _sample_saldo_i_aar_df()
        p = tmp_path / "saldo.xlsx"
        _write_xlsx(p, {"Saldobalanse": df})

        # Direct reader
        result = read_trial_balance(p)
        assert result.loc[0, "ib"] == 100.0
        assert result.loc[0, "ub"] == 150.0

        # Preview path
        raw = read_raw_trial_balance(p)
        cols, _ = infer_columns_with_year_detection(raw)
        assert cols.ib is not None
        assert cols.ub is not None

    def test_year_columns_detected_in_preview(self, tmp_path):
        """Year-number columns should be detected by preview path."""
        from trial_balance_reader import (
            read_raw_trial_balance,
            infer_columns_with_year_detection,
        )

        df = _sample_year_columns_df()
        p = tmp_path / "year_cols.xlsx"
        _write_xlsx(p, {"TB": df})

        raw = read_raw_trial_balance(p)
        cols, year_map = infer_columns_with_year_detection(raw)

        assert year_map == {"2024": "ib", "2025": "ub"}
        assert cols.ib == "2024"
        assert cols.ub == "2025"

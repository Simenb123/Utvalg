"""Tests for consolidation_mapping_tab.py — MappingTab logic."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_tb() -> pd.DataFrame:
    return pd.DataFrame({
        "konto": ["1000", "1500", "3000", "4000"],
        "kontonavn": ["Bank", "Kundefordringer", "Salg", "Varekost"],
        "ib": [100.0, 200.0, 0.0, 0.0],
        "ub": [150.0, 180.0, -500.0, 300.0],
        "netto": [50.0, -20.0, -500.0, 300.0],
    })


def _sample_mapped_tb() -> pd.DataFrame:
    return pd.DataFrame({
        "konto": ["1000", "1500", "3000", "4000"],
        "kontonavn": ["Bank", "Kundefordringer", "Salg", "Varekost"],
        "regnr": pd.array([100, 110, None, 200], dtype="Int64"),
        "ib": [100.0, 200.0, 0.0, 0.0],
        "ub": [150.0, 180.0, -500.0, 300.0],
        "netto": [50.0, -20.0, -500.0, 300.0],
    })


def _sample_duplicate_tb() -> pd.DataFrame:
    return pd.DataFrame({
        "konto": ["6510", "6510", "3000"],
        "kontonavn": ["Leie lokaler", "Leie lokaler", "Salg"],
        "ib": [0.0, 0.0, 0.0],
        "ub": [100.0, 50.0, -500.0],
        "netto": [100.0, 50.0, -500.0],
    })


def _sample_regnskapslinjer() -> pd.DataFrame:
    return pd.DataFrame({
        "regnr": [100, 110, 200, 300, 900],
        "regnskapslinje": [
            "Bankinnskudd", "Kundefordringer", "Varekost",
            "Driftsinntekter", "Sum driftsinntekter",
        ],
        "sumpost": [False, False, False, False, True],
        "formel": [None, None, None, None, "=SUM(100:300)"],
    })


def _regnr_to_name() -> dict[int, str]:
    return {
        70: "Annen driftskostnad",
        100: "Bankinnskudd",
        110: "Kundefordringer",
        200: "Varekost",
        300: "Driftsinntekter",
        900: "Sum driftsinntekter",
    }


def _make_tab(callback=None):
    """Create a MappingTab instance without tkinter by using __new__."""
    from consolidation_mapping_tab import MappingTab

    tab = MappingTab.__new__(MappingTab)
    tab._on_overrides_changed = callback

    # Mock tk widgets
    tab._filter_left_var = MagicMock()
    tab._filter_left_var.get.return_value = ""
    tab._show_unmapped_var = MagicMock()
    tab._show_unmapped_var.get.return_value = False
    tab._hide_zero_var = MagicMock()
    tab._hide_zero_var.get.return_value = False
    tab._filter_right_var = MagicMock()
    tab._filter_right_var.get.return_value = ""
    tab._status_var = MagicMock()

    mock_tree_left = MagicMock()
    mock_tree_left.get_children.return_value = []
    mock_tree_left.selection.return_value = []
    mock_tree_left.exists.return_value = True
    tab._tree_left = mock_tree_left

    mock_tree_right = MagicMock()
    mock_tree_right.get_children.return_value = []
    mock_tree_right.selection.return_value = []
    tab._tree_right = mock_tree_right

    # Init state
    tab._company_id = None
    tab._tb = None
    tab._mapped_tb = None
    tab._overrides = {}
    tab._base_regnr = {}
    tab._review_accounts = set()
    tab._regnr_to_name = {}
    tab._rl_rows = []

    return tab


# ---------------------------------------------------------------------------
# Tests: set_data and get_overrides
# ---------------------------------------------------------------------------

class TestSetDataAndOverrides:
    def test_set_data_populates_state(self):
        tab = _make_tab()
        tab.set_data("company-1", _sample_tb(), _sample_mapped_tb(),
                      {"3000": 300}, _sample_regnskapslinjer(), _regnr_to_name())

        assert tab._company_id == "company-1"
        assert tab._overrides == {"3000": 300}
        assert len(tab._rl_rows) == 4  # 5 - 1 sumpost
        assert tab._tree_left.delete.called
        assert tab._tree_right.delete.called

    def test_get_overrides_returns_copy(self):
        tab = _make_tab()
        tab._overrides = {"1000": 100}
        result = tab.get_overrides()
        assert result == {"1000": 100}
        result["2000"] = 200
        assert "2000" not in tab._overrides

    def test_set_data_builds_rl_rows_without_sumposter(self):
        tab = _make_tab()
        tab.set_data("c1", _sample_tb(), _sample_mapped_tb(), {},
                      _sample_regnskapslinjer(), _regnr_to_name())
        regnrs = [r[0] for r in tab._rl_rows]
        assert 900 not in regnrs
        assert 100 in regnrs
        assert 300 in regnrs

    def test_clear_resets_state(self):
        tab = _make_tab()
        tab.set_data("c1", _sample_tb(), _sample_mapped_tb(), {"1000": 100},
                      _sample_regnskapslinjer(), _regnr_to_name())
        tab.clear()
        assert tab._company_id is None
        assert tab._overrides == {}
        assert tab._rl_rows == []

    def test_set_data_with_none_mapped_tb(self):
        tab = _make_tab()
        tab.set_data("c1", _sample_tb(), None, {}, _sample_regnskapslinjer(), _regnr_to_name())
        assert tab._company_id == "c1"
        assert tab._base_regnr == {}

    def test_display_rows_aggregates_duplicate_accounts(self):
        tab = _make_tab()
        tab._tb = _sample_duplicate_tb()
        rows = tab._display_rows()
        by_konto = {str(row["konto"]): row for row in rows}
        assert set(by_konto) == {"6510", "3000"}
        assert by_konto["6510"]["ub"] == 150.0
        assert by_konto["6510"]["netto"] == 150.0


# ---------------------------------------------------------------------------
# Tests: assign and remove
# ---------------------------------------------------------------------------

class TestAssignAndRemove:
    def _tab_with_data(self, callback=None):
        tab = _make_tab(callback)
        tab._company_id = "company-1"
        tab._tb = _sample_tb()
        tab._mapped_tb = _sample_mapped_tb()
        tab._overrides = {}
        tab._base_regnr = {"1000": 100, "1500": 110, "3000": None, "4000": 200}
        tab._regnr_to_name = _regnr_to_name()
        tab._rl_rows = [(100, "Bankinnskudd"), (110, "Kundefordringer"),
                         (200, "Varekost"), (300, "Driftsinntekter")]
        return tab

    def test_assign_adds_overrides(self):
        callback = MagicMock()
        tab = self._tab_with_data(callback)

        tab._tree_left.selection.return_value = ["3000"]
        tab._tree_right.selection.return_value = ["300"]

        tab._on_assign()

        assert tab._overrides == {"3000": 300}
        callback.assert_called_once_with("company-1", {"3000": 300})

    def test_assign_multiple_accounts(self):
        callback = MagicMock()
        tab = self._tab_with_data(callback)

        tab._tree_left.selection.return_value = ["3000", "4000"]
        tab._tree_right.selection.return_value = ["300"]

        tab._on_assign()

        assert tab._overrides == {"3000": 300, "4000": 300}
        callback.assert_called_once()

    def test_assign_no_right_selection_does_nothing(self):
        callback = MagicMock()
        tab = self._tab_with_data(callback)

        tab._tree_left.selection.return_value = ["3000"]
        tab._tree_right.selection.return_value = []

        tab._on_assign()

        assert tab._overrides == {}
        callback.assert_not_called()

    def test_assign_no_left_selection_does_nothing(self):
        callback = MagicMock()
        tab = self._tab_with_data(callback)

        tab._tree_left.selection.return_value = []
        tab._tree_right.selection.return_value = ["300"]

        tab._on_assign()

        assert tab._overrides == {}
        callback.assert_not_called()

    def test_remove_clears_override(self):
        callback = MagicMock()
        tab = self._tab_with_data(callback)
        tab._overrides = {"3000": 300, "4000": 200}

        tab._tree_left.selection.return_value = ["3000"]

        tab._on_remove()

        assert tab._overrides == {"4000": 200}
        callback.assert_called_once_with("company-1", {"4000": 200})

    def test_remove_nonexistent_override_is_harmless(self):
        callback = MagicMock()
        tab = self._tab_with_data(callback)
        tab._overrides = {}

        tab._tree_left.selection.return_value = ["1000"]

        tab._on_remove()

        assert tab._overrides == {}
        callback.assert_called_once()

    def test_assign_without_company_does_nothing(self):
        tab = self._tab_with_data()
        tab._company_id = None

        tab._tree_left.selection.return_value = ["3000"]
        tab._tree_right.selection.return_value = ["300"]

        tab._on_assign()
        assert tab._overrides == {}


# ---------------------------------------------------------------------------
# Tests: status update
# ---------------------------------------------------------------------------

class TestMappingStatus:
    def test_status_counts_mapped_correctly(self):
        tab = _make_tab()
        tab._company_id = "c1"
        tab._tb = _sample_tb()
        tab._overrides = {}
        tab._base_regnr = {"1000": 100, "1500": 110, "3000": None, "4000": 200}

        tab._update_status()
        # 3 mapped (1000, 1500, 4000), 1 unmapped (3000)
        tab._status_var.set.assert_called_with("3/4 kontoer mappet (75%)")

    def test_status_with_override_increases_count(self):
        tab = _make_tab()
        tab._company_id = "c1"
        tab._tb = _sample_tb()
        tab._overrides = {"3000": 300}
        tab._base_regnr = {"1000": 100, "1500": 110, "3000": None, "4000": 200}

        tab._update_status()
        tab._status_var.set.assert_called_with("4/4 kontoer mappet (100%)")

    def test_status_counts_review_accounts_as_mapping_issues(self):
        tab = _make_tab()
        tab._company_id = "c1"
        tab._tb = _sample_tb()
        tab._overrides = {}
        tab._base_regnr = {"1000": 100, "1500": 110, "3000": 15, "4000": 200}
        tab._review_accounts = {"3000"}

        tab._update_status()
        tab._status_var.set.assert_called_with("3/4 kontoer mappet (75%) | 1 mappeavvik")

    def test_status_counts_unique_accounts_when_tb_contains_duplicates(self):
        tab = _make_tab()
        tab._company_id = "c1"
        tab._tb = _sample_duplicate_tb()
        tab._overrides = {}
        tab._base_regnr = {"6510": 70, "3000": 300}
        tab._review_accounts = set()

        tab._update_status()
        tab._status_var.set.assert_called_with("2/2 kontoer mappet (100%)")

    def test_status_with_no_tb(self):
        tab = _make_tab()
        tab._tb = None

        tab._update_status()
        tab._status_var.set.assert_called_with("Velg et selskap for aa redigere mapping.")


# ---------------------------------------------------------------------------
# Tests: page_consolidation callback wiring
# ---------------------------------------------------------------------------

class TestOverridesChangedCallback:
    def test_callback_updates_project_and_remaps(self):
        from page_consolidation import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = MagicMock()
        page._project.mapping_config.company_overrides = {}

        page._refresh_company_tree = MagicMock()
        page._show_company_detail = MagicMock()
        page._company_tbs = {"c1": _sample_tb()}
        page._mapped_tbs = {}
        page._mapping_unmapped = {}
        page._mapping_review_accounts = {}
        page._mapping_review_details = {}
        page._mapping_pct = {}
        page._include_ao_var = MagicMock()
        page._include_ao_var.get.return_value = False
        page._intervals = pd.DataFrame({"fra": [1000], "til": [4999], "regnr": [100]})
        page._regnskapslinjer = _sample_regnskapslinjer()

        mapped_result = _sample_mapped_tb()
        with patch("consolidation.mapping.map_company_tb", return_value=(mapped_result, [])), \
             patch("page_consolidation.storage") as mock_storage:
            page._on_mapping_overrides_changed("c1", {"3000": 300})

        assert page._project.mapping_config.company_overrides["c1"] == {"3000": 300}
        page._project.touch.assert_called_once()
        page._refresh_company_tree.assert_called_once()
        page._show_company_detail.assert_called_once_with("c1")

    def test_show_unmapped_activates_filter(self):
        tab = _make_tab()
        tab._tb = _sample_tb()
        tab.show_unmapped()

        tab._show_unmapped_var.set.assert_called_with(True)

    def test_show_unmapped_filter_keeps_review_accounts_visible(self):
        tab = _make_tab()
        tab._tb = pd.DataFrame(
            {
                "konto": ["3000", "4000"],
                "kontonavn": ["Disponering annen egenkapital", "Varekost"],
                "ib": [0.0, 0.0],
                "ub": [-285718.06, 300.0],
                "netto": [-285718.06, 300.0],
            }
        )
        tab._base_regnr = {"3000": 15, "4000": 20}
        tab._review_accounts = {"3000"}
        tab._regnr_to_name = {15: "Annen driftsinntekt", 20: "Varekost"}
        tab._show_unmapped_var.get.return_value = True
        tab._tree_left.insert = MagicMock()

        tab._refresh_left_tree()

        inserted = [call.kwargs.get("iid") for call in tab._tree_left.insert.call_args_list]
        assert "3000" in inserted
        assert "4000" not in inserted

    def test_refresh_left_tree_handles_duplicate_accounts_without_duplicate_iid(self):
        tab = _make_tab()
        tab._tb = _sample_duplicate_tb()
        tab._base_regnr = {"6510": 70, "3000": 300}
        tab._regnr_to_name = _regnr_to_name()
        tab._tree_left.insert = MagicMock()

        tab._refresh_left_tree()

        inserted = [call.kwargs.get("iid") for call in tab._tree_left.insert.call_args_list]
        assert inserted.count("6510") == 1
        assert inserted.count("3000") == 1

    def test_empty_overrides_removes_key(self):
        from page_consolidation import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = MagicMock()
        page._project.mapping_config.company_overrides = {"c1": {"1000": 100}}
        page._refresh_company_tree = MagicMock()
        page._show_company_detail = MagicMock()
        page._company_tbs = {}
        page._mapped_tbs = {}
        page._mapping_unmapped = {}
        page._mapping_pct = {}
        page._intervals = None
        page._regnskapslinjer = None

        with patch("page_consolidation.storage"):
            page._on_mapping_overrides_changed("c1", {})

        assert "c1" not in page._project.mapping_config.company_overrides

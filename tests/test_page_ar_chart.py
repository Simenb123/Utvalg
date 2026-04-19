from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_build_owned_help_text_describes_row() -> None:
    from page_ar import _build_owned_help_text

    text = _build_owned_help_text(
        {
            "company_name": "Air Cargo Logistics AS",
            "ownership_pct": 100.0,
            "relation_type": "datter",
            "source": "carry_forward",
            "matched_client": "Air Cargo Logistics AS",
            "has_active_sb": True,
        },
        year="2025",
        accepted_meta={"source_year": "2024"},
    )

    assert "100,00 % av Air Cargo Logistics AS" in text
    assert "akseptert eierstatus 2024" in text
    assert "aktiv SB finnes for 2025" in text


def _make_page():
    from page_ar import ARPage

    page = ARPage.__new__(ARPage)
    page._nb = MagicMock()
    page._frm_chart = "chart-tab"
    page._tree_owned = MagicMock()
    page._tree_owners = MagicMock()
    page._tree_changes = MagicMock()
    page._owned_rows_by_iid = {
        "owned-1": {"company_orgnr": "914305195", "company_name": "Air Cargo Logistics AS"},
    }
    page._owners_rows_by_iid = {
        "owner-1": {"shareholder_orgnr": "999999999", "shareholder_name": "AIR MANAGEMENT HOLDING AS"},
    }
    page._change_rows_by_iid = {}
    page._compare_rows_by_iid = {}
    page._history_rows_by_iid = {}
    page._shareholder_change_rows_by_iid = {}
    page._tree_history = MagicMock()
    page._tree_compare_tx = MagicMock()
    page._tree_shareholder_changes = MagicMock()
    page._btn_compare_open_pdf = MagicMock()
    page._btn_compare_import_detail = MagicMock()
    page._frm_owners = "owners-tab"
    page._overview = {
        "owned_companies": [], "owners": [], "pending_changes": [],
        "owners_compare": [], "import_history": [],
        "owners_compare_changed": [], "owners_compare_trace_available": False,
    }
    page._client = "Test AS"
    page._year = "2025"
    page._chart_dirty = False
    page._overview_loading = False
    page._chart_zoom = 1.0
    page.var_chart_zoom = MagicMock()
    page.var_manual_mode = MagicMock()
    page.var_owners_caption = MagicMock()
    page.var_compare_header = MagicMock()
    page.var_compare_summary = MagicMock()
    page.var_compare_source_year = MagicMock()
    page.var_compare_imported_at = MagicMock()
    page.var_compare_source_file = MagicMock()
    page.var_compare_data_basis = MagicMock()
    page.var_compare_rf_status = MagicMock()
    page.var_compare_tx_empty = MagicMock()
    page.var_compare_no_import = MagicMock()
    page.var_changes_empty = MagicMock()
    page.var_sh_changes_empty = MagicMock()
    page.var_history_empty = MagicMock()
    page.var_trace_compare = MagicMock()
    page.var_trace_basis = MagicMock()
    page.var_trace_import = MagicMock()
    page.var_detail_shares_base = MagicMock()
    page.var_detail_shares_current = MagicMock()
    page.var_detail_shares_delta = MagicMock()
    page.var_detail_pct_base = MagicMock()
    page.var_detail_pct_current = MagicMock()
    page.var_detail_change_type = MagicMock()
    page._lbl_detail_shares_base_title = MagicMock()
    page._lbl_detail_shares_current_title = MagicMock()
    page._lbl_detail_pct_base_title = MagicMock()
    page._lbl_detail_pct_current_title = MagicMock()
    page._lbl_compare_tx_empty = MagicMock()
    page._lbl_compare_no_import = MagicMock()
    page._lbl_changes_empty = MagicMock()
    page._lbl_sh_changes_empty = MagicMock()
    page._lbl_history_empty = MagicMock()
    page._btn_accept_selected = MagicMock()
    page._btn_accept_all = MagicMock()
    page._btn_delete_manual = MagicMock()
    page._btn_open_source_pdf = MagicMock()
    page._on_owned_selected = MagicMock()
    page._on_new_manual_change = MagicMock()
    return page


def test_execute_chart_action_selects_owned_row() -> None:
    page = _make_page()

    page._execute_chart_action({"kind": "owned", "company_orgnr": "914305195"})

    page._nb.select.assert_called_with(0)
    page._tree_owned.selection_set.assert_called_once_with(("owned-1",))
    page._tree_owned.focus.assert_called_once_with("owned-1")
    page._tree_owned.see.assert_called_once_with("owned-1")
    page._on_owned_selected.assert_called_once()


def test_execute_chart_action_selects_owner_row() -> None:
    page = _make_page()

    page._execute_chart_action({"kind": "owner", "shareholder_orgnr": "999999999"})

    page._nb.select.assert_called_with(1)
    page._tree_owners.selection_set.assert_called_once_with(("owner-1",))
    page._tree_owners.focus.assert_called_once_with("owner-1")
    page._tree_owners.see.assert_called_once_with("owner-1")


def test_on_chart_mousewheel_scales_canvas() -> None:
    page = _make_page()
    canvas = MagicMock()
    canvas.canvasx.side_effect = lambda value: value
    canvas.canvasy.side_effect = lambda value: value
    canvas.bbox.return_value = (0, 0, 200, 120)
    page._org_canvas = canvas
    page._chart_zoom = 1.0

    page._on_chart_mousewheel(SimpleNamespace(delta=120, x=40, y=50))

    canvas.scale.assert_called_once()
    canvas.configure.assert_called_once_with(scrollregion=(-40, -40, 240, 160))
    page.var_chart_zoom.set.assert_called_once()


def test_chart_reset_view_refreshes_chart() -> None:
    page = _make_page()
    page._refresh_org_chart = MagicMock()

    with patch("page_ar.ARPage._chart_positions_path", return_value=None):
        page._chart_reset_view()

    page._refresh_org_chart.assert_called_once()


def test_refresh_current_overview_starts_background_load() -> None:
    from page_ar import ARPage

    page = ARPage.__new__(ARPage)
    page._client = "Spor Arkitekter AS"
    page._year = "2025"
    page._overview_request_id = 0
    page._overview_loading = False
    page.var_status = MagicMock()

    with patch("page_ar.threading.Thread") as mock_thread:
        page._refresh_current_overview()

    assert page._overview_loading is True
    assert page._overview_request_id == 1
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()


def test_refresh_trees_defers_chart_when_tab_not_selected() -> None:
    page = _make_page()
    page._nb.select.return_value = "owned-tab"
    page._refresh_org_chart = MagicMock()

    page._refresh_trees()

    assert page._chart_dirty is True
    page._refresh_org_chart.assert_not_called()
    page._on_new_manual_change.assert_called_once()


def test_tab_changed_refreshes_dirty_chart() -> None:
    page = _make_page()
    page._chart_dirty = True
    page._nb.select.return_value = "chart-tab"
    page._refresh_org_chart = MagicMock()

    page._on_tab_changed(SimpleNamespace(widget=page._nb))

    page._refresh_org_chart.assert_called_once()


# ─── Runde 3: AR BRREG-tab ─────────────────────────────────────────────────

def _make_brreg_page():
    """En tynnere ARPage uten fullt GUI, for BRREG-lazy-load-tester."""
    from page_ar import ARPage

    page = ARPage.__new__(ARPage)
    page._brreg_data = {}
    page._brreg_loading = set()
    page._brreg_request_id = 0
    page._brreg_current_orgnr = ""
    page._master_df = None
    page._mode = "eide_selskaper"
    page._selected_nr = ""
    page.var_brreg_header = MagicMock()
    page.var_brreg_status = MagicMock()
    page._btn_brreg_refresh = MagicMock()
    # after() schedules callback på UI-tråd; vi kjører den synkront i tester
    page.after = lambda delay, fn, *args: fn(*args)
    return page


def test_filter_owned_rows_matches_name_orgnr_and_matched_client() -> None:
    page = _make_brreg_page()
    page.var_owned_search = SimpleNamespace(get=lambda: "Cargo")
    rows = [
        {"company_name": "Air Cargo Logistics AS", "company_orgnr": "914305195", "matched_client": ""},
        {"company_name": "Andre AS", "company_orgnr": "999999999", "matched_client": ""},
    ]
    assert page._filter_owned_rows(rows) == [rows[0]]

    page.var_owned_search = SimpleNamespace(get=lambda: "99999")
    assert page._filter_owned_rows(rows) == [rows[1]]

    page.var_owned_search = SimpleNamespace(get=lambda: "")
    assert page._filter_owned_rows(rows) == rows


def test_brreg_header_is_set_on_selection_with_orgnr_and_name() -> None:
    page = _make_brreg_page()
    page._update_brreg_header("914305195", "Air Cargo Logistics AS")
    page.var_brreg_header.set.assert_called_with("Air Cargo Logistics AS (914305195)")


def test_brreg_header_empty_state_when_no_selection() -> None:
    page = _make_brreg_page()
    page._update_brreg_header("", "")
    page.var_brreg_header.set.assert_called_with("— velg et eid selskap —")


def test_load_brreg_for_row_without_orgnr_shows_empty_state_and_skips_fetch() -> None:
    page = _make_brreg_page()
    with patch("page_ar_brreg.threading.Thread") as mock_thread, \
         patch("reskontro_brreg_panel.update_brreg_panel") as mock_update:
        page._load_brreg_for_selected_row({"company_orgnr": "", "company_name": "Ukjent AS"})

    mock_thread.assert_not_called()
    mock_update.assert_called_once()
    page.var_brreg_status.set.assert_any_call(
        "Ingen gyldig org.nr for denne raden — BRREG kan ikke hentes."
    )


def test_load_brreg_starts_lazy_fetch_on_first_selection() -> None:
    page = _make_brreg_page()
    with patch("page_ar_brreg.threading.Thread") as mock_thread:
        page._load_brreg_for_selected_row({
            "company_orgnr": "914305195", "company_name": "Air Cargo Logistics AS",
        })

    assert page._brreg_request_id == 1
    assert "914305195" in page._brreg_loading
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()
    page.var_brreg_status.set.assert_any_call("Henter BRREG-data…")


def test_load_brreg_uses_cache_when_already_fetched_and_no_force() -> None:
    page = _make_brreg_page()
    page._brreg_data["914305195"] = {"enhet": {"orgnr": "914305195"}, "regnskap": {}}
    with patch("page_ar_brreg.threading.Thread") as mock_thread, \
         patch("reskontro_brreg_panel.update_brreg_panel") as mock_update:
        page._load_brreg_for_selected_row({
            "company_orgnr": "914305195", "company_name": "Air Cargo Logistics AS",
        })

    mock_thread.assert_not_called()
    mock_update.assert_called_once_with(page, "914305195")
    page.var_brreg_status.set.assert_any_call("Vist fra cache.")


def test_brreg_apply_result_ignores_stale_selection() -> None:
    page = _make_brreg_page()
    page._brreg_request_id = 5
    page._brreg_current_orgnr = "222222222"  # user har klikket videre
    page._brreg_loading.add("111111111")

    with patch("reskontro_brreg_panel.update_brreg_panel") as mock_update:
        page._brreg_apply_result(5, "111111111", {"orgnr": "111111111"}, {"aar": "2023"}, None)

    # Cachen ble fortsatt oppdatert
    assert "111111111" in page._brreg_data
    # men panelet ble IKKE oppdatert
    mock_update.assert_not_called()


def test_brreg_apply_result_updates_panel_when_selection_still_matches() -> None:
    page = _make_brreg_page()
    page._brreg_request_id = 7
    page._brreg_current_orgnr = "111111111"
    page._brreg_loading.add("111111111")

    with patch("reskontro_brreg_panel.update_brreg_panel") as mock_update:
        page._brreg_apply_result(7, "111111111", {"orgnr": "111111111"}, {"aar": "2023"}, None)

    mock_update.assert_called_once_with(page, "111111111")
    page.var_brreg_status.set.assert_any_call("Hentet fra BRREG.")


def test_brreg_refresh_button_forces_new_fetch_bypassing_cache() -> None:
    page = _make_brreg_page()
    page._brreg_data["914305195"] = {"enhet": {}, "regnskap": {}}
    page._selected_owned_row = MagicMock(return_value={
        "company_orgnr": "914305195", "company_name": "Air Cargo Logistics AS",
    })
    with patch("page_ar_brreg.threading.Thread") as mock_thread:
        page._on_brreg_refresh_clicked()

    assert "914305195" not in page._brreg_data  # cachen ble tømt
    mock_thread.assert_called_once()
    _, kwargs = mock_thread.call_args
    # use_cache=False skal være siste positional i args-tupelen
    args = kwargs.get("args") or ()
    assert args[-1] is False  # use_cache=False


def test_brreg_worker_propagates_exception_via_apply_result() -> None:
    page = _make_brreg_page()
    page._brreg_current_orgnr = "111111111"
    page._brreg_request_id = 1
    page._brreg_loading.add("111111111")

    with patch("brreg_client.fetch_enhet", side_effect=RuntimeError("nettverk nede")):
        page._brreg_worker("111111111", 1, True)

    # apply_result ble kalt (via after()-stub) og skrev feil-status
    page.var_brreg_status.set.assert_any_call("Feil ved henting: nettverk nede")
    assert "111111111" not in page._brreg_loading

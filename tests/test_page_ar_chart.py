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


def test_on_chart_mousewheel_rerenders_from_model() -> None:
    """Zoom skal re-rendere fra logisk modell — ikke kalle canvas.scale.

    Gamle implementasjonen brukte canvas.scale("all", ...), men det lar
    _chart_node_centers bli usynkronisert etter zoom. Ny implementasjon
    holder logiske koordinater som sannhet og tegner på nytt.
    """
    page = _make_page()
    canvas = MagicMock()
    canvas.canvasx.side_effect = lambda value: value
    canvas.canvasy.side_effect = lambda value: value
    canvas.winfo_width.return_value = 800
    canvas.winfo_height.return_value = 400
    canvas.bbox.return_value = (0, 0, 200, 120)
    page._org_canvas = canvas
    page._chart_zoom = 1.0
    page._chart_node_centers = {}
    page._chart_model_meta = {"empty": True}

    page._on_chart_mousewheel(SimpleNamespace(delta=120, x=40, y=50))

    canvas.scale.assert_not_called()
    canvas.delete.assert_any_call("all")
    page.var_chart_zoom.set.assert_called()
    assert abs(page._chart_zoom - 1.1) < 0.01


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


# ─── Stabilitet i kart-modellen ────────────────────────────────────────────

def test_load_chart_positions_accepts_valid_json(tmp_path) -> None:
    import json as _json
    import page_ar_chart as chart

    page = _make_page()
    payload = {"root:123": [10.5, 20.25], "child:ACME": [100.0, 200.0]}
    positions_file = tmp_path / "chart_positions.json"
    positions_file.write_text(_json.dumps(payload), encoding="utf-8")

    with patch.object(page, "_chart_positions_path", return_value=positions_file):
        loaded = chart.load_chart_positions(page)

    assert loaded == {"root:123": [10.5, 20.25], "child:ACME": [100.0, 200.0]}


def test_load_chart_positions_returns_empty_on_invalid_json(tmp_path) -> None:
    import page_ar_chart as chart

    page = _make_page()
    positions_file = tmp_path / "chart_positions.json"
    positions_file.write_text("{not valid json", encoding="utf-8")

    with patch.object(page, "_chart_positions_path", return_value=positions_file):
        loaded = chart.load_chart_positions(page)

    assert loaded == {}


def test_load_chart_positions_discards_malformed_entries(tmp_path) -> None:
    import json as _json
    import page_ar_chart as chart

    page = _make_page()
    payload = {
        "root:123": [10.0, 20.0],          # ok
        "bad:1": "not-a-list",             # skal forkastes
        "bad:2": [1, 2, 3],                 # feil lengde
        "bad:3": ["abc", "def"],           # ikke tall
    }
    positions_file = tmp_path / "chart_positions.json"
    positions_file.write_text(_json.dumps(payload), encoding="utf-8")

    with patch.object(page, "_chart_positions_path", return_value=positions_file):
        loaded = chart.load_chart_positions(page)

    assert loaded == {"root:123": [10.0, 20.0]}


def test_save_chart_positions_is_atomic(tmp_path) -> None:
    import json as _json
    import page_ar_chart as chart

    page = _make_page()
    positions_file = tmp_path / "chart_positions.json"
    page._chart_node_centers = {"root:123": (42.0, 84.0)}

    with patch.object(page, "_chart_positions_path", return_value=positions_file):
        chart.save_chart_positions(page)

    assert positions_file.exists()
    # Ingen ..tmp-restfiler.
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
    assert _json.loads(positions_file.read_text(encoding="utf-8")) == {
        "root:123": [42.0, 84.0],
    }


def test_chart_fit_view_does_not_recurse_into_refresh() -> None:
    """chart_fit_view skal ikke kalle _refresh_org_chart — den re-rendrer
    fra logisk modell direkte. Dette hindrer auto-fit-loopen."""
    import page_ar_chart as chart

    page = _make_page()
    canvas = MagicMock()
    canvas.winfo_width.return_value = 600
    canvas.winfo_height.return_value = 400
    canvas.bbox.return_value = (0, 0, 200, 100)
    page._org_canvas = canvas
    page._chart_zoom = 1.0
    page._chart_node_centers = {"root:1": (100.0, 50.0), "child:1": (200.0, 150.0)}
    page._chart_model_meta = {"empty": True}  # ingen noder å tegne
    page._refresh_org_chart = MagicMock()

    chart.chart_fit_view(page)

    page._refresh_org_chart.assert_not_called()


def test_scheduled_fit_view_ignores_stale_render_id() -> None:
    import page_ar_chart as chart

    page = _make_page()
    page._chart_render_id = 7
    page._chart_node_centers = {"root:1": (100.0, 50.0)}
    page._refresh_org_chart = MagicMock()
    page._org_canvas = MagicMock()

    # En tidligere scheduler med gammel id skal ikke gjøre noe.
    chart._scheduled_fit_view(page, render_id=3)

    page._refresh_org_chart.assert_not_called()


def test_refresh_org_chart_defers_when_user_is_dragging() -> None:
    import page_ar_chart as chart

    page = _make_page()
    page._chart_dragging = True
    page._chart_dirty = False
    page._org_canvas = MagicMock()

    chart.refresh_org_chart(page)

    # Render skal ikke slette canvas midt i en drag.
    page._org_canvas.delete.assert_not_called()
    assert page._chart_dirty is True


def test_zoom_does_not_mutate_logical_positions() -> None:
    """Endret zoom skal ikke endre lagrede logiske koordinater."""
    import page_ar_chart as chart

    page = _make_page()
    canvas = MagicMock()
    canvas.canvasx.side_effect = lambda v: v
    canvas.canvasy.side_effect = lambda v: v
    canvas.winfo_width.return_value = 800
    canvas.winfo_height.return_value = 400
    canvas.bbox.return_value = (0, 0, 400, 200)
    page._org_canvas = canvas
    page._chart_zoom = 1.0
    page._chart_node_centers = {"root:1": (100.0, 50.0), "child:1": (200.0, 150.0)}
    page._chart_model_meta = {"empty": True}

    before = {k: v for k, v in page._chart_node_centers.items()}
    chart.chart_apply_zoom(page, 1.25, x=100, y=100)

    assert page._chart_node_centers == before
    assert abs(page._chart_zoom - 1.25) < 0.001


def test_load_overview_worker_does_not_block_on_circular_detection() -> None:
    """Kritisk regresjonsvakt: _load_overview_worker skal ALDRI kalle
    detect_circular_ownership. Hvis den gjør det, kan AR-tabellene bli
    blanke fordi tung SQLite-analyse forsinker _apply_loaded_overview."""
    from page_ar import ARPage

    page = ARPage.__new__(ARPage)
    page._overview_request_id = 1
    page.after = lambda _delay, callback, *a, **kw: None

    with patch("page_ar.get_client_ownership_overview", return_value={"owners": []}) as m_ov, \
         patch("page_ar.detect_circular_ownership") as m_circ:
        page._load_overview_worker(1, "Test AS", "2025")

    m_ov.assert_called_once_with("Test AS", "2025")
    m_circ.assert_not_called()


def test_apply_loaded_overview_fills_tables_without_circular_result() -> None:
    """_apply_loaded_overview skal fylle tabellene selv om circular
    ownership ikke er beregnet. Kartet viser evt. varsel senere."""
    from page_ar import ARPage

    page = _make_page()
    page._overview_request_id = 1
    page._circular_request_id = 0
    page._update_trace_strip = MagicMock()
    page._refresh_trees = MagicMock()
    page.var_orgnr = MagicMock()
    page.var_status = MagicMock()

    overview = {
        "client_orgnr": "111222333",
        "owners": [{"shareholder_name": "X"}],
        "owned_companies": [{"company_name": "Y"}],
        # NB: circular_ownership_cycles er IKKE med
    }
    ARPage._apply_loaded_overview(page, 1, "Test AS", "2025", overview, None)

    assert page._overview is overview
    page._refresh_trees.assert_called_once()
    page._update_trace_strip.assert_called_once()
    # Ny overview skal automatisk invalidere tidligere circular-resultater.
    assert page._circular_request_id == 1


def test_start_circular_worker_runs_in_background_with_request_id() -> None:
    from page_ar import ARPage

    page = ARPage.__new__(ARPage)
    page._client = "Test AS"
    page._year = "2025"
    page._overview = {"owners": []}  # mangler circular_ownership_cycles
    page._circular_request_id = 4
    page._circular_in_flight = False

    with patch("page_ar.threading.Thread") as mock_thread:
        page._start_circular_worker()

    assert page._circular_in_flight is True
    assert page._circular_request_id == 5
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()


def test_start_circular_worker_is_noop_when_cycles_already_present() -> None:
    from page_ar import ARPage

    page = ARPage.__new__(ARPage)
    page._client = "Test AS"
    page._year = "2025"
    page._overview = {"circular_ownership_cycles": []}
    page._circular_request_id = 3
    page._circular_in_flight = False

    with patch("page_ar.threading.Thread") as mock_thread:
        page._start_circular_worker()

    mock_thread.assert_not_called()
    assert page._circular_in_flight is False
    assert page._circular_request_id == 3


def test_apply_circular_result_ignores_stale_request() -> None:
    from page_ar import ARPage

    page = ARPage.__new__(ARPage)
    page._client = "Test AS"
    page._year = "2025"
    page._overview = {"owners": []}
    page._circular_request_id = 10  # nåværende
    page._circular_in_flight = True
    page._is_chart_tab_selected = MagicMock(return_value=True)
    page._chart_dragging = False
    page._refresh_org_chart = MagicMock()

    # Et resultat fra en eldre worker skal droppes helt.
    ARPage._apply_circular_result(page, 5, "Test AS", "2025", [("A", "B")], None)

    assert "circular_ownership_cycles" not in page._overview
    page._refresh_org_chart.assert_not_called()


def test_apply_circular_result_injects_and_rerenders_when_fresh() -> None:
    from page_ar import ARPage

    page = ARPage.__new__(ARPage)
    page._client = "Test AS"
    page._year = "2025"
    page._overview = {"owners": []}
    page._circular_request_id = 7
    page._circular_in_flight = True
    page._is_chart_tab_selected = MagicMock(return_value=True)
    page._chart_dragging = False
    page._refresh_org_chart = MagicMock()

    ARPage._apply_circular_result(page, 7, "Test AS", "2025", [("X", "Y")], None)

    assert page._overview["circular_ownership_cycles"] == [("X", "Y")]
    assert page._circular_in_flight is False
    page._refresh_org_chart.assert_called_once()


def test_apply_circular_result_ignores_different_client_year() -> None:
    from page_ar import ARPage

    page = ARPage.__new__(ARPage)
    page._client = "Other AS"
    page._year = "2026"
    page._overview = {"owners": []}
    page._circular_request_id = 7
    page._circular_in_flight = True
    page._is_chart_tab_selected = MagicMock(return_value=True)
    page._chart_dragging = False
    page._refresh_org_chart = MagicMock()

    ARPage._apply_circular_result(page, 7, "Test AS", "2025", [("X",)], None)

    assert "circular_ownership_cycles" not in page._overview
    page._refresh_org_chart.assert_not_called()


def test_chart_render_without_cycles_triggers_circular_worker_once() -> None:
    import page_ar_chart as chart

    page = _make_page()
    page._org_canvas = MagicMock()
    page._org_canvas.winfo_width.return_value = 800
    page._org_canvas.bbox.return_value = (0, 0, 400, 200)
    page._overview = {
        "client_orgnr": "999888777",
        "owners": [],
        "owned_companies": [],
        # ingen circular_ownership_cycles
    }
    page._chart_dragging = False
    page._chart_dirty = True
    page._chart_zoom = 1.0
    page.after = lambda _d, cb, *a, **kw: None
    page._start_circular_worker = MagicMock()

    with patch.object(page, "_load_chart_positions", return_value={}):
        chart.refresh_org_chart(page)

    page._start_circular_worker.assert_called_once()


def test_chart_render_skips_circular_worker_when_cycles_ready() -> None:
    import page_ar_chart as chart

    page = _make_page()
    page._org_canvas = MagicMock()
    page._org_canvas.winfo_width.return_value = 800
    page._org_canvas.bbox.return_value = (0, 0, 400, 200)
    page._overview = {
        "client_orgnr": "999888777",
        "owners": [],
        "owned_companies": [],
        "circular_ownership_cycles": [],
    }
    page._chart_dragging = False
    page._chart_dirty = True
    page._chart_zoom = 1.0
    page.after = lambda _d, cb, *a, **kw: None
    page._start_circular_worker = MagicMock()

    with patch.object(page, "_load_chart_positions", return_value={}):
        chart.refresh_org_chart(page)

    page._start_circular_worker.assert_not_called()


def test_chart_renders_when_circular_cycles_missing() -> None:
    """Kartet skal kunne tegnes selv når circular_ownership_cycles ikke
    finnes i overview — varselet bare utelates."""
    import page_ar_chart as chart

    page = _make_page()
    canvas = MagicMock()
    canvas.winfo_width.return_value = 800
    canvas.bbox.return_value = (0, 0, 400, 200)
    page._org_canvas = canvas
    page._overview = {
        "client_orgnr": "111",
        "owners": [],
        "owned_companies": [],
    }
    page._chart_dragging = False
    page._chart_dirty = True
    page._chart_zoom = 1.0
    page.after = lambda _d, cb, *a, **kw: None
    page._start_circular_worker = MagicMock()

    with patch.object(page, "_load_chart_positions", return_value={}):
        chart.refresh_org_chart(page)  # skal ikke kaste

    canvas.delete.assert_any_call("all")


def test_chart_render_reads_cycles_from_overview_not_sqlite() -> None:
    """refresh_org_chart skal ikke selv kalle detect_circular_ownership —
    den skal lese ferdig beregnede sykler fra overview."""
    import page_ar_chart as chart

    page = _make_page()
    page._org_canvas = MagicMock()
    page._org_canvas.winfo_width.return_value = 800
    page._org_canvas.bbox.return_value = (0, 0, 400, 200)
    page._overview = {
        "client_orgnr": "999888777",
        "owners": [],
        "owned_companies": [],
        "circular_ownership_cycles": [("A", "B", "C")],
    }
    page._chart_dragging = False
    page._chart_dirty = True
    page._chart_zoom = 1.0
    page.after = lambda _delay, callback, *_a, **_kw: None

    with patch.object(page, "_load_chart_positions", return_value={}), \
         patch("ar_store.detect_circular_ownership") as mock_detect:
        chart.refresh_org_chart(page)

    mock_detect.assert_not_called()


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

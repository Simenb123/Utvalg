from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_load_a07_clicked_loads_json_and_triggers_refresh(monkeypatch, tmp_path) -> None:
    source_path = tmp_path / "input_a07.json"
    source_path.write_text(
        '{"inntekter":[{"loennsinntekt":{"type":"fastloenn","beskrivelse":"Fastloenn"},"beloep":1000}]}',
        encoding="utf-8",
    )
    stored_path = tmp_path / "workspace_a07.json"
    stored_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")

    page = object.__new__(page_a07.A07Page)
    page.workspace = SimpleNamespace(source_a07_df=None, a07_df=None)
    page.a07_path = None
    page.a07_path_var = _DummyVar()
    page.status_var = _DummyVar()
    page._a07_source_cache = {}
    page._session_context = lambda _session: ("Air Management AS", "2025")
    page._current_context_snapshot = lambda client, year: ("snapshot", client, year)

    calls = {"refresh_reason": None, "showerror": 0}

    monkeypatch.setattr(
        page_a07.filedialog,
        "askopenfilename",
        lambda **kwargs: str(source_path),
    )
    monkeypatch.setattr(page_a07, "get_a07_workspace_dir", lambda client, year: tmp_path)
    monkeypatch.setattr(
        page_a07,
        "copy_a07_source_to_workspace",
        lambda path, client=None, year=None: stored_path,
    )
    monkeypatch.setattr(
        page_a07.messagebox,
        "showerror",
        lambda *args, **kwargs: calls.__setitem__("showerror", calls["showerror"] + 1),
    )
    monkeypatch.setattr(
        page,
        "_refresh_core",
        lambda reason=None: calls.__setitem__("refresh_reason", reason),
    )

    page_a07.A07Page._load_a07_clicked(page)

    assert calls["showerror"] == 0
    assert calls["refresh_reason"] == "load_a07"
    assert page.a07_path == stored_path
    assert page.a07_path_var.value == f"A07: {stored_path}"
    assert page.status_var.value == f"Lastet A07 fra {source_path.name} og lagret kopi i klientmappen."
    assert isinstance(page.workspace.source_a07_df, pd.DataFrame)
    assert list(page.workspace.source_a07_df["Kode"]) == ["fastloenn"]
    assert list(page.workspace.a07_df["Kode"]) == ["fastloenn"]

def test_auto_refresh_signature_is_claimed_only_once() -> None:
    dummy = SimpleNamespace(
        _context_key=("kunde", "2025"),
        _auto_refresh_signatures=set(),
        workspace=SimpleNamespace(mapping={"5250": "skattepliktigDelForsikringer"}, basis_col="UB"),
    )
    auto_result = {
        "accounts": ["5250"],
        "codes": ["skattepliktigDelForsikringer"],
        "focus_code": "skattepliktigDelForsikringer",
    }

    signature = page_a07.A07Page._auto_refresh_signature(dummy, auto_result)

    assert page_a07.A07Page._claim_auto_refresh_signature(dummy, signature) is True
    assert page_a07.A07Page._claim_auto_refresh_signature(dummy, signature) is False

def test_apply_core_refresh_payload_clears_pending_support_refresh() -> None:
    scheduled: list[str] = []

    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value):
            self.value = value

    class _Tree:
        def __init__(self) -> None:
            self._children = ()

        def get_children(self):
            return self._children

    dummy = SimpleNamespace(
        rulebook_path=None,
        matcher_settings={},
        previous_mapping={},
        previous_mapping_path=None,
        previous_mapping_year=None,
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(),
            membership={},
            suggestions=pd.DataFrame(),
            basis_col="Endring",
        ),
        control_gl_df=pd.DataFrame(),
        a07_overview_df=pd.DataFrame(),
        control_df=pd.DataFrame(columns=["Kode"]),
        groups_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        unmapped_df=pd.DataFrame(),
        mapping_df=pd.DataFrame(),
        history_compare_df=pd.DataFrame(),
        tree_groups=_Tree(),
        tree_control_suggestions=_Tree(),
        tree_control_accounts=_Tree(),
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        _refresh_control_gl_tree=lambda: scheduled.append("gl"),
        _refresh_a07_tree=lambda: scheduled.append("a07"),
        _fill_tree=lambda *args, **kwargs: scheduled.append("fill"),
        _update_control_panel=lambda: scheduled.append("panel"),
        _update_control_transfer_buttons=lambda: scheduled.append("buttons"),
        _update_summary=lambda: scheduled.append("summary"),
        _support_views_ready=True,
        _support_views_dirty=False,
        _loaded_support_tabs={"history"},
        _refresh_in_progress=True,
        _pending_focus_code=None,
        _pending_support_refresh=True,
        _control_details_visible=True,
        after_idle=lambda cb: scheduled.append("after_idle"),
        _schedule_support_refresh=lambda: scheduled.append("support"),
        _pending_session_refresh=False,
    )

    payload = {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert dummy._pending_support_refresh is False
    assert "support" not in scheduled

def test_apply_core_refresh_payload_does_not_auto_apply_or_restart() -> None:
    calls: list[tuple[str, object]] = []
    auto_called = {"value": False}

    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value) -> None:
            self.value = value

    dummy = SimpleNamespace(
        _a07_refresh_warnings=[],
        _diag=lambda *args, **kwargs: None,
        _auto_apply_strict_a07_suggestions=lambda: auto_called.__setitem__("value", True),
        _cancel_refresh_watchdog=lambda: calls.append(("watchdog", None)),
        _refresh_core=lambda **kwargs: calls.append(("refresh", kwargs.get("focus_code"))),
        _refresh_in_progress=True,
        _refresh_control_gl_tree=lambda: calls.append(("gl", None)),
        _refresh_a07_tree=lambda: calls.append(("a07", None)),
        _update_control_panel=lambda: calls.append(("panel", None)),
        _update_control_transfer_buttons=lambda: calls.append(("buttons", None)),
        _update_summary=lambda: calls.append(("summary", None)),
        _loaded_support_tabs=set(),
        _loaded_support_context_keys={},
        _pending_focus_code=None,
        _pending_support_refresh=False,
        _pending_session_refresh=False,
        _selected_rf1022_group_id=None,
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        control_statement_accounts_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(),
            membership={},
            suggestions=pd.DataFrame(),
            basis_col="UB",
        ),
    )
    payload = {
        "rulebook_path": None,
        "effective_rulebook": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "effective_mapping": {},
        "effective_previous_mapping": {},
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "reconcile_df": pd.DataFrame(),
        "mapping_df": pd.DataFrame(),
        "mapping_audit_df": pd.DataFrame(),
        "mapping_review_df": pd.DataFrame(),
        "unmapped_df": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(),
        "rf1022_overview_df": pd.DataFrame(),
        "groups_df": pd.DataFrame(),
        "control_statement_base_df": pd.DataFrame(),
        "control_statement_df": pd.DataFrame(),
        "warnings": [],
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert auto_called["value"] is False
    assert ("refresh", "skattepliktigDelForsikringer") not in calls
    assert calls[-1] == ("watchdog", None)

def test_apply_core_refresh_payload_shows_warning_status() -> None:
    scheduled: list[str] = []

    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value):
            self.value = value

    class _Tree:
        def get_children(self):
            return ()

    dummy = SimpleNamespace(
        _a07_refresh_warnings=[],
        rulebook_path=None,
        matcher_settings={},
        previous_mapping={},
        previous_mapping_path=None,
        previous_mapping_year=None,
        workspace=SimpleNamespace(a07_df=pd.DataFrame(), membership={}, suggestions=pd.DataFrame(), basis_col="Endring"),
        control_gl_df=pd.DataFrame(),
        a07_overview_df=pd.DataFrame(),
        control_df=pd.DataFrame(columns=["Kode"]),
        groups_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        unmapped_df=pd.DataFrame(),
        mapping_df=pd.DataFrame(),
        history_compare_df=pd.DataFrame(),
        tree_groups=_Tree(),
        tree_control_suggestions=_Tree(),
        tree_control_accounts=_Tree(),
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        _refresh_control_gl_tree=lambda: scheduled.append("gl"),
        _refresh_a07_tree=lambda: scheduled.append("a07"),
        _fill_tree=lambda *args, **kwargs: scheduled.append("fill"),
        _update_control_panel=lambda: scheduled.append("panel"),
        _update_control_transfer_buttons=lambda: scheduled.append("buttons"),
        _update_summary=lambda: scheduled.append("summary"),
        _support_views_ready=True,
        _support_views_dirty=False,
        _loaded_support_tabs=set(),
        _refresh_in_progress=True,
        _pending_focus_code=None,
        _pending_support_refresh=False,
        _control_details_visible=True,
        after_idle=lambda cb: cb(),
        _pending_session_refresh=False,
        _diag=lambda *args, **kwargs: None,
    )

    payload = {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
        "warnings": [{"scope": "rulebook", "message": "A07-regelbok kunne ikke lastes.", "detail": "boom"}],
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert dummy.status_var.value == "A07 oppdatert med advarsler."
    assert "rulebook" in dummy.details_var.value
    assert "boom" in dummy.details_var.value

def test_apply_core_refresh_payload_tolerates_missing_optional_support_trees() -> None:
    scheduled: list[str] = []

    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value) -> None:
            self.value = value

    class _Tree:
        def get_children(self):
            return ()

    dummy = SimpleNamespace(
        rulebook_path=None,
        matcher_settings={},
        previous_mapping={},
        previous_mapping_path=None,
        previous_mapping_year=None,
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(),
            membership={},
            suggestions=pd.DataFrame(),
            basis_col="Endring",
        ),
        control_gl_df=pd.DataFrame(),
        a07_overview_df=pd.DataFrame(),
        control_df=pd.DataFrame(columns=["Kode"]),
        groups_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        unmapped_df=pd.DataFrame(),
        mapping_df=pd.DataFrame(),
        history_compare_df=pd.DataFrame(),
        control_statement_base_df=pd.DataFrame(),
        control_statement_df=pd.DataFrame(),
        control_statement_accounts_df=pd.DataFrame(),
        tree_a07=_Tree(),
        tree_control_suggestions=_Tree(),
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        control_statement_accounts_summary_var=_Var(),
        control_statement_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        control_statement_include_unclassified_var=SimpleNamespace(get=lambda: False),
        _build_current_control_statement_df=lambda include_unclassified=False: pd.DataFrame(),
        _refresh_control_gl_tree=lambda: scheduled.append("gl"),
        _refresh_a07_tree=lambda: scheduled.append("a07"),
        _fill_tree=lambda *args, **kwargs: scheduled.append("fill"),
        _update_control_panel=lambda: scheduled.append("panel"),
        _update_control_transfer_buttons=lambda: scheduled.append("buttons"),
        _update_summary=lambda: scheduled.append("summary"),
        _support_views_ready=True,
        _support_views_dirty=False,
        _loaded_support_tabs=set(),
        _refresh_in_progress=True,
        _pending_focus_code=None,
        _pending_support_refresh=False,
        _control_details_visible=True,
        _pending_session_refresh=False,
        _cancel_refresh_watchdog=lambda: scheduled.append("cancel_watchdog"),
        _diag=lambda *_args, **_kwargs: None,
        _context_has_changed=lambda: False,
        _set_control_details_visible=lambda visible: scheduled.append(f"details:{visible}"),
        _selected_control_code=lambda: None,
    )

    payload = {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "effective_mapping": {},
        "effective_previous_mapping": {},
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "reconcile_df": pd.DataFrame(),
        "mapping_df": pd.DataFrame(),
        "unmapped_df": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
        "control_statement_df": pd.DataFrame(),
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert "summary" in scheduled
    assert dummy._refresh_in_progress is False

def test_apply_core_refresh_payload_keeps_full_control_statement_base_for_non_payroll_view() -> None:
    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value) -> None:
            self.value = value

    base_df = pd.DataFrame(
        [
            {"Gruppe": "100_loenn_ol", "Navn": "Post 100", "Endring": 100.0, "AntallKontoer": 1},
            {"Gruppe": "Skyldig MVA", "Navn": "Skyldig MVA", "Endring": 50.0, "AntallKontoer": 1},
        ]
    )
    legacy_df = pd.DataFrame(
        [
            {"Gruppe": "Skyldig MVA", "Navn": "Skyldig MVA", "Endring": 50.0, "AntallKontoer": 1},
        ]
    )

    dummy = SimpleNamespace(
        rulebook_path=None,
        matcher_settings={},
        previous_mapping={},
        previous_mapping_path=None,
        previous_mapping_year=None,
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(),
            membership={},
            suggestions=pd.DataFrame(),
            basis_col="Endring",
        ),
        control_gl_df=pd.DataFrame(),
        a07_overview_df=pd.DataFrame(),
        control_df=pd.DataFrame(columns=["Kode"]),
        groups_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        unmapped_df=pd.DataFrame(),
        mapping_df=pd.DataFrame(),
        history_compare_df=pd.DataFrame(),
        control_statement_base_df=pd.DataFrame(),
        control_statement_df=pd.DataFrame(),
        control_statement_accounts_df=pd.DataFrame(),
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        control_statement_accounts_summary_var=_Var(),
        control_statement_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        _selected_control_statement_view=lambda: page_a07.CONTROL_STATEMENT_VIEW_LEGACY,
        _build_current_control_statement_df=lambda **_kwargs: legacy_df.copy(deep=True),
        _support_views_ready=True,
        _support_views_dirty=False,
        _history_compare_ready=False,
        _loaded_support_tabs=set(),
        _refresh_in_progress=True,
        _pending_focus_code=None,
        _pending_support_refresh=False,
        _pending_session_refresh=False,
        _control_details_visible=False,
        _update_history_details_from_selection=lambda: None,
        _update_control_panel=lambda: None,
        _update_control_transfer_buttons=lambda: None,
        _update_summary=lambda: None,
        _refresh_control_gl_tree=lambda: None,
        _refresh_a07_tree=lambda: None,
        after_idle=lambda _callback: None,
    )

    payload = {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "effective_mapping": {},
        "effective_previous_mapping": {},
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "reconcile_df": pd.DataFrame(),
        "mapping_df": pd.DataFrame(),
        "unmapped_df": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
        "control_statement_base_df": base_df,
        "control_statement_df": base_df.iloc[[0]].copy(deep=True),
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert dummy.control_statement_base_df["Gruppe"].tolist() == ["100_loenn_ol", "Skyldig MVA"]
    assert dummy.control_statement_df["Gruppe"].tolist() == ["Skyldig MVA"]

def test_apply_core_refresh_payload_refreshes_support_windows() -> None:
    scheduled: list[str] = []

    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value) -> None:
            self.value = value

    class _Tree:
        def get_children(self):
            return ()

    dummy = SimpleNamespace(
        rulebook_path=None,
        matcher_settings={},
        previous_mapping={},
        previous_mapping_path=None,
        previous_mapping_year=None,
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(),
            membership={},
            suggestions=pd.DataFrame(),
            basis_col="Endring",
        ),
        control_gl_df=pd.DataFrame(),
        a07_overview_df=pd.DataFrame(),
        control_df=pd.DataFrame(columns=["Kode"]),
        groups_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        unmapped_df=pd.DataFrame(),
        mapping_df=pd.DataFrame(),
        history_compare_df=pd.DataFrame(),
        control_statement_base_df=pd.DataFrame(),
        control_statement_df=pd.DataFrame(),
        control_statement_accounts_df=pd.DataFrame(),
        tree_a07=_Tree(),
        tree_groups=_Tree(),
        tree_control_suggestions=_Tree(),
        tree_control_accounts=_Tree(),
        tree_control_statement_accounts=_Tree(),
        tree_mapping=_Tree(),
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        control_statement_accounts_summary_var=_Var(),
        control_statement_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        _selected_control_statement_view=lambda: page_a07.CONTROL_STATEMENT_VIEW_PAYROLL,
        _selected_control_work_level=lambda: "a07",
        _build_current_control_statement_df=lambda **_kwargs: pd.DataFrame(),
        _support_views_ready=True,
        _support_views_dirty=False,
        _history_compare_ready=False,
        _loaded_support_tabs=set(),
        _refresh_in_progress=True,
        _pending_focus_code=None,
        _pending_support_refresh=False,
        _pending_session_refresh=False,
        _control_details_visible=False,
        _update_history_details_from_selection=lambda: None,
        _update_control_panel=lambda: scheduled.append("panel"),
        _update_control_transfer_buttons=lambda: scheduled.append("buttons"),
        _update_summary=lambda: scheduled.append("summary"),
        _refresh_control_gl_tree=lambda: scheduled.append("gl"),
        _refresh_a07_tree=lambda: scheduled.append("a07"),
        _refresh_control_statement_window=lambda: scheduled.append("control_statement_window"),
        _fill_tree=lambda *args, **kwargs: scheduled.append("fill"),
        _cancel_refresh_watchdog=lambda: scheduled.append("cancel_watchdog"),
        _diag=lambda *_args, **_kwargs: None,
        _context_has_changed=lambda: False,
        _set_control_details_visible=lambda visible: scheduled.append(f"details:{visible}"),
        _selected_control_code=lambda: None,
        after_idle=lambda _callback: None,
    )

    payload = {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "effective_mapping": {},
        "effective_previous_mapping": {},
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "reconcile_df": pd.DataFrame(),
        "mapping_df": pd.DataFrame(),
        "unmapped_df": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
        "control_statement_base_df": pd.DataFrame(),
        "control_statement_df": pd.DataFrame(),
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert "rf1022_window" not in scheduled
    assert "control_statement_window" in scheduled

def test_apply_core_refresh_payload_refreshes_support_trees_for_initial_selected_code() -> None:
    scheduled: list[str] = []

    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value) -> None:
            self.value = value

    class _Tree:
        def __init__(self, children=()) -> None:
            self._children = tuple(children)

        def get_children(self):
            return self._children

    dummy = SimpleNamespace(
        rulebook_path=None,
        matcher_settings={},
        previous_mapping={},
        previous_mapping_path=None,
        previous_mapping_year=None,
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(),
            membership={},
            suggestions=pd.DataFrame(),
            basis_col="Endring",
            selected_code=None,
        ),
        control_gl_df=pd.DataFrame(),
        a07_overview_df=pd.DataFrame(),
        control_df=pd.DataFrame(columns=["Kode"]),
        groups_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        unmapped_df=pd.DataFrame(),
        mapping_df=pd.DataFrame(),
        history_compare_df=pd.DataFrame(),
        control_statement_base_df=pd.DataFrame(),
        control_statement_df=pd.DataFrame(),
        control_statement_accounts_df=pd.DataFrame(),
        tree_a07=_Tree(children=("timeleonn",)),
        tree_groups=_Tree(),
        tree_control_suggestions=_Tree(),
        tree_control_accounts=_Tree(),
        tree_control_statement_accounts=_Tree(),
        tree_mapping=_Tree(),
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        control_statement_accounts_summary_var=_Var(),
        control_statement_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        _selected_control_statement_view=lambda: page_a07.CONTROL_STATEMENT_VIEW_PAYROLL,
        _selected_control_work_level=lambda: "a07",
        _build_current_control_statement_df=lambda **_kwargs: pd.DataFrame(),
        _support_views_ready=True,
        _support_views_dirty=False,
        _history_compare_ready=False,
        _loaded_support_tabs=set(),
        _refresh_in_progress=True,
        _pending_focus_code=None,
        _pending_support_refresh=False,
        _pending_session_refresh=False,
        _control_details_visible=True,
        _skip_initial_control_followup=False,
        _update_history_details_from_selection=lambda: scheduled.append("history"),
        _update_control_panel=lambda: scheduled.append("panel"),
        _update_control_transfer_buttons=lambda: scheduled.append("buttons"),
        _update_summary=lambda: scheduled.append("summary"),
        _refresh_control_gl_tree=lambda: scheduled.append("gl"),
        _refresh_a07_tree=lambda: scheduled.append("a07"),
        _refresh_control_statement_window=lambda: scheduled.append("control_statement_window"),
        _refresh_control_support_trees=lambda: scheduled.append("support_trees"),
        _render_active_support_tab=lambda force=False: scheduled.append(f"render:{force}"),
        _active_support_tab_key=lambda: "mapping",
        _fill_tree=lambda *args, **kwargs: scheduled.append("fill"),
        _cancel_refresh_watchdog=lambda: scheduled.append("cancel_watchdog"),
        _diag=lambda *_args, **_kwargs: None,
        _context_has_changed=lambda: False,
        _set_control_details_visible=lambda visible: scheduled.append(f"details:{visible}"),
        _set_tree_selection=lambda _tree, target: scheduled.append(f"select:{target}"),
        after_idle=lambda _callback: None,
    )

    payload = {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "effective_mapping": {},
        "effective_previous_mapping": {},
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "reconcile_df": pd.DataFrame(),
        "mapping_df": pd.DataFrame(),
        "unmapped_df": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
        "control_statement_df": pd.DataFrame(),
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert "select:timeleonn" in scheduled
    assert "support_trees" in scheduled
    assert "render:True" in scheduled
    assert dummy.workspace.selected_code == "timeleonn"
    assert dummy._skip_initial_control_followup is False

def test_refresh_all_cancels_pending_core_jobs_before_starting() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _refresh_in_progress=False,
        _pending_session_refresh=True,
        _pending_support_refresh=True,
        _cancel_core_refresh_jobs=lambda: calls.append("cancel_core"),
        _cancel_support_refresh=lambda: calls.append("cancel_support"),
        _support_views_ready=True,
        _start_core_refresh=lambda: calls.append("start_core"),
    )

    page_a07.A07Page._refresh_all(dummy)

    assert calls == ["cancel_core", "cancel_support", "start_core"]
    assert dummy._refresh_in_progress is True
    assert dummy._pending_session_refresh is False
    assert dummy._pending_support_refresh is False
    assert dummy._support_views_ready is False

def test_refresh_clicked_defers_focus_until_refresh_finishes() -> None:
    calls: list[str] = []
    workspace = SimpleNamespace(a07_df=pd.DataFrame([{"Kode": "70"}]), gl_df=pd.DataFrame([{"Konto": "5000"}]))
    dummy = SimpleNamespace(
        workspace=workspace,
        _selected_control_code=lambda: "fastloenn",
        _refresh_all=lambda: calls.append("refresh_all"),
        _focus_control_code=lambda code: calls.append(f"focus:{code}"),
        _notify_inline=lambda *args, **kwargs: calls.append("notify"),
        status_var=SimpleNamespace(set=lambda value: calls.append(f"status:{value}")),
        _pending_focus_code=None,
    )

    page_a07.A07Page._refresh_clicked(dummy)

    assert dummy._pending_focus_code == "fastloenn"
    assert "refresh_all" in calls
    assert not any(call.startswith("focus:") for call in calls)

def test_schedule_control_selection_followup_requests_support_when_details_are_visible() -> None:
    calls: list[str] = []

    class _Dummy:
        _skip_initial_control_followup = False
        _control_details_visible = True
        _support_requested = False
        _support_views_ready = False

        def _cancel_scheduled_job(self, *_args, **_kwargs):
            return None

        def after(self, _delay, callback):
            callback()
            return "job"

        def _diag(self, _message):
            return None

        def _active_support_tab_key(self):
            return "history"

        def _refresh_suggestions_tree(self):
            calls.append("suggestions")

        def _refresh_control_support_trees(self):
            calls.append("support")

        def _schedule_support_refresh(self):
            calls.append("schedule_support")

        def _retag_control_gl_tree(self):
            calls.append("retag")
            return True

        def _schedule_control_gl_refresh(self, delay_ms=0):
            calls.append(f"gl:{delay_ms}")

        def _update_control_transfer_buttons(self):
            calls.append("buttons")

    page_a07.A07Page._schedule_control_selection_followup(_Dummy())

    assert calls == ["schedule_support", "buttons"]


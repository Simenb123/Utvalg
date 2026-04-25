from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_create_app_exposes_a07_page() -> None:
    app = ui_main.create_app()
    try:
        try:
            app.withdraw()  # type: ignore[attr-defined]
        except Exception:
            pass

        assert hasattr(app, "page_a07")
        assert hasattr(app.page_a07, "refresh_from_session")
        # In headless mode the stub has no real widgets â€” skip detailed checks
        if hasattr(app.page_a07, "nb"):
            assert len(app.page_a07.nb.tabs()) == 0
            assert hasattr(app.page_a07, "tree_control_gl")
            assert hasattr(app.page_a07, "tree_a07")
    finally:
        try:
            app.destroy()  # type: ignore[attr-defined]
        except Exception:
            pass

def test_control_statement_module_exports_tk_for_window_opening() -> None:
    assert getattr(page_a07_control_statement, "tk", None) is not None
    assert getattr(page_a07_control_statement.tk, "Toplevel", None) is not None

def test_sync_shared_refs_updates_env_and_compat_runtime_refs(monkeypatch) -> None:
    from a07_feature import page_a07_env

    app_paths_ref = object()
    client_store_ref = object()
    session_ref = object()
    filedialog_ref = object()
    messagebox_ref = object()
    simpledialog_ref = object()
    konto_klassifisering_ref = object()

    monkeypatch.setattr(page_a07, "app_paths", app_paths_ref)
    monkeypatch.setattr(page_a07, "client_store", client_store_ref)
    monkeypatch.setattr(page_a07, "session", session_ref)
    monkeypatch.setattr(page_a07, "filedialog", filedialog_ref)
    monkeypatch.setattr(page_a07, "messagebox", messagebox_ref)
    monkeypatch.setattr(page_a07, "simpledialog", simpledialog_ref)
    monkeypatch.setattr(page_a07, "konto_klassifisering", konto_klassifisering_ref)

    page_a07._sync_shared_refs()

    assert page_a07_env.app_paths is app_paths_ref
    assert page_a07_env.client_store is client_store_ref
    assert page_a07_env.session is session_ref
    assert page_a07_env.filedialog is filedialog_ref
    assert page_a07_env.messagebox is messagebox_ref
    assert page_a07_env.simpledialog is simpledialog_ref
    assert page_a07_env.konto_klassifisering is konto_klassifisering_ref
    assert page_a07._shared.app_paths is app_paths_ref
    assert page_a07._shared.client_store is client_store_ref
    assert page_a07._ui_focus_helpers.messagebox is messagebox_ref

def test_context_restore_payload_collects_degraded_state_warnings(monkeypatch) -> None:
    from a07_feature import page_a07_refresh_services as refresh_services

    def _raise(label: str):
        raise OSError(label)

    globals_ = refresh_services.build_context_restore_payload.__globals__
    monkeypatch.setitem(globals_, "resolve_context_source_path", lambda client, year: Path("a07_source.json"))
    monkeypatch.setitem(globals_, "resolve_context_mapping_path", lambda *args, **kwargs: Path("a07_mapping.json"))
    monkeypatch.setitem(globals_, "default_a07_groups_path", lambda client, year: Path("a07_groups.json"))
    monkeypatch.setitem(globals_, "default_a07_locks_path", lambda client, year: Path("a07_locks.json"))
    monkeypatch.setitem(globals_, "default_a07_project_path", lambda client, year: Path("a07_project.json"))
    monkeypatch.setitem(globals_, "load_a07_groups", lambda path: _raise("groups"))
    monkeypatch.setitem(globals_, "load_locks", lambda path: _raise("locks"))
    monkeypatch.setitem(globals_, "load_project_state", lambda path: _raise("project"))

    payload = refresh_services.build_context_restore_payload(
        client="Air Management AS",
        year="2025",
        load_active_trial_balance_cached=lambda client, year: (pd.DataFrame(), None),
        load_a07_source_cached=lambda path: _raise("source"),
        load_mapping_file_cached=lambda path, client=None, year=None: _raise("mapping"),
        load_previous_year_mapping_cached=lambda client, year: ({}, None, None),
        resolve_rulebook_path_cached=lambda client, year: _raise("rulebook"),
    )

    scopes = {warning["scope"] for warning in payload["warnings"]}
    assert {"a07_source", "mapping", "groups", "locks", "project", "rulebook_path"}.issubset(scopes)
    assert payload["a07_path"] is None
    assert payload["mapping_path"] is None
    assert payload["groups"] == {}
    assert payload["locks"] == set()
    assert payload["project_meta"] == {}

def test_control_statement_export_collects_warning_when_source_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        a07_control_data,
        "build_current_control_statement_rows",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("catalog unavailable")),
    )
    warnings: list[dict[str, str]] = []

    out = a07_control_data.build_control_statement_export_df(
        client="Air Management AS",
        year="2025",
        gl_df=pd.DataFrame([{"Konto": "5000", "Navn": "Lonn", "IB": 0.0, "Endring": 100.0, "UB": 100.0}]),
        warning_collector=warnings,
    )

    assert out.empty
    assert warnings == [
        {
            "scope": "control_statement",
            "message": "Kontrolloppstilling kunne ikke bygges.",
            "detail": "catalog unavailable",
        }
    ]

def test_refresh_service_builders_keep_expected_payload_shapes() -> None:
    from a07_feature import page_a07_refresh_services as refresh_services

    context_payload = refresh_services.build_context_restore_payload(
        client=None,
        year=None,
        load_active_trial_balance_cached=lambda client, year: (page_a07._empty_gl_df(), None),
        load_a07_source_cached=lambda path: page_a07._empty_a07_df(),
        load_mapping_file_cached=lambda path, client=None, year=None: {},
        load_previous_year_mapping_cached=lambda client, year: ({}, None, None),
        resolve_rulebook_path_cached=lambda client, year: None,
    )
    assert {
        "gl_df",
        "tb_path",
        "source_a07_df",
        "a07_df",
        "a07_path",
        "mapping",
        "mapping_path",
        "groups",
        "groups_path",
        "locks",
        "locks_path",
        "project_meta",
        "project_path",
        "basis_col",
        "previous_mapping",
        "previous_mapping_path",
        "previous_mapping_year",
        "rulebook_path",
        "pending_focus_code",
    }.issubset(context_payload)

    core_payload = refresh_services.build_core_refresh_payload(
        client=None,
        year=None,
        source_a07_df=page_a07._empty_a07_df(),
        gl_df=page_a07._empty_gl_df(),
        groups={},
        mapping={},
        basis_col="Endring",
        locks=set(),
        previous_mapping={},
        usage_df=None,
        previous_mapping_path=None,
        previous_mapping_year=None,
        rulebook_path=None,
        load_code_profile_state=lambda client, year, mapping_current, gl_df=None: {},
    )
    assert {
        "rulebook_path",
        "matcher_settings",
        "previous_mapping",
        "previous_mapping_path",
        "previous_mapping_year",
        "effective_mapping",
        "effective_previous_mapping",
        "grouped_a07_df",
        "membership",
        "suggestions",
        "reconcile_df",
        "mapping_df",
        "unmapped_df",
        "control_gl_df",
        "a07_overview_df",
        "control_df",
        "groups_df",
        "control_statement_base_df",
        "control_statement_df",
    }.issubset(core_payload)

    support_payload = refresh_services.build_support_refresh_payload(
        a07_df=page_a07._empty_a07_df(),
        gl_df=page_a07._empty_gl_df(),
        effective_mapping={},
        effective_previous_mapping={},
    )
    assert set(support_payload) == {"history_compare_df"}

def test_active_a07_modules_do_not_import_page_a07_shared_directly() -> None:
    project_root = Path(__file__).resolve().parents[2]
    active_modules = (
        project_root / "a07_feature" / "page_a07_background.py",
        project_root / "a07_feature" / "control" / "mapping_audit.py",
        project_root / "a07_feature" / "control" / "mapping_audit_rules.py",
        project_root / "a07_feature" / "control" / "mapping_audit_status.py",
        project_root / "a07_feature" / "control" / "mapping_review.py",
        project_root / "a07_feature" / "control" / "mapping_audit_projection.py",
        project_root / "a07_feature" / "control" / "statement_ui.py",
        project_root / "a07_feature" / "control" / "statement_view_state.py",
        project_root / "a07_feature" / "control" / "statement_window_ui.py",
        project_root / "a07_feature" / "control" / "statement_panel_ui.py",
        project_root / "a07_feature" / "page_a07_context_menu.py",
        project_root / "a07_feature" / "page_a07_context_menu_base.py",
        project_root / "a07_feature" / "page_a07_context_menu_control.py",
        project_root / "a07_feature" / "page_a07_context_menu_codes.py",
        project_root / "a07_feature" / "page_a07_dialogs.py",
        project_root / "a07_feature" / "page_a07_dialogs_editors.py",
        project_root / "a07_feature" / "page_a07_dialogs_shared.py",
        project_root / "a07_feature" / "page_a07_manual_mapping_dialog.py",
        project_root / "a07_feature" / "payroll" / "rf1022.py",
        project_root / "a07_feature" / "ui" / "helpers.py",
        project_root / "a07_feature" / "ui" / "selection.py",
    )

    for module_path in active_modules:
        source = module_path.read_text(encoding="utf-8")
        assert "from .page_a07_shared import" not in source


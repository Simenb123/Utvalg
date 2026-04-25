from __future__ import annotations

from .shared import *  # noqa: F401,F403


class _Var:
    def __init__(self) -> None:
        self.value = None

    def set(self, value) -> None:
        self.value = value


class _Tree:
    def __init__(self, name: str, children=()) -> None:
        self.name = name
        self._children = tuple(children)

    def get_children(self):
        return self._children


def _payload(*, suggestions: pd.DataFrame | None = None) -> dict[str, object]:
    return {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "effective_mapping": {},
        "effective_previous_mapping": {},
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": suggestions if suggestions is not None else pd.DataFrame(),
        "reconcile_df": pd.DataFrame(),
        "mapping_df": pd.DataFrame(),
        "unmapped_df": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
        "control_statement_df": pd.DataFrame(),
    }


def _refresh_page(*, code_children=(), fills: list[tuple[str, int]], scheduled: list[str]):
    def _fill_tree(tree, df, *_args, **_kwargs):
        fills.append((getattr(tree, "name", ""), len(getattr(df, "index", ()))))

    return SimpleNamespace(
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
        tree_a07=_Tree("a07", children=code_children),
        tree_control_suggestions=_Tree("suggestions", children=("old-suggestion",)),
        tree_control_accounts=_Tree("accounts", children=("5000",)),
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
        _fill_tree=_fill_tree,
        _cancel_refresh_watchdog=lambda: scheduled.append("cancel_watchdog"),
        _diag=lambda *_args, **_kwargs: None,
        _context_has_changed=lambda: False,
        _set_control_details_visible=lambda visible: scheduled.append(f"details:{visible}"),
        _set_tree_selection=lambda _tree, target: scheduled.append(f"select:{target}"),
        _schedule_active_support_render=lambda force=False: scheduled.append(f"support_render:{force}"),
        after_idle=lambda _callback: None,
    )


def test_core_refresh_keeps_support_trees_visible_while_selection_restores() -> None:
    fills: list[tuple[str, int]] = []
    scheduled: list[str] = []
    page = _refresh_page(code_children=("fastloenn",), fills=fills, scheduled=scheduled)
    suggestions = pd.DataFrame([{"Kode": "fastloenn", "ForslagKontoer": "5000"}])

    page_a07.A07Page._apply_core_refresh_payload(page, _payload(suggestions=suggestions))

    assert "select:fastloenn" in scheduled
    assert "support_render:True" in scheduled
    assert not any(name in {"suggestions", "accounts"} and count == 0 for name, count in fills)


def test_core_refresh_clears_support_trees_when_no_selection_can_restore() -> None:
    fills: list[tuple[str, int]] = []
    page = _refresh_page(code_children=(), fills=fills, scheduled=[])

    page_a07.A07Page._apply_core_refresh_payload(page, _payload())

    assert ("suggestions", 0) in fills
    assert ("accounts", 0) in fills

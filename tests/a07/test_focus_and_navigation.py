from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_focus_linked_code_for_selected_gl_account_uses_effective_mapping() -> None:
    calls: list[str] = []
    statuses: list[str] = []
    dummy = SimpleNamespace(
        tree_control_gl=object(),
        _selected_control_gl_accounts=lambda: ["5000"],
        _effective_mapping=lambda: {"5000": "fastloenn"},
        _activate_a07_code_for_explicit_account_action=lambda code: calls.append(code),
        status_var=SimpleNamespace(set=lambda value: statuses.append(value)),
    )

    page_a07.A07Page._focus_linked_code_for_selected_gl_account(dummy)

    assert calls == ["fastloenn"]
    assert statuses == ["Konto 5000 er koblet til A07-kode fastloenn."]

def test_open_saldobalanse_workspace_selects_tab_and_focuses_accounts() -> None:
    selected_pages: list[object] = []
    refresh_calls: list[object] = []
    focus_calls: list[list[str]] = []
    statuses: list[str] = []

    page_saldobalanse = SimpleNamespace(
        refresh_from_session=lambda session_obj=None: refresh_calls.append(session_obj),
        focus_payroll_accounts=lambda accounts: focus_calls.append(list(accounts)),
    )
    host = SimpleNamespace(
        nb=SimpleNamespace(select=lambda page: selected_pages.append(page)),
        page_saldobalanse=page_saldobalanse,
    )
    dummy = SimpleNamespace(
        winfo_toplevel=lambda: host,
        status_var=SimpleNamespace(set=lambda value: statuses.append(value)),
    )

    out = page_a07.A07Page._open_saldobalanse_workspace(
        dummy,
        accounts=["5000", "5210"],
        status_text="Apnet Saldobalanse.",
    )

    assert out is True
    assert selected_pages == [page_saldobalanse]
    assert refresh_calls == [page_a07.session]
    assert focus_calls == [["5000", "5210"]]
    assert statuses == ["Apnet Saldobalanse."]

def test_open_saldobalanse_for_selected_code_classification_uses_selected_code_accounts() -> None:
    calls: list[tuple[list[str], str, str]] = []

    class DummyPage:
        tree_a07 = object()

        def _selected_control_code(self):
            return "fastloenn"

        def _selected_code_accounts(self, code=None):
            assert code == "fastloenn"
            return ["5000", "5001"]

        def _selected_control_row(self):
            return pd.Series({"NesteHandling": "Tildel RF-1022-post i Saldobalanse."})

        def _open_saldobalanse_workspace(self, *, accounts=None, payroll_scope=None, status_text=None):
            calls.append((list(accounts or ()), str(payroll_scope or ""), str(status_text or "")))
            return True

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            raise AssertionError(message)

    page_a07.A07Page._open_saldobalanse_for_selected_code_classification(DummyPage())

    assert calls == [
        (
            ["5000", "5001"],
            classification_workspace.QUEUE_REVIEW,
                "Tildel RF-1022-post i Saldobalanse. A07 viser behovet, men klassifiseringen gjøres i Saldobalanse.",
        )
    ]

def test_open_saldobalanse_for_selected_code_classification_uses_suspicious_queue_for_conflicts() -> None:
    calls: list[tuple[list[str], str]] = []

    class DummyPage:
        tree_a07 = object()

        def _selected_control_code(self):
            return "fastloenn"

        def _selected_code_accounts(self, code=None):
            assert code == "fastloenn"
            return ["5000"]

        def _selected_control_row(self):
            return pd.Series({"NesteHandling": "Rydd RF-1022-post for mappede kontoer."})

        def _open_saldobalanse_workspace(self, *, accounts=None, payroll_scope=None, status_text=None):
            calls.append((list(accounts or ()), str(payroll_scope or "")))
            return True

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            raise AssertionError(message)

    page_a07.A07Page._open_saldobalanse_for_selected_code_classification(DummyPage())

    assert calls == [(["5000"], classification_workspace.QUEUE_SUSPICIOUS)]

def test_on_control_selection_changed_updates_status_with_connected_accounts_summary() -> None:
    status_calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _is_tree_selection_suppressed=lambda _tree: False,
        tree_a07=object(),
        workspace=SimpleNamespace(selected_code=None, basis_col="Endring"),
        _selected_control_code=lambda: "elektroniskKommunikasjon",
        _update_history_details_from_selection=lambda: None,
        _control_details_visible=False,
        _refresh_in_progress=False,
        _update_control_panel=lambda: None,
        _update_control_transfer_buttons=lambda: None,
        _sync_groups_panel_visibility=lambda: None,
        _schedule_control_selection_followup=lambda: None,
        control_gl_df=pd.DataFrame(
            [
                {"Konto": "5210", "Navn": "Fri telefon", "Endring": 38064.0, "Kode": "elektroniskKommunikasjon"},
            ]
        ),
        status_var=SimpleNamespace(set=lambda value: status_calls.append(value)),
    )

    page_a07.A07Page._on_control_selection_changed(dummy)

    assert dummy.workspace.selected_code == "elektroniskKommunikasjon"
    assert status_calls == [
        "Valgt elektroniskKommunikasjon | 1 konto koblet | Endring 38 064,00 | 5210 Fri telefon"
    ]

def test_focus_selected_control_account_in_gl_focuses_first_account() -> None:
    calls: list[str] = []

    class DummyPage:
        def _selected_control_account_ids(self):
            return ["5000", "5001"]

        def _focus_mapping_account(self, konto):
            calls.append(konto)

    page_a07.A07Page._focus_selected_control_account_in_gl(DummyPage())

    assert calls == ["5000"]

def test_focus_selected_control_account_in_gl_skips_passive_multiselect() -> None:
    calls: list[str] = []

    class DummyPage:
        def _selected_control_account_ids(self):
            return ["5000", "5001"]

        def _focus_mapping_account(self, konto):
            calls.append(konto)

    page_a07.A07Page._focus_selected_control_account_in_gl(DummyPage(), allow_multi=False)

    assert calls == []

def test_focus_control_code_defers_while_refresh_is_running() -> None:
    dummy = SimpleNamespace(
        _refresh_in_progress=True,
        _pending_focus_code=None,
    )

    page_a07.A07Page._focus_control_code(dummy, "fastloenn")

    assert dummy._pending_focus_code == "fastloenn"

def test_focus_control_code_stops_when_code_is_unknown() -> None:
    calls: list[str] = []

    class _Tree:
        def get_children(self):
            return ()

    dummy = SimpleNamespace(
        _refresh_in_progress=False,
        tree_a07=_Tree(),
        control_df=pd.DataFrame([{"Kode": "fastloenn"}]),
        rf1022_overview_df=pd.DataFrame(),
        groups_df=pd.DataFrame(),
        _diag=lambda _msg: None,
        _schedule_a07_refresh=lambda **_kwargs: calls.append("schedule"),
    )

    page_a07.A07Page._focus_control_code(dummy, "ukjentKode")

    assert calls == []

def test_focus_control_code_limits_refilter_attempts() -> None:
    calls: list[int] = []

    class _Var:
        def set(self, _value):
            return None

    class _Widget:
        def set(self, _value):
            return None

    class _Tree:
        def get_children(self):
            return ()

    dummy = SimpleNamespace(
        _refresh_in_progress=False,
        _focus_control_code_attempts={},
        tree_a07=_Tree(),
        control_df=pd.DataFrame([{"Kode": "fastloenn"}]),
        rf1022_overview_df=pd.DataFrame(),
        groups_df=pd.DataFrame(),
        a07_filter_var=_Var(),
        a07_filter_label_var=_Var(),
        a07_match_filter_var=_Var(),
        a07_filter_widget=_Widget(),
        _diag=lambda _msg: None,
        _schedule_a07_refresh=lambda delay_ms=0, **_kwargs: calls.append(delay_ms),
    )

    page_a07.A07Page._focus_control_code(dummy, "fastloenn")
    page_a07.A07Page._focus_control_code(dummy, "fastloenn")
    page_a07.A07Page._focus_control_code(dummy, "fastloenn")

    assert calls == [1, 1]

def test_sync_control_account_selection_selects_account_when_present() -> None:
    class DummyTree:
        def __init__(self) -> None:
            self.selected = None
            self.focused = None
            self.seen = None

        def get_children(self) -> tuple[str, ...]:
            return ("5000", "5001")

        def selection_set(self, value: str) -> None:
            self.selected = value

        def focus(self, value: str) -> None:
            self.focused = value

        def see(self, value: str) -> None:
            self.seen = value

    dummy = type("DummyPage", (), {})()
    dummy.tree_control_accounts = DummyTree()

    page_a07.A07Page._sync_control_account_selection(dummy, "5001")

    assert dummy.tree_control_accounts.selected == "5001"
    assert dummy.tree_control_accounts.focused == "5001"
    assert dummy.tree_control_accounts.seen == "5001"

def test_focus_mapping_account_clears_control_gl_filters_when_account_is_hidden() -> None:
    refresh_calls: list[str] = []

    class DummyVar:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

        def set(self, value) -> None:
            self.value = value

    class DummyTree:
        def __init__(self, children=()) -> None:
            self._children = tuple(children)
            self.selected = None
            self.focused = None
            self.seen = None

        def get_children(self):
            return self._children

        def selection_set(self, value: str) -> None:
            self.selected = value

        def focus(self, value: str) -> None:
            self.focused = value

        def see(self, value: str) -> None:
            self.seen = value

    class DummyPage:
        def __init__(self) -> None:
            self.tree_mapping = DummyTree()
            self.tree_control_gl = DummyTree(children=("5000",))
            self.tree_control_accounts = DummyTree(children=("5001",))
            self.control_gl_unmapped_only_var = DummyVar(True)
            self.control_gl_filter_var = DummyVar("bonus")

        def _refresh_control_gl_tree(self) -> None:
            refresh_calls.append("refresh")
            self.tree_control_gl._children = ("5000", "5001")

        def _sync_control_account_selection(self, konto: str) -> None:
            page_a07.A07Page._sync_control_account_selection(self, konto)

    dummy = DummyPage()

    page_a07.A07Page._focus_mapping_account(dummy, "5001")

    assert refresh_calls == ["refresh"]
    assert dummy.control_gl_unmapped_only_var.get() is False
    assert dummy.control_gl_filter_var.get() == ""
    assert dummy.tree_control_gl.selected == "5001"
    assert dummy.tree_control_accounts.selected == "5001"

def test_clear_control_gl_selection_tolerates_empty_tree_selection() -> None:
    class DummyTree:
        def __init__(self) -> None:
            self.removed = None
            self.focused = None

        def selection(self):
            return ("5000",)

        def selection_remove(self, value) -> None:
            self.removed = value

        def focus(self, value: str) -> None:
            self.focused = value

    dummy = SimpleNamespace(tree_control_gl=DummyTree())

    page_a07.A07Page._clear_control_gl_selection(dummy)

    assert dummy.tree_control_gl.removed == ("5000",)
    assert dummy.tree_control_gl.focused == ""

def test_current_drag_accounts_prefers_control_drag_accounts() -> None:
    dummy = SimpleNamespace(
        _drag_control_accounts=["5000", "5001"],
        _drag_unmapped_account="6990",
    )

    out = page_a07.A07Page._current_drag_accounts(dummy)

    assert out == ["5000", "5001"]

def test_current_drag_accounts_falls_back_to_unmapped_drag_account() -> None:
    dummy = SimpleNamespace(
        _drag_control_accounts=[],
        _drag_unmapped_account="6990",
    )

    out = page_a07.A07Page._current_drag_accounts(dummy)

    assert out == ["6990"]

def test_selected_suggestion_row_prefers_control_support_notebook() -> None:
    tab_suggestions = object()
    tree_control = object()

    class _Notebook:
        def select(self) -> str:
            return "suggestions"

        def nametowidget(self, name: str) -> object:
            assert name == "suggestions"
            return tab_suggestions

    def _row_from_tree(tree: object):
        if tree is tree_control:
            return {"Kode": "bonus"}
        return None

    dummy = SimpleNamespace(
        control_support_nb=_Notebook(),
        tab_suggestions=tab_suggestions,
        tree_control_suggestions=tree_control,
        focus_get=lambda: None,
        _selected_suggestion_row_from_tree=_row_from_tree,
    )

    out = page_a07.A07Page._selected_suggestion_row(dummy)

    assert out == {"Kode": "bonus"}

def test_on_control_selection_changed_skips_hidden_detail_refresh() -> None:
    calls: list[str] = []
    workspace = SimpleNamespace(selected_code=None)
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        workspace=workspace,
        _selected_control_code=lambda: "70",
        _update_history_details_from_selection=lambda: calls.append("history"),
        _support_views_ready=False,
        _active_support_tab_key=lambda: "history",
        _refresh_suggestions_tree=lambda: calls.append("support_suggestions"),
        _control_details_visible=False,
        _refresh_control_support_trees=lambda: calls.append("detail_support"),
        _retag_control_gl_tree=lambda: False,
        _refresh_control_gl_tree=lambda: calls.append("gl"),
        _update_control_panel=lambda: calls.append("panel"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
    )

    page_a07.A07Page._on_control_selection_changed(dummy)

    assert workspace.selected_code == "70"
    assert "detail_support" not in calls
    assert calls == ["history", "panel", "buttons"]

def test_on_control_gl_selection_changed_skips_code_sync_while_refresh_runs() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _refresh_in_progress=True,
        control_gl_df=pd.DataFrame([{"Konto": "5000", "Kode": "70"}]),
        _selected_control_gl_account=lambda: "5000",
        _sync_control_account_selection=lambda konto: calls.append(f"sync:{konto}"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
    )

    page_a07.A07Page._on_control_gl_selection_changed(dummy)

    assert calls == ["sync:5000", "buttons"]

def test_on_control_gl_selection_changed_keeps_selected_work_code() -> None:
    calls: list[str] = []
    status_calls: list[str] = []
    focus_calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _refresh_in_progress=False,
        control_gl_df=pd.DataFrame([{"Konto": "5000", "Kode": "fastloenn"}]),
        _selected_control_gl_accounts=lambda: ["5000"],
        _selected_control_gl_account=lambda: "5000",
        _sync_control_account_selection=lambda konto: calls.append(f"sync:{konto}"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _selected_control_code=lambda: "feriepenger",
        _focus_control_code=lambda code: focus_calls.append(code),
        status_var=SimpleNamespace(set=lambda value: status_calls.append(value)),
    )

    page_a07.A07Page._on_control_gl_selection_changed(dummy)

    assert calls == ["sync:5000", "buttons"]
    assert focus_calls == []
    assert status_calls == ["Konto 5000 er koblet til fastloenn. Bruk høyreklikk for å vise koden eller endre kobling."]

def test_on_control_gl_selection_changed_keeps_work_code_for_multi_select() -> None:
    calls: list[str] = []
    status_calls: list[str] = []
    focus_calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _refresh_in_progress=False,
        control_gl_df=pd.DataFrame(
            [
                {"Konto": "5000", "Kode": "fastloenn"},
                {"Konto": "5001", "Kode": "fastloenn"},
            ]
        ),
        _selected_control_gl_accounts=lambda: ["5000", "5001"],
        _selected_control_gl_account=lambda: "5000",
        _sync_control_account_selection=lambda konto: calls.append(f"sync:{konto}"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _selected_control_code=lambda: "feriepenger",
        _focus_control_code=lambda code: focus_calls.append(code),
        status_var=SimpleNamespace(set=lambda value: status_calls.append(value)),
    )

    page_a07.A07Page._on_control_gl_selection_changed(dummy)

    assert calls == ["sync:5000", "buttons"]
    assert focus_calls == []
    assert status_calls == ["2 kontoer er valgt og er koblet til fastloenn."]

def test_on_control_gl_selection_changed_prefers_amount_summary_when_available() -> None:
    calls: list[str] = []
    status_calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _refresh_in_progress=False,
        control_gl_df=pd.DataFrame(
            [
                {"Konto": "5000", "Kode": "fastloenn", "IB": 0.0, "Endring": 100.0, "UB": 100.0},
                {"Konto": "5001", "Kode": "fastloenn", "IB": 0.0, "Endring": 25.0, "UB": 25.0},
            ]
        ),
        _selected_control_gl_accounts=lambda: ["5000", "5001"],
        _selected_control_gl_account=lambda: "5000",
        _sync_control_account_selection=lambda konto: calls.append(f"sync:{konto}"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        status_var=SimpleNamespace(set=lambda value: status_calls.append(value)),
    )

    page_a07.A07Page._on_control_gl_selection_changed(dummy)

    assert calls == ["sync:5000", "buttons"]
    assert status_calls == ["2 kontoer valgt | IB: 0,00 | Endring: 125,00 | UB: 125,00"]

def test_on_control_selection_changed_prefers_retagging_gl_tree() -> None:
    calls: list[str] = []
    workspace = SimpleNamespace(selected_code=None)
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        workspace=workspace,
        _selected_control_code=lambda: "70",
        _update_history_details_from_selection=lambda: calls.append("history"),
        _support_views_ready=False,
        _active_support_tab_key=lambda: "history",
        _refresh_suggestions_tree=lambda: calls.append("support_suggestions"),
        _control_details_visible=False,
        _refresh_control_support_trees=lambda: calls.append("detail_support"),
        _retag_control_gl_tree=lambda: True,
        _refresh_control_gl_tree=lambda: calls.append("gl"),
        _update_control_panel=lambda: calls.append("panel"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
    )

    page_a07.A07Page._on_control_selection_changed(dummy)

    assert workspace.selected_code == "70"
    assert calls == ["history", "panel", "buttons"]

def test_on_suggestion_selected_prefers_retagging_gl_tree() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _update_selected_suggestion_details=lambda: calls.append("details"),
        _retag_control_gl_tree=lambda: True,
        _refresh_control_gl_tree=lambda: calls.append("gl"),
        tree_control_suggestions=None,
        _update_history_details_from_selection=lambda: calls.append("history"),
    )

    page_a07.A07Page._on_suggestion_selected(dummy)

    assert calls == ["details", "history"]

def test_on_suggestion_selected_does_not_require_missing_highlight_helper() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _update_selected_suggestion_details=lambda: calls.append("details"),
        _retag_control_gl_tree=lambda: True,
        _refresh_control_gl_tree=lambda: calls.append("gl"),
        tree_control_suggestions=object(),
        tree_a07=object(),
        a07_overview_df=pd.DataFrame(),
        workspace=SimpleNamespace(gl_df=pd.DataFrame(), basis_col="Endring"),
        _selected_code_from_tree=lambda _tree: "fastloenn",
        _selected_suggestion_row_from_tree=lambda _tree: pd.Series({"Kode": "fastloenn", "WithinTolerance": True}),
        _ensure_suggestion_display_fields=lambda: pd.DataFrame([{"Kode": "fastloenn", "WithinTolerance": True}]),
        control_suggestion_summary_var=SimpleNamespace(set=lambda _value: calls.append("summary")),
        control_suggestion_effect_var=SimpleNamespace(set=lambda _value: calls.append("effect")),
        _effective_mapping=lambda: {"5000": "fastloenn"},
        _effective_previous_mapping=lambda: {},
        _update_history_details_from_selection=lambda: calls.append("history"),
    )

    page_a07.A07Page._on_suggestion_selected(dummy)

    assert calls == ["details", "summary", "effect", "history"]

def test_on_control_selection_changed_keeps_manual_support_tab_when_details_are_visible() -> None:
    calls: list[str] = []
    workspace = SimpleNamespace(selected_code=None)
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        workspace=workspace,
        _selected_control_code=lambda: "70",
        _update_history_details_from_selection=lambda: calls.append("history"),
        _refresh_in_progress=False,
        _control_details_visible=True,
        _preferred_support_tab_for_selected_code=lambda: "history",
        _select_support_tab_key=lambda key, force_render=False: calls.append(f"tab:{key}:{force_render}"),
        _update_control_panel=lambda: calls.append("panel"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _schedule_control_selection_followup=lambda: calls.append("followup"),
    )

    page_a07.A07Page._on_control_selection_changed(dummy)

    assert workspace.selected_code == "70"
    assert calls == ["history", "panel", "buttons", "followup"]

def test_session_context_falls_back_to_dataset_store_when_session_is_missing() -> None:
    session_obj = SimpleNamespace(client=None, year=None)
    store_section = SimpleNamespace(
        client_var=SimpleNamespace(get=lambda: "Air Management AS"),
        year_var=SimpleNamespace(get=lambda: "2025"),
    )
    host = SimpleNamespace(page_dataset=SimpleNamespace(dp=SimpleNamespace(_store_section=store_section)))
    dummy = SimpleNamespace(winfo_toplevel=lambda: host)

    out = page_a07.A07Page._session_context(dummy, session_obj)

    assert out == ("Air Management AS", "2025")


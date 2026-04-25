from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_poll_support_refresh_clears_state_for_stale_generation() -> None:
    dummy = SimpleNamespace(
        _refresh_generation=3,
        _support_refresh_thread="thread",
        _support_refresh_result={"token": 2},
        _support_views_ready=True,
    )

    page_a07.A07Page._poll_support_refresh(dummy, 2)

    assert dummy._support_refresh_thread is None
    assert dummy._support_refresh_result is None
    assert dummy._support_views_ready is False

def test_refresh_support_views_renders_current_tab_when_payload_is_ready() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _control_details_visible=True,
        _support_views_ready=True,
        _support_views_dirty=False,
        _refresh_in_progress=False,
        _support_refresh_thread=None,
        _render_active_support_tab=lambda: calls.append("render"),
        _schedule_support_refresh=lambda: calls.append("schedule"),
        _start_support_refresh=lambda: calls.append("start"),
    )

    page_a07.A07Page._refresh_support_views(dummy)

    assert calls == ["render"]

def test_refresh_support_views_skips_when_details_are_hidden() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _control_details_visible=False,
        _pending_support_refresh=True,
        _support_views_ready=False,
        _support_views_dirty=True,
        _refresh_in_progress=False,
        _support_refresh_thread=None,
        _render_active_support_tab=lambda: calls.append("render"),
        _schedule_support_refresh=lambda: calls.append("schedule"),
        _start_support_refresh=lambda: calls.append("start"),
    )

    page_a07.A07Page._refresh_support_views(dummy)

    assert calls == []
    assert dummy._pending_support_refresh is False

def test_refresh_support_views_requests_support_when_details_are_visible() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _control_details_visible=True,
        _support_requested=False,
        _pending_support_refresh=True,
        _support_views_ready=False,
        _support_views_dirty=True,
        _refresh_in_progress=False,
        _support_refresh_thread=None,
        _render_active_support_tab=lambda: calls.append("render"),
        _schedule_support_refresh=lambda: calls.append("schedule"),
        _start_support_refresh=lambda: calls.append("start"),
    )

    page_a07.A07Page._refresh_support_views(dummy)

    assert calls == ["start"]
    assert dummy._support_requested is True
    assert dummy._pending_support_refresh is False

def test_schedule_active_support_render_replaces_pending_job() -> None:
    calls: list[tuple[str, object]] = []
    callbacks: list[object] = []

    class DummyPage:
        _control_details_visible = True
        _support_render_job = "old-job"

        def _cancel_scheduled_job(self, attr_name):
            calls.append(("cancel", attr_name))
            setattr(self, attr_name, None)

        def after(self, delay_ms, callback):
            calls.append(("after", delay_ms))
            callbacks.append(callback)
            return f"job-{len(callbacks)}"

        def _render_active_support_tab(self, *, force=False):
            calls.append(("render", force))

    dummy = DummyPage()

    page_a07.A07Page._schedule_active_support_render(dummy, force=True)
    page_a07.A07Page._schedule_active_support_render(dummy, force=False)

    assert calls[:4] == [
        ("cancel", "_support_render_job"),
        ("after", 45),
        ("cancel", "_support_render_job"),
        ("after", 45),
    ]
    assert dummy._support_render_job == "job-2"
    callbacks[-1]()
    assert calls[-1] == ("render", False)

def test_render_active_support_tab_uses_context_key_not_tab_only() -> None:
    calls: list[str] = []
    context = {"value": ("mapping", "rf1022", "100_refusjon", "", "alle", "")}
    dummy = SimpleNamespace(
        _control_details_visible=True,
        _loaded_support_tabs={"mapping"},
        _loaded_support_context_keys={"mapping": ("mapping", "rf1022", "100_loenn_ol", "", "alle", "")},
        _active_support_tab_key=lambda: "mapping",
        _support_tab_context_key=lambda tab_key=None: context["value"],
        _refresh_groups_tree=lambda: calls.append("groups"),
        _refresh_control_support_trees=lambda: calls.append("support"),
    )

    page_a07.A07Page._render_active_support_tab(dummy)

    assert calls == ["groups", "support"]
    assert dummy._loaded_support_context_keys["mapping"] == context["value"]

    calls.clear()
    page_a07.A07Page._render_active_support_tab(dummy)

    assert calls == ["groups"]

def test_active_support_tab_key_defaults_to_both_without_notebook() -> None:
    dummy = SimpleNamespace(
        _control_details_visible=True,
        control_support_nb=None,
    )

    assert page_a07.A07Page._active_support_tab_key(dummy) == "both"

def test_refresh_control_support_trees_renders_suggestions_and_links_for_fixed_workspace() -> None:
    calls: list[object] = []

    class _Var:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

    class _AccountsTree:
        def selection(self):
            return ()

        def get_children(self):
            return ()

    dummy = SimpleNamespace(
        _active_support_tab_key=lambda: "both",
        _selected_control_work_level=lambda: "a07",
        _selected_rf1022_group=lambda: "",
        _selected_control_code=lambda: "fastloenn",
        _refresh_suggestions_tree=lambda: calls.append("suggestions"),
        _set_control_accounts_mode=lambda mode: calls.append(("mode", mode)),
        tree_control_accounts=_AccountsTree(),
        control_gl_df=pd.DataFrame([{"Konto": "5000", "Kode": "fastloenn"}]),
        control_selected_accounts_df=pd.DataFrame(),
        control_accounts_summary_var=_Var(),
        _filter_visible_mapping_accounts_df=lambda df: df.reset_index(drop=True),
        _control_accounts_summary_text=lambda df, label: f"{label}:{len(df.index)}",
        _update_mapping_review_buttons=lambda: calls.append("review-buttons"),
        _fill_tree=lambda *args, **kwargs: calls.append(("fill", int(len(args[1].index)))),
        tree_mapping=None,
        _selected_control_gl_account=lambda: None,
        _update_a07_action_button_state=lambda: calls.append("actions"),
    )

    page_a07.A07Page._refresh_control_support_trees(dummy)

    assert calls[:2] == [("mode", "mapping"), "suggestions"]
    assert ("fill", 1) in calls
    assert dummy.control_accounts_summary_var.value == "fastloenn:1"

def test_refresh_suggestions_tree_shows_unresolved_rf1022_codes_and_disables_auto() -> None:
    filled: list[pd.DataFrame] = []
    configured: list[tuple[str, ...]] = []
    button_states: dict[str, list[tuple[str, ...]]] = {"best": [], "batch": []}
    button_texts: dict[str, str] = {}

    class _Var:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

    class _Tree:
        def selection(self):
            return ()

    class _Button:
        def __init__(self, key: str) -> None:
            self.key = key

        def configure(self, **kwargs) -> None:
            if "text" in kwargs:
                button_texts[self.key] = kwargs["text"]

        def state(self, values) -> None:
            button_states[self.key].append(tuple(values))

    class _Dummy:
        tree_control_suggestions = _Tree()
        tree_suggestions = None
        control_df = pd.DataFrame(
            [
                {
                    "Kode": "timeloenn",
                    "A07Post": "timeloenn",
                    "A07_Belop": 100.0,
                    "GL_Belop": 0.0,
                    "Diff": 100.0,
                    "Rf1022GroupId": "uavklart_rf1022",
                    "GuidetStatus": "Maa avklares",
                }
            ]
        )
        btn_control_best = _Button("best")
        btn_control_batch_suggestions = _Button("batch")
        control_suggestion_summary_var = _Var()
        control_suggestion_effect_var = _Var()
        suggestion_details_var = _Var()

        def _selected_control_work_level(self):
            return "rf1022"

        def _selected_control_code(self):
            return "timeloenn"

        def _selected_rf1022_group(self):
            return "uavklart_rf1022"

        def _safe_auto_matching_enabled(self):
            return True

        def _refresh_unresolved_rf1022_suggestions(self, group_id):
            return page_a07.A07Page._refresh_unresolved_rf1022_suggestions(self, group_id)

        def _reconfigure_tree_columns(self, _tree, columns):
            configured.append(tuple(column_id for column_id, *_rest in columns))

        def _fill_tree(self, _tree, df, _columns, **_kwargs):
            filled.append(df.copy())

    dummy = _Dummy()

    page_a07.A07Page._refresh_suggestions_tree(dummy)

    assert configured[-1] == ("A07Post", "AgaPliktig", "A07_Belop", "GL_Belop", "Diff")
    assert filled[-1]["Kode"].tolist() == ["timeloenn"]
    assert button_texts == {"best": "Bruk trygg kandidat", "batch": "Kjør trygg auto-matching"}
    assert button_states == {"best": [("disabled",)], "batch": [("disabled",)]}
    assert "Uavklart RF-1022" in dummy.control_suggestion_summary_var.get()

def test_active_support_tab_key_reads_direct_notebook_tab_keys() -> None:
    class _Notebook:
        def __init__(self, selected):
            self.selected_widget = selected

        def select(self):
            return "current"

        def nametowidget(self, _name):
            return self.selected_widget

    mapping_tab = object()
    dummy = SimpleNamespace(
        _control_details_visible=True,
        control_support_nb=_Notebook(mapping_tab),
        tab_suggestions=object(),
        tab_history=object(),
        tab_mapping=mapping_tab,
        tab_control_statement=object(),
        tab_unmapped=object(),
    )

    out = page_a07.A07Page._active_support_tab_key(dummy)

    assert out == "mapping"


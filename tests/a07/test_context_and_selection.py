from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_build_control_suggestion_summary_describes_selected_row() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "bonus", "ForslagKontoer": "5000,5001", "Diff": Decimal("12.50"), "WithinTolerance": True},
            {"Kode": "bonus", "ForslagKontoer": "5090", "Diff": Decimal("100.00"), "WithinTolerance": False},
        ]
    )

    out = page_a07.build_control_suggestion_summary("bonus", suggestions_df, suggestions_df.iloc[1])
    diff_text = page_a07._format_picker_amount(Decimal("100.00"))

    assert out == f"Beste forslag for bonus | 2 kandidat(er) | Nå valgt: 5090 | Må vurderes | Diff {diff_text}"

def test_build_rf1022_statement_df_sorts_rows_by_post_and_uses_selected_basis() -> None:
    control_statement_df = pd.DataFrame(
        [
            {
                "Gruppe": "Skyldig pensjon",
                "Navn": "Skyldig pensjon",
                "Endring": 300.0,
                "A07": 250.0,
                "Diff": 50.0,
                "Status": "Manuell",
                "AntallKontoer": 1,
            },
            {
                "Gruppe": "Skattetrekk",
                "Navn": "Skattetrekk",
                "Endring": 200.0,
                "A07": 200.0,
                "Diff": 0.0,
                "Status": "Ferdig",
                "AntallKontoer": 2,
            },
            {
                "Gruppe": "Skyldig arbeidsgiveravgift",
                "Navn": "Skyldig arbeidsgiveravgift",
                "Endring": 100.0,
                "A07": 90.0,
                "Diff": 10.0,
                "Status": "Manuell",
                "AntallKontoer": 1,
            },
        ]
    )

    out = page_a07.build_rf1022_statement_df(control_statement_df, basis_col="Endring")

    assert out["Post"].tolist() == ["100", "110", "120"]
    assert out["Kontrollgruppe"].tolist() == [
        "Skattetrekk",
        "Skyldig arbeidsgiveravgift",
        "Skyldig pensjon",
    ]
    assert out["GL_Belop"].tolist() == [200.0, 100.0, 300.0]

def test_build_control_selected_account_df_filters_accounts_for_selected_code() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn", "IB": 0.0, "Endring": 1200.0, "UB": 1200.0},
            {"Konto": "5001", "Navn": "Bonus", "IB": 0.0, "Endring": 300.0, "UB": 300.0},
            {"Konto": "6990", "Navn": "Telefon", "IB": 0.0, "Endring": 250.0, "UB": 250.0},
        ]
    )

    out = page_a07.build_control_selected_account_df(
        gl_df,
        {"5000": "fastloenn", "5001": "fastloenn", "6990": "telefon"},
        "fastloenn",
    )

    assert out["Konto"].tolist() == ["5000", "5001"]
    assert out.columns.tolist() == [
        "Konto",
        "Navn",
        "AliasStatus",
        "MappingAuditStatus",
        "MappingAuditReason",
        "IB",
        "Endring",
        "UB",
    ]
    assert out["Endring"].tolist() == [1200.0, 300.0]

def test_build_control_selected_account_df_uses_requested_basis_as_active_amount() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn", "IB": 10.0, "Endring": 1200.0, "UB": 1210.0},
            {"Konto": "5001", "Navn": "Bonus", "IB": 5.0, "Endring": 300.0, "UB": 305.0},
        ]
    )

    out = page_a07.build_control_selected_account_df(
        gl_df,
        {"5000": "fastloenn", "5001": "fastloenn"},
        "fastloenn",
        basis_col="UB",
    )

    assert out["IB"].tolist() == [10.0, 5.0]
    assert out["Endring"].tolist() == [1200.0, 300.0]
    assert out["UB"].tolist() == [1210.0, 305.0]

def test_selected_rf1022_group_does_not_leak_stored_group_in_a07_mode() -> None:
    dummy = SimpleNamespace(
        _selected_control_work_level=lambda: "a07",
        _selected_rf1022_group_id="100_loenn_ol",
        workspace=SimpleNamespace(selected_code="fastloenn"),
        control_df=pd.DataFrame([{"Kode": "fastloenn", "Rf1022GroupId": "100_loenn_ol"}]),
    )

    assert page_a07.A07Page._selected_rf1022_group(dummy) is None

def test_apply_control_gl_scope_rf1022_selected_post_uses_group_only() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Kode": "fastloenn", "Rf1022GroupId": "100"},
            {"Konto": "6300", "Kode": "annet", "Rf1022GroupId": "112"},
            {"Konto": "6990", "Kode": "", "Rf1022GroupId": ""},
        ]
    )
    page = _control_gl_scope_page("koblede", work_level="rf1022", group_id="100")

    out = page_a07.A07Page._apply_control_gl_scope(page, control_gl_df, selected_code="fastloenn")

    assert out["Konto"].tolist() == ["5000"]

def test_apply_control_gl_scope_a07_linked_ignores_history_and_suggestion_union() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Kode": "fastloenn", "Rf1022GroupId": "100"},
            {"Konto": "6300", "Kode": "annet", "Rf1022GroupId": "100"},
            {"Konto": "6990", "Kode": "", "Rf1022GroupId": "100"},
        ]
    )
    page = _control_gl_scope_page("relevante", work_level="a07")
    page._selected_control_suggestion_accounts = lambda: ["6300", "6990"]

    out = page_a07.A07Page._apply_control_gl_scope(page, control_gl_df, selected_code="fastloenn")

    assert page_a07.A07Page._selected_control_gl_scope(page) == "koblede"
    assert out["Konto"].tolist() == ["5000"]

def test_apply_control_gl_scope_a07_suggestions_uses_selected_suggestion_accounts_only() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Kode": "fastloenn", "Rf1022GroupId": "100"},
            {"Konto": "6300", "Kode": "annet", "Rf1022GroupId": "112"},
        ]
    )
    page = _control_gl_scope_page("forslag", work_level="a07")
    page._selected_control_suggestion_accounts = lambda: ["6300"]

    out = page_a07.A07Page._apply_control_gl_scope(page, control_gl_df, selected_code="fastloenn")

    assert out["Konto"].tolist() == ["6300"]

def test_sync_control_gl_scope_widget_hides_suggestion_scope_in_rf1022_mode() -> None:
    page = _control_gl_scope_page("forslag", work_level="rf1022", group_id="100")
    page.control_gl_scope_widget = _ScopeWidget("Forslag for valgt A07-kode")

    page_a07.A07Page._sync_control_gl_scope_widget(page)

    assert page.control_gl_scope_var.get() == "alle"
    assert page.control_gl_scope_label_var.get() == "Alle kontoer"
    assert page.control_gl_scope_widget.value == "Alle kontoer"
    assert page.control_gl_scope_widget.config["values"] == ["Alle kontoer", "Valgt RF-1022-post"]

def test_set_control_details_visible_does_not_move_sash_position() -> None:
    sash_calls: list[tuple] = []

    class _Pane:
        def winfo_height(self):
            return 600

        def sashpos(self, *args):
            sash_calls.append(args)
            return 300

    dummy = SimpleNamespace(
        _diag=lambda _message: None,
        control_support_nb=None,
        control_vertical_panes=_Pane(),
        _support_views_ready=False,
        _schedule_support_refresh=lambda: None,
    )

    page_a07.A07Page._set_control_details_visible(dummy, False)
    page_a07.A07Page._set_control_details_visible(dummy, True)

    assert sash_calls == []

def test_selected_code_from_tree_prefers_tree_selection_for_a07_work_code() -> None:
    class DummyTree:
        def focus(self):
            return "sumAvgiftsgrunnlagRefusjon"

        def selection(self):
            return ("feriepenger",)

        def item(self, iid, option):
            if iid == "feriepenger" and option == "values":
                return ("feriepenger", "Feriepenger")
            if iid == "sumAvgiftsgrunnlagRefusjon" and option == "values":
                return ("sumAvgiftsgrunnlagRefusjon", "Sum avgiftsgrunnlag refusjon")
            return ()

    tree = DummyTree()
    dummy = SimpleNamespace(tree_a07=tree)

    out = page_a07.A07Page._selected_code_from_tree(dummy, tree)

    assert out == "feriepenger"

def test_selected_code_from_tree_uses_a07_iid_when_first_column_is_display_label() -> None:
    class DummyTree:
        def focus(self):
            return ""

        def selection(self):
            return ("tilskuddOgPremieTilPensjon",)

        def item(self, iid, option):
            if iid == "tilskuddOgPremieTilPensjon" and option == "values":
                return ("Tilskudd og premie til pensjon (tilskuddOgPremieTilPensjon)", "690 556,00")
            return ()

    tree = DummyTree()
    dummy = SimpleNamespace(tree_a07=tree)

    out = page_a07.A07Page._selected_code_from_tree(dummy, tree)

    assert out == "tilskuddOgPremieTilPensjon"

def test_remove_mapping_accounts_only_removes_selected_existing_accounts() -> None:
    mapping = {"5000": "fastloenn", "5001": "fastloenn", "6990": "telefon"}

    out = page_a07.remove_mapping_accounts(mapping, ["5001", "5001", "8888"])

    assert out == ["5001"]
    assert mapping == {"5000": "fastloenn", "6990": "telefon"}

def test_clear_selected_control_mapping_checks_lock_before_mutating() -> None:
    statuses: list[str] = []
    autosaves: list[str] = []

    class DummyPage:
        tree_control_gl = object()
        workspace = SimpleNamespace(mapping={"5000": "fastloenn"}, locks={"fastloenn"}, membership={})

        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _effective_mapping(self):
            return self.workspace.mapping

        def _notify_locked_conflicts(self, conflicts, **_kwargs):
            statuses.append(",".join(conflicts))
            return True

        def _autosave_mapping(self):
            autosaves.append("save")
            return False

    page = DummyPage()

    page_a07.A07Page._clear_selected_control_mapping(page)

    assert page.workspace.mapping == {"5000": "fastloenn"}
    assert statuses == ["fastloenn"]
    assert autosaves == []

def test_sync_control_work_level_ui_disables_view_filter_in_rf1022_mode() -> None:
    events: list[tuple[str, str]] = []

    class _Widget:
        def configure(self, **kwargs) -> None:
            if "state" in kwargs:
                events.append(("state", kwargs["state"]))
            if "style" in kwargs:
                events.append(("style", kwargs["style"]))

    dummy = SimpleNamespace(
        _selected_control_work_level=lambda: "rf1022",
        a07_filter_widget=_Widget(),
        lbl_control_view_caption=_Widget(),
    )

    page_a07.A07Page._sync_control_work_level_ui(dummy)

    assert ("state", "disabled") in events
    assert ("style", "Muted.TLabel") in events

def test_apply_best_suggestion_for_selected_code_guides_when_missing() -> None:
    focused: list[str] = []
    statuses: list[str] = []

    class DummyTree:
        def focus_set(self) -> None:
            focused.append("a07")

    class DummyPage:
        tree_a07 = DummyTree()
        tree_control_suggestions = object()
        workspace = SimpleNamespace(suggestions=pd.DataFrame())

        def _selected_control_code(self):
            return "fastloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)
            if focus_widget is not None:
                focus_widget.focus_set()

    page_a07.A07Page._apply_best_suggestion_for_selected_code(DummyPage())

    assert statuses == ["Fant ikke et forslag for valgt kode."]
    assert focused == ["a07"]

def test_apply_best_suggestion_for_selected_code_blocks_locked_code() -> None:
    focused: list[str] = []
    statuses: list[str] = []

    class DummyTree:
        def focus_set(self) -> None:
            focused.append("a07")

    class DummyPage:
        tree_a07 = DummyTree()
        workspace = SimpleNamespace(suggestions=pd.DataFrame([{"Kode": "fastloenn", "WithinTolerance": True}]), locks={"fastloenn"})

        def _selected_control_code(self):
            return "fastloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)
            if focus_widget is not None:
                focus_widget.focus_set()

    page_a07.A07Page._apply_best_suggestion_for_selected_code(DummyPage())

    assert statuses == ["Valgt kode er låst. Lås opp før du bruker forslag."]
    assert focused == ["a07"]

def test_selected_group_id_falls_back_to_selected_control_group() -> None:
    class _Tree:
        def selection(self):
            return ()

    dummy = SimpleNamespace(
        tree_groups=_Tree(),
        _selected_control_code=lambda: "A07_GROUP:fastloenn+timeloenn",
    )

    out = page_a07.A07Page._selected_group_id(dummy)

    assert out == "A07_GROUP:fastloenn+timeloenn"

def test_filter_suggestions_df_supports_selected_code_and_unsolved_scope() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "ForslagKontoer": "5000"},
            {"Kode": "bonus", "ForslagKontoer": "5090"},
            {"Kode": "telefon", "ForslagKontoer": "6990"},
        ],
        index=[2, 4, 7],
    )

    selected = page_a07.filter_suggestions_df(
        suggestions_df,
        scope_key="valgt_kode",
        selected_code="bonus",
        unresolved_code_values=["fastloenn", "telefon"],
    )
    unsolved = page_a07.filter_suggestions_df(
        suggestions_df,
        scope_key="uloste",
        selected_code=None,
        unresolved_code_values=["fastloenn", "telefon"],
    )

    assert selected.index.tolist() == [4]
    assert selected["Kode"].tolist() == ["bonus"]
    assert unsolved.index.tolist() == [2, 7]
    assert unsolved["Kode"].tolist() == ["fastloenn", "telefon"]

def test_build_control_accounts_summary_describes_selected_accounts() -> None:
    accounts_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn", "IB": Decimal("0"), "Endring": Decimal("1200"), "UB": Decimal("1200")},
            {"Konto": "5001", "Navn": "Bonus", "IB": Decimal("0"), "Endring": Decimal("300"), "UB": Decimal("300")},
        ]
    )

    out = page_a07.build_control_accounts_summary(accounts_df, "fastloenn")

    assert out == "2 kontoer koblet | Endring 1 500,00 | 5000 Lonn, 5001 Bonus"

def test_on_rf1022_suggestion_selected_enables_candidate_button_only_for_apply_plan() -> None:
    button_states: list[tuple[str, ...]] = []

    class _Button:
        def state(self, values):
            button_states.append(tuple(values))

    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _is_tree_selection_suppressed=lambda _tree: False,
        _selected_control_work_level=lambda: "rf1022",
        tree_control_suggestions=object(),
        btn_control_best=_Button(),
        _selected_suggestion_row_from_tree=lambda _tree: pd.Series(
            {
                "Konto": "5000",
                "Kode": "fastloenn",
                "Forslagsstatus": "Må vurderes",
            }
        ),
        _build_global_auto_mapping_plan=lambda _df: pd.DataFrame(
            [{"Konto": "5000", "Kode": "fastloenn", "Action": "review"}]
        ),
        suggestion_details_var=SimpleNamespace(set=lambda _value: None),
        control_suggestion_effect_var=SimpleNamespace(set=lambda _value: None),
    )

    page_a07.A07Page._on_suggestion_selected(dummy)

    assert button_states == [("disabled",)]
    button_states.clear()
    dummy._build_global_auto_mapping_plan = lambda _df: pd.DataFrame(
        [{"Konto": "5000", "Kode": "fastloenn", "Action": "apply"}]
    )

    page_a07.A07Page._on_suggestion_selected(dummy)

    assert button_states == [("!disabled",)]

def test_selected_control_statement_group_follows_rf1022_or_selected_a07_row() -> None:
    dummy = SimpleNamespace(
        _selected_control_work_level=lambda: "rf1022",
        _selected_rf1022_group=lambda: "100_loenn_ol",
        tree_control_statement=SimpleNamespace(selection=lambda: ()),
    )

    assert page_a07.A07Page._selected_control_statement_group(dummy) == "100_loenn_ol"

    dummy = SimpleNamespace(
        _selected_control_work_level=lambda: "a07",
        _selected_control_row=lambda: pd.Series({"Rf1022GroupId": "112_pensjon"}),
        tree_control_statement=SimpleNamespace(selection=lambda: ()),
    )

    assert page_a07.A07Page._selected_control_statement_group(dummy) == "112_pensjon"

def test_selected_control_alternative_mode_falls_back_to_var_without_widget() -> None:
    dummy = SimpleNamespace(
        control_alternative_mode_var=SimpleNamespace(get=lambda: "history"),
    )

    out = page_a07.A07Page._selected_control_alternative_mode(dummy)

    assert out == "history"

def test_select_support_tab_key_routes_groups_to_side_panel_without_notebook_select() -> None:
    calls: list[str] = []

    class _GroupsTree:
        def focus_set(self) -> None:
            calls.append("focus_groups")

    class _Notebook:
        def select(self, _target) -> None:
            calls.append("select_notebook")

    dummy = SimpleNamespace(
        control_support_nb=_Notebook(),
        tree_groups=_GroupsTree(),
        _refresh_groups_tree=lambda: calls.append("refresh_groups"),
        _sync_groups_panel_visibility=lambda: calls.append("sync_groups"),
    )

    page_a07.A07Page._select_support_tab_key(dummy, "groups")

    assert calls == ["focus_groups", "refresh_groups", "sync_groups"]

def test_select_support_tab_key_opens_group_popup_without_support_notebook() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        control_support_nb=None,
        _open_groups_popup=lambda: calls.append("popup"),
    )

    page_a07.A07Page._select_support_tab_key(dummy, "groups")

    assert calls == ["popup"]

def test_select_support_tab_key_routes_legacy_tabs_to_visible_mapping_tab() -> None:
    calls: list[object] = []

    class _Notebook:
        def select(self, target) -> None:
            calls.append(target)

    mapping_tab = object()
    dummy = SimpleNamespace(
        control_support_nb=_Notebook(),
        tab_mapping=mapping_tab,
        _support_views_ready=False,
        _schedule_support_refresh=lambda: calls.append("refresh"),
    )

    page_a07.A07Page._select_support_tab_key(dummy, "reconcile")

    assert calls == [mapping_tab, "refresh"]

def test_sync_support_notebook_tabs_hides_advanced_tabs_by_default() -> None:
    calls: list[tuple[object, str]] = []

    class _Notebook:
        def tab(self, tab, **kwargs):
            for key, value in kwargs.items():
                calls.append((tab, f"{key}:{value}"))

        def select(self, target):
            calls.append((target, "select"))

    history_tab = object()
    unmapped_tab = object()
    mapping_tab = object()
    suggestions_tab = object()
    dummy = SimpleNamespace(
        control_support_nb=_Notebook(),
        _control_advanced_visible=False,
        tab_suggestions=suggestions_tab,
        tab_history=history_tab,
        tab_unmapped=unmapped_tab,
        tab_mapping=mapping_tab,
        _active_support_tab_key=lambda: "history",
    )

    page_a07.A07Page._sync_support_notebook_tabs(dummy)

    assert (suggestions_tab, "text:Forslag") in calls
    assert (mapping_tab, "text:Koblinger") in calls
    assert (suggestions_tab, "select") in calls
    assert not any(call[0] in {history_tab, unmapped_tab} for call in calls)

def test_sync_support_notebook_tabs_updates_labels_for_rf1022_mode() -> None:
    tab_calls: list[tuple[object, str, str]] = []

    class _Notebook:
        def tab(self, tab, **kwargs):
            for key, value in kwargs.items():
                tab_calls.append((tab, key, value))

    suggestions_tab = object()
    mapping_tab = object()
    control_tab = object()
    dummy = SimpleNamespace(
        control_support_nb=_Notebook(),
        _control_advanced_visible=False,
        _selected_control_work_level=lambda: "rf1022",
        tab_suggestions=suggestions_tab,
        tab_mapping=mapping_tab,
        tab_control_statement=control_tab,
        tab_history=None,
        tab_unmapped=None,
        _active_support_tab_key=lambda: "suggestions",
    )

    page_a07.A07Page._sync_support_notebook_tabs(dummy)

    assert (suggestions_tab, "text", "Forslag") in tab_calls
    assert (mapping_tab, "text", "Koblinger") in tab_calls
    assert not any(call[0] is control_tab for call in tab_calls)

def test_control_code_filter_only_schedules_tree_render() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _refresh_in_progress=False,
        _on_control_selection_changed=lambda: None,
        _schedule_a07_refresh=lambda **_kwargs: calls.append("tree"),
        _refresh_core=lambda **_kwargs: calls.append("core"),
    )

    page_a07.A07Page._on_control_code_filter_changed(dummy)

    assert calls == ["tree"]

def test_tree_iid_from_event_prefers_identified_row_and_falls_back_to_selection() -> None:
    class DummyTree:
        def __init__(self) -> None:
            self._selection = ("selected_iid",)

        def identify_row(self, y: int) -> str:
            return "row_from_pointer" if y == 10 else ""

        def selection(self) -> tuple[str, ...]:
            return self._selection

    event = type("Event", (), {"y": 10})()
    fallback_event = type("Event", (), {"y": 0})()
    tree = DummyTree()

    assert page_a07.A07Page._tree_iid_from_event(object(), tree, event) == "row_from_pointer"
    assert page_a07.A07Page._tree_iid_from_event(object(), tree, fallback_event) == "selected_iid"
    assert page_a07.A07Page._tree_iid_from_event(object(), tree, None) == "selected_iid"

def test_sync_control_panel_visibility_hides_compact_guided_labels() -> None:
    class _Widget:
        def __init__(self, visible: bool = False) -> None:
            self.visible = visible

        def winfo_manager(self):
            return "pack" if self.visible else ""

        def pack(self, *args, **kwargs) -> None:
            self.visible = True

        def pack_forget(self) -> None:
            self.visible = False

    class _Var:
        def __init__(self, value: str) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

    dummy = SimpleNamespace(
        _compact_control_status=True,
        lbl_control_summary=_Widget(False),
        lbl_control_meta=_Widget(False),
        lbl_control_next=_Widget(True),
        control_summary_var=_Var("Telefon | Har forslag"),
        control_meta_var=_Var("Matching kjort | Forslag 2"),
        control_next_var=_Var("Neste: Bruk forslag."),
        btn_control_smart=_Widget(False),
        control_panel=_Widget(True),
    )

    page_a07.A07Page._sync_control_panel_visibility(dummy)

    assert dummy.lbl_control_summary.visible is False
    assert dummy.lbl_control_meta.visible is False
    assert dummy.lbl_control_next.visible is False
    assert dummy.control_panel.visible is False


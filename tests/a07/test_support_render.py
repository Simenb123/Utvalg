from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_mapping_filter_stays_all_when_visible_filter_is_removed() -> None:
    class _Var:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    dummy = SimpleNamespace(
        _mapping_filter_user_selected=False,
        mapping_filter_widget=None,
        mapping_filter_var=_Var("alle"),
        mapping_filter_label_var=_Var("Alle"),
    )
    dummy._selected_mapping_filter_key = lambda: page_a07.A07Page._selected_mapping_filter_key(dummy)
    dummy._set_mapping_filter_key = lambda key: page_a07.A07Page._set_mapping_filter_key(dummy, key)
    accounts_df = pd.DataFrame(
        [
            {"Konto": "6701", "MappingAuditStatus": "Feil"},
            {"Konto": "5000", "MappingAuditStatus": "Trygg"},
        ]
    )

    page_a07.A07Page._maybe_default_mapping_filter_to_critical(dummy, accounts_df)

    assert dummy.mapping_filter_var.get() == "alle"
    assert dummy.mapping_filter_label_var.get() == "Alle"

def test_focus_next_control_account_problem_cycles_visible_critical_rows() -> None:
    class _Tree:
        def __init__(self):
            self.selection_value = ("6701",)
            self.selected = None
            self.focused = False

        def selection(self):
            return self.selection_value

        def get_children(self):
            return ("6701", "5890", "5000")

        def focus_set(self):
            self.focused = True

    class _Status:
        def __init__(self):
            self.value = ""

        def set(self, value):
            self.value = value

    tree = _Tree()
    status = _Status()
    dummy = SimpleNamespace(
        tree_control_accounts=tree,
        status_var=status,
        control_selected_accounts_df=pd.DataFrame(
            [
                {"Konto": "6701", "MappingAuditStatus": "Feil"},
                {"Konto": "5890", "MappingAuditStatus": "Mistenkelig"},
                {"Konto": "5000", "MappingAuditStatus": "Trygg"},
            ]
        ),
        _set_tree_selection=lambda _tree, target: setattr(tree, "selected", target) or True,
    )

    page_a07.A07Page._focus_next_control_account_problem(dummy)

    assert tree.selected == "5890"
    assert tree.focused is True
    assert status.value == "Neste problem: konto 5890."

def test_canonical_a07_account_lists_use_extended_multiselect() -> None:
    control_source = (Path(__file__).resolve().parents[2] / "a07_feature" / "ui" / "control_layout.py").read_text(
        encoding="utf-8"
    )
    support_source = (Path(__file__).resolve().parents[2] / "a07_feature" / "ui" / "support_layout.py").read_text(
        encoding="utf-8"
    )
    bindings_source = (Path(__file__).resolve().parents[2] / "a07_feature" / "ui" / "bindings.py").read_text(
        encoding="utf-8"
    )

    assert 'self.tree_control_gl.configure(selectmode="extended")' in control_source
    assert 'view_id="control_accounts"' in support_source
    assert 'selectmode="extended"' in support_source
    assert 'self.tree_control_accounts.bind("<<TreeviewSelect>>", lambda _event: self._update_a07_action_button_state())' in bindings_source
    assert 'text="Koble ->"' not in control_source
    assert 'text="<- Fjern"' not in control_source
    assert "self.a07_filter_widget = None" in control_source
    assert "_CONTROL_PRIMARY_VIEW_KEYS" not in control_source
    assert "control_assign_panel" not in control_source
    assert 'self.tree_a07.bind("<Double-1>", a07_double_click)' in bindings_source
    assert 'self.tree_a07.bind("<Return>", lambda _event: self._link_selected_control_rows())' in bindings_source
    assert "register_treeview_selection_summary" in bindings_source
    assert 'columns=("IB", "Endring", "UB")' in control_source
    assert 'row_noun="kontoer"' in control_source
    assert "hide_zero=False" in bindings_source
    assert "A07-utvalg:" not in control_source
    assert "control_gl_scope = ttk.Combobox" not in control_source
    assert 'text="Drag og slipp:"' in control_source
    assert "textvariable=self.control_drag_var" in control_source
    assert '"drop_target": ("FOREST", "TEXT_ON_FOREST")' in control_source

def test_canonical_support_area_uses_fixed_suggestion_and_mapping_panes() -> None:
    canonical_source = (Path(__file__).resolve().parents[2] / "a07_feature" / "ui" / "canonical_layout.py").read_text(
        encoding="utf-8"
    )
    support_source = (Path(__file__).resolve().parents[2] / "a07_feature" / "ui" / "support_layout.py").read_text(
        encoding="utf-8"
    )

    assert 'ttk.LabelFrame(lower_body, text="Forslag"' in canonical_source
    assert 'ttk.LabelFrame(lower_body, text="Koblinger"' in canonical_source
    assert "self.control_support_nb = None" in support_source
    assert "self.control_suggestions_actions = suggestions_actions" in support_source
    assert 'suggestions_actions.pack(fill="x", pady=(0, 4))' in support_source
    assert 'text="Tryllestav: finn 0-diff"' in support_source
    assert 'view_id="history"' in support_source
    assert 'view_id="control_statement_accounts"' in support_source
    assert 'view_id="suggestions"' in support_source
    assert 'view_id="unmapped"' in support_source
    assert "self.tree_control_suggestions = self._build_tree_tab" not in support_source
    assert "self.tree_unmapped = self._build_tree_tab" not in support_source
    assert "control_support_nb.add" not in support_source
    assert "control_statement_top" not in support_source
    assert "control_accounts_top" not in support_source
    assert "control_statement_accounts_top" not in support_source
    assert "RF-1022..." not in support_source
    assert "Åpne vindu" not in support_source
    assert "Visning:" not in support_source
    assert 'text="Vis i GL"' not in support_source
    assert 'text="Fjern valgt"' not in support_source
    assert "suggestions_details" not in support_source
    assert "suggestions_details.pack" not in support_source
    assert "self.tree_control_statement = self._build_tree_tab(self.tab_control_statement" not in support_source
    assert "self.tree_suggestions = None" not in support_source
    assert "self.tree_mapping = None" not in support_source
    assert "self.tab_reconcile = None" not in support_source
    assert "_build_hidden_compat_surfaces" not in support_source
    assert "_build_hidden_compat_surfaces" not in canonical_source
    assert 'text="Konti i kontrolloppstilling"' not in support_source
    assert 'text="Neste problem"' not in support_source


def test_low_risk_a07_trees_use_managed_treeview_pilot() -> None:
    support_source = (Path(__file__).resolve().parents[2] / "a07_feature" / "ui" / "support_layout.py").read_text(
        encoding="utf-8"
    )
    groups_source = (Path(__file__).resolve().parents[2] / "a07_feature" / "ui" / "groups_popup.py").read_text(
        encoding="utf-8"
    )

    assert 'view_id="history"' in support_source
    assert 'view_id="control_accounts"' in support_source
    assert 'view_id="control_statement_accounts"' in support_source
    assert 'view_id="suggestions"' in support_source
    assert 'view_id="unmapped"' in support_source
    assert 'view_id="groups"' in groups_source
    assert "self.tree_control_suggestions = self._build_tree_tab" not in support_source
    assert "self.tree_unmapped = self._build_tree_tab" not in support_source

def test_tools_menu_hides_legacy_rf1022_entries_and_uses_decoded_labels(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str | None, object | None]] = []

        def add_command(self, *, label, command=None) -> None:
            self.items.append(("command", label, command))

        def add_separator(self) -> None:
            self.items.append(("separator", None, None))

        def add_cascade(self, *, label, menu) -> None:
            self.items.append(("cascade", label, menu))

    monkeypatch.setattr(a07_canonical_layout.tk, "Menu", _Menu)
    dummy = SimpleNamespace(
        _open_manual_mapping_clicked=lambda: None,
        _export_clicked=lambda: None,
        _open_saldobalanse_workspace=lambda **_kwargs: None,
        _open_source_overview=lambda: None,
        _open_control_statement_window=lambda: None,
        _sync_active_tb_clicked=lambda: None,
        _load_mapping_clicked=lambda: None,
        _save_mapping_clicked=lambda: None,
        _open_mapping_overview=lambda: None,
        _load_rulebook_clicked=lambda: None,
        _open_a07_rulebook_admin=lambda: None,
    )

    menu = page_a07.A07Page._build_tools_menu(dummy, object())
    labels = [label for kind, label, _payload in menu.items if kind != "separator" and label is not None]

    assert "Åpne saldobalanse" in labels
    assert "Kontrolloppstilling..." in labels
    assert "Kontrollvisning" not in labels
    assert "Lønns- og kontrolloppstilling..." not in labels
    assert not any("Ã" in label or "Ă" in label or "Ĺ" in label or "ř" in label for label in labels)

def test_control_statement_window_hides_rf1022_popup_and_legacy_view_choice() -> None:
    from a07_feature.control import statement_window_ui

    labels = statement_window_ui._control_statement_window_view_labels()
    mode_labels = statement_window_ui._control_statement_window_mode_labels()
    source = (Path(__file__).resolve().parents[2] / "a07_feature" / "control" / "statement_window_ui.py").read_text(
        encoding="utf-8"
    )
    impl_source = (
        Path(__file__).resolve().parents[2] / "src" / "pages" / "a07" / "frontend" / "control_statement_window_ui.py"
    ).read_text(encoding="utf-8")

    assert labels == ["Payroll", "Alle", "Uklassifisert"]
    assert "RF-1022 avstemming" in mode_labels
    assert statement_window_ui._control_statement_window_mode_from_label("RF-1022 avstemming") == "rf1022"
    assert "mode_var = tk.StringVar(value=_STATEMENT_MODE_RF1022)" in impl_source
    assert "build_control_statement_summary_card_strip" in impl_source
    assert "append_rf1022_total_row(raw_overview_df)" in impl_source
    assert '"summary_total": ("FOREST", "TEXT_ON_FOREST")' in impl_source
    assert 'text="RF-1022..."' not in source
    assert "_open_rf1022_window" not in source

def test_primary_a07_toolbar_labels_are_decoded() -> None:
    canonical_source = (Path(__file__).resolve().parents[2] / "a07_feature" / "ui" / "canonical_layout.py").read_text(
        encoding="utf-8"
    )
    control_source = (Path(__file__).resolve().parents[2] / "a07_feature" / "ui" / "control_layout.py").read_text(
        encoding="utf-8"
    )

    assert 'text="Beløpsbasis:"' in canonical_source
    assert 'text="Verktøy"' in canonical_source
    assert 'text="Søk:"' in control_source
    assert "BelÃ" not in canonical_source
    assert "VerktÃ" not in canonical_source
    assert "SÃ" not in control_source

def test_tools_control_statement_view_menu_is_removed_from_page_surface() -> None:
    assert not hasattr(page_a07.A07Page, "_add_control_statement_view_menu")

def test_set_control_statement_view_from_menu_updates_vars_and_refreshes() -> None:
    class _Var:
        def __init__(self, value=None) -> None:
            self.value = value

        def get(self):
            return self.value

        def set(self, value) -> None:
            self.value = value

    calls: list[str] = []
    dummy = SimpleNamespace(
        control_statement_view_var=_Var(),
        control_statement_view_label_var=_Var(),
        control_statement_include_unclassified_var=_Var(False),
        control_statement_view_widget=None,
        _on_control_statement_filter_changed=lambda: calls.append("refresh"),
    )
    dummy._sync_control_statement_view_vars = lambda view: page_a07.A07Page._sync_control_statement_view_vars(dummy, view)

    page_a07.A07Page._set_control_statement_view_from_menu(dummy, page_a07.CONTROL_STATEMENT_VIEW_ALL)

    assert dummy.control_statement_view_var.get() == page_a07.CONTROL_STATEMENT_VIEW_ALL
    assert dummy.control_statement_view_label_var.get() == page_a07._CONTROL_STATEMENT_VIEW_LABELS[page_a07.CONTROL_STATEMENT_VIEW_ALL]
    assert dummy.control_statement_include_unclassified_var.get() is True
    assert calls == ["refresh"]

def test_track_unmapped_drop_target_marks_drop_target_tag_and_clears_previous() -> None:
    class _Tree:
        def __init__(self) -> None:
            self.rows = {
                "100_loenn_ol": ("family_payroll",),
                "111_naturalytelser": ("family_natural",),
            }

        def get_children(self):
            return tuple(self.rows)

        def item(self, iid, option=None, **kwargs):
            if kwargs:
                if "tags" in kwargs:
                    self.rows[iid] = tuple(kwargs["tags"])
                return None
            if option == "tags":
                return self.rows[iid]
            return {"tags": self.rows[iid]}

        def selection_set(self, _iid) -> None:
            return None

        def focus(self, _iid) -> None:
            return None

        def see(self, _iid) -> None:
            return None

    dummy = SimpleNamespace(
        tree_a07=_Tree(),
        _current_drag_accounts=lambda: ["5800"],
        _tree_iid_from_event=lambda _tree, event: getattr(event, "target", None),
        _set_tree_selection=lambda _tree, _iid: True,
        control_drag_var=SimpleNamespace(set=lambda _value: None),
        lbl_control_drag=SimpleNamespace(configure=lambda **_kwargs: None),
        _control_drop_target_iid=None,
        _drag_feedback_message=lambda **_kwargs: ("", "Ready.TLabel"),
        _set_control_drag_feedback=lambda _message, *, style: None,
        _update_control_drag_visuals=lambda *_args, **_kwargs: None,
        _teardown_control_drag_visuals=lambda: None,
        _restore_control_drag_hint=lambda: None,
    )
    dummy._set_control_drop_target = lambda iid: page_a07.A07Page._set_control_drop_target(dummy, iid)
    dummy._clear_control_drop_target = lambda: page_a07.A07Page._clear_control_drop_target(dummy)

    page_a07.A07Page._track_unmapped_drop_target(dummy, SimpleNamespace(target="100_loenn_ol"))
    assert dummy.tree_a07.rows["100_loenn_ol"] == ("family_payroll", "drop_target")

    page_a07.A07Page._track_unmapped_drop_target(dummy, SimpleNamespace(target="111_naturalytelser"))
    assert dummy.tree_a07.rows["100_loenn_ol"] == ("family_payroll",)
    assert dummy.tree_a07.rows["111_naturalytelser"] == ("family_natural", "drop_target")

    page_a07.A07Page._clear_control_drag_state(dummy)
    assert dummy.tree_a07.rows["111_naturalytelser"] == ("family_natural",)

def test_track_unmapped_drop_target_updates_selection_and_hint() -> None:
    class DummyVar:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

    class DummyLabel:
        def __init__(self) -> None:
            self.style = None

        def configure(self, **kwargs) -> None:
            self.style = kwargs.get("style")

    class DummyTree:
        def __init__(self) -> None:
            self.selected = None
            self.focused = None
            self.seen = None

        def selection_set(self, value: str) -> None:
            self.selected = value

        def focus(self, value: str) -> None:
            self.focused = value

        def see(self, value: str) -> None:
            self.seen = value

    dummy = type("DummyPage", (), {})()
    dummy._drag_unmapped_account = "1000"
    dummy._drag_control_accounts = []
    dummy.tree_a07 = DummyTree()
    dummy.control_drag_var = DummyVar()
    dummy.lbl_control_drag = DummyLabel()
    dummy._tree_iid_from_event = lambda tree, event=None: "fastloenn"
    dummy._drag_feedback_message = lambda **_kwargs: ("Slipp naa: konto 1000 -> fastloenn.", "Ready.TLabel")
    dummy._set_control_drag_feedback = (
        lambda message, *, style: page_a07.A07Page._set_control_drag_feedback(dummy, message, style=style)
    )
    dummy._update_control_drag_visuals = lambda *_args, **_kwargs: None

    page_a07.A07Page._track_unmapped_drop_target(dummy, object())

    assert dummy.tree_a07.selected == "fastloenn"
    assert dummy.tree_a07.focused == "fastloenn"
    assert dummy.tree_a07.seen == "fastloenn"
    assert dummy.control_drag_var.value == "Slipp naa: konto 1000 -> fastloenn."
    assert dummy.lbl_control_drag.style == "Ready.TLabel"

def test_control_smart_button_can_hide_pure_navigation_actions() -> None:
    class _Button:
        def __init__(self) -> None:
            self.visible = True
            self.states: list[tuple[str, ...]] = []
            self.text = ""

        def state(self, values) -> None:
            self.states.append(tuple(values))

        def pack_forget(self) -> None:
            self.visible = False

        def winfo_manager(self):
            return "pack" if self.visible else ""

        def pack(self, *args, **kwargs) -> None:
            self.visible = True

        def configure(self, **kwargs) -> None:
            if "text" in kwargs:
                self.text = kwargs["text"]

    button = _Button()
    dummy = SimpleNamespace(btn_control_smart=button)

    page_a07.A07Page._set_control_smart_button(dummy, visible=False)
    page_a07.A07Page._set_control_smart_button(
        dummy,
        text="Kontroller kobling",
        command=lambda: None,
        enabled=True,
        visible=True,
    )

    assert button.states[0] == ("disabled",)
    assert button.visible is True
    assert button.text == "Kontroller kobling"
    assert button.states[-1] == ("!disabled",)

def test_control_smart_button_stays_hidden_when_removed_from_gui() -> None:
    class _Button:
        def __init__(self) -> None:
            self.visible = True
            self.states: list[tuple[str, ...]] = []

        def state(self, values) -> None:
            self.states.append(tuple(values))

        def pack_forget(self) -> None:
            self.visible = False

        def pack(self, *args, **kwargs) -> None:
            self.visible = True

        def configure(self, **kwargs) -> None:
            raise AssertionError("removed button should not be configured")

    button = _Button()
    dummy = SimpleNamespace(
        _control_smart_button_removed=True,
        _compact_control_status=True,
        btn_control_smart=button,
        control_panel=None,
    )

    page_a07.A07Page._set_control_smart_button(
        dummy,
        text="Apne lonnsklassifisering",
        command=lambda: None,
        enabled=True,
        visible=True,
    )

    assert button.visible is False
    assert button.states == [("disabled",)]

def test_on_support_tab_changed_requests_support_before_loading() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _control_details_visible=True,
        _support_requested=False,
        _support_views_ready=False,
        _diag=lambda _message: None,
        _active_support_tab_key=lambda: "history",
        _render_active_support_tab=lambda: calls.append("render"),
        _schedule_support_refresh=lambda: calls.append("schedule"),
    )

    page_a07.A07Page._on_support_tab_changed(dummy)

    assert dummy._support_requested is True
    assert calls == ["schedule"]


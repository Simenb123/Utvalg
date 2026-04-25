from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_run_selected_control_gl_action_assigns_when_code_is_selected() -> None:
    calls: list[str] = []

    class DummyPage:
        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _selected_control_code(self):
            return "fastloenn"

        def _assign_selected_control_mapping(self):
            calls.append("assign")

        def _open_manual_mapping_clicked(self):
            calls.append("manual")

    page_a07.A07Page._run_selected_control_gl_action(DummyPage())

    assert calls == ["assign"]

def test_link_selected_control_rows_assigns_when_left_and_right_are_selected() -> None:
    calls: list[str] = []

    class DummyPage:
        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _run_selected_control_gl_action(self):
            calls.append("assign-from-linked-lists")

        def _run_selected_control_action(self):
            calls.append("smart-action")

    page_a07.A07Page._link_selected_control_rows(DummyPage())

    assert calls == ["assign-from-linked-lists"]

def test_link_selected_control_rows_keeps_smart_action_when_no_left_account_is_selected() -> None:
    calls: list[str] = []

    class DummyPage:
        def _selected_control_gl_accounts(self):
            return []

        def _run_selected_control_gl_action(self):
            calls.append("assign-from-linked-lists")

        def _run_selected_control_action(self):
            calls.append("smart-action")

    page_a07.A07Page._link_selected_control_rows(DummyPage())

    assert calls == ["smart-action"]

def test_run_selected_control_gl_action_guides_user_without_selected_code() -> None:
    focused: list[str] = []
    statuses: list[str] = []

    class DummyPage:
        class DummyTree:
            def focus_set(self) -> None:
                focused.append("a07")

        tree_a07 = DummyTree()

        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _selected_control_code(self):
            return None

        @property
        def status_var(self):
            return SimpleNamespace(set=lambda value: statuses.append(value))

        def _assign_selected_control_mapping(self):
            raise AssertionError("should not assign without selected code")

    page_a07.A07Page._run_selected_control_gl_action(DummyPage())

    assert focused == ["a07"]
    assert statuses == ["Velg en A07-kode til hoyre for du tildeler kontoer fra GL-listen."]

def test_run_selected_control_gl_action_assigns_to_selected_rf1022_group() -> None:
    calls: list[tuple[str, tuple[str, ...], str]] = []

    class DummyPage:
        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _selected_control_work_level(self):
            return "rf1022"

        def _selected_rf1022_group(self):
            return "100_loenn_ol"

        def _assign_accounts_to_rf1022_group(self, accounts, group_id, *, source_label="RF-1022-mapping"):
            calls.append((source_label, tuple(accounts), group_id))

    page_a07.A07Page._run_selected_control_gl_action(DummyPage())

    assert calls == [("RF-1022-mapping", ("5000",), "100_loenn_ol")]

def test_assign_selected_control_mapping_guides_user_without_gl_selection() -> None:
    focused: list[str] = []
    statuses: list[str] = []

    class DummyTree:
        def focus_set(self) -> None:
            focused.append("gl")

    class DummyPage:
        tree_control_gl = DummyTree()
        tree_a07 = object()

        def _selected_control_gl_accounts(self):
            return []

        def _selected_control_code(self):
            return "fastloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)
            if focus_widget is not None:
                focus_widget.focus_set()

    page_a07.A07Page._assign_selected_control_mapping(DummyPage())

    assert statuses == ["Velg en eller flere GL-kontoer til venstre forst."]
    assert focused == ["gl"]

def test_assign_selected_control_mapping_guides_user_without_selected_code() -> None:
    focused: list[str] = []
    statuses: list[str] = []

    class DummyTree:
        def focus_set(self) -> None:
            focused.append("a07")

    class DummyPage:
        tree_control_gl = object()
        tree_a07 = DummyTree()

        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _selected_control_code(self):
            return None

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)
            if focus_widget is not None:
                focus_widget.focus_set()

    page_a07.A07Page._assign_selected_control_mapping(DummyPage())

    assert statuses == ["Velg en A07-kode til hoyre forst."]
    assert focused == ["a07"]

def test_assign_selected_control_mapping_uses_selected_rf1022_group_when_in_rf_mode() -> None:
    calls: list[tuple[tuple[str, ...], str, str]] = []

    class DummyPage:
        tree_control_gl = object()
        tree_a07 = object()

        def _selected_control_gl_accounts(self):
            return ["5800", "5890"]

        def _selected_control_work_level(self):
            return "rf1022"

        def _selected_rf1022_group(self):
            return "100_refusjon"

        def _assign_accounts_to_rf1022_group(self, accounts, group_id, *, source_label="RF-1022-mapping"):
            calls.append((tuple(accounts), group_id, source_label))

    page_a07.A07Page._assign_selected_control_mapping(DummyPage())

    assert calls == [(("5800", "5890"), "100_refusjon", "RF-1022-mapping")]

def test_a07_code_menu_choices_use_control_queue_before_workspace_fallback() -> None:
    dummy = SimpleNamespace(
        control_df=pd.DataFrame(
            [
                {"Kode": "fastloenn", "Navn": "Fast lonn"},
                {"Kode": "A07_GROUP:demo", "Navn": "Gruppe"},
            ]
        ),
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(
                [
                    {"Kode": "fastloenn", "Navn": "Fast lonn", "Belop": 100.0},
                    {"Kode": "elektroniskKommunikasjon", "Navn": "Elektronisk kommunikasjon", "Belop": 50.0},
                ]
            )
        ),
    )

    out = page_a07.A07Page._a07_code_menu_choices(dummy)

    assert out[0] == ("fastloenn", "fastloenn - Fast lonn")
    assert out[1][0] == "elektroniskKommunikasjon"
    assert all(not code.startswith("A07_GROUP:") for code, _label in out)

def test_assign_selected_accounts_to_a07_code_maps_and_focuses() -> None:
    calls: list[tuple[str, object]] = []
    statuses: list[str] = []

    class DummyPage:
        tree_control_gl = object()
        tree_a07 = object()

        def __init__(self) -> None:
            self.workspace = SimpleNamespace(mapping={}, locks=set(), membership={})
            self.status_var = SimpleNamespace(set=lambda value: statuses.append(value))

        def _selected_control_gl_accounts(self):
            return ["5000", "5001"]

        def _assign_accounts_to_a07_code(self, accounts, code, *, source_label="Mapping"):
            return page_a07.A07Page._assign_accounts_to_a07_code(
                self,
                accounts,
                code,
                source_label=source_label,
            )

        def _autosave_mapping(self):
            return False

        def _refresh_core(self, *, focus_code=None):
            calls.append(("refresh", focus_code))

        def _focus_mapping_account(self, account):
            calls.append(("account", account))

        def _activate_a07_code_for_explicit_account_action(self, code):
            calls.append(("code", code))

        def _select_primary_tab(self):
            calls.append(("tab", "primary"))

    page = DummyPage()

    page_a07.A07Page._assign_selected_accounts_to_a07_code(page, "fastloenn")

    assert page.workspace.mapping == {"5000": "fastloenn", "5001": "fastloenn"}
    assert calls == [
        ("refresh", "fastloenn"),
        ("account", "5000"),
        ("code", "fastloenn"),
        ("tab", "primary"),
    ]
    assert statuses == ["Mapping: tildelte 2 konto(er) til fastloenn."]

def test_drop_unmapped_on_control_assigns_to_rf1022_group_in_rf_mode() -> None:
    calls: list[tuple[tuple[str, ...], str, str]] = []

    class DummyTree:
        def selection_set(self, _iid) -> None:
            return None

        def focus(self, _iid) -> None:
            return None

        def see(self, _iid) -> None:
            return None

    dummy = SimpleNamespace(
        tree_a07=DummyTree(),
        _selected_control_work_level=lambda: "rf1022",
        _current_drag_accounts=lambda: ["5800"],
        _tree_iid_from_event=lambda _tree, _event: "100_refusjon",
        _assign_accounts_to_rf1022_group=lambda accounts, group_id, *, source_label="RF-1022-mapping": calls.append(
            (tuple(accounts), group_id, source_label)
        ),
        _clear_control_drag_state=lambda: calls.append((tuple(), "", "cleared")),
    )

    page_a07.A07Page._drop_unmapped_on_control(dummy, event=None)

    assert calls[0] == (("5800",), "100_refusjon", "Drag-and-drop mot RF-1022")
    assert calls[-1] == (tuple(), "", "cleared")

def test_show_control_gl_context_menu_offers_rf1022_group_submenu(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_command(self, *, label, command=None, state=None) -> None:
            self.items.append(("command", label, state))

        def add_cascade(self, *, label, menu) -> None:
            self.items.append(("cascade", label, menu))

        def add_separator(self) -> None:
            self.items.append(("separator", "", None))

    monkeypatch.setattr(a07_context_menu.tk, "Menu", _Menu)

    dummy = SimpleNamespace(
        tree_control_gl=object(),
        _prepare_tree_context_selection=lambda *args, **kwargs: "acct:5800",
        _selected_control_gl_accounts=lambda: ["5800"],
        _selected_control_code=lambda: "",
        _selected_control_work_level=lambda: "rf1022",
        _selected_rf1022_group=lambda: "100_refusjon",
        _effective_mapping=lambda: {},
        _rf1022_group_menu_choices=lambda: [
            ("100_loenn_ol", "Post 100 Lonn o.l."),
            ("100_refusjon", "Post 100 Refusjon"),
            ("111_naturalytelser", "Post 111 Naturalytelser"),
        ],
        _a07_code_menu_choices=lambda: [
            ("fastloenn", "fastloenn - Fast lonn"),
            ("elektroniskKommunikasjon", "elektroniskKommunikasjon - Elektronisk kommunikasjon"),
        ],
        _assign_selected_control_mapping=lambda: None,
        _assign_selected_accounts_to_rf1022_group=lambda _group_id: None,
        _assign_selected_accounts_to_a07_code=lambda _code: None,
        _clear_selected_control_mapping=lambda: None,
        _focus_linked_code_for_selected_gl_account=lambda: None,
        _set_control_gl_scope=lambda _scope: None,
        _run_selected_control_action=lambda: None,
        _apply_rf1022_candidate_suggestions=lambda: None,
        _all_rf1022_candidate_df=lambda: pd.DataFrame([{"Konto": "5800", "Forslagsstatus": "Trygt forslag"}]),
        _rf1022_candidate_action_counts=lambda _candidates: {"actionable": 1},
        _apply_best_suggestion_for_selected_code=lambda: None,
        _apply_history_for_selected_code=lambda: None,
        _open_manual_mapping_clicked=lambda: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_gl_context_menu(dummy, SimpleNamespace())

    assert menu is not None
    labels = [label for kind, label, _payload in menu.items if kind in {"command", "cascade"}]
    assert "Velg RF-1022-post" in labels
    assert "Velg A07-kode" in labels
    assert any(
        label.startswith("Tildel til Post 100 Refusjon")
        for kind, label, _payload in menu.items
        if kind == "command"
    )
    assert "Vis RF-1022-kandidater" in [label for kind, label, _payload in next(payload for kind, label, payload in menu.items if kind == "cascade" and label == "Avansert").items if kind == "command"]
    assert "Kjør trygg auto-matching" not in labels
    assert "Bruk beste forslag" not in labels
    assert "Bruk historikk" not in labels
    rf_menu = next(payload for kind, label, payload in menu.items if kind == "cascade" and label == "Velg RF-1022-post")
    assert [label for kind, label, _payload in rf_menu.items if kind == "command"] == [
        "Post 100 Lonn o.l.",
        "Post 100 Refusjon",
        "Post 111 Naturalytelser",
    ]
    a07_menu = next(payload for kind, label, payload in menu.items if kind == "cascade" and label == "Velg A07-kode")
    assert [label for kind, label, _payload in a07_menu.items if kind == "command"] == [
        "fastloenn - Fast lonn",
        "elektroniskKommunikasjon - Elektronisk kommunikasjon",
    ]

def test_show_control_gl_context_menu_defaults_to_a07_surface(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_command(self, *, label, command=None, state=None) -> None:
            self.items.append(("command", label, state))

        def add_cascade(self, *, label, menu) -> None:
            self.items.append(("cascade", label, menu))

        def add_separator(self) -> None:
            self.items.append(("separator", "", None))

    monkeypatch.setattr(a07_context_menu.tk, "Menu", _Menu)

    dummy = SimpleNamespace(
        tree_control_gl=object(),
        _prepare_tree_context_selection=lambda *args, **kwargs: "acct:5000",
        _selected_control_gl_accounts=lambda: ["5000"],
        _selected_control_code=lambda: "fastloenn",
        _selected_control_work_level=lambda: "a07",
        _selected_rf1022_group=lambda: None,
        _effective_mapping=lambda: {},
        _rf1022_group_menu_choices=lambda: [("100_loenn_ol", "Post 100 Lonn o.l.")],
        _a07_code_menu_choices=lambda: [
            ("fastloenn", "fastloenn - Fast lonn"),
            ("feriepenger", "feriepenger - Feriepenger"),
        ],
        _assign_selected_control_mapping=lambda: None,
        _assign_selected_accounts_to_rf1022_group=lambda _group_id: None,
        _assign_selected_accounts_to_a07_code=lambda _code: None,
        _clear_selected_control_mapping=lambda: None,
        _focus_linked_code_for_selected_gl_account=lambda: None,
        _set_control_gl_scope=lambda _scope: None,
        _run_selected_control_action=lambda: None,
        _apply_best_suggestion_for_selected_code=lambda: None,
        _apply_history_for_selected_code=lambda: None,
        _open_manual_mapping_clicked=lambda: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_gl_context_menu(dummy, SimpleNamespace())

    labels = [label for kind, label, _payload in menu.items if kind in {"command", "cascade"}]
    assert "Velg RF-1022-post" not in labels
    assert "Velg A07-kode" in labels
    assert any(label.startswith("Tildel til fastloenn") for label in labels)
    assert "Vis RF-1022-kandidater" not in labels
    assert not any("auto-matching" in label for label in labels)

def test_show_control_code_context_menu_uses_rf1022_actions_in_rf_mode(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_command(self, *, label, command=None, state=None) -> None:
            self.items.append(("command", label, state))

        def add_cascade(self, *, label, menu=None, state=None) -> None:
            self.items.append(("cascade", label, menu))

        def add_separator(self) -> None:
            self.items.append(("separator", "", None))

    monkeypatch.setattr(a07_context_menu.tk, "Menu", _Menu)

    dummy = SimpleNamespace(
        tree_a07=object(),
        _prepare_tree_context_selection=lambda *args, **kwargs: "100_refusjon",
        _on_control_selection_changed=lambda: None,
        _selected_control_code=lambda: "sumAvgiftsgrunnlagRefusjon",
        _groupable_selected_control_codes=lambda: [],
        _selected_control_gl_accounts=lambda: ["5800"],
        _effective_mapping=lambda: {"5800": "sumAvgiftsgrunnlagRefusjon"},
        _locked_codes=lambda: set(),
        _selected_control_work_level=lambda: "rf1022",
        _selected_rf1022_group=lambda: "100_refusjon",
        _assign_selected_control_mapping=lambda: None,
        _clear_selected_control_mapping=lambda: None,
        _run_selected_control_action=lambda: None,
        _apply_rf1022_candidate_suggestions=lambda: None,
        _all_rf1022_candidate_df=lambda: pd.DataFrame([{"Konto": "5800", "Forslagsstatus": "Trygt forslag"}]),
        _rf1022_candidate_action_counts=lambda _candidates: {"actionable": 1},
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_code_context_menu(dummy, SimpleNamespace())

    labels = [label for kind, label, _payload in menu.items if kind == "command"]
    assert any(label.startswith("Tildel valgte kontoer til Post 100 Refusjon") for label in labels)
    assert "Fjern mapping fra valgte kontoer (<-)" in labels
    assert "Vis RF-1022-kandidater" in [label for kind, label, _payload in next(payload for kind, label, payload in menu.items if kind == "cascade" and label == "Avansert").items if kind == "command"]
    assert "Kjør trygg auto-matching" not in labels
    assert "Smartmapping for valgt kode" not in labels
    assert "Bruk beste forslag" not in labels
    assert "Bruk historikk" not in labels

def test_show_control_code_context_menu_allows_group_creation_for_multi_a07_selection(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_command(self, *, label, command=None, state=None) -> None:
            self.items.append(("command", label, state))

        def add_cascade(self, *, label, menu=None, state=None) -> None:
            self.items.append(("cascade", label, menu))

        def add_separator(self) -> None:
            self.items.append(("separator", "", None))

    monkeypatch.setattr(a07_context_menu.tk, "Menu", _Menu)

    dummy = SimpleNamespace(
        tree_a07=object(),
        _prepare_tree_context_selection=lambda *args, **kwargs: "fastloenn",
        _on_control_selection_changed=lambda: None,
        _selected_control_code=lambda: "fastloenn",
        _groupable_selected_control_codes=lambda: ["fastloenn", "timeleonn"],
        _selected_control_gl_accounts=lambda: [],
        _effective_mapping=lambda: {},
        _locked_codes=lambda: set(),
        _selected_control_work_level=lambda: "a07",
        _assign_accounts_to_a07_code=lambda *args, **kwargs: None,
        _remove_mapping_accounts_checked=lambda *args, **kwargs: None,
        _run_selected_control_action=lambda: None,
        _apply_best_suggestion_for_selected_code=lambda: None,
        _apply_history_for_selected_code=lambda: None,
        _create_group_from_selection=lambda: None,
        _rename_selected_group=lambda: None,
        _remove_selected_group=lambda: None,
        _unlock_selected_code=lambda: None,
        _lock_selected_code=lambda: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_code_context_menu(dummy, SimpleNamespace())

    group_menu = next(payload for kind, label, payload in menu.items if kind == "cascade" and label == "Gruppe")
    states_by_label = {
        label: payload
        for kind, label, payload in group_menu.items
        if kind == "command"
    }
    assert states_by_label["Opprett A07-gruppe fra valgte koder"] == "normal"

def test_show_control_code_context_menu_offers_add_to_existing_group(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_command(self, *, label, command=None, state=None) -> None:
            self.items.append(("command", label, {"command": command, "state": state}))

        def add_cascade(self, *, label, menu=None, state=None) -> None:
            self.items.append(("cascade", label, {"menu": menu, "state": state}))

        def add_separator(self) -> None:
            self.items.append(("separator", "", None))

    monkeypatch.setattr(a07_context_menu.tk, "Menu", _Menu)
    calls: list[str] = []

    dummy = SimpleNamespace(
        tree_a07=object(),
        _prepare_tree_context_selection=lambda *args, **kwargs: "bonus",
        _on_control_selection_changed=lambda: None,
        _selected_control_code=lambda: "bonus",
        _groupable_selected_control_codes=lambda: ["bonus"],
        _selected_control_gl_accounts=lambda: [],
        _effective_mapping=lambda: {},
        _locked_codes=lambda: set(),
        _selected_control_work_level=lambda: "a07",
        _assign_accounts_to_a07_code=lambda *args, **kwargs: None,
        _remove_mapping_accounts_checked=lambda *args, **kwargs: None,
        _run_selected_control_action=lambda: None,
        _apply_best_suggestion_for_selected_code=lambda: None,
        _apply_history_for_selected_code=lambda: None,
        _create_group_from_selection=lambda: None,
        _a07_group_menu_choices=lambda: [("A07_GROUP:fastloenn+timeloenn", "Fastloenn + Timeloenn (2 koder)")],
        _add_selected_codes_to_group=lambda group_id: calls.append(group_id),
        _rename_selected_group=lambda: None,
        _remove_selected_group=lambda: None,
        _unlock_selected_code=lambda: None,
        _lock_selected_code=lambda: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_code_context_menu(dummy, SimpleNamespace())

    group_menu = next(payload["menu"] for kind, label, payload in menu.items if kind == "cascade" and label == "Gruppe")
    cascade = next(payload for kind, label, payload in group_menu.items if kind == "cascade" and label == "Legg til i eksisterende gruppe")
    assert cascade["state"] == "normal"
    submenu = cascade["menu"]
    command = next(payload["command"] for kind, label, payload in submenu.items if kind == "command" and label.startswith("Fastloenn"))
    command()
    assert calls == ["A07_GROUP:fastloenn+timeloenn"]

def test_control_account_context_menu_keeps_mapping_actions_available(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_command(self, *, label, command=None, state=None) -> None:
            self.items.append(("command", label, state))

        def add_cascade(self, *, label, menu=None, state=None) -> None:
            self.items.append(("cascade", label, menu))

        def add_separator(self) -> None:
            self.items.append(("separator", "", None))

    monkeypatch.setattr(a07_context_menu.tk, "Menu", _Menu)
    dummy = SimpleNamespace(
        tree_control_accounts=object(),
        _prepare_tree_context_selection=lambda *args, **kwargs: "5000",
        _selected_control_account_ids=lambda: ["5000"],
        _focus_selected_control_account_in_gl=lambda: None,
        _remove_selected_control_accounts=lambda: None,
        _append_selected_control_account_names_to_a07_alias=lambda: None,
        _exclude_selected_control_account_names_from_a07_code=lambda: None,
        _remove_selected_control_accounts_and_exclude_alias=lambda: None,
        _open_manual_mapping_clicked=lambda: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_accounts_context_menu(dummy, SimpleNamespace())

    assert [label for kind, label, _payload in menu.items if kind == "command"] == [
        "Vis i GL",
        "Fjern mapping",
    ]
    cascades = [(label, payload) for kind, label, payload in menu.items if kind == "cascade"]
    assert [label for label, _payload in cascades] == ["Lær regel", "Avansert"]
    learn_menu = cascades[0][1]
    assert [label for kind, label, _payload in learn_menu.items if kind == "command"] == [
        "Lær kontonavn som alias for A07-kode",
        "Ekskluder kontonavn fra A07-kode",
        "Fjern mapping og ekskluder kontonavn fra A07-kode",
    ]
    assert [state for kind, _label, state in learn_menu.items if kind == "command"] == [
        "disabled",
        "disabled",
        "disabled",
    ]

def test_control_statement_account_context_menu_keeps_focus_action_available(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_command(self, *, label, command=None, state=None) -> None:
            self.items.append(("command", label, state))

    monkeypatch.setattr(a07_context_menu.tk, "Menu", _Menu)
    dummy = SimpleNamespace(
        tree_control_statement_accounts=object(),
        _prepare_tree_context_selection=lambda *args, **kwargs: "5000",
        _selected_control_statement_account_ids=lambda: ["5000"],
        _focus_selected_control_statement_account_in_gl=lambda: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_statement_accounts_context_menu(dummy, SimpleNamespace())

    assert [label for kind, label, _payload in menu.items if kind == "command"] == ["Vis i GL"]

def test_control_suggestions_context_menu_exposes_core_actions(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_command(self, *, label, command=None, state=None) -> None:
            self.items.append(("command", label, state))

        def add_separator(self) -> None:
            self.items.append(("separator", "", None))

    monkeypatch.setattr(a07_context_menu.tk, "Menu", _Menu)
    tree = object()
    dummy = SimpleNamespace(
        tree_control_suggestions=tree,
        tree_suggestions=object(),
        _prepare_tree_context_selection=lambda *_args, **_kwargs: "0",
        _on_suggestion_selected=lambda: None,
        _selected_suggestion_row_from_tree=lambda _tree: pd.Series({"Kode": "feriepenger", "ForslagKontoer": "5020"}),
        _selected_control_code=lambda: "feriepenger",
        _selected_control_suggestion_accounts=lambda: ["5020"],
        _apply_selected_suggestion=lambda: None,
        _focus_mapping_account=lambda _account: None,
        _focus_control_code=lambda _code: None,
        _open_manual_mapping_clicked=lambda **_kwargs: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_suggestions_context_menu(
        dummy,
        SimpleNamespace(widget=tree),
    )

    assert [label for kind, label, _state in menu.items if kind == "command"] == [
        "Bruk forslag",
        "Vis foreslått konto i GL",
        "Gå til A07-kode",
        "Avansert mapping...",
    ]

def test_bind_canonical_events_registers_right_click_context_menus() -> None:
    class _Tree:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object, object | None]] = []

        def bind(self, sequence, callback, add=None) -> None:
            self.calls.append((sequence, callback, add))

    tree_control_gl = _Tree()
    tree_a07 = _Tree()
    tree_groups = _Tree()

    dummy = SimpleNamespace(
        tree_control_gl=tree_control_gl,
        tree_a07=tree_a07,
        tree_history=_Tree(),
        tree_control_suggestions=_Tree(),
        tree_control_accounts=_Tree(),
        tree_control_statement_accounts=_Tree(),
        tree_unmapped=_Tree(),
        tree_groups=tree_groups,
        _on_control_gl_selection_changed=lambda: None,
        _run_selected_control_gl_action=lambda: None,
        _assign_selected_control_mapping=lambda: None,
        _clear_selected_control_mapping=lambda: None,
        _show_control_gl_context_menu=lambda _event: None,
        _start_control_gl_drag=lambda _event: None,
        _on_control_selection_changed=lambda: None,
        _run_selected_control_action=lambda: None,
        _link_selected_control_rows=lambda: None,
        _show_control_code_context_menu=lambda _event: None,
        _track_unmapped_drop_target=lambda _event: None,
        _drop_unmapped_on_control=lambda _event: None,
        _update_history_details_from_selection=lambda: None,
        _apply_selected_history_mapping=lambda: None,
        _apply_selected_suggestion=lambda: None,
        _on_suggestion_selected=lambda: None,
        _show_control_suggestions_context_menu=lambda _event: None,
        _focus_selected_control_account_in_gl=lambda: None,
        _open_manual_mapping_clicked=lambda: None,
        _remove_selected_control_accounts=lambda: None,
        _show_control_accounts_context_menu=lambda _event: None,
        _focus_selected_control_statement_account_in_gl=lambda: None,
        _show_control_statement_accounts_context_menu=lambda _event: None,
        _start_unmapped_drag=lambda _event: None,
        _map_selected_unmapped=lambda: None,
        _on_group_selection_changed=lambda: None,
        _focus_selected_group_code=lambda: None,
        _show_group_context_menu=lambda _event: None,
    )

    page_a07.A07Page._bind_canonical_events(dummy)

    assert any(sequence == "<Button-3>" for sequence, _callback, _add in tree_control_gl.calls)
    assert any(sequence == "<Button-3>" for sequence, _callback, _add in tree_a07.calls)
    assert any(sequence == "<Return>" for sequence, _callback, _add in tree_a07.calls)
    assert any(sequence == "<Button-3>" for sequence, _callback, _add in dummy.tree_control_suggestions.calls)
    assert any(sequence == "<Button-3>" for sequence, _callback, _add in dummy.tree_control_accounts.calls)
    assert any(sequence == "<Button-3>" for sequence, _callback, _add in dummy.tree_control_statement_accounts.calls)
    assert any(sequence == "<Button-3>" for sequence, _callback, _add in tree_groups.calls)

def test_assign_selected_control_mapping_blocks_when_target_code_is_locked() -> None:
    statuses: list[str] = []
    focused: list[str] = []

    class DummyTree:
        def focus_set(self) -> None:
            focused.append("a07")

    class DummyPage:
        tree_control_gl = object()
        tree_a07 = DummyTree()
        workspace = SimpleNamespace(mapping={}, locks={"fastloenn"})

        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _selected_control_code(self):
            return "fastloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)
            if focus_widget is not None:
                focus_widget.focus_set()

    page_a07.A07Page._assign_selected_control_mapping(DummyPage())

    assert statuses == ["Endringen berorer laaste koder: fastloenn. Laas opp for du endrer mapping."]
    assert focused == ["a07"]

def test_remove_selected_group_blocks_when_group_is_still_used_in_mapping() -> None:
    statuses: list[str] = []
    focused_codes: list[str] = []

    class DummyPage:
        tree_groups = object()
        workspace = SimpleNamespace(
            mapping={"5000": "A07_GROUP:fastloenn+timeloenn"},
            groups={"A07_GROUP:fastloenn+timeloenn": object()},
            locks=set(),
        )

        def _selected_group_id(self):
            return "A07_GROUP:fastloenn+timeloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)

        def _focus_control_code(self, code):
            focused_codes.append(code)

    page_a07.A07Page._remove_selected_group(DummyPage())

    assert statuses == ["Kan ikke oppløse gruppe som fortsatt brukes i mapping (1 konto). Fjern eller flytt mapping først."]
    assert focused_codes == ["A07_GROUP:fastloenn+timeloenn"]

def test_create_group_from_codes_uses_auto_name_without_prompt(monkeypatch) -> None:
    autosaved: list[bool] = []
    refreshes: list[str | None] = []
    focuses: list[str] = []

    class _Var:
        value = ""

        def set(self, value: str) -> None:
            self.value = value

    def _fail_prompt(*args, **kwargs):
        raise AssertionError("group creation should not prompt for name in the fast path")

    monkeypatch.setattr(page_a07.simpledialog, "askstring", _fail_prompt)

    class DummyPage:
        workspace = SimpleNamespace(groups={})
        tree_a07 = object()
        status_var = _Var()

        def _default_group_name(self, codes):
            assert list(codes) == ["trekkLoennForFerie", "fastloenn"]
            return "Trekk i loenn for ferie + Fastloenn"

        def _next_group_id(self, codes):
            assert list(codes) == ["trekkLoennForFerie", "fastloenn"]
            return "A07_GROUP:trekkLoennForFerie+fastloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            raise AssertionError(message)

        def _autosave_workspace_state(self) -> None:
            autosaved.append(True)

        def _refresh_core(self, focus_code=None) -> None:
            refreshes.append(focus_code)

        def _focus_control_code(self, code) -> None:
            focuses.append(code)

    dummy = DummyPage()

    out = page_a07.A07Page._create_group_from_codes(dummy, ["trekkLoennForFerie", "fastloenn"])

    assert out == "A07_GROUP:trekkLoennForFerie+fastloenn"
    assert autosaved == [True]
    assert refreshes == ["A07_GROUP:trekkLoennForFerie+fastloenn"]
    assert focuses == ["A07_GROUP:trekkLoennForFerie+fastloenn"]
    assert dummy.workspace.groups[out].group_name == "Trekk i loenn for ferie + Fastloenn"
    assert dummy.workspace.groups[out].member_codes == ["trekkLoennForFerie", "fastloenn"]
    assert "Trekk i loenn for ferie + Fastloenn" in dummy.status_var.value

def test_add_codes_to_existing_group_updates_id_members_mapping_and_locks() -> None:
    old_group_id = "A07_GROUP:fastloenn+timeloenn"
    new_group_id = "A07_GROUP:fastloenn+timeloenn+bonus"
    autosaved: list[bool] = []
    refreshes: list[str | None] = []
    focuses: list[str] = []

    class _Var:
        value = ""

        def set(self, value: str) -> None:
            self.value = value

    class DummyPage:
        workspace = SimpleNamespace(
            groups={
                old_group_id: page_a07.A07Group(
                    group_id=old_group_id,
                    group_name="Fastloenn + Timeloenn",
                    member_codes=["fastloenn", "timeloenn"],
                )
            },
            mapping={"5000": old_group_id, "5015": "bonus"},
            locks={old_group_id},
            selected_code=old_group_id,
        )
        status_var = _Var()
        tree_a07 = object()

        def _default_group_name(self, codes):
            return " + ".join(codes)

        def _next_group_id(self, codes):
            assert list(codes) == ["fastloenn", "timeloenn", "bonus"]
            return new_group_id

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            raise AssertionError(message)

        def _autosave_workspace_state(self) -> None:
            autosaved.append(True)

        def _refresh_core(self, focus_code=None) -> None:
            refreshes.append(focus_code)

        def _focus_control_code(self, code) -> None:
            focuses.append(code)

    dummy = DummyPage()

    out = page_a07.A07Page._add_codes_to_group(dummy, old_group_id, ["bonus"])

    assert out == new_group_id
    assert old_group_id not in dummy.workspace.groups
    assert dummy.workspace.groups[new_group_id].member_codes == ["fastloenn", "timeloenn", "bonus"]
    assert dummy.workspace.groups[new_group_id].group_id == new_group_id
    assert dummy.workspace.mapping["5000"] == new_group_id
    assert dummy.workspace.mapping["5015"] == "bonus"
    assert dummy.workspace.locks == {new_group_id}
    assert dummy.workspace.selected_code == new_group_id
    assert autosaved == [True]
    assert refreshes == [new_group_id]
    assert focuses == [new_group_id]
    assert "bonus" in dummy.status_var.value

def test_locked_mapping_conflicts_uses_effective_group_mapping_and_membership() -> None:
    dummy = type("DummyPage", (), {})()
    dummy.workspace = SimpleNamespace(
        mapping={"5000": "fastloenn"},
        membership={"fastloenn": "A07_GROUP:lonn"},
        locks={"A07_GROUP:lonn"},
    )

    conflicts = page_a07.A07Page._locked_mapping_conflicts(dummy, ["5000"], target_code="fastloenn")

    assert conflicts == ["A07_GROUP:lonn"]

def test_sync_active_tb_clicked_guides_user_inline_when_no_active_trial_balance() -> None:
    statuses: list[str] = []

    class DummyPage:
        tb_path = None

        def _sync_active_trial_balance(self, *, refresh: bool) -> bool:
            assert refresh is True
            return False

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)

        @property
        def status_var(self):
            return SimpleNamespace(set=lambda value: statuses.append(value))

    page_a07.A07Page._sync_active_tb_clicked(DummyPage())

    assert statuses == [
        "Fant ingen aktiv saldobalanse for valgt klient/aar. Velg eller opprett den via Dataset -> Versjoner."
    ]

def test_update_control_transfer_buttons_enables_assign_in_rf1022_mode_when_group_selected() -> None:
    states: list[tuple[str, tuple[str, ...]]] = []

    class _Button:
        def __init__(self, name: str) -> None:
            self.name = name

        def state(self, values):
            states.append((self.name, tuple(values)))

    dummy = SimpleNamespace(
        btn_control_assign=_Button("assign"),
        btn_control_clear=_Button("clear"),
        _selected_control_work_level=lambda: "rf1022",
        _selected_control_gl_accounts=lambda: ["5000"],
        _selected_rf1022_group=lambda: "100_loenn_ol",
        _selected_control_code=lambda: "fastloenn",
        _effective_mapping=lambda: {"5000": "fastloenn"},
    )

    page_a07.A07Page._update_control_transfer_buttons(dummy)

    assert ("assign", ("!disabled",)) in states
    assert ("clear", ("!disabled",)) in states


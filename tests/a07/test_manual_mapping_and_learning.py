from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_apply_manual_mapping_choice_trims_and_updates_mapping() -> None:
    mapping = {"1920": "annet"}

    konto, kode = page_a07.apply_manual_mapping_choice(mapping, " 5000 ", " fastloenn ")

    assert (konto, kode) == ("5000", "fastloenn")
    assert mapping["5000"] == "fastloenn"

def test_a07_rule_learning_writes_keywords_and_excludes_to_rulebook(monkeypatch, tmp_path) -> None:
    rulebook_path = tmp_path / "global_full_a07_rulebook.json"
    rulebook_path.write_text(
        json.dumps(
            {
                "rules": {
                    "fastloenn": {
                        "keywords": ["Honorar revisjon"],
                        "exclude_keywords": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(a07_rule_learning.classification_config, "resolve_rulebook_path", lambda: rulebook_path)
    monkeypatch.setattr(a07_rule_learning.classification_config, "repo_rulebook_path", lambda: rulebook_path)

    result = a07_rule_learning.append_a07_rule_keyword("fastloenn", "Honorar revisjon", exclude=True)

    saved = json.loads(rulebook_path.read_text(encoding="utf-8"))
    assert result.field == "exclude_keywords"
    assert saved["rules"]["fastloenn"]["label"] == "fastloenn"
    assert saved["rules"]["fastloenn"]["exclude_keywords"] == ["Honorar revisjon"]
    assert "keywords" not in saved["rules"]["fastloenn"]

def test_a07_rule_learning_creates_visible_rule_for_missing_code(monkeypatch, tmp_path) -> None:
    rulebook_path = tmp_path / "global_full_a07_rulebook.json"
    rulebook_path.write_text(json.dumps({"rules": {}}), encoding="utf-8")
    monkeypatch.setattr(a07_rule_learning.classification_config, "resolve_rulebook_path", lambda: rulebook_path)
    monkeypatch.setattr(a07_rule_learning.classification_config, "repo_rulebook_path", lambda: rulebook_path)

    a07_rule_learning.append_a07_rule_keyword("timeloenn", "Honorar juridisk", exclude=True)

    saved = json.loads(rulebook_path.read_text(encoding="utf-8"))
    assert saved["rules"]["timeloenn"]["label"] == "timeloenn"
    assert saved["rules"]["timeloenn"]["exclude_keywords"] == ["Honorar juridisk"]

def test_manual_mapping_defaults_prefers_selected_control_gl_and_control_code() -> None:
    class DummyPage:
        tree_control_gl = object()
        tree_unmapped = object()
        tree_mapping = object()
        tree_control_accounts = object()
        tree_a07 = object()
        tree_control_suggestions = object()
        tree_suggestions = object()

        def _selected_tree_values(self, tree):
            if tree is self.tree_control_gl:
                return ("5000", "Lonn", "0,00", "1 200,00", "1 200,00", "")
            return ()

        def _selected_code_from_tree(self, tree):
            if tree is self.tree_a07:
                return "fastloenn"
            return None

    konto, kode = page_a07.A07Page._manual_mapping_defaults(DummyPage())

    assert konto == "5000"
    assert kode == "fastloenn"

def test_apply_manual_mapping_choices_assigns_multiple_accounts_to_same_code() -> None:
    mapping = {"4000": "bonus"}

    out = page_a07.apply_manual_mapping_choices(mapping, ["5000", "5001", "5000"], "fastloenn")

    assert out == ["5000", "5001"]
    assert mapping == {"4000": "bonus", "5000": "fastloenn", "5001": "fastloenn"}

def test_show_control_gl_context_menu_exposes_rule_learning_for_selected_code(monkeypatch) -> None:
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
        _prepare_tree_context_selection=lambda *args, **kwargs: "5290",
        _selected_control_gl_accounts=lambda: ["5290"],
        _selected_control_code=lambda: "feriepenger",
        _selected_control_work_level=lambda: "a07",
        _selected_rf1022_group=lambda: None,
        _effective_mapping=lambda: {},
        _a07_code_menu_choices=lambda: [],
        _assign_selected_control_mapping=lambda: None,
        _assign_accounts_to_a07_code=lambda *args, **kwargs: None,
        _remove_mapping_accounts_checked=lambda *args, **kwargs: None,
        _focus_linked_code_for_selected_gl_account=lambda: None,
        _selected_control_gl_learning_context=lambda: {
            "enabled": True,
            "code_label": "feriepenger",
            "accounts": ["5290"],
            "remove_enabled": False,
        },
        _append_selected_control_gl_names_to_a07_alias=lambda: None,
        _exclude_selected_control_gl_names_from_a07_code=lambda: None,
        _remove_selected_control_gl_accounts_and_exclude_alias=lambda: None,
        _set_control_gl_scope=lambda _scope: None,
        _run_selected_control_action=lambda: None,
        _apply_best_suggestion_for_selected_code=lambda: None,
        _apply_history_for_selected_code=lambda: None,
        _open_manual_mapping_clicked=lambda: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_gl_context_menu(dummy, SimpleNamespace())

    learn_menu = [payload for kind, label, payload in menu.items if kind == "cascade" and label == "Lær regel"][0]
    assert [label for kind, label, _payload in learn_menu.items if kind == "command"] == [
        "Lær kontonavn som alias for feriepenger",
        "Ekskluder kontonavn fra feriepenger",
        "Fjern mapping og ekskluder kontonavn fra feriepenger",
    ]
    assert [state for kind, _label, state in learn_menu.items if kind == "command"] == [
        "normal",
        "normal",
        "disabled",
    ]

def test_control_account_context_menu_exposes_rule_learning_for_mapped_account(monkeypatch) -> None:
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
        _prepare_tree_context_selection=lambda *args, **kwargs: "6701",
        _selected_control_account_ids=lambda: ["6701"],
        _selected_control_account_learning_context=lambda: {
            "enabled": True,
            "code_label": "annet",
            "accounts": ["6701"],
        },
        _focus_selected_control_account_in_gl=lambda: None,
        _remove_selected_control_accounts=lambda: None,
        _append_selected_control_account_names_to_a07_alias=lambda: None,
        _exclude_selected_control_account_names_from_a07_code=lambda: None,
        _remove_selected_control_accounts_and_exclude_alias=lambda: None,
        _open_manual_mapping_clicked=lambda: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_accounts_context_menu(dummy, SimpleNamespace())

    learn_menu = [payload for kind, label, payload in menu.items if kind == "cascade" and label == "Lær regel"][0]
    assert [label for kind, label, _payload in learn_menu.items if kind == "command"] == [
        "Lær kontonavn som alias for annet",
        "Ekskluder kontonavn fra annet",
        "Fjern mapping og ekskluder kontonavn fra annet",
    ]
    assert [state for kind, _label, state in learn_menu.items if kind == "command"] == [
        "normal",
        "normal",
        "normal",
    ]

def test_control_account_context_menu_multi_select_exposes_rule_learning(monkeypatch) -> None:
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
        _prepare_tree_context_selection=lambda *args, **kwargs: "6701",
        _selected_control_account_ids=lambda: ["6701", "7040"],
        _selected_control_account_learning_context=lambda: {
            "enabled": True,
            "code_label": "valgte A07-koder",
            "accounts": ["6701", "7040"],
        },
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
        "Vis første i GL",
        "Fjern mapping fra 2 valgte",
    ]
    cascades = [(label, payload) for kind, label, payload in menu.items if kind == "cascade"]
    assert [label for label, _payload in cascades] == ["Lær regel", "Avansert"]
    learn_menu = cascades[0][1]
    assert [label for kind, label, _payload in learn_menu.items if kind == "command"] == [
        "Lær valgte kontonavn som alias for valgte A07-koder",
        "Ekskluder valgte kontonavn fra valgte A07-koder",
        "Fjern mapping og ekskluder valgte kontonavn fra valgte A07-koder",
    ]
    assert [state for kind, _label, state in learn_menu.items if kind == "command"] == [
        "normal",
        "normal",
        "normal",
    ]

def test_remove_and_exclude_control_account_uses_rule_learning_and_checked_remove(monkeypatch) -> None:
    learned: list[tuple[str, str, bool]] = []
    removed_calls: list[tuple[list[str], str]] = []

    class _Status:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

    monkeypatch.setattr(
        a07_mapping_actions,
        "append_a07_rule_keywords",
        lambda entries, exclude=False: (
            (entry_list := list(entries)),
            learned.extend((code, term, exclude) for code, term in entry_list),
            SimpleNamespace(
                results=tuple(SimpleNamespace(code=code, term=term, changed=True) for code, term in entry_list),
                changed_count=len(entry_list),
                path=Path("rules.json"),
            ),
        )[2],
    )
    monkeypatch.setattr(
        a07_mapping_actions.payroll_classification,
        "invalidate_runtime_caches",
        lambda: None,
    )
    dummy = SimpleNamespace(
        tree_control_accounts=object(),
        status_var=_Status(),
        _selected_control_account_ids=lambda: ["6701"],
        _locked_mapping_conflicts=lambda accounts, target_code=None: [],
        _notify_locked_conflicts=lambda conflicts, focus_widget=None: bool(conflicts),
        _control_account_name_lookup=lambda accounts: {"6701": "Honorar revisjon"},
        _mapped_a07_code_for_account=lambda account: "annet",
        _remove_mapping_accounts_checked=lambda accounts, **kwargs: (
            removed_calls.append((list(accounts), kwargs.get("refresh"))),
            list(accounts),
        )[1],
        _refresh_all=lambda: None,
        _notify_inline=lambda *_args, **_kwargs: None,
    )

    page_a07.A07Page._learn_selected_control_account_names(dummy, exclude=True, remove_mapping=True)

    assert learned == [("annet", "Honorar revisjon", True)]
    assert removed_calls == [(["6701"], "none")]
    assert "mapping" in dummy.status_var.get()

def test_learning_control_account_names_handles_multi_select_mixed_codes(monkeypatch) -> None:
    learned: list[tuple[str, str, bool]] = []

    class _Status:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

    monkeypatch.setattr(
        a07_mapping_actions,
        "append_a07_rule_keywords",
        lambda entries, exclude=False: (
            (entry_list := list(entries)),
            learned.extend((code, term, exclude) for code, term in entry_list),
            SimpleNamespace(
                results=tuple(SimpleNamespace(code=code, term=term, changed=True) for code, term in entry_list),
                changed_count=len(entry_list),
                path=Path("rules.json"),
            ),
        )[2],
    )
    monkeypatch.setattr(
        a07_mapping_actions.payroll_classification,
        "invalidate_runtime_caches",
        lambda: None,
    )
    dummy = SimpleNamespace(
        tree_control_accounts=object(),
        status_var=_Status(),
        _selected_control_account_ids=lambda: ["6701", "7040"],
        _control_account_name_lookup=lambda accounts: {
            "6701": "Honorar revisjon",
            "7040": "Forsikring ansvar rettshjelp",
        },
        _mapped_a07_code_for_account=lambda account: {
            "6701": "annet",
            "7040": "overtidsgodtgjoerelse",
        }.get(account, ""),
        _refresh_all=lambda: None,
        _notify_inline=lambda *_args, **_kwargs: None,
    )

    page_a07.A07Page._learn_selected_control_account_names(dummy, exclude=True, remove_mapping=False)

    assert learned == [
        ("annet", "Honorar revisjon", True),
        ("overtidsgodtgjoerelse", "Forsikring ansvar rettshjelp", True),
    ]
    assert "2 kontonavn" in dummy.status_var.get()

def test_learning_control_gl_account_names_uses_selected_a07_code_for_unmapped_account(monkeypatch) -> None:
    learned: list[tuple[str, str, bool]] = []
    refresh_calls: list[str] = []

    class _Status:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

    monkeypatch.setattr(
        a07_mapping_actions,
        "append_a07_rule_keywords",
        lambda entries, exclude=False: (
            (entry_list := list(entries)),
            learned.extend((code, term, exclude) for code, term in entry_list),
            SimpleNamespace(
                results=tuple(SimpleNamespace(code=code, term=term, changed=True) for code, term in entry_list),
                changed_count=len(entry_list),
                path=Path("rules.json"),
            ),
        )[2],
    )
    monkeypatch.setattr(
        a07_mapping_actions.payroll_classification,
        "invalidate_runtime_caches",
        lambda: None,
    )
    dummy = SimpleNamespace(
        tree_control_gl=object(),
        tree_a07=object(),
        status_var=_Status(),
        _selected_control_gl_accounts=lambda: ["5290"],
        _selected_control_code=lambda: "feriepenger",
        _control_account_name_lookup=lambda accounts: {"5290": "Motkonto for gruppe 52"},
        _mapped_a07_code_for_account=lambda account: "",
        _selected_control_gl_learning_context=lambda: page_a07.A07Page._selected_control_gl_learning_context(dummy),
        _refresh_core=lambda focus_code=None: refresh_calls.append(focus_code),
        _refresh_all=lambda: None,
        _notify_inline=lambda *_args, **_kwargs: None,
        _notify_a07_rule_learning_changed=lambda: None,
    )

    page_a07.A07Page._learn_selected_control_gl_account_names(dummy, exclude=False, remove_mapping=False)

    assert learned == [("feriepenger", "Motkonto for gruppe 52", False)]
    assert refresh_calls == ["feriepenger"]
    assert "1 kontonavn lagt til som alias" in dummy.status_var.get()

def test_rule_learning_notification_defers_admin_rulebook_reload(monkeypatch) -> None:
    reload_calls: list[object] = []
    idle_callbacks: list[object] = []

    class _RulebookEditor:
        def reload(self, *, select_key=None) -> None:
            reload_calls.append(select_key)

    app = SimpleNamespace(page_admin=SimpleNamespace(_rulebook_editor=_RulebookEditor()))
    monkeypatch.setattr(a07_mapping_actions.session, "APP", app, raising=False)
    dummy = SimpleNamespace(after_idle=lambda callback: idle_callbacks.append(callback))

    page_a07.A07Page._notify_a07_rule_learning_changed(
        dummy,
        focus_code="tilskuddOgPremieTilPensjon",
    )

    assert reload_calls == []
    assert len(idle_callbacks) == 1
    idle_callbacks[0]()
    assert reload_calls == ["tilskuddOgPremieTilPensjon"]

def test_rule_learning_notification_skips_heavy_external_page_refresh(monkeypatch) -> None:
    refresh_calls: list[tuple[str, object | None, bool | None]] = []
    idle_callbacks: list[object] = []

    class _AnalysePage:
        def refresh_from_session(self, session_obj=None, *, defer_heavy: bool = False) -> None:
            refresh_calls.append(("analyse", session_obj, defer_heavy))

    class _SaldobalansePage:
        def refresh_from_session(self, session_obj=None, **_kwargs) -> None:
            refresh_calls.append(("saldobalanse", session_obj, None))

    app = SimpleNamespace(
        page_admin=SimpleNamespace(_rulebook_editor=None),
        page_saldobalanse=_SaldobalansePage(),
        page_analyse=_AnalysePage(),
    )
    monkeypatch.setattr(a07_mapping_actions.session, "APP", app, raising=False)

    dummy = SimpleNamespace(after_idle=lambda callback: idle_callbacks.append(callback))
    page_a07.A07Page._notify_a07_rule_learning_changed(dummy, focus_code="feriepenger")

    assert refresh_calls == []
    assert len(idle_callbacks) == 1
    idle_callbacks[0]()
    assert refresh_calls == []

def test_append_a07_rule_keywords_clears_rulebook_cache(monkeypatch, tmp_path) -> None:
    document: dict[str, object] = {"rules": {"feriepenger": {"label": "Feriepenger", "keywords": []}}}
    cache_clears: list[bool] = []

    monkeypatch.setattr(
        a07_rule_learning.classification_config,
        "load_rulebook_document",
        lambda: document,
    )
    monkeypatch.setattr(
        a07_rule_learning.classification_config,
        "save_rulebook_document",
        lambda data: tmp_path / "global_full_a07_rulebook.json",
    )
    monkeypatch.setattr(a07_rule_learning, "clear_rulebook_cache", lambda: cache_clears.append(True))

    result = a07_rule_learning.append_a07_rule_keywords([("feriepenger", "OTP Innberettet")])

    assert result.changed_count == 1
    assert cache_clears == [True]
    assert document["rules"]["feriepenger"]["keywords"] == ["OTP Innberettet"]  # type: ignore[index]


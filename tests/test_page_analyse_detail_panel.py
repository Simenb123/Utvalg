from __future__ import annotations

from types import SimpleNamespace


class _DummyVar:
    def __init__(self, value=""):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class _FakeTree:
    def __init__(self, rows=None):
        self._rows = rows or {}
        self.selection_items = []
        self.focus_item = ""
        self.seen = []

    def get_children(self, *_a, **_k):
        return list(self._rows.keys())

    def set(self, item, col):
        return self._rows.get(item, {}).get(col, "")

    def selection_set(self, items):
        if isinstance(items, (list, tuple)):
            self.selection_items = list(items)
        else:
            self.selection_items = [items]

    def selection(self):
        return list(self.selection_items)

    def focus(self, item=None):
        if item is None:
            return self.focus_item
        self.focus_item = item

    def see(self, item):
        self.seen.append(item)


def test_selected_transaction_accounts_narrows_on_explicit_selection() -> None:
    import page_analyse_detail_panel

    page = SimpleNamespace(
        _detail_selected_account="3000",
        _detail_selected_account_explicit=True,
    )

    assert page_analyse_detail_panel.selected_transaction_accounts(page, ["1500", "3000"]) == ["3000"]


def test_selected_transaction_accounts_ignores_auto_selected_account() -> None:
    """RL-mode: auto-selected detail account must not narrow transactions."""
    import page_analyse_detail_panel

    page = SimpleNamespace(
        _detail_selected_account="3000",
        _detail_selected_account_explicit=False,
    )

    assert page_analyse_detail_panel.selected_transaction_accounts(
        page, ["3000", "3001", "3002"]
    ) == ["3000", "3001", "3002"]


def test_on_detail_account_selected_marks_selection_explicit() -> None:
    """User clicking a detail-panel row marks the selection as explicit."""
    import page_analyse_detail_panel

    tree = _FakeTree(rows={"i1": {"Konto": "3001"}})
    tree.selection_items = ["i1"]

    page = SimpleNamespace(
        _detail_accounts_tree=tree,
        _detail_selected_account="",
        _detail_selected_account_explicit=False,
        _detail_suggestion_tree=None,
        _detail_suggestions_by_account={},
        _detail_profiles_by_account={},
        _detail_accounts_df=None,
    )
    page._refresh_transactions_view = lambda: None

    page_analyse_detail_panel.on_detail_account_selected(page)

    assert page._detail_selected_account == "3001"
    assert page._detail_selected_account_explicit is True
    # narrowing kicks in
    assert page_analyse_detail_panel.selected_transaction_accounts(
        page, ["3001", "3002"]
    ) == ["3001"]


def test_reset_detail_selection_restores_full_scope() -> None:
    """Switching RL via pivot-select resets detail so transactions go full scope."""
    import page_analyse_detail_panel

    page = SimpleNamespace(
        _detail_selected_account="3001",
        _detail_selected_account_explicit=True,
    )

    page_analyse_detail_panel.reset_detail_selection(page)

    assert page._detail_selected_account == ""
    assert page._detail_selected_account_explicit is False
    assert page_analyse_detail_panel.selected_transaction_accounts(
        page, ["4000", "4001"]
    ) == ["4000", "4001"]


def test_jump_to_analysis_context_sets_period_and_restores_rl_selection(monkeypatch) -> None:
    import page_analyse_detail_panel

    calls = {"apply": 0, "refresh_detail": 0, "refresh_tx": 0, "restore": None}
    page = SimpleNamespace(
        _var_date_from=_DummyVar(""),
        _var_date_to=_DummyVar(""),
        _var_aggregering=_DummyVar("Regnskapslinje"),
        _detail_selected_account="",
        _detail_selected_account_explicit=False,
    )
    page._apply_filters_now = lambda: calls.__setitem__("apply", calls["apply"] + 1)
    page._restore_rl_pivot_selection = lambda values: calls.__setitem__("restore", list(values))
    monkeypatch.setattr(page_analyse_detail_panel, "refresh_detail_panel", lambda page: calls.__setitem__("refresh_detail", calls["refresh_detail"] + 1))
    page._refresh_transactions_view = lambda: calls.__setitem__("refresh_tx", calls["refresh_tx"] + 1)

    page_analyse_detail_panel.jump_to_analysis_context(
        page,
        {"period_from": "3", "period_to": "5", "regnr_values": [10, 20], "accounts": ["3000"]},
    )

    assert page._var_date_from.get() == "3"
    assert page._var_date_to.get() == "5"
    assert calls["apply"] == 1
    assert calls["restore"] == [10, 20]
    assert calls["refresh_detail"] == 1
    assert calls["refresh_tx"] == 1


def test_focus_detail_panel_refreshes_and_returns_true(monkeypatch) -> None:
    import page_analyse_detail_panel

    tree = _FakeTree()
    tree.focus_set = lambda: None
    calls = {"refresh": 0}
    page = SimpleNamespace(_detail_accounts_tree=tree)
    monkeypatch.setattr(page_analyse_detail_panel, "refresh_detail_panel", lambda page: calls.__setitem__("refresh", calls["refresh"] + 1))

    assert page_analyse_detail_panel.focus_detail_panel(page) is True
    assert calls["refresh"] == 1

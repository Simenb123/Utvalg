from __future__ import annotations

from types import SimpleNamespace

import pandas as pd


class _FakeLabel:
    def __init__(self):
        self.text = ""

    def configure(self, **kwargs):
        if "text" in kwargs:
            self.text = str(kwargs["text"])


class _FakeSBTree:
    def __init__(self, rows=None, selected=None, focus_item=""):
        self.rows = dict(rows or {})
        self._selection = list(selected or [])
        self._focus = focus_item
        self.selection_calls = []
        self.focus_calls = []
        self.see_calls = []
        self.tag_configs = {}

    def selection(self):
        return list(self._selection)

    def focus(self, item=None):
        if item is None:
            return self._focus
        self._focus = item
        self.focus_calls.append(item)

    def see(self, item):
        self.see_calls.append(item)

    def item(self, item, option=None):
        values = self.rows.get(item, [])
        if option == "values":
            return list(values)
        return {"values": list(values)}

    def get_children(self, *_a, **_k):
        return list(self.rows.keys())

    def delete(self, item):
        self.rows.pop(item, None)

    def insert(self, _parent, _index, values=(), tags=()):
        item = f"row{len(self.rows) + 1}"
        self.rows[item] = list(values)
        return item

    def selection_set(self, items):
        if isinstance(items, (list, tuple)):
            self._selection = list(items)
        else:
            self._selection = [items]
        self.selection_calls.append(list(self._selection))

    def tag_configure(self, tag, **kwargs):
        self.tag_configs[tag] = dict(kwargs)


def test_capture_sb_selection_reads_selected_accounts_and_focus():
    import page_analyse_sb

    tree = _FakeSBTree(
        rows={
            "a": ["1000", "Bank", "0,00", "10,00", "10,00", ""],
            "b": ["1500", "Kunde", "0,00", "20,00", "20,00", ""],
        },
        selected=["b"],
        focus_item="b",
    )

    selected_accounts, focused_account = page_analyse_sb._capture_sb_selection(tree)

    assert selected_accounts == ["1500"]
    assert focused_account == "1500"


def test_refresh_sb_view_restores_selection_after_refresh(monkeypatch):
    import page_analyse_sb

    tree = _FakeSBTree(
        rows={
            "old1": ["1000", "Bank", "0,00", "10,00", "10,00", ""],
            "old2": ["1500", "Kunde", "0,00", "20,00", "20,00", ""],
        },
        selected=["old2"],
        focus_item="old2",
    )
    page = SimpleNamespace(
        _sb_tree=tree,
        _rl_sb_df=pd.DataFrame(
            {
                "konto": ["1000", "1500"],
                "kontonavn": ["Bank", "Kunde"],
                "ib": [0.0, 0.0],
                "endring": [10.0, 20.0],
                "ub": [10.0, 20.0],
            }
        ),
        _lbl_tx_summary=_FakeLabel(),
        _get_effective_sb_df=lambda: pd.DataFrame(
            {
                "konto": ["1000", "1500"],
                "kontonavn": ["Bank", "Kunde"],
                "ib": [0.0, 0.0],
                "endring": [10.0, 20.0],
                "ub": [10.0, 20.0],
            }
        ),
    )

    monkeypatch.setattr(page_analyse_sb, "_clear_tree", lambda t: [t.delete(item) for item in list(t.get_children(""))])
    monkeypatch.setattr(page_analyse_sb, "_resolve_target_kontoer", lambda **_k: {"1000", "1500"})
    monkeypatch.setattr(page_analyse_sb, "_bind_sb_once", lambda **_k: None)

    page_analyse_sb.refresh_sb_view(page=page)

    assert tree.selection_calls, "SB refresh should restore selection when there was one before refresh"
    selected_item = tree.selection_calls[-1][0]
    values = tree.item(selected_item, "values")
    assert values[0] == "1500"
    assert tree.focus_calls[-1] == selected_item
    assert tree.see_calls[-1] == selected_item

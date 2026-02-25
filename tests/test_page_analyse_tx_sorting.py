from __future__ import annotations

import page_analyse


def test_enable_tx_sorting_calls_helper(monkeypatch):
    calls = []

    def fake_enable(tree, columns=None, text_key=None):
        calls.append((tree, columns))

    monkeypatch.setattr(page_analyse, "_enable_treeview_sorting", fake_enable)

    page = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    page._tk_ok = True
    page._tx_tree = object()
    page.TX_COLS = ("Konto", "Dato", "Beløp")

    page._enable_tx_sorting()

    assert calls == [(page._tx_tree, page.TX_COLS)]


def test_enable_tx_sorting_noop_when_no_tree(monkeypatch):
    calls = []

    def fake_enable(tree, columns=None, text_key=None):
        calls.append((tree, columns))

    monkeypatch.setattr(page_analyse, "_enable_treeview_sorting", fake_enable)

    page = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    page._tk_ok = True
    page._tx_tree = None
    page.TX_COLS = ("Konto",)

    page._enable_tx_sorting()
    assert calls == []

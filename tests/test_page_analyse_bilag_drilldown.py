# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd

import page_analyse


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Bilag": ["1", "1", "2", "2"],
            "Konto": ["3000", "1920", "3000", "1920"],
            "Beløp": [-100.0, 100.0, -200.0, 200.0],
            "Tekst": ["Salg", "Bank", "Salg 2", "Bank 2"],
            "Dato": ["01.01.2026", "01.01.2026", "02.01.2026", "02.01.2026"],
        }
    )


def test_open_bilag_drilldown_for_bilag_calls_dialog_with_scope(monkeypatch) -> None:
    df_all = _make_df()

    calls: dict[str, object] = {}

    def fake_open(master, df_base=None, df_all=None, bilag_value=None, bilag_col="Bilag", **_kwargs):
        calls["master"] = master
        calls["df_base"] = df_base.copy() if isinstance(df_base, pd.DataFrame) else df_base
        calls["df_all"] = df_all.copy() if isinstance(df_all, pd.DataFrame) else df_all
        calls["bilag_value"] = bilag_value
        calls["bilag_col"] = bilag_col

    monkeypatch.setattr(page_analyse, "_open_bilag_drill_dialog", fake_open, raising=True)

    p = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    p.dataset = df_all
    p._df_filtered = df_all.copy()
    p._tx_tree = None

    p._get_selected_accounts = lambda: ["3000"]  # type: ignore[method-assign]

    page_analyse.AnalysePage._open_bilag_drilldown_for_bilag(p, "1")

    assert calls["bilag_value"] == "1"
    assert calls["bilag_col"] == "Bilag"

    df_base = calls["df_base"]
    assert isinstance(df_base, pd.DataFrame)
    assert set(df_base["Konto"].unique().tolist()) == {"3000"}

    df_all_called = calls["df_all"]
    assert isinstance(df_all_called, pd.DataFrame)
    assert len(df_all_called) == len(df_all)


def test_open_bilag_drilldown_for_bilag_falls_back_without_scope(monkeypatch) -> None:
    df_all = _make_df()

    calls: dict[str, object] = {}

    def fake_open(master, df_base=None, df_all=None, bilag_value=None, bilag_col="Bilag", **_kwargs):
        calls["df_base"] = df_base.copy() if isinstance(df_base, pd.DataFrame) else df_base
        calls["df_all"] = df_all.copy() if isinstance(df_all, pd.DataFrame) else df_all
        calls["bilag_value"] = bilag_value
        calls["bilag_col"] = bilag_col

    monkeypatch.setattr(page_analyse, "_open_bilag_drill_dialog", fake_open, raising=True)

    p = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    p.dataset = df_all
    p._df_filtered = df_all.copy()
    p._tx_tree = None

    p._get_selected_accounts = lambda: []  # type: ignore[method-assign]

    page_analyse.AnalysePage._open_bilag_drilldown_for_bilag(p, "2")

    df_base = calls["df_base"]
    assert isinstance(df_base, pd.DataFrame)
    assert set(df_base["Konto"].unique().tolist()) == {"3000", "1920"}


def test_open_bilag_drilldown_from_tx_selection_without_tree_does_not_popup(monkeypatch) -> None:
    # Under pytest skal vi ikke åpne messagebox (det stopper testkjøringen).
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")

    class FakeMsgBox:
        @staticmethod
        def showinfo(*_a, **_k):
            raise AssertionError("messagebox.showinfo skal ikke kalles under pytest")

        @staticmethod
        def showerror(*_a, **_k):
            raise AssertionError("messagebox.showerror skal ikke kalles under pytest")

    monkeypatch.setattr(page_analyse, "messagebox", FakeMsgBox, raising=False)

    p = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    p._tx_tree = None
    p.dataset = _make_df()
    p._df_filtered = p.dataset.copy()

    # Ikke kall dialog
    monkeypatch.setattr(page_analyse, "_open_bilag_drill_dialog", lambda *a, **k: None, raising=True)

    # Skal ikke raise, og skal ikke poppe GUI
    page_analyse.AnalysePage._open_bilag_drilldown_from_tx_selection(p)

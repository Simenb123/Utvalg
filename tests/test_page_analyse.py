"""Tests for the minimal AnalysePage implementation.

These tests verify that the AnalysePage class is defined correctly,
exposes a ``refresh_from_session`` method with the expected signature, and
that the method can be called without errors. Additional tests cover the
callback mechanism used to communicate selected accounts to another
component.
"""

from __future__ import annotations

import inspect
import tkinter

import pandas as pd


def test_class_exists() -> None:
    """Ensure that the AnalysePage class exists in the page_analyse module."""
    import page_analyse

    assert hasattr(page_analyse, "AnalysePage"), "AnalysePage must be defined"
    AnalysePage = getattr(page_analyse, "AnalysePage")
    assert inspect.isclass(AnalysePage), "AnalysePage must be a class"


def test_refresh_from_session_signature() -> None:
    """Verify that refresh_from_session has the correct signature."""
    import page_analyse

    AnalysePage = page_analyse.AnalysePage
    assert hasattr(AnalysePage, "refresh_from_session"), "Missing refresh_from_session method"

    fn = getattr(AnalysePage, "refresh_from_session")
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    # The method should take at least self and session
    assert len(params) >= 2, "refresh_from_session should take self and session"
    # The name of the second parameter should be session or similar
    assert params[1].name in {"session", "sess"}, (
        "Second parameter of refresh_from_session should be named 'session' or 'sess'"
    )


def test_refresh_from_session_callable() -> None:
    """Check that refresh_from_session can be called with a dummy session."""
    import page_analyse

    class DummySession:
        def __init__(self) -> None:
            self.dataset = "dummy"

    AnalysePage = page_analyse.AnalysePage
    page = AnalysePage(None)
    session = DummySession()
    # Should not raise an exception
    page.refresh_from_session(session)
    # The dataset attribute should now be set to the dummy value
    assert page.dataset == "dummy"


def test_utvalg_callback() -> None:
    """Ensure that set_utvalg_callback registers a callback and is invoked correctly."""
    import page_analyse

    AnalysePage = page_analyse.AnalysePage

    called_with = {}

    def callback(accounts) -> None:
        called_with["accounts"] = accounts

    page = AnalysePage(None)
    page.set_utvalg_callback(callback)
    # Trigger the callback via the protected method
    page._send_to_selection([1, 2, 3])
    assert called_with.get("accounts") == [1, 2, 3], (
        "Callback did not receive the expected accounts"
    )


class _DummyVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _FakePivotTree:
    def __init__(self, regnr_by_item):
        self._regnr_by_item = dict(regnr_by_item)
        self.selection_calls = []
        self.focus_calls = []
        self.see_calls = []

    def get_children(self, *_a, **_k):
        return list(self._regnr_by_item.keys())

    def set(self, item, col):
        if col != "Konto":
            return ""
        return self._regnr_by_item[item]

    def selection_set(self, items):
        self.selection_calls.append(list(items))

    def focus(self, item):
        self.focus_calls.append(item)

    def see(self, item):
        self.see_calls.append(item)


def test_open_rl_drilldown_passes_mapping_context(monkeypatch) -> None:
    import page_analyse
    import page_analyse_rl
    import session as _session

    page = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    page._var_aggregering = _DummyVar("Regnskapslinje")
    page._rl_regnskapslinjer = pd.DataFrame(
        {"nr": [10], "regnskapslinje": ["Salg"], "sumpost": ["nei"], "Formel": [""]}
    )

    drill_df = pd.DataFrame({"Nr": [10], "Konto": ["3000"]})
    reloaded_df = pd.DataFrame({"Nr": [10], "Konto": ["3010"]})

    monkeypatch.setattr(_session, "client", "Nbs Regnskap AS", raising=False)
    monkeypatch.setattr(
        page_analyse_rl,
        "build_selected_rl_account_drilldown",
        lambda *, page: (drill_df, [(10, "Salg")]),
    )
    monkeypatch.setattr(page, "_reload_rl_drilldown_df", lambda regnr_filter: reloaded_df, raising=False)

    calls = {}

    def fake_open(master, df, **kwargs):
        calls["master"] = master
        calls["df"] = df
        calls["kwargs"] = kwargs
        calls["reloaded"] = kwargs["reload_callback"]()

    monkeypatch.setattr(page_analyse, "_open_rl_account_drilldown", fake_open, raising=False)

    page_analyse.AnalysePage._open_rl_drilldown_from_pivot_selection(page)

    assert calls["master"] is page
    assert calls["df"].equals(drill_df)
    assert calls["kwargs"]["title"] == "RL-drilldown: 10 Salg"
    assert calls["kwargs"]["client"] == "Nbs Regnskap AS"
    assert calls["kwargs"]["regnskapslinjer"] is page._rl_regnskapslinjer
    assert calls["reloaded"].equals(reloaded_df)


def test_reload_rl_drilldown_df_refreshes_and_restores_selection(monkeypatch) -> None:
    import page_analyse
    import page_analyse_rl

    page = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    page._pivot_tree = _FakePivotTree({"row1": "10", "row2": "20", "row3": "99"})
    page._df_filtered = pd.DataFrame({"Konto": ["1000"], "Beløp": [123.0]})
    page._rl_intervals = object()
    page._rl_regnskapslinjer = object()
    page._rl_sb_df = object()

    refresh_calls = {"pivot": 0, "tx": 0}

    monkeypatch.setattr(page, "_refresh_pivot", lambda: refresh_calls.__setitem__("pivot", refresh_calls["pivot"] + 1), raising=False)
    monkeypatch.setattr(
        page,
        "_refresh_transactions_view",
        lambda: refresh_calls.__setitem__("tx", refresh_calls["tx"] + 1),
        raising=False,
    )

    expected = pd.DataFrame({"Nr": [10], "Konto": ["1000"]})
    captured = {}

    monkeypatch.setattr(page_analyse_rl, "_load_current_client_account_overrides", lambda: {"1000": 10})

    def fake_build(df_filtered, intervals, regnskapslinjer, **kwargs):
        captured["df_filtered"] = df_filtered
        captured["intervals"] = intervals
        captured["regnskapslinjer"] = regnskapslinjer
        captured["kwargs"] = kwargs
        return expected

    monkeypatch.setattr(page_analyse_rl, "build_rl_account_drilldown", fake_build)

    out = page_analyse.AnalysePage._reload_rl_drilldown_df(page, [10, 20])

    assert refresh_calls == {"pivot": 1, "tx": 1}
    assert page._pivot_tree.selection_calls == [["row1", "row2"]]
    assert page._pivot_tree.focus_calls == ["row1"]
    assert page._pivot_tree.see_calls == ["row1"]
    assert captured["kwargs"]["regnr_filter"] == [10, 20]
    assert captured["kwargs"]["account_overrides"] == {"1000": 10}
    assert out.equals(expected)


def test_export_regnskapsoppstilling_excel_uses_payload_and_save_dialog(monkeypatch, tmp_path) -> None:
    import page_analyse

    page = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    payload = {
        "rl_df": pd.DataFrame({"regnr": [10], "regnskapslinje": ["Eiendeler"], "IB": [0.0], "Endring": [1.0], "UB": [1.0], "Antall": [1]}),
        "regnskapslinjer": pd.DataFrame({"nr": [10], "regnskapslinje": ["Eiendeler"], "sumpost": ["nei"], "Formel": [""]}),
        "transactions_df": pd.DataFrame({"Konto": ["1000"], "Beløp": [1.0]}),
        "client": "Nbs Regnskap AS",
        "year": "2025",
    }

    monkeypatch.setattr(
        page_analyse.page_analyse_export,
        "prepare_regnskapsoppstilling_export_data",
        lambda *, page: payload,
    )
    monkeypatch.setattr(
        tkinter.filedialog,
        "asksaveasfilename",
        lambda **_kwargs: str(tmp_path / "regnskapsoppstilling.xlsx"),
    )

    calls = {}

    def fake_save(path, **kwargs):
        calls["path"] = path
        calls["kwargs"] = kwargs
        return str(path)

    import analyse_regnskapsoppstilling_excel

    monkeypatch.setattr(analyse_regnskapsoppstilling_excel, "save_regnskapsoppstilling_workbook", fake_save)
    monkeypatch.setattr(page_analyse, "messagebox", None, raising=False)

    page_analyse.AnalysePage._export_regnskapsoppstilling_excel(page)

    assert str(calls["path"]).endswith("regnskapsoppstilling.xlsx")
    assert calls["kwargs"]["rl_df"].equals(payload["rl_df"])
    assert calls["kwargs"]["regnskapslinjer"] is payload["regnskapslinjer"]
    assert calls["kwargs"]["transactions_df"].equals(payload["transactions_df"])
    assert calls["kwargs"]["client"] == "Nbs Regnskap AS"
    assert calls["kwargs"]["year"] == "2025"

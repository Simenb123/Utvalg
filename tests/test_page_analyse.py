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
from types import SimpleNamespace

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


class _FakeWidthTree:
    def __init__(self, *, widths, available_width, columns=None):
        self._columns = tuple(columns or ("Konto", "Kontonavn", "Sum", "Antall"))
        self._displaycolumns = self._columns
        self._widths = dict(widths)
        self._available_width = int(available_width)

    def __getitem__(self, key):
        if key == "columns":
            return self._columns
        if key == "displaycolumns":
            return self._displaycolumns
        raise KeyError(key)

    def column(self, col, option=None, **kwargs):
        if kwargs:
            if "width" in kwargs:
                self._widths[col] = int(kwargs["width"])
            return {"width": self._widths.get(col, 0)}
        if option == "width":
            return self._widths.get(col, 0)
        return {"width": self._widths.get(col, 0)}

    def winfo_width(self):
        return self._available_width


class _FakeAccountRefreshTree:
    def __init__(self, initial_rows):
        self._rows = dict(initial_rows)
        self._selection = list(initial_rows.keys())[:1]
        self._focus = self._selection[0] if self._selection else ""
        self.selection_calls = []
        self.focus_calls = []
        self.see_calls = []
        self._counter = 0

    def get_children(self, *_a, **_k):
        return list(self._rows.keys())

    def set(self, item, col):
        return self._rows.get(item, {}).get(col, "")

    def selection(self):
        return list(self._selection)

    def selection_set(self, items):
        if isinstance(items, (list, tuple)):
            self._selection = list(items)
        else:
            self._selection = [items]
        self.selection_calls.append(list(self._selection))

    def focus(self, item=None):
        if item is None:
            return self._focus
        self._focus = item
        self.focus_calls.append(item)

    def see(self, item):
        self.see_calls.append(item)

    def insert(self, _parent, _index, values=(), tags=()):
        self._counter += 1
        item = f"new{self._counter}"
        row = {
            "Konto": values[0] if len(values) > 0 else "",
            "Kontonavn": values[1] if len(values) > 1 else "",
        }
        self._rows[item] = row
        return item

    def delete(self, item):
        self._rows.pop(item, None)


class _FakeHeaderTree:
    def __init__(self):
        self._suppress_next_heading_sort = False

    def identify_region(self, _x, _y):
        return "heading"


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
    monkeypatch.setattr(page, "_get_effective_sb_df", lambda: "effective-sb", raising=False)

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
    assert captured["kwargs"]["sb_df"] == "effective-sb"
    assert out.equals(expected)


def test_account_pivot_refresh_restores_selected_account(monkeypatch) -> None:
    import page_analyse_pivot

    tree = _FakeAccountRefreshTree(
        {
            "old1": {"Konto": "1000", "Kontonavn": "Bank"},
            "old2": {"Konto": "2000", "Kontonavn": "Kasse"},
        }
    )
    page = SimpleNamespace(
        _pivot_tree=tree,
        _df_filtered=pd.DataFrame(
            {
                "Konto": ["1000", "1000", "2000"],
                "Kontonavn": ["Bank", "Bank", "Kasse"],
                "Beløp": [100.0, -25.0, 50.0],
            }
        ),
        _clear_tree=lambda target: [target.delete(item) for item in list(target.get_children(""))],
        _maybe_auto_fit_pivot_tree=lambda: None,
    )

    # Test HB-konto-style refresh direkte: etter Pulje A dirigerer refresh_pivot
    # alle ikke-Regnskapslinje-moduser til SB-konto (som krever _get_effective_sb_df).
    # Denne testen verifiserer at HB-pivotens refresh fortsatt restaurerer valgt konto.
    page_analyse_pivot.refresh_hb_konto_pivot(page=page)

    assert tree.selection_calls, "Refresh should restore a selection when one existed before refresh"
    selected_item = tree.selection_calls[-1][0]
    assert tree.set(selected_item, "Konto") == "1000"
    assert tree.focus_calls[-1] == selected_item
    assert tree.see_calls[-1] == selected_item


def test_tx_header_drag_reorders_columns(monkeypatch) -> None:
    import page_analyse_columns

    page = SimpleNamespace(
        _tx_tree=_FakeHeaderTree(),
        _tx_cols_order=["Konto", "Kontonavn", "Dato", "Bilag", "Beløp", "Tekst"],
        TX_COLS=("Konto", "Kontonavn", "Dato", "Bilag", "Beløp", "Tekst"),
        TX_COLS_DEFAULT=("Konto", "Kontonavn", "Dato", "Bilag", "Beløp", "Tekst"),
        PINNED_TX_COLS=("Konto", "Kontonavn"),
        REQUIRED_TX_COLS=("Konto", "Kontonavn", "Bilag"),
    )

    captured = {}

    monkeypatch.setattr(
        page_analyse_columns,
        "column_id_from_event",
        lambda _tree, event: event.col,
    )
    monkeypatch.setattr(
        page_analyse_columns,
        "get_all_tx_columns_for_chooser",
        lambda *, page: list(page._tx_cols_order),
    )
    monkeypatch.setattr(
        page_analyse_columns,
        "apply_tx_column_config",
        lambda *, page, order, visible, all_cols=None: captured.update(
            {"order": list(order), "visible": list(visible)}
        ),
    )

    press = SimpleNamespace(x=10, y=0, col="Tekst")
    drag = SimpleNamespace(x=40, y=0, col="Tekst")
    release = SimpleNamespace(x=60, y=0, col="Beløp")

    page_analyse_columns.on_tx_tree_mouse_press(page=page, event=press)
    page_analyse_columns.on_tx_tree_mouse_drag(page=page, event=drag)
    page_analyse_columns.on_tx_tree_mouse_release(page=page, event=release)

    assert page._tx_tree._suppress_next_heading_sort is True
    assert captured["order"].index("Tekst") < captured["order"].index("Beløp")
    assert captured["visible"] == list(page.TX_COLS)


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


def test_rebalance_pivot_tree_columns_uses_available_width() -> None:
    import page_analyse_columns

    tree = _FakeWidthTree(
        widths={"Konto": 80, "Kontonavn": 210, "Sum": 110, "Antall": 60},
        available_width=720,
    )
    page = SimpleNamespace(_pivot_tree=tree)

    page_analyse_columns.rebalance_pivot_tree_columns(page=page)

    total = sum(tree.column(col, option="width") for col in tree["displaycolumns"])
    assert total >= 700
    assert tree.column("Kontonavn", option="width") > 210


def test_rebalance_pivot_tree_columns_keeps_widths_when_no_extra_space() -> None:
    import page_analyse_columns

    tree = _FakeWidthTree(
        widths={"Konto": 80, "Kontonavn": 210, "Sum": 110, "Antall": 60},
        available_width=430,
    )
    page = SimpleNamespace(_pivot_tree=tree)

    page_analyse_columns.rebalance_pivot_tree_columns(page=page)

    assert tree.column("Konto", option="width") == 80
    assert tree.column("Kontonavn", option="width") == 210
    assert tree.column("Sum", option="width") == 110
    assert tree.column("Antall", option="width") == 60


def test_adapt_pivot_columns_for_mode_migrates_legacy_rl_default_columns(monkeypatch) -> None:
    import page_analyse_columns

    class _DummyTree:
        def __init__(self):
            self.columns = (
                "Konto",
                "Kontonavn",
                "IB",
                "Endring",
                "Sum",
                "AO_belop",
                "UB_for_ao",
                "UB_etter_ao",
                "Antall",
            )
            self.displaycolumns = ()

        def __getitem__(self, key):
            if key == "columns":
                return self.columns
            raise KeyError(key)

        def __setitem__(self, key, value):
            if key == "displaycolumns":
                self.displaycolumns = tuple(value)
                return
            raise KeyError(key)

        def heading(self, _col, option=None):
            if option == "text":
                return "synlig"
            return {"text": "synlig"}

    tree = _DummyTree()
    page = SimpleNamespace(
        _var_aggregering=_DummyVar("Regnskapslinje"),
        _pivot_visible_cols=[
            "Konto",
            "Kontonavn",
            "IB",
            "Endring",
            "Sum",
            "AO_belop",
            "UB_for_ao",
            "UB_etter_ao",
            "Antall",
        ],
        PIVOT_COLS=tree.columns,
        PIVOT_COLS_PINNED=("Konto", "Kontonavn"),
        PIVOT_COLS_DEFAULT_VISIBLE=("Konto", "Kontonavn", "Endring", "Sum", "Antall"),
        PIVOT_COLS_DEFAULT_KONTO=("Konto", "Kontonavn", "Sum", "Antall"),
        PIVOT_COLS_DEFAULT_RL=("Konto", "Kontonavn", "IB", "Endring", "Sum", "Antall"),
        _pivot_tree=tree,
    )

    monkeypatch.setattr(page_analyse_columns, "persist_pivot_visible_columns", lambda **_k: None)

    page_analyse_columns.adapt_pivot_columns_for_mode(page=page)

    assert page._pivot_visible_cols == ["Konto", "Kontonavn", "IB", "Endring", "Sum", "Antall"]
    assert tree.displaycolumns == ("Konto", "Kontonavn", "IB", "Endring", "Sum", "Antall")


def test_pivot_default_for_mode_rl_with_prev_year() -> None:
    """RL-modus med fjor\u00e5rsdata gir kanonisk rekkefølge."""
    import page_analyse_columns
    import pandas as pd

    page = SimpleNamespace(
        _var_aggregering=_DummyVar("Regnskapslinje"),
        PIVOT_COLS_DEFAULT_VISIBLE=("Konto", "Kontonavn", "Endring", "Sum", "Antall"),
        PIVOT_COLS_DEFAULT_KONTO=("Konto", "Kontonavn", "Sum", "Antall"),
        PIVOT_COLS_DEFAULT_RL=(
            "Konto", "Kontonavn", "Sum", "UB_fjor",
            "Endring", "Endring_fjor", "Endring_pct", "Antall",
        ),
        _rl_sb_prev_df=pd.DataFrame({"konto": ["1000"], "ub": [5.0]}),
    )

    out = page_analyse_columns.pivot_default_for_mode(page=page)
    assert out == (
        "Konto", "Kontonavn", "Sum", "UB_fjor",
        "Endring", "Endring_fjor", "Endring_pct", "Antall",
    )


def test_pivot_default_for_mode_rl_without_prev_year() -> None:
    """RL-modus uten fjor\u00e5rsdata dropper UB_fjor/Endring_fjor/Endring_pct
    uten å sette inn intern 'Endring' som fallback (slank visning)."""
    import page_analyse_columns

    page = SimpleNamespace(
        _var_aggregering=_DummyVar("Regnskapslinje"),
        PIVOT_COLS_DEFAULT_VISIBLE=("Konto", "Kontonavn", "Endring", "Sum", "Antall"),
        PIVOT_COLS_DEFAULT_KONTO=("Konto", "Kontonavn", "Sum", "Antall"),
        PIVOT_COLS_DEFAULT_RL=(
            "Konto", "Kontonavn", "Sum", "UB_fjor",
            "Endring_fjor", "Endring_pct", "Antall",
        ),
        _rl_sb_prev_df=None,
    )

    out = page_analyse_columns.pivot_default_for_mode(page=page)
    assert "Endring" not in out
    assert out == ("Konto", "Kontonavn", "Sum", "Antall")


def test_pivot_default_for_mode_legacy_konto_maps_to_sb_konto() -> None:
    """Legacy 'Konto' skal migreres til SB-konto-modus."""
    import page_analyse_columns

    sb_default = (
        "Konto", "Kontonavn", "Sum", "UB_fjor",
        "Endring_fjor", "Endring_pct", "Antall",
    )
    page = SimpleNamespace(
        _var_aggregering=_DummyVar("Konto"),
        PIVOT_COLS_DEFAULT_VISIBLE=("Konto", "Kontonavn", "Endring", "Sum", "Antall"),
        PIVOT_COLS_DEFAULT_KONTO=("Konto", "Kontonavn", "Sum", "Antall"),
        PIVOT_COLS_DEFAULT_HB_KONTO=("Konto", "Kontonavn", "Sum", "Antall"),
        PIVOT_COLS_DEFAULT_SB_KONTO=sb_default,
        PIVOT_COLS_DEFAULT_RL=sb_default,
    )

    # Uten fjorsdata gir SB-konto en slank visning uten 'Endring' —
    # fallback-kolonnen er tilgjengelig via kolonne-menyen.
    out = page_analyse_columns.pivot_default_for_mode(page=page)
    assert out == ("Konto", "Kontonavn", "Sum", "Antall")

from __future__ import annotations

from dataclasses import dataclass


def test_analysepage_on_pivot_select_refreshes_transactions(monkeypatch) -> None:
    """Når bruker klikker konto i pivotlisten, skal transaksjonslisten oppdateres."""
    import page_analyse

    p = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)

    calls = {"tx": 0, "detail": 0}

    def fake_refresh() -> None:
        calls["tx"] += 1

    monkeypatch.setattr(p, "_refresh_transactions_view", fake_refresh, raising=False)
    monkeypatch.setattr(p, "_refresh_detail_panel", lambda: calls.__setitem__("detail", calls["detail"] + 1), raising=False)

    page_analyse.AnalysePage._on_pivot_select(p)

    assert calls == {"tx": 1, "detail": 1}


def test_analysepage_on_pivot_select_is_defensive(monkeypatch) -> None:
    """Hooken skal aldri kaste exception selv om refresh feiler."""
    import page_analyse

    p = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)

    def boom() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(p, "_refresh_transactions_view", boom, raising=False)

    # Skal ikke raise
    page_analyse.AnalysePage._on_pivot_select(p)



def test_analysepage_on_escape_calls_reset_filters(monkeypatch) -> None:
    """Esc skal nullstille filtre (tilsvarer "Nullstill")."""
    import page_analyse

    p = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    calls = {"n": 0}

    def fake_reset() -> None:
        calls["n"] += 1

    monkeypatch.setattr(p, "_reset_filters", fake_reset, raising=False)

    res = page_analyse.AnalysePage._on_escape(p)
    assert res == "break"
    assert calls["n"] == 1


def test_analysepage_on_escape_is_defensive(monkeypatch) -> None:
    """Esc-hooken skal aldri kaste selv om reset feiler."""
    import page_analyse

    p = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)

    def boom() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(p, "_reset_filters", boom, raising=False)

    # Skal ikke raise
    res = page_analyse.AnalysePage._on_escape(p)
    assert res == "break"
# ---------------------------------------------------------------------------
# UI builder regression tests (headless)
# ---------------------------------------------------------------------------


class DummyVar:
    def __init__(self, master=None, value=None):
        self._value = value
        self.trace_calls: list[tuple[str, object]] = []

    def get(self):
        return self._value

    def set(self, value):
        self._value = value

    def trace_add(self, mode: str, callback):
        self.trace_calls.append((mode, callback))
        return f"trace-{len(self.trace_calls)}"

    def trace(self, mode: str, callback):
        self.trace_calls.append((mode, callback))
        return f"trace-{len(self.trace_calls)}"


class DummyMenu:
    def __init__(self, master=None, tearoff=False):
        self.master = master
        self.tearoff = tearoff
        self.commands: list[dict[str, object]] = []
        self.separators = 0

    def add_command(self, **kwargs):
        self.commands.append(kwargs)

    def add_separator(self):
        self.separators += 1


class DummyWidget:
    def __init__(self, master=None, **kwargs):
        self.master = master
        self.kwargs = dict(kwargs)
        self.bindings: dict[str, object] = {}
        self._config: dict[str, object] = {}
        self._grid_calls: list[dict[str, object]] = []
        self._pack_calls: list[dict[str, object]] = []

    def pack(self, **kwargs):
        self._pack_calls.append(kwargs)
        return self

    def grid(self, **kwargs):
        self._grid_calls.append(kwargs)
        return self

    def rowconfigure(self, *_a, **_k):
        return None

    def columnconfigure(self, *_a, **_k):
        return None

    # Tk/ttk har også grid_columnconfigure/grid_rowconfigure-aliaser
    def grid_columnconfigure(self, *_a, **_k):
        return None

    def grid_rowconfigure(self, *_a, **_k):
        return None

    def bind(self, seq: str, fn):
        self.bindings[seq] = fn
        return None

    def config(self, **kwargs):
        self._config.update(kwargs)
        return None

    def configure(self, **kwargs):
        self._config.update(kwargs)
        return None

    def __setitem__(self, key: str, value):
        self._config[key] = value

    def __getitem__(self, key: str):
        return self._config[key]


class DummyEntry(DummyWidget):
    pass


class DummyCombobox(DummyWidget):
    pass


class DummyButton(DummyWidget):
    pass


class DummyMenubutton(DummyWidget):
    pass


class DummyCheckbutton(DummyWidget):
    pass


class DummySpinbox(DummyWidget):
    pass


class DummySeparator(DummyWidget):
    pass


class DummyScrollbar(DummyWidget):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)

    def set(self, *_a, **_k):
        return None


class DummyTreeview(DummyWidget):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._columns = tuple(kwargs.get("columns", ()))
        self._headings: dict[str, str] = {}
        self._columns_cfg: dict[str, dict[str, object]] = {}
        self.tag_configs: dict[str, dict[str, object]] = {}
        self._items: list[dict[str, object]] = []

    def __getitem__(self, key: str):
        if key == "columns":
            return self._columns
        return super().__getitem__(key)

    def heading(self, col: str, text: str = "", option: str = "text"):
        # Support both heading(col, text=...) and heading(col, option="text")
        if option == "text" and text:
            self._headings[col] = text
            return None
        if option == "text":
            return self._headings.get(col, col)
        raise KeyError(option)

    def column(self, col: str, **kwargs):
        self._columns_cfg.setdefault(col, {}).update(kwargs)
        return None

    def yview(self, *_a, **_k):
        return None

    def xview(self, *_a, **_k):
        return None

    def tag_configure(self, tag: str, **kwargs):
        self.tag_configs[tag] = dict(kwargs)
        return None

    def get_children(self, *_a, **_k):
        return []

    def item(self, *_a, **_k):
        return {"values": []}

    def identify_region(self, *_a, **_k):
        return "cell"

    def identify_column(self, *_a, **_k):
        return "#1"


class DummyFrame(DummyWidget):
    pass


class DummyLabel(DummyWidget):
    pass


class DummyTkModule:
    StringVar = DummyVar
    IntVar = DummyVar
    BooleanVar = DummyVar
    Menu = DummyMenu


class DummyTtkModule:
    Frame = DummyFrame
    Label = DummyLabel
    Entry = DummyEntry
    Combobox = DummyCombobox
    Button = DummyButton
    Menubutton = DummyMenubutton
    Checkbutton = DummyCheckbutton
    Spinbox = DummySpinbox
    Separator = DummySeparator
    Treeview = DummyTreeview
    Scrollbar = DummyScrollbar


@dataclass
class _DirOpt:
    label: str


class DummyPage:
    def __init__(self):
        self.calls: dict[str, int] = {}
        self._suspend_live_filter = False

        # Pre-definer vars for å sjekke trace_add/trace
        self._var_search = DummyVar(value="")
        self._var_direction = DummyVar(value="Alle")
        self._var_bilag = DummyVar(value="")
        self._var_motpart = DummyVar(value="")
        self._var_date_from = DummyVar(value="")
        self._var_date_to = DummyVar(value="")
        self._var_min = DummyVar(value="")
        self._var_max = DummyVar(value="")
        self._var_mva_code = DummyVar(value="")
        self._var_mva_mode = DummyVar(value="Alle")
        self._var_max_rows = DummyVar(value=200)
        self._series_vars = [DummyVar(value=0) for _ in range(10)]

    def _inc(self, key: str) -> None:
        self.calls[key] = self.calls.get(key, 0) + 1

    # Methods used by build_ui wiring
    def _reset_filters(self):
        self._inc("reset")

    def _select_all_accounts(self):
        self._inc("select_all")

    def _send_to_utvalg(self):
        self._inc("send_utvalg")

    def _open_motpost_analysis(self):
        self._inc("motpost")

    def _open_nr_series_control(self):
        self._inc("nr_series")

    def _open_override_checks(self):
        self._inc("override")

    def _open_mva_config(self):
        self._inc("mva_config")

    def _open_tx_column_chooser(self):
        self._inc("columns")

    def _reset_tx_columns_to_default(self):
        self._inc("columns_reset")

    def _bind_entry_select_all(self, _entry):
        self._inc("bind_entry_select_all")

    def _schedule_apply_filters(self):
        self._inc("schedule")

    def _apply_filters_now(self):
        self._inc("apply_now")

    def _on_live_filter_var_changed(self):
        self._inc("live_var_changed")

    def _on_max_rows_changed(self):
        self._inc("max_rows_changed")

    def _refresh_transactions_view(self):
        self._inc("refresh_tx")

    def _on_pivot_select(self):
        self._inc("pivot_select")

    def _on_tx_select(self):
        self._inc("tx_select")

    def _on_tx_tree_mouse_press(self, _event=None):
        self._inc("tx_press")

    def _on_tx_tree_mouse_drag(self, _event=None):
        self._inc("tx_drag")

    def _open_bilag_drilldown_from_tx_selection(self):
        self._inc("drilldown")

    def _open_rl_drilldown_from_pivot_selection(self):
        self._inc("rl_drilldown")

    def _enable_tx_sorting(self):
        self._inc("enable_tx_sort")

    def _enable_pivot_sorting(self):
        self._inc("enable_pivot_sort")

    def _bind_shortcuts(self, **_kwargs):
        self._inc("bind_shortcuts")


def test_build_ui_restores_missing_analyse_features() -> None:
    """Verifiser at Analyse-UI har bindings/konfig som ofte regresserer."""
    import page_analyse_ui

    page = DummyPage()

    page_analyse_ui.build_ui(
        page=page,
        tk=DummyTkModule,
        ttk=DummyTtkModule,
        dir_options=[_DirOpt("Alle"), _DirOpt("Debet"), _DirOpt("Kredit")],
    )

    # 1) Pivot-tree skal støtte multi-select
    assert page._pivot_tree.kwargs.get("selectmode") == "extended"

    # 2) Negativt beløp tag skal være definert (rød tekst)
    assert "neg" in page._tx_tree.tag_configs
    assert page._tx_tree.tag_configs["neg"].get("foreground") == "red"
    assert "sumline" in page._pivot_tree.tag_configs

    # 3) Konto-klikk skal trigge pivot hook
    assert "<<TreeviewSelect>>" in page._pivot_tree.bindings
    page._pivot_tree.bindings["<<TreeviewSelect>>"](None)
    assert page.calls.get("pivot_select", 0) == 1

    assert "<Return>" in page._pivot_tree.bindings
    page._pivot_tree.bindings["<Return>"](None)
    assert page.calls.get("rl_drilldown", 0) == 1

    # 4) Enter i søkefelt skal apply filtre nå
    assert "<Return>" in page._ent_search.bindings
    page._ent_search.bindings["<Return>"](None)
    assert page.calls.get("apply_now", 0) == 1

    menu = page._actions_menu
    labels = [str(cmd.get("label")) for cmd in menu.commands]
    assert "Nr.-seriekontroll (valgt scope)" in labels
    for cmd in menu.commands:
        if cmd.get("label") == "Nr.-seriekontroll (valgt scope)":
            cmd.get("command")()
            break
    assert page.calls.get("nr_series", 0) == 1

    # 5) Bilag drilldown via dobbelklikk/Enter på transaksjoner
    assert "<Double-1>" in page._tx_tree.bindings
    res = page._tx_tree.bindings["<Double-1>"](None)
    assert res == "break"
    assert page.calls.get("drilldown", 0) == 1

    assert "<Return>" in page._tx_tree.bindings
    res2 = page._tx_tree.bindings["<Return>"](None)
    assert res2 == "break"
    assert page.calls.get("drilldown", 0) == 2
    assert "<ButtonPress-1>" in page._tx_tree.bindings
    page._tx_tree.bindings["<ButtonPress-1>"](None)
    assert page.calls.get("tx_press", 0) == 1
    assert "<B1-Motion>" in page._tx_tree.bindings
    page._tx_tree.bindings["<B1-Motion>"](None)
    assert page.calls.get("tx_drag", 0) == 1

    # 6) trace_add/trace for live filter + max rows
    assert page._var_search.trace_calls, "Forventer variabel-trace på _var_search"
    assert page._var_min.trace_calls, "Forventer variabel-trace på _var_min"
    assert page._var_max.trace_calls, "Forventer variabel-trace på _var_max"
    assert page._var_max_rows.trace_calls, "Forventer variabel-trace på _var_max_rows"

    # 7) sorting + shortcuts kalles som best-effort
    assert page.calls.get("enable_pivot_sort", 0) == 1
    assert page.calls.get("enable_tx_sort", 0) == 1
    assert page.calls.get("bind_shortcuts", 0) == 1

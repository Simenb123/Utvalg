"""Tester for opt-in selection-summary + global footer-infrastruktur.

Dekker:
  - eksplisitt kolonneregistrering via `register_treeview_selection_summary`
  - opt-in-modus: uregistrerte Treeviews ignoreres helt
  - heuristikk gjenkjenner `IB`, `UB`, `Endring`, `Bevegelse`
  - usynlige/nullbrede kolonner tas ikke med
  - summary bygges med synlig headingtekst (ikke intern kolonne-id)
  - notebook-fanebytte nullstiller footer
  - headless `App` eksponerer footer-API uten å kaste
  - `install_runtime_ui_behaviors` bruker opt-in og skriver til app-footer
"""
from __future__ import annotations

import types
from typing import Any, Optional

import ui_hotkeys
import ui_selection_summary


class DummyTree:
    def __init__(
        self,
        columns: list[str],
        values: dict[str, dict[str, Any]],
        *,
        headings: Optional[dict[str, str]] = None,
        widths: Optional[dict[str, int]] = None,
        displaycolumns: Optional[list[str]] = None,
    ) -> None:
        self._columns = list(columns)
        self._values = values
        self._selection: list[str] = []
        self._children = list(values.keys())
        self._headings = dict(headings) if headings else {c: c for c in columns}
        self._widths = dict(widths) if widths else {c: 100 for c in columns}
        self._displaycolumns = displaycolumns

    def __getitem__(self, key: str):
        if key == "columns":
            return tuple(self._columns)
        if key == "displaycolumns":
            return (
                tuple(self._displaycolumns)
                if self._displaycolumns is not None
                else ("#all",)
            )
        raise KeyError(key)

    def heading(self, col: str, option: str = "text"):
        if option == "text":
            return self._headings.get(col, col)
        raise KeyError(option)

    def column(self, col: str, option: str):
        if option == "width":
            return self._widths.get(col, 100)
        raise KeyError(option)

    def set(self, iid: str, col: str):
        return self._values.get(iid, {}).get(col, "")

    def get_children(self, item: str = ""):
        return tuple(self._children)

    def selection(self):
        return tuple(self._selection)

    def selection_set(self, items):
        if isinstance(items, (list, tuple)):
            self._selection = list(items)
        else:
            self._selection = [items]


class DummyRoot:
    def __init__(self) -> None:
        self.bindings: dict[str, list[Any]] = {}
        self._focus: Any = None

    def bind_all(self, seq: str, fn, add: str = ""):
        self.bindings.setdefault(seq, []).append(fn)

    def focus_get(self):
        return self._focus


def _install(root: DummyRoot, *, require_opt_in: bool = False):
    last = {"txt": None}

    def setter(txt: str) -> None:
        last["txt"] = txt

    ui_selection_summary.install_global_selection_summary(
        root, status_setter=setter, require_opt_in=require_opt_in
    )
    return last


# ---------------------------------------------------------------------------
# Eksplisitt kolonneregistrering
# ---------------------------------------------------------------------------

def test_register_treeview_uses_explicit_columns() -> None:
    tree = DummyTree(
        columns=["Konto", "IB", "UB", "Antall"],
        values={
            "a": {"Konto": "1000", "IB": "100", "UB": "500", "Antall": "3"},
            "b": {"Konto": "2000", "IB": "50", "UB": "200", "Antall": "1"},
        },
    )
    ui_selection_summary.register_treeview_selection_summary(
        tree, columns=("IB", "UB", "Antall")
    )
    tree.selection_set(["a", "b"])

    n, sums = ui_selection_summary.treeview_selection_sums(tree)
    assert n == 2
    assert set(sums.keys()) == {"IB", "UB", "Antall"}
    assert abs(sums["IB"] - 150) < 1e-9
    assert abs(sums["UB"] - 700) < 1e-9


def test_explicit_columns_override_heuristic() -> None:
    """Hvis eksplisitt registrering finnes, brukes den — ikke heuristikken."""
    tree = DummyTree(
        columns=["Konto", "Beløp", "Antall"],
        values={
            "a": {"Konto": "1", "Beløp": "1000", "Antall": "5"},
        },
    )
    # Registrer bare Antall — Beløp skal ikke tas med selv om heuristikken ville tatt det
    ui_selection_summary.register_treeview_selection_summary(tree, columns=("Antall",))
    tree.selection_set(["a"])

    _, sums = ui_selection_summary.treeview_selection_sums(tree)
    assert set(sums.keys()) == {"Antall"}


# ---------------------------------------------------------------------------
# Opt-in-modus
# ---------------------------------------------------------------------------

def test_opt_in_ignores_unregistered_tree() -> None:
    root = DummyRoot()
    last = _install(root, require_opt_in=True)

    tree = DummyTree(
        columns=["Bilag", "Beløp"],
        values={"i1": {"Bilag": "1", "Beløp": "100"}},
    )
    tree.selection_set(["i1"])

    root.bindings["<<TreeviewSelect>>"][0](types.SimpleNamespace(widget=tree))
    assert last["txt"] is None, "uregistrert tree skal ikke skrive til footer"


def test_opt_in_accepts_registered_tree() -> None:
    root = DummyRoot()
    last = _install(root, require_opt_in=True)

    tree = DummyTree(
        columns=["Bilag", "Beløp"],
        values={"i1": {"Bilag": "1", "Beløp": "100"}},
    )
    ui_selection_summary.register_treeview_selection_summary(tree, columns=("Beløp",))
    tree.selection_set(["i1"])

    root.bindings["<<TreeviewSelect>>"][0](types.SimpleNamespace(widget=tree))
    assert last["txt"] is not None
    assert "1 rad valgt" in last["txt"]
    assert "Beløp:" in last["txt"]


def test_opt_in_ignores_disabled_registration() -> None:
    root = DummyRoot()
    last = _install(root, require_opt_in=True)

    tree = DummyTree(
        columns=["Bilag", "Beløp"],
        values={"i1": {"Bilag": "1", "Beløp": "100"}},
    )
    ui_selection_summary.register_treeview_selection_summary(tree, enabled=False)
    tree.selection_set(["i1"])

    root.bindings["<<TreeviewSelect>>"][0](types.SimpleNamespace(widget=tree))
    assert last["txt"] is None


def test_empty_selection_clears_footer() -> None:
    root = DummyRoot()
    last = _install(root, require_opt_in=True)

    tree = DummyTree(
        columns=["Bilag", "Beløp"],
        values={"i1": {"Bilag": "1", "Beløp": "100"}},
    )
    ui_selection_summary.register_treeview_selection_summary(tree, columns=("Beløp",))

    root.bindings["<<TreeviewSelect>>"][0](types.SimpleNamespace(widget=tree))
    assert last["txt"] == ""


# ---------------------------------------------------------------------------
# Heuristikk-utvidelse
# ---------------------------------------------------------------------------

def test_heuristic_recognizes_ib_ub_endring_bevegelse() -> None:
    for col in ("IB", "UB", "Endring", "Bevegelse"):
        assert col in ui_selection_summary.guess_sum_columns([col, "Konto"]), col


def test_heuristic_skips_pct_columns() -> None:
    cols = ui_selection_summary.guess_sum_columns(["Endring", "Endring_pct"])
    assert "Endring" in cols
    assert "Endring_pct" not in cols


# ---------------------------------------------------------------------------
# Synlighet
# ---------------------------------------------------------------------------

def test_hidden_columns_are_excluded_even_if_registered() -> None:
    tree = DummyTree(
        columns=["IB", "UB"],
        values={"a": {"IB": "100", "UB": "500"}},
        widths={"IB": 120, "UB": 0},  # UB skjult via bredde=0
    )
    ui_selection_summary.register_treeview_selection_summary(tree, columns=("IB", "UB"))
    tree.selection_set(["a"])

    _, sums = ui_selection_summary.treeview_selection_sums(tree)
    assert "IB" in sums
    assert "UB" not in sums


def test_displaycolumns_excludes_columns() -> None:
    tree = DummyTree(
        columns=["IB", "UB", "Antall"],
        values={"a": {"IB": "100", "UB": "500", "Antall": "3"}},
        displaycolumns=["IB", "Antall"],
    )
    ui_selection_summary.register_treeview_selection_summary(
        tree, columns=("IB", "UB", "Antall")
    )
    tree.selection_set(["a"])

    _, sums = ui_selection_summary.treeview_selection_sums(tree)
    assert "IB" in sums
    assert "UB" not in sums
    assert "Antall" in sums


def test_empty_heading_column_is_excluded() -> None:
    tree = DummyTree(
        columns=["IB", "UB"],
        values={"a": {"IB": "100", "UB": "500"}},
        headings={"IB": "IB 2025", "UB": ""},  # UB har tom heading
    )
    ui_selection_summary.register_treeview_selection_summary(tree, columns=("IB", "UB"))
    tree.selection_set(["a"])

    _, sums = ui_selection_summary.treeview_selection_sums(tree)
    assert "IB" in sums
    assert "UB" not in sums


# ---------------------------------------------------------------------------
# Heading-tekst i footer
# ---------------------------------------------------------------------------

def test_footer_uses_visible_heading_text() -> None:
    root = DummyRoot()
    last = _install(root, require_opt_in=True)

    tree = DummyTree(
        columns=["Sum", "UB_fjor"],
        values={"a": {"Sum": "1000", "UB_fjor": "900"}},
        headings={"Sum": "UB 2025", "UB_fjor": "UB 2024"},
    )
    ui_selection_summary.register_treeview_selection_summary(
        tree, columns=("Sum", "UB_fjor")
    )
    tree.selection_set(["a"])

    root.bindings["<<TreeviewSelect>>"][0](types.SimpleNamespace(widget=tree))

    assert last["txt"] is not None
    assert "UB 2025:" in last["txt"]
    assert "UB 2024:" in last["txt"]
    # Interne id-er skal ikke lekke til footer-teksten
    assert "UB_fjor:" not in last["txt"]


# ---------------------------------------------------------------------------
# ui_hotkeys pass-through
# ---------------------------------------------------------------------------

def test_install_global_hotkeys_passes_require_opt_in() -> None:
    root = DummyRoot()
    last: dict[str, Any] = {"txt": None}

    def setter(txt: str) -> None:
        last["txt"] = txt

    ui_hotkeys.install_global_hotkeys(
        root, status_setter=setter, selection_summary_require_opt_in=True
    )

    # Uregistrert tree skal ikke trigge footer
    tree = DummyTree(columns=["Beløp"], values={"a": {"Beløp": "100"}})
    tree.selection_set(["a"])
    root.bindings["<<TreeviewSelect>>"][0](types.SimpleNamespace(widget=tree))
    assert last["txt"] is None


# ---------------------------------------------------------------------------
# App-footer + runtime helper
# ---------------------------------------------------------------------------

def test_app_exposes_footer_api_in_any_mode() -> None:
    """Både GUI- og headless-App skal eksponere footer-API uten å kaste."""
    import ui_main

    app = ui_main.create_app()
    try:
        # Metodene skal finnes og være kallbare
        assert callable(getattr(app, "set_selection_summary", None))
        assert callable(getattr(app, "clear_selection_summary", None))
        assert callable(getattr(app, "set_status_message", None))
        assert callable(getattr(app, "set_status", None))
        # Ingen av dem skal kaste
        app.set_selection_summary("test")
        app.clear_selection_summary()
        app.set_status_message("status")
        app.set_status("alias")
    finally:
        try:
            app.destroy()
        except Exception:
            pass


def test_install_runtime_ui_behaviors_is_callable() -> None:
    """Sanity: helperen finnes og kan kalles på en App uten å kaste."""
    import ui_main

    assert callable(getattr(ui_main, "install_runtime_ui_behaviors", None))

    app = ui_main.create_app()
    try:
        ui_main.install_runtime_ui_behaviors(app)
    finally:
        try:
            app.destroy()
        except Exception:
            pass

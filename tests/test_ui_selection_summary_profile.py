"""Tester for v1.1 footer-polish: profil-styrt rendering av selection-summary.

Dekker:
  - `build_selection_summary_text` bruker `{N} {noun} valgt`-format
  - `hide_zero` skjuler nullsummer
  - `max_items` capper antall viste summer
  - `priority` styrer rekkefølge
  - registreringsprofil med row_noun/max_items/hide_zero/priority_columns
  - callable `priority_columns` evalueres på hvert selection-event
  - Analyse-registreringer har forventet profil per tre/modus
"""
from __future__ import annotations

import types
from typing import Any, Optional

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

    def bind_all(self, seq: str, fn, add: str = ""):
        self.bindings.setdefault(seq, []).append(fn)


def _install(root: DummyRoot, *, require_opt_in: bool = True):
    last = {"txt": None}

    def setter(txt: str) -> None:
        last["txt"] = txt

    ui_selection_summary.install_global_selection_summary(
        root, status_setter=setter, require_opt_in=require_opt_in
    )
    return last


# ---------------------------------------------------------------------------
# build_selection_summary_text: nytt format + row_noun
# ---------------------------------------------------------------------------

def test_format_singular_row() -> None:
    txt = ui_selection_summary.build_selection_summary_text(1, {})
    assert txt == "1 rad valgt"


def test_format_plural_rows() -> None:
    txt = ui_selection_summary.build_selection_summary_text(5, {})
    assert txt == "5 rader valgt"


def test_format_kontoer() -> None:
    assert (
        ui_selection_summary.build_selection_summary_text(1, {}, row_noun="kontoer")
        == "1 konto valgt"
    )
    assert (
        ui_selection_summary.build_selection_summary_text(3, {}, row_noun="kontoer")
        == "3 kontoer valgt"
    )


def test_format_transaksjoner() -> None:
    assert (
        ui_selection_summary.build_selection_summary_text(
            1, {}, row_noun="transaksjoner"
        )
        == "1 transaksjon valgt"
    )
    assert (
        ui_selection_summary.build_selection_summary_text(
            4, {}, row_noun="transaksjoner"
        )
        == "4 transaksjoner valgt"
    )


def test_hide_zero_drops_zero_sum() -> None:
    txt = ui_selection_summary.build_selection_summary_text(
        3,
        {"Sum": 1000.0, "MVA": 0.0},
        hide_zero=True,
    )
    assert "Sum:" in txt
    assert "MVA:" not in txt


def test_hide_zero_false_keeps_zero() -> None:
    txt = ui_selection_summary.build_selection_summary_text(
        3, {"Sum": 0.0, "Antall": 5.0}, hide_zero=False
    )
    assert "Sum:" in txt
    assert "Antall:" in txt


def test_max_items_caps_output() -> None:
    sums = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0}
    txt = ui_selection_summary.build_selection_summary_text(
        2, sums, priority=("A", "B", "C", "D"), max_items=2
    )
    # Teller pipe-separerte deler utenom "N rader valgt"
    parts = txt.split(" | ")
    assert parts[0].endswith("valgt")
    assert len(parts) == 1 + 2  # antall + to summer


def test_priority_controls_order() -> None:
    sums = {"Endring": 10.0, "UB 2025": 500.0, "UB 2024": 400.0}
    txt = ui_selection_summary.build_selection_summary_text(
        3,
        sums,
        priority=("UB 2025", "UB 2024", "Endring"),
        max_items=3,
    )
    # Rekkefølge speiler priority
    idx_ub = txt.index("UB 2025:")
    idx_ub_fjor = txt.index("UB 2024:")
    idx_endring = txt.index("Endring:")
    assert idx_ub < idx_ub_fjor < idx_endring


def test_only_count_when_no_sums_left() -> None:
    # Alle summer er null og hide_zero=True -> bare radtelling
    txt = ui_selection_summary.build_selection_summary_text(
        2, {"Sum": 0.0, "Antall": 0.0}, hide_zero=True
    )
    assert txt == "2 rader valgt"


# ---------------------------------------------------------------------------
# Registreringsprofil
# ---------------------------------------------------------------------------

def test_registration_profile_applied_in_footer() -> None:
    root = DummyRoot()
    last = _install(root)

    tree = DummyTree(
        columns=["Sum", "UB_fjor", "Endring_fjor", "IB", "Antall"],
        values={
            "a": {
                "Sum": "1000", "UB_fjor": "900", "Endring_fjor": "100",
                "IB": "50", "Antall": "3",
            },
        },
        headings={
            "Sum": "UB 2025",
            "UB_fjor": "UB 2024",
            "Endring_fjor": "Endring",
            "IB": "IB",
            "Antall": "Antall",
        },
    )
    ui_selection_summary.register_treeview_selection_summary(
        tree,
        columns=("Sum", "UB_fjor", "Endring_fjor", "IB", "Antall"),
        priority_columns=("Sum", "UB_fjor", "Endring_fjor"),
        row_noun="rader",
        max_items=3,
        hide_zero=True,
    )
    tree.selection_set(["a"])

    root.bindings["<<TreeviewSelect>>"][0](types.SimpleNamespace(widget=tree))

    txt = last["txt"]
    assert txt is not None
    assert txt.startswith("1 rad valgt")
    assert "UB 2025:" in txt
    assert "UB 2024:" in txt
    assert "Endring:" in txt
    # IB og Antall skal ikke vises når priority dekker nok
    assert "IB:" not in txt
    assert "Antall:" not in txt


def test_callable_priority_columns_resolved_per_event() -> None:
    """Callable resolver skal evalueres på hvert event — simuler modusbytte."""
    root = DummyRoot()
    last = _install(root)

    tree = DummyTree(
        columns=["Sum", "UB_fjor", "Endring_fjor", "Endring", "Antall"],
        values={
            "a": {
                "Sum": "1000", "UB_fjor": "900", "Endring_fjor": "100",
                "Endring": "50", "Antall": "3",
            },
        },
        headings={
            "Sum": "UB 2025",
            "UB_fjor": "UB 2024",
            "Endring_fjor": "Endring",
            "Endring": "Bevegelse",
            "Antall": "Antall",
        },
    )

    mode = {"current": "with_prev"}

    def resolver(_tree):
        if mode["current"] == "with_prev":
            return ("Sum", "UB_fjor", "Endring_fjor")
        return ("Sum", "Endring")

    ui_selection_summary.register_treeview_selection_summary(
        tree,
        columns=("Sum", "UB_fjor", "Endring_fjor", "Endring", "Antall"),
        priority_columns=resolver,
        row_noun="rader",
        max_items=3,
        hide_zero=True,
    )
    tree.selection_set(["a"])

    # Modus 1: med fjorår
    root.bindings["<<TreeviewSelect>>"][0](types.SimpleNamespace(widget=tree))
    assert last["txt"] is not None
    assert "UB 2024:" in last["txt"]

    # Modus 2: uten fjorår — samme tree, callable får nytt svar
    mode["current"] = "no_prev"
    last["txt"] = None
    root.bindings["<<TreeviewSelect>>"][0](types.SimpleNamespace(widget=tree))
    assert last["txt"] is not None
    assert "UB 2024:" not in last["txt"]
    assert "Bevegelse:" in last["txt"]


def test_tx_tree_profile_hides_zero_mva() -> None:
    root = DummyRoot()
    last = _install(root)

    tree = DummyTree(
        columns=["Beløp", "MVA-beløp"],
        values={
            "a": {"Beløp": "1000", "MVA-beløp": "0"},
            "b": {"Beløp": "500", "MVA-beløp": "0"},
        },
    )
    ui_selection_summary.register_treeview_selection_summary(
        tree,
        columns=("Beløp", "MVA-beløp"),
        priority_columns=("Beløp", "MVA-beløp"),
        row_noun="transaksjoner",
        max_items=2,
        hide_zero=True,
    )
    tree.selection_set(["a", "b"])

    root.bindings["<<TreeviewSelect>>"][0](types.SimpleNamespace(widget=tree))

    txt = last["txt"]
    assert txt is not None
    assert txt.startswith("2 transaksjoner valgt")
    assert "Beløp:" in txt
    assert "MVA-beløp:" not in txt


def test_sb_tree_profile_hides_ib() -> None:
    root = DummyRoot()
    last = _install(root)

    tree = DummyTree(
        columns=["IB", "Endring", "UB", "UB_fjor", "Antall"],
        values={
            "a": {
                "IB": "100", "Endring": "50", "UB": "150",
                "UB_fjor": "120", "Antall": "7",
            },
        },
        headings={
            "IB": "IB", "Endring": "Endring", "UB": "UB",
            "UB_fjor": "UB i fjor", "Antall": "Antall",
        },
    )
    ui_selection_summary.register_treeview_selection_summary(
        tree,
        columns=("IB", "Endring", "UB", "UB_fjor", "Antall"),
        priority_columns=("UB", "UB_fjor", "Endring"),
        row_noun="kontoer",
        max_items=3,
        hide_zero=True,
    )
    tree.selection_set(["a"])

    root.bindings["<<TreeviewSelect>>"][0](types.SimpleNamespace(widget=tree))

    txt = last["txt"]
    assert txt is not None
    assert txt.startswith("1 konto valgt")
    assert "UB:" in txt
    assert "UB i fjor:" in txt
    assert "Endring:" in txt
    # IB skal ikke dukke opp siden priority ikke inkluderer det
    assert "IB:" not in txt


# ---------------------------------------------------------------------------
# Sanity på Analyse-registreringer
# ---------------------------------------------------------------------------

def test_page_analyse_ui_registers_profiles_with_correct_row_nouns() -> None:
    """Sanity: Analyse-siden registrerer profiler med forventede row_noun."""
    import importlib
    import tkinter as tk

    try:
        root = tk.Tk()
    except Exception:
        import pytest
        pytest.skip("Tk not available in this environment")

    try:
        # Bygg en minimal dummy page og kjør registrerings-kodepathen indirekte
        # ved å instansiere AnalysePage (som kaller build_ui).
        import page_analyse

        page = page_analyse.AnalysePage(root)

        # Hent tre registreringsprofiler via selection-summary config-attribut
        from ui_selection_summary import _SelectionSummaryConfig, _REGISTRATION_ATTR

        pivot_cfg = getattr(page._pivot_tree, _REGISTRATION_ATTR, None)
        tx_cfg = getattr(page._tx_tree, _REGISTRATION_ATTR, None)
        assert isinstance(pivot_cfg, _SelectionSummaryConfig)
        assert isinstance(tx_cfg, _SelectionSummaryConfig)

        assert pivot_cfg.row_noun == "rader"
        assert pivot_cfg.max_items == 3
        assert pivot_cfg.hide_zero is True
        assert callable(pivot_cfg.priority_columns)

        assert tx_cfg.row_noun == "transaksjoner"
        assert tx_cfg.max_items == 2
        assert tx_cfg.hide_zero is True

        sb_tree = getattr(page, "_sb_tree", None)
        if sb_tree is not None:
            sb_cfg = getattr(sb_tree, _REGISTRATION_ATTR, None)
            assert isinstance(sb_cfg, _SelectionSummaryConfig)
            assert sb_cfg.row_noun == "kontoer"
            # IB ikke i priority
            assert "IB" not in tuple(sb_cfg.priority_columns or ())
    finally:
        try:
            root.destroy()
        except Exception:
            pass

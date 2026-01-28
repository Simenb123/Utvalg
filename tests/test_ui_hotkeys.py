from __future__ import annotations

import types
from typing import Any

import ui_hotkeys
import ui_selection_summary


class DummyTree:
    def __init__(self, columns: list[str], values: dict[str, dict[str, Any]]):
        self._columns = list(columns)
        self._values = values
        self._selection: list[str] = []
        self._children = list(values.keys())
        self._headings = {c: c for c in columns}

    def __getitem__(self, key: str):
        if key == "columns":
            return tuple(self._columns)
        raise KeyError(key)

    def heading(self, col: str, option: str = "text"):
        if option == "text":
            return self._headings.get(col, col)
        raise KeyError(option)

    def set(self, iid: str, col: str):
        return self._values.get(iid, {}).get(col, "")

    def get_children(self, item: str = ""):
        return tuple(self._children)

    def selection(self):
        return tuple(self._selection)

    def selection_set(self, items):
        # ttk.Treeview lar både enkelt-iid og liste; vi støtter begge.
        if isinstance(items, (list, tuple)):
            self._selection = list(items)
        else:
            self._selection = [items]


class DummyListbox:
    def __init__(self, items: list[str]):
        self._items = list(items)
        self._sel: list[int] = []

    def size(self) -> int:
        return len(self._items)

    def selection_set(self, a: int, b: int | None = None):
        if b is None:
            self._sel = [a]
        else:
            self._sel = list(range(a, b + 1))

    def curselection(self):
        return tuple(self._sel)

    def get(self, idx: int):
        return self._items[idx]


class DummyRoot:
    def __init__(self):
        self.bindings: dict[str, list[Any]] = {}
        self._focus: Any = None
        self.clipboard: str = ""

    def bind_all(self, seq: str, fn, add: str = ""):
        self.bindings.setdefault(seq, []).append(fn)

    def focus_get(self):
        return self._focus

    def clipboard_clear(self):
        self.clipboard = ""

    def clipboard_append(self, txt: str):
        self.clipboard = txt


def test_guess_sum_columns_prefers_belop() -> None:
    cols = ["Bilag", "Beløp", "Tekst", "Konto"]
    assert ui_selection_summary.guess_sum_columns(cols) == ["Beløp"]


def test_treeview_selection_sums_parses_norwegian_numbers() -> None:
    tree = DummyTree(
        columns=["Bilag", "Beløp"],
        values={
            "i1": {"Bilag": "1", "Beløp": "1 234,50"},
            "i2": {"Bilag": "2", "Beløp": "-200,00"},
            "i3": {"Bilag": "3", "Beløp": "(34,50)"},
        },
    )
    tree.selection_set(["i1", "i2", "i3"])

    n, sums = ui_selection_summary.treeview_selection_sums(tree)
    assert n == 3
    assert set(sums.keys()) == {"Beløp"}
    assert abs(float(sums["Beløp"]) - (1234.50 - 200.00 - 34.50)) < 1e-9


def test_treeview_selection_to_tsv_default_has_no_header() -> None:
    tree = DummyTree(
        columns=["Konto", "Sum"],
        values={
            "a": {"Konto": "1000", "Sum": "10"},
            "b": {"Konto": "2000", "Sum": "20"},
        },
    )
    tree.selection_set(["a", "b"])
    tsv = ui_hotkeys.treeview_selection_to_tsv(tree)
    lines = tsv.splitlines()
    assert lines[0] == "1000\t10"
    assert "2000\t20" in lines


def test_treeview_selection_to_tsv_can_include_header() -> None:
    tree = DummyTree(
        columns=["Konto", "Sum"],
        values={
            "a": {"Konto": "1000", "Sum": "10"},
        },
    )
    tree.selection_set(["a"])
    tsv = ui_hotkeys.treeview_selection_to_tsv(tree, include_headers=True)
    lines = tsv.splitlines()
    assert lines[0] == "Konto\tSum"
    assert lines[1] == "1000\t10"


def test_install_global_hotkeys_ctrl_a_ctrl_c_and_selection_summary() -> None:
    root = DummyRoot()

    tree = DummyTree(
        columns=["Bilag", "Beløp"],
        values={
            "i1": {"Bilag": "1", "Beløp": "100"},
            "i2": {"Bilag": "2", "Beløp": "200"},
        },
    )
    root._focus = tree

    last_status: dict[str, str] = {"txt": ""}

    def set_status(txt: str) -> None:
        last_status["txt"] = txt

    ui_hotkeys.install_global_hotkeys(root, status_setter=set_status)

    # Ctrl+A selects all rows
    ev = types.SimpleNamespace(widget=tree)
    root.bindings["<Control-a>"][0](ev)
    assert set(tree.selection()) == {"i1", "i2"}

    # Ctrl+C copies TSV to clipboard (uten header)
    root.bindings["<Control-c>"][0](ev)
    assert "1\t100" in root.clipboard
    assert "2\t200" in root.clipboard
    assert not root.clipboard.splitlines()[0].startswith("Bilag\t")

    # Ctrl+Shift+C copies TSV med header
    root.bindings["<Control-C>"][0](ev)
    assert root.clipboard.splitlines()[0] == "Bilag\tBeløp"
    assert "1\t100" in root.clipboard

    # Selection summary updates status
    root.bindings["<<TreeviewSelect>>"][0](ev)
    assert "Markert:" in last_status["txt"]
    assert "Beløp:" in last_status["txt"]


def test_listbox_select_all_and_copy_lines() -> None:
    root = DummyRoot()
    lb = DummyListbox(["a", "b", "c"])
    root._focus = lb

    ui_hotkeys.install_global_hotkeys(root)

    ev = types.SimpleNamespace(widget=lb)
    root.bindings["<Control-a>"][0](ev)
    assert lb.curselection() == (0, 1, 2)

    root.bindings["<Control-c>"][0](ev)
    assert root.clipboard.splitlines() == ["a", "b", "c"]

from __future__ import annotations

import pytest

from src.shared.ui.treeview_sort import enable_treeview_sorting


class DummyTree:
    """Minimal Treeview-lignende objekt for å teste sortering uten Tk."""

    def __init__(self, columns: list[str], rows: list[dict[str, str]]):
        self._columns = list(columns)
        self._items = [f"iid{i}" for i in range(len(rows))]
        self._data: dict[str, dict[str, str]] = {}
        for iid, row in zip(self._items, rows):
            self._data[iid] = {col: row.get(col, "") for col in self._columns}

        self._heading_cmds: dict[str, object] = {}
        self._selection: list[str] = []
        self._focus: str = ""

    def __getitem__(self, key: str):
        if key == "columns":
            return tuple(self._columns)
        raise KeyError(key)

    def heading(self, col: str, text: str | None = None, command=None):
        if command is not None:
            self._heading_cmds[col] = command

    def get_children(self, item: str = ""):
        return tuple(self._items)

    def set(self, iid: str, col: str):
        return self._data[iid].get(col, "")

    def move(self, iid: str, parent: str, index: int):
        if iid in self._items:
            self._items.remove(iid)
        self._items.insert(index, iid)

    def selection(self):
        return tuple(self._selection)

    def focus(self, iid: str | None = None):
        if iid is None:
            return self._focus
        self._focus = iid
        return None

    def selection_set(self, selection):
        self._selection = list(selection)


def _values_in_order(tree: DummyTree, col: str) -> list[str]:
    return [tree.set(iid, col) for iid in tree.get_children("")]


def test_sort_dates_ddmmyyyy_is_chronological():
    tree = DummyTree(
        columns=["Dato"],
        rows=[
            {"Dato": "02.01.2025"},
            {"Dato": "31.12.2024"},
            {"Dato": "15.02.2025"},
        ],
    )
    enable_treeview_sorting(tree)

    # Første klikk = stigende
    tree._heading_cmds["Dato"]()
    assert _values_in_order(tree, "Dato") == ["31.12.2024", "02.01.2025", "15.02.2025"]

    # Andre klikk = synkende
    tree._heading_cmds["Dato"]()
    assert _values_in_order(tree, "Dato") == ["15.02.2025", "02.01.2025", "31.12.2024"]


def test_sort_numbers_with_norwegian_formatting():
    tree = DummyTree(
        columns=["Beløp"],
        rows=[
            {"Beløp": "1 200,00"},
            {"Beløp": "-50,00"},
            {"Beløp": "10,00"},
        ],
    )
    enable_treeview_sorting(tree)

    tree._heading_cmds["Beløp"]()
    assert _values_in_order(tree, "Beløp") == ["-50,00", "10,00", "1 200,00"]


def test_sort_mixed_numeric_and_text_keeps_numeric_first_in_mixed_mode():
    # Ikke nok "tall" til å trigge numeric_mode (0.8), så dette går via mixed-sort.
    tree = DummyTree(
        columns=["Bilag"],
        rows=[
            {"Bilag": "A10"},
            {"Bilag": "2"},
            {"Bilag": "10"},
        ],
    )
    enable_treeview_sorting(tree)

    tree._heading_cmds["Bilag"]()
    assert _values_in_order(tree, "Bilag") == ["2", "10", "A10"]


def test_sorting_preserves_selection_and_focus_best_effort():
    tree = DummyTree(
        columns=["Beløp"],
        rows=[
            {"Beløp": "1 000,00"},
            {"Beløp": "2 000,00"},
            {"Beløp": "-1 000,00"},
        ],
    )
    enable_treeview_sorting(tree)

    tree.selection_set(["iid1", "iid2"])
    tree.focus("iid2")

    tree._heading_cmds["Beløp"]()

    assert set(tree.selection()) == {"iid1", "iid2"}
    assert tree.focus() == "iid2"


def test_sorting_can_be_suppressed_once_for_header_drag():
    tree = DummyTree(
        columns=["BelÃ¸p"],
        rows=[
            {"BelÃ¸p": "1 000,00"},
            {"BelÃ¸p": "-1 000,00"},
        ],
    )
    enable_treeview_sorting(tree)

    tree._suppress_next_heading_sort = True
    tree._heading_cmds["BelÃ¸p"]()
    assert _values_in_order(tree, "BelÃ¸p") == ["1 000,00", "-1 000,00"]

    tree._heading_cmds["BelÃ¸p"]()
    assert _values_in_order(tree, "BelÃ¸p") == ["-1 000,00", "1 000,00"]

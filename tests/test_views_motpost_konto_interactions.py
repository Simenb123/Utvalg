from __future__ import annotations

import types
from typing import Any

import views_motpost_konto as vm


class DummyTree:
    def __init__(self, values_by_iid: dict[str, tuple[Any, ...]], y_to_iid: dict[int, str]):
        self._values_by_iid = values_by_iid
        self._y_to_iid = y_to_iid
        self._selection: list[str] = []
        self.config: dict[str, Any] = {}
        self.bindings: dict[str, Any] = {}

    def configure(self, **kwargs):
        self.config.update(kwargs)

    def bind(self, seq: str, fn, add: str | None = None):
        # Vi lagrer bare siste handler per sekvens i testen
        self.bindings[seq] = fn

    def identify_row(self, y: int):
        return self._y_to_iid.get(y, "")

    def selection_set(self, iid):
        self._selection = [iid]

    def selection(self):
        return tuple(self._selection)

    def item(self, iid: str, option: str = "values"):
        if option != "values":
            raise KeyError(option)
        return self._values_by_iid.get(iid, ())


def test_configure_bilag_details_tree_enables_multiselect_and_binds_handlers() -> None:
    tree = DummyTree(values_by_iid={"r1": (323,), "r2": (352,)}, y_to_iid={10: "r1"})
    opened: list[str] = []

    vm.configure_bilag_details_tree(tree, open_bilag_callback=lambda b: opened.append(b))

    assert tree.config.get("selectmode") == "extended"
    assert "<Double-1>" in tree.bindings
    assert "<Return>" in tree.bindings

    # Double click opens the bilag under cursor (y=10 -> r1 -> bilag 323)
    ev = types.SimpleNamespace(y=10)
    tree.bindings["<Double-1>"](ev)
    assert opened == ["323"]
    assert tree.selection() == ("r1",)


def test_enter_opens_first_selected_bilag() -> None:
    tree = DummyTree(values_by_iid={"r1": (323,), "r2": (352,)}, y_to_iid={})
    opened: list[str] = []

    vm.configure_bilag_details_tree(tree, open_bilag_callback=lambda b: opened.append(b))

    tree.selection_set("r2")
    ev = types.SimpleNamespace()
    tree.bindings["<Return>"](ev)
    assert opened == ["352"]

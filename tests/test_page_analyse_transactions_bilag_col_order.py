from __future__ import annotations

from dataclasses import dataclass

from page_analyse_transactions import get_selected_bilag_from_tx_tree


class DummyTree:
    def __init__(self, values_by_item: dict[str, list[str]], *, set_returns: str = "") -> None:
        self._values_by_item = values_by_item
        self._set_returns = set_returns

    def selection(self):
        return tuple(self._values_by_item.keys())

    def set(self, item, col):
        # Kan tvinge fallback-path ved å returnere tom streng
        return self._set_returns

    def item(self, item):
        return {"values": self._values_by_item[item]}


@dataclass
class DummyPage:
    TX_COLS: tuple[str, ...]
    _tx_tree: DummyTree


def test_get_selected_bilag_works_when_bilag_not_first_column() -> None:
    cols = ("Konto", "Kontonavn", "Dato", "Bilag", "Tekst", "Beløp")
    values = ["3000", "Salg", "01.01.2025", "123", "Test", "100,00"]

    tree = DummyTree({"item1": values}, set_returns="")  # force fallback to values[]
    page = DummyPage(TX_COLS=cols, _tx_tree=tree)

    bilag = get_selected_bilag_from_tx_tree(page=page)
    assert bilag == "123"

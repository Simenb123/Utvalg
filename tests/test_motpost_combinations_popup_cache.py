from __future__ import annotations

import pandas as pd

from motpost import combinations_popup


def test_get_drilldown_payload_uses_combo_bilag_map_and_caches_result() -> None:
    popup = combinations_popup._MotkontoCombinationsPopup.__new__(combinations_popup._MotkontoCombinationsPopup)
    popup._drilldown_cache = {}
    popup._combo_to_bilag = {"1500,2700": ["10"]}
    popup._selected_accounts_set = {"3000"}
    popup._selected_direction = "Kredit"
    popup._distribution_mode = lambda: "konto"
    popup._df_scope = pd.DataFrame(
        [
            {"Bilag_str": "10", "Konto_str": "3000", "Bel\u00f8p_num": -100.0, "Tekst": "Salg", "Dato": "2025-01-01"},
            {"Bilag_str": "10", "Konto_str": "1500", "Bel\u00f8p_num": 75.0, "Tekst": "Kunde", "Dato": "2025-01-01"},
            {"Bilag_str": "10", "Konto_str": "2700", "Bel\u00f8p_num": 25.0, "Tekst": "MVA", "Dato": "2025-01-01"},
        ]
    )

    payload_first = popup._get_drilldown_payload("1500,2700")
    payload_second = popup._get_drilldown_payload("1500,2700")

    assert payload_first is payload_second
    assert payload_first["bilag_list"] == ["10"]
    assert float(payload_first["sum_sel"]) == -100.0
    assert float(payload_first["sum_mot"]) == 100.0
    assert float(payload_first["kontroll"]) == 0.0
    assert len(payload_first["df_sel"]) == 1
    assert len(payload_first["df_mot"]) == 2


class _FakeTree:
    def __init__(self) -> None:
        self._children = ["old"]
        self.inserted = []

    def get_children(self):
        return list(self._children)

    def delete(self, *items):
        self._children = []

    def insert(self, *args, **kwargs):
        self.inserted.append({"args": args, "kwargs": kwargs})


def test_populate_account_sum_tree_derives_missing_belop_num() -> None:
    popup = combinations_popup._MotkontoCombinationsPopup.__new__(combinations_popup._MotkontoCombinationsPopup)
    popup._selected_accounts_set = {"3000"}
    popup._konto_regnskapslinje_map = {}
    popup._konto_navn_map = {"1500": "Kundefordringer", "3000": "Salgsinntekt"}
    popup._distribution_mode = lambda: "konto"
    popup._tree_mot = _FakeTree()
    popup._tree_sel = _FakeTree()
    popup._clear_tree = lambda tree: tree.delete(*tree.get_children())

    df_lines = pd.DataFrame(
        [
            {"Konto_str": "1500", "Beløp": 75.0, "Kontonavn": "Kundefordringer"},
            {"Konto_str": "3000", "Beløp": -75.0, "Kontonavn": "Salgsinntekt"},
        ]
    )

    popup._populate_account_sum_tree(popup._tree_mot, df_lines, base_sum=-75.0)

    assert len(popup._tree_mot.inserted) == 2

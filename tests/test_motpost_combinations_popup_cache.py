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


def test_populate_account_sum_tree_with_belop_num_present() -> None:
    """When Beløp_num already exists, it should be used directly (no derivation)."""
    popup = combinations_popup._MotkontoCombinationsPopup.__new__(combinations_popup._MotkontoCombinationsPopup)
    popup._selected_accounts_set = {"3000"}
    popup._konto_regnskapslinje_map = {}
    popup._konto_navn_map = {"1500": "Kundefordringer"}
    popup._distribution_mode = lambda: "konto"
    popup._tree_mot = _FakeTree()
    popup._tree_sel = _FakeTree()
    tree = _FakeTree()
    popup._clear_tree = lambda t: t.delete(*t.get_children())

    df_lines = pd.DataFrame(
        [
            {"Konto_str": "1500", "Beløp_num": 200.0, "Beløp": "wrong", "Kontonavn": "Kundefordringer"},
        ]
    )

    popup._populate_account_sum_tree(tree, df_lines, base_sum=200.0)
    assert len(tree.inserted) == 1


def test_populate_account_sum_tree_empty_df_noop() -> None:
    """Empty DataFrame should not insert any rows."""
    popup = combinations_popup._MotkontoCombinationsPopup.__new__(combinations_popup._MotkontoCombinationsPopup)
    popup._selected_accounts_set = set()
    popup._konto_regnskapslinje_map = {}
    popup._distribution_mode = lambda: "konto"
    popup._tree_mot = _FakeTree()
    popup._tree_sel = _FakeTree()
    tree = _FakeTree()
    popup._clear_tree = lambda t: t.delete(*t.get_children())

    popup._populate_account_sum_tree(tree, pd.DataFrame(), base_sum=0.0)
    assert len(tree.inserted) == 0


# ---------------------------------------------------------------------------
# Tests: build_bilag_rows NaN handling
# ---------------------------------------------------------------------------

def test_build_bilag_rows_nan_dato_tekst() -> None:
    """build_bilag_rows should fill NaN Dato/Tekst with empty string, not 'nan'."""
    from motpost.combinations_popup_helpers import build_bilag_rows

    df_combo = pd.DataFrame([
        {"Bilag_str": "10", "Konto_str": "1500", "Beløp_num": 100.0, "Dato": "2025-01-01", "Tekst": "Salg"},
        {"Bilag_str": "20", "Konto_str": "1500", "Beløp_num": 50.0},  # no Dato/Tekst
    ])
    df_sel = pd.DataFrame([
        {"Bilag_str": "10", "Beløp_num": 100.0},
        {"Bilag_str": "20", "Beløp_num": 50.0},
    ])
    df_mot = pd.DataFrame([
        {"Bilag_str": "10", "Beløp_num": -100.0},
        {"Bilag_str": "20", "Beløp_num": -50.0},
    ])

    result = build_bilag_rows(df_combo, df_sel, df_mot)

    # bilag 20 should have empty Dato/Tekst, not NaN
    row20 = result[result["Bilag"] == "20"].iloc[0]
    assert row20["Dato"] == "" or row20["Dato"] == "2025-01-01" or pd.isna(row20["Dato"]) is False
    assert str(row20["Tekst"]) != "nan"


def test_build_bilag_rows_no_date_column() -> None:
    """build_bilag_rows should handle missing Dato column gracefully."""
    from motpost.combinations_popup_helpers import build_bilag_rows

    df_combo = pd.DataFrame([
        {"Bilag_str": "10", "Konto_str": "1500", "Beløp_num": 100.0, "Tekst": "Salg"},
    ])
    df_sel = pd.DataFrame([{"Bilag_str": "10", "Beløp_num": 100.0}])
    df_mot = pd.DataFrame([{"Bilag_str": "10", "Beløp_num": -100.0}])

    result = build_bilag_rows(df_combo, df_sel, df_mot)
    assert len(result) == 1
    assert result.iloc[0]["Dato"] == ""


# ---------------------------------------------------------------------------
# Tests: _refresh_drilldown_comment / comment display
# ---------------------------------------------------------------------------

class _FakeLabel:
    """Minimal fake for ttk.Label."""
    def __init__(self):
        self.text = ""

    def config(self, **kwargs):
        self.text = kwargs.get("text", self.text)


def test_refresh_drilldown_comment_shows_comment() -> None:
    """_refresh_drilldown_comment should display comment from map."""
    popup = combinations_popup._MotkontoCombinationsPopup.__new__(combinations_popup._MotkontoCombinationsPopup)
    popup._combo_comment_map = {"1500,2700": "Sjekket mot faktura"}
    popup._current_selection = combinations_popup._ComboSelection(combo="1500,2700")
    popup._lbl_combo_comment = _FakeLabel()

    popup._refresh_drilldown_comment()

    assert "Sjekket mot faktura" in popup._lbl_combo_comment.text
    assert popup._lbl_combo_comment.text.startswith("Kommentar:")


def test_refresh_drilldown_comment_empty_when_no_comment() -> None:
    """_refresh_drilldown_comment should clear label when no comment exists."""
    popup = combinations_popup._MotkontoCombinationsPopup.__new__(combinations_popup._MotkontoCombinationsPopup)
    popup._combo_comment_map = {}
    popup._current_selection = combinations_popup._ComboSelection(combo="1500,2700")
    popup._lbl_combo_comment = _FakeLabel()

    popup._refresh_drilldown_comment()

    assert popup._lbl_combo_comment.text == ""


def test_refresh_drilldown_comment_no_selection() -> None:
    """_refresh_drilldown_comment should clear label when no selection."""
    popup = combinations_popup._MotkontoCombinationsPopup.__new__(combinations_popup._MotkontoCombinationsPopup)
    popup._combo_comment_map = {"1500,2700": "Test"}
    popup._current_selection = None
    popup._lbl_combo_comment = _FakeLabel()

    popup._refresh_drilldown_comment()

    assert popup._lbl_combo_comment.text == ""


def test_update_drilldown_sets_comment_label() -> None:
    """_popup_update_drilldown should set the comment label for the selected combo."""
    popup = combinations_popup._MotkontoCombinationsPopup.__new__(combinations_popup._MotkontoCombinationsPopup)
    popup._drilldown_cache = {}
    popup._combo_to_bilag = {"1500,2700": ["10"]}
    popup._selected_accounts_set = {"3000"}
    popup._selected_direction = "Kredit"
    popup._distribution_mode = lambda: "konto"
    popup._konto_regnskapslinje_map = {}
    popup._konto_navn_map = {"1500": "Kundefordringer", "3000": "Salgsinntekt"}
    popup._combo_comment_map = {"1500,2700": "Verifisert"}
    popup._lbl_combo_comment = _FakeLabel()
    popup._lbl_combo = _FakeLabel()
    popup._lbl_vis_info = _FakeLabel()
    popup._lbl_sel_total = _FakeLabel()
    popup._lbl_mot_total = _FakeLabel()
    popup._tree_sel = _FakeTree()
    popup._tree_mot = _FakeTree()
    popup._tree_bilag = _FakeTree()
    popup._bilag_rows_cache = None
    popup._clear_tree = lambda t: t.delete(*t.get_children())
    popup._df_scope = pd.DataFrame([
        {"Bilag_str": "10", "Konto_str": "3000", "Beløp_num": -100.0, "Tekst": "Salg", "Dato": "2025-01-01"},
        {"Bilag_str": "10", "Konto_str": "1500", "Beløp_num": 100.0, "Tekst": "Kunde", "Dato": "2025-01-01"},
    ])

    selection = combinations_popup._ComboSelection(combo="1500,2700")
    combinations_popup._popup_update_drilldown(popup, selection)

    assert "Verifisert" in popup._lbl_combo_comment.text

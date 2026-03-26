from __future__ import annotations

import pandas as pd

from page_analyse_transactions import refresh_transactions_view


class DummyVar:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value


class DummyLabel:
    def __init__(self) -> None:
        self.text = ""

    def config(self, **kwargs) -> None:
        self.text = str(kwargs.get("text", ""))


class DummyTree:
    pass


class DummyPage:
    def __init__(self, *, agg_mode: str, warning: str, df_filtered: pd.DataFrame) -> None:
        self._tx_tree = DummyTree()
        self._lbl_tx_summary = DummyLabel()
        self._df_filtered = df_filtered
        self._var_aggregering = DummyVar(agg_mode)
        self._rl_mapping_warning = warning

    def _clear_tree(self, _tree) -> None:
        return None


def test_refresh_transactions_view_appends_rl_mapping_warning() -> None:
    page = DummyPage(
        agg_mode="Regnskapslinje",
        warning="Mappingavvik: 1 konto uten regnskapslinje-mapping (9999)",
        df_filtered=pd.DataFrame(),
    )

    refresh_transactions_view(page=page)

    assert "Oppsummering: (ingen rader)" in page._lbl_tx_summary.text
    assert "Mappingavvik: 1 konto uten regnskapslinje-mapping (9999)" in page._lbl_tx_summary.text

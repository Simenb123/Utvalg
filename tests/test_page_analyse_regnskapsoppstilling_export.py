from __future__ import annotations

import pandas as pd


class _DummyPage:
    TX_COLS = ("Konto", "Kontonavn", "Dato", "Bilag", "Tekst", "Beløp")

    def __init__(self):
        self._df_filtered = pd.DataFrame(
            {
                "Konto": ["1000", "1000"],
                "Kontonavn": ["Bank", "Bank"],
                "Dato": ["2025-01-01", "2025-01-02"],
                "Bilag": ["1", "2"],
                "Tekst": ["A", "B"],
                "Beløp": [100.0, -50.0],
            }
        )
        self._rl_intervals = pd.DataFrame({"fra": [1000], "til": [1999], "regnr": [10]})
        self._rl_regnskapslinjer = pd.DataFrame(
            {"nr": [10], "regnskapslinje": ["Eiendeler"], "sumpost": ["nei"], "Formel": [""]}
        )
        self._rl_sb_df = None

    def _get_selected_accounts(self):
        return ["1000"]


def test_prepare_regnskapsoppstilling_export_data_builds_rl_and_transactions(monkeypatch) -> None:
    import page_analyse_export
    import session as _session

    monkeypatch.setattr(_session, "client", "Nbs Regnskap AS", raising=False)
    monkeypatch.setattr(_session, "year", "2025", raising=False)

    payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(page=_DummyPage())

    assert payload["client"] == "Nbs Regnskap AS"
    assert payload["year"] == "2025"
    assert not payload["rl_df"].empty
    assert payload["rl_df"].loc[0, "regnr"] == 10
    assert not payload["transactions_df"].empty
    assert set(payload["transactions_df"]["Konto"].astype(str)) == {"1000"}

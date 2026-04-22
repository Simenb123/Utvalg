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


def test_prepare_export_includes_unfiltered_hb_for_kontospesifisert(monkeypatch) -> None:
    """Regresjonsvern: Kontospesifisert-arket i regnskapsoppstilling-eksporten
    skal alltid ha tilgang til alle HB-kontoer, uavhengig av hva brukeren
    har markert. Før fix 2026-04-22 ble df_hb utledet fra den seleksjons-
    filtrerte transactions_df, slik at eksporten bare viste kontoene
    under den RL-en som tilfeldigvis var markert i UI.
    """
    import page_analyse_export
    import session as _session

    class _MultiAccountPage:
        TX_COLS = ("Konto", "Kontonavn", "Dato", "Bilag", "Tekst", "Beløp")

        def __init__(self):
            self._df_filtered = pd.DataFrame(
                {
                    "Konto": ["1000", "2000", "3000"],
                    "Kontonavn": ["Bank", "Leverandør", "Salg"],
                    "Dato": ["2025-01-01"] * 3,
                    "Bilag": ["1", "2", "3"],
                    "Tekst": ["A", "B", "C"],
                    "Beløp": [100.0, -50.0, 200.0],
                }
            )
            self._rl_intervals = pd.DataFrame(
                {"fra": [1000, 2000, 3000], "til": [1999, 2999, 3999], "regnr": [10, 20, 30]},
            )
            self._rl_regnskapslinjer = pd.DataFrame(
                {"nr": [10, 20, 30], "regnskapslinje": ["A", "B", "C"],
                 "sumpost": ["nei", "nei", "nei"], "Formel": ["", "", ""]},
            )
            self._rl_sb_df = None

        def _get_selected_accounts(self):
            # Bruker har markert bare én konto i UI
            return ["1000"]

    monkeypatch.setattr(_session, "client", "Demo AS", raising=False)
    monkeypatch.setattr(_session, "year", "2025", raising=False)

    payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(page=_MultiAccountPage())

    # transactions_df er seleksjons-filtrert som før (til nøkkeltall-bruk)
    assert set(payload["transactions_df"]["Konto"].astype(str)) == {"1000"}
    # df_hb skal inneholde ALLE kontoer — Kontospesifisert-arket skal vise alt
    assert "df_hb" in payload
    assert set(payload["df_hb"]["Konto"].astype(str)) == {"1000", "2000", "3000"}


def test_prepare_export_calls_resolve_sb_views_with_keyword_arg(monkeypatch) -> None:
    """Regresjonsvern: _resolve_analysis_sb_views er keyword-only (def f(*, page)),
    så den MÅ kalles med page=page. Hvis noen skriver det om til positional,
    kastes TypeError som før ble stille svelget — og sb_df falt da tilbake til
    base SB uten ÅO-justering. Det ga feil tall i nøkkeltallsrapporten.
    """
    import page_analyse_export
    import page_analyse_rl

    captured: dict[str, object] = {}

    def _fake_resolve(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        # Returner tuple som matcher faktisk signatur
        base = pd.DataFrame({"konto": ["1000"], "ib": [0.0], "ub": [0.0]})
        return base, base, base

    monkeypatch.setattr(page_analyse_rl, "_resolve_analysis_sb_views", _fake_resolve)

    page_analyse_export.prepare_regnskapsoppstilling_export_data(page=_DummyPage())

    assert captured["args"] == ()
    assert "page" in captured["kwargs"]

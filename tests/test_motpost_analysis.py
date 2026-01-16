from __future__ import annotations

import pandas as pd


def test_build_motpost_data_basic() -> None:
    from views_motpost_konto import build_motpost_data

    df = pd.DataFrame(
        [
            # Bilag 1
            {"Bilag": 1.0, "Konto": 3000, "Kontonavn": "Salgsinntekter", "Beløp": -100.0, "Dato": "01.01.2025", "Tekst": "Salg"},
            {"Bilag": 1.0, "Konto": 1920, "Kontonavn": "Bank", "Beløp": 100.0, "Dato": "01.01.2025", "Tekst": "Salg"},
            # Bilag 2
            {"Bilag": 2.0, "Konto": 3000, "Kontonavn": "Salgsinntekter", "Beløp": -200.0, "Dato": "02.01.2025", "Tekst": "Salg"},
            {"Bilag": 2.0, "Konto": 1500, "Kontonavn": "Kundefordringer", "Beløp": 200.0, "Dato": "02.01.2025", "Tekst": "Salg"},
            # Bilag 3 (ikke i scope)
            {"Bilag": 3.0, "Konto": 1920, "Kontonavn": "Bank", "Beløp": -50.0, "Dato": "03.01.2025", "Tekst": "Annet"},
            {"Bilag": 3.0, "Konto": 2400, "Kontonavn": "Leverandørgjeld", "Beløp": 50.0, "Dato": "03.01.2025", "Tekst": "Annet"},
        ]
    )

    data = build_motpost_data(df_transactions=df, konto_list=["3000"])

    # Scope: bilag 1 og 2
    assert set(data.df_summary["Motkonto"].tolist()) == {"1920", "1500"}
    # Summer per motkonto
    sums = dict(zip(data.df_summary["Motkonto"], data.df_summary["SumBeløp"]))
    assert sums["1920"] == 100.0
    assert sums["1500"] == 200.0

    # Detaljer inneholder 2 rader (1 per bilag per motkonto)
    assert len(data.df_details) == 2
    # Beløp valgte kontoer per bilag
    det = data.df_details.set_index("Bilag_key")
    assert det.loc["1", "Beløp valgte kontoer"] == -100.0
    assert det.loc["2", "Beløp valgte kontoer"] == -200.0


def test_open_motpost_uses_filtered_bilag_scope(monkeypatch) -> None:
    import page_analyse

    df_all = pd.DataFrame(
        [
            # Bilag 1
            {"Bilag": 1.0, "Konto": 3000, "Beløp": -100.0},
            {"Bilag": 1.0, "Konto": 1920, "Beløp": 100.0},
            # Bilag 2 (skal IKKE med dersom filtrert scope kun gir bilag 1)
            {"Bilag": 2.0, "Konto": 3000, "Beløp": -200.0},
            {"Bilag": 2.0, "Konto": 1500, "Beløp": 200.0},
        ]
    )

    # Filteret (analysevisning) ser bare bilag 1 og bare valgt konto
    df_filtered = df_all[(df_all["Bilag"] == 1.0) & (df_all["Konto"] == 3000)].copy()

    # Patch session.dataset i modulen
    monkeypatch.setattr(page_analyse.session, "dataset", df_all, raising=False)

    # Lag AnalysePage uten Tk-init
    p = page_analyse.AnalysePage.__new__(page_analyse.AnalysePage)
    p.dataset = None
    p._df_filtered = df_filtered
    p._get_selected_accounts = lambda: ["3000"]

    captured = {}

    def fake_show(master, df_transactions, konto_list):
        captured["accounts"] = list(konto_list)
        captured["df"] = df_transactions.copy()

    # Unngå GUI
    monkeypatch.setattr(page_analyse, "_show_motpost_konto", fake_show)
    monkeypatch.setattr(page_analyse, "messagebox", None)

    p._open_motpost()

    assert captured["accounts"] == ["3000"]

    # Skal inneholde alle linjer for bilag 1, men ikke bilag 2
    assert set(captured["df"]["Bilag"].tolist()) == {1.0}
    assert len(captured["df"]) == 2

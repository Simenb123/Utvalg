from __future__ import annotations

import pandas as pd


def test_analyze_account_rows_can_suggest_sales_from_behavior_outside_3xxx() -> None:
    import regnskap_intelligence

    accounts_df = pd.DataFrame(
        {
            "Nr": [799],
            "Regnskapslinje": ["Annen driftskostnad"],
            "Konto": ["8090"],
            "Kontonavn": ["Salg prosjekt"],
            "IB": [0.0],
            "Endring": [-1250.0],
            "UB": [-1250.0],
            "Antall": [2],
        }
    )
    df_all = pd.DataFrame(
        {
            "Konto": ["8090", "1500", "2700", "8090", "1500"],
            "Bilag": ["B1", "B1", "B1", "B2", "B2"],
            "Tekst": ["Faktura prosjekt", "Faktura prosjekt", "Utgående mva", "Faktura prosjekt", "Faktura prosjekt"],
            "Beløp": [-1000.0, 1250.0, -250.0, -500.0, 500.0],
            "MVA-kode": ["3", "", "", "3", ""],
            "MVA-beløp": [250.0, 0.0, 0.0, 125.0, 0.0],
        }
    )
    regnskapslinjer = pd.DataFrame(
        {
            "nr": [10, 610, 799],
            "regnskapslinje": ["Salgsinntekt", "Kundefordringer", "Annen driftskostnad"],
            "sumpost": ["nei", "nei", "nei"],
            "Formel": ["", "", ""],
        }
    )

    detail_df, suggestions, _profiles = regnskap_intelligence.analyze_account_rows(
        accounts_df,
        df_all=df_all,
        regnskapslinjer=regnskapslinjer,
    )

    assert detail_df.loc[0, "OppforerSegSom"] == "Salgsinntekt"
    assert suggestions["8090"].suggested_regnr == 10
    assert suggestions["8090"].confidence_label in {"Hoy", "Middels"}


def test_build_account_behavior_profile_flags_credit_like_inventory() -> None:
    import regnskap_intelligence

    row = {
        "Nr": 605,
        "Regnskapslinje": "Lager av varer og annen beholdning",
        "Konto": "1463",
        "Kontonavn": "Konsignasjonslager",
        "IB": 10_000.0,
        "Endring": -2_000.0,
        "UB": 8_000.0,
        "Antall": 5,
    }
    df_all = pd.DataFrame(
        {
            "Konto": ["1463", "4000"],
            "Bilag": ["B1", "B1"],
            "Tekst": ["Lagerjustering", "Varekostnad"],
            "Beløp": [-2000.0, 2000.0],
        }
    )

    profile = regnskap_intelligence.build_account_behavior_profile(row, df_all=df_all)

    assert any("Lagerlinje" in alert.message for alert in profile.alerts)

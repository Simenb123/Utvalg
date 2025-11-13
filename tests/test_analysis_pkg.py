import pandas as pd
import pytest

from analysis_pkg import (
    _is_round_amount,
    round_share_by_group,
    outliers_by_group,
    generate_analysis_workbook,
)
from models import Columns


def test_is_round_amount_basic():
    # eksakt runde beløp
    assert _is_round_amount(1000.0)
    assert _is_round_amount(-500.0)

    # helt klart ikke rundt
    assert not _is_round_amount(123.0)

    # nesten rundt: innenfor toleranse
    assert _is_round_amount(999.9, bases=(1000,), tol=0.2)  # 0,1 fra 1000
    # utenfor toleranse
    assert not _is_round_amount(999.9, bases=(1000,), tol=0.05)


def test_round_share_by_group_konto_basic():
    # Lite datasett med to konti, noen runde og noen ikke-runde beløp
    df = pd.DataFrame(
        {
            "Konto": ["3000", "3000", "4000", "4000"],
            "Beløp": [1000.0, 200.0, 500.0, 123.0],
        }
    )
    cols = Columns(konto="Konto", belop="Beløp")

    res = round_share_by_group(df, cols, group="Konto", min_rows=1)

    # Forventer én rad per konto
    assert set(res["Konto"]) == {"3000", "4000"}

    # Konto 3000: begge er runde (1000 og 200 er multipler av 100)
    andel_3000 = res.loc[res["Konto"] == "3000", "andel_runde"].iloc[0]
    assert andel_3000 == pytest.approx(1.0)

    # Konto 4000: 1 av 2 er rund (500 / 123)
    andel_4000 = res.loc[res["Konto"] == "4000", "andel_runde"].iloc[0]
    assert andel_4000 == pytest.approx(0.5)


def test_outliers_by_group_mad_basic():
    # Ett datasett med én konto og to tydelige outliers
    normal_values = [100, 105, 95, 110, 102, 98, 101, 99, 103, 97]
    outliers = [1000, -900]
    df = pd.DataFrame(
        {
            "Konto": ["3000"] * (len(normal_values) + len(outliers)),
            "Beløp": normal_values + outliers,
        }
    )
    cols = Columns(konto="Konto", belop="Beløp")

    res = outliers_by_group(
        df,
        cols,
        method="MAD",
        threshold=3.5,
        group_by="Konto",
        min_group_size=5,
        basis="abs",
    )

    # Vi forventer at de to ekstremverdiene flagges
    assert not res.empty
    flagged = set(res["Beløp"])
    assert flagged == {1000, -900}

    # __gruppe-kolonnen skal være satt til kontonummer
    assert "__gruppe" in res.columns
    assert set(res["__gruppe"]) == {"3000"}


def test_generate_analysis_workbook_creates_expected_sheets(monkeypatch):
    """
    Verifiserer at generate_analysis_workbook bygger opp et sheets-dict
    med minst 'Runde_beløp_andeler' og 'Outliers', uten å skrive ekte Excel-filer.
    """
    captured_sheets = {}

    def fake_export_temp_excel(sheets, prefix="Analyser_"):
        # Kopier innholdet slik at vi kan inspisere det etterpå
        captured_sheets.update(sheets)
        return "dummy.xlsx"

    # Monkeypatch funksjonen som ellers skriver Excel + åpner fil
    monkeypatch.setattr("analysis_pkg.export_temp_excel", fake_export_temp_excel)

    # Gjenbruk datasettet fra outlier-testen, så vi vet at vi får ut outliers
    normal_values = [100, 105, 95, 110, 102, 98, 101, 99, 103, 97]
    outliers = [1000, -900]
    df = pd.DataFrame(
        {
            "Konto": ["3000"] * (len(normal_values) + len(outliers)),
            "Beløp": normal_values + outliers,
        }
    )
    cols = Columns(konto="Konto", belop="Beløp")

    path = generate_analysis_workbook(
        df,
        cols,
        round_group="Konto",
        round_bases=(1000, 500, 100),
        round_tol=0.0,
        round_min_rows=1,   # senk terskel for små datasett
        out_method="MAD",
        out_threshold=3.5,
        out_group="Konto",
        out_min_group=5,    # som i outlier-testen
        out_basis="abs",
    )

    # Funksjonen skal returnere filsti-strengen fra export_temp_excel
    assert path == "dummy.xlsx"

    # Vi forventer at minst disse to arkene ble laget
    assert "Runde_beløp_andeler" in captured_sheets
    assert "Outliers" in captured_sheets

    # Og de skal være DataFrames
    assert isinstance(captured_sheets["Runde_beløp_andeler"], pd.DataFrame)
    assert isinstance(captured_sheets["Outliers"], pd.DataFrame)

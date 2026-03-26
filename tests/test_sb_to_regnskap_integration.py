"""Integrasjonstest: saldobalanse-fil → reader → mapping → aggregert per regnr.

Tester hele flyten fra raw Excel-fil til ferdig aggregert DataFrame på
regnskapslinje-nivå, uten GUI og uten echte datafiler.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name)


# ---------------------------------------------------------------------------
# Hjelpere: lag test-Excel-filer in-memory
# ---------------------------------------------------------------------------

def _make_trial_balance_xlsx(path: Path) -> None:
    """Lager en minimal saldobalanse med realistisk kolonnestruktur."""
    tb = pd.DataFrame(
        {
            "Konto": [1000, 1500, 3000, 4000, 9999],
            "Kontonavn": ["Bank", "Kundefordringer", "Salgsinntekter", "Varekostnad", "Ingen mapping"],
            "IB": [500.0, 200.0, 0.0, 0.0, 10.0],
            "UB": [600.0, 180.0, -1000.0, 400.0, 15.0],
        }
    )
    _write_xlsx(path, {"Saldobalanse": tb})


def _make_intervals_xlsx(path: Path) -> None:
    """Intervall-mapping: konto 1000-1999 → regnr 10, 3000-4999 → regnr 20."""
    iv = pd.DataFrame(
        {
            "Fra": [1000, 3000],
            "Til": [1999, 4999],
            "Regnr": [10, 20],
        }
    )
    _write_xlsx(path, {"Intervall": iv})


def _make_regnskapslinjer_xlsx(path: Path) -> None:
    """Regnskapslinjer: regnr 10 = Balanse, 20 = Resultat, 99 = SUM (formel)."""
    rl = pd.DataFrame(
        {
            "Nr": [10, 20, 99],
            "Regnskapslinje": ["Balanse", "Resultat", "SUM"],
            "Sumpost": ["nei", "nei", "ja"],
            "Formel": ["", "", "=10+20"],
        }
    )
    _write_xlsx(path, {"Sheet1": rl})


# ---------------------------------------------------------------------------
# Integrasjonstest
# ---------------------------------------------------------------------------

def test_full_flow_sb_to_regnskapslinje(tmp_path: Path) -> None:
    """End-to-end: Excel SB → reader → intervall-mapping → aggregering."""
    from trial_balance_reader import read_trial_balance
    from regnskap_mapping import apply_interval_mapping, aggregate_by_regnskapslinje

    sb_path = tmp_path / "saldobalanse.xlsx"
    iv_path = tmp_path / "intervaller.xlsx"
    rl_path = tmp_path / "regnskapslinjer.xlsx"

    _make_trial_balance_xlsx(sb_path)
    _make_intervals_xlsx(iv_path)
    _make_regnskapslinjer_xlsx(rl_path)

    # Steg 1: les og normaliser SB
    tb = read_trial_balance(sb_path)
    assert list(tb.columns) == ["konto", "kontonavn", "ib", "ub", "netto"]
    assert tb["konto"].tolist() == ["1000", "1500", "3000", "4000", "9999"]

    # Steg 2: les intervall-mapping
    iv_df = pd.read_excel(iv_path, sheet_name="Intervall")

    # Steg 3: anvend mapping
    result = apply_interval_mapping(tb, iv_df)

    assert result.unmapped_konto == ["9999"], f"Forventet ['9999'] umappet, fikk {result.unmapped_konto}"
    mapped = result.mapped

    # konto 1000 og 1500 → regnr 10; 3000 og 4000 → regnr 20; 9999 → NaN
    regnr_list = mapped["regnr"].tolist()
    assert regnr_list[0] == 10   # 1000
    assert regnr_list[1] == 10   # 1500
    assert regnr_list[2] == 20   # 3000
    assert regnr_list[3] == 20   # 4000
    assert pd.isna(regnr_list[4])  # 9999

    # Steg 4: regnskapslinjer som in-memory DataFrame (formler kan ikke round-trippe
    # via Excel uten recalculation; dette testes separat i test_regnskap_mapping.py)
    rl_df = pd.DataFrame(
        {
            "Nr": [10, 20, 99],
            "Regnskapslinje": ["Balanse", "Resultat", "SUM"],
            "Sumpost": ["nei", "nei", "ja"],
            "Formel": ["", "", "=10+20"],
        }
    )
    _ = rl_path  # opprettet men ikke lest her

    # Steg 5: aggreger leaf-linjer
    agg = aggregate_by_regnskapslinje(mapped, rl_df, amount_col="ub", include_sum_lines=False)

    assert set(agg["regnr"].tolist()) == {10, 20}

    balanse = float(agg.loc[agg["regnr"] == 10, "belop"].iloc[0])
    resultat = float(agg.loc[agg["regnr"] == 20, "belop"].iloc[0])

    # Balanse: UB 1000 (600) + UB 1500 (180) = 780
    assert balanse == pytest.approx(780.0)
    # Resultat: UB 3000 (-1000) + UB 4000 (400) = -600
    assert resultat == pytest.approx(-600.0)

    # Steg 6: aggreger med sumlinjer
    agg_with_sum = aggregate_by_regnskapslinje(
        mapped, rl_df, amount_col="ub", include_sum_lines=True
    )

    assert set(agg_with_sum["regnr"].tolist()) == {10, 20, 99}

    total = float(agg_with_sum.loc[agg_with_sum["regnr"] == 99, "belop"].iloc[0])
    # SUM = =10+20 = 780 + (-600) = 180
    assert total == pytest.approx(180.0)


def test_reader_debet_kredit_columns(tmp_path: Path) -> None:
    """Reader håndterer Debet/Kredit-kolonne-format (netto = debet - kredit)."""
    from trial_balance_reader import read_trial_balance

    tb = pd.DataFrame(
        {
            "Konto": [1000, 3000],
            "Kontonavn": ["Bank", "Salg"],
            "Debet": [1000.0, 0.0],
            "Kredit": [200.0, 800.0],
        }
    )
    path = tmp_path / "debet_kredit.xlsx"
    _write_xlsx(path, {"TB": tb})

    out = read_trial_balance(path)
    # netto = debet - kredit (kredit er negativt fortegn per spec)
    assert out.loc[0, "netto"] == pytest.approx(800.0)   # 1000 - 200
    assert out.loc[1, "netto"] == pytest.approx(-800.0)  # 0 - 800


def test_unmapped_kontos_are_tracked(tmp_path: Path) -> None:
    """Kontoer uten treff i intervall-mapping rapporteres korrekt."""
    from trial_balance_reader import read_trial_balance
    from regnskap_mapping import apply_interval_mapping

    tb = pd.DataFrame(
        {
            "Konto": [1000, 5000, 8000],
            "IB": [0.0, 0.0, 0.0],
            "UB": [100.0, 200.0, 300.0],
        }
    )
    path = tmp_path / "sb.xlsx"
    _write_xlsx(path, {"TB": tb})

    iv = pd.DataFrame({"fra": [1000], "til": [1999], "regnr": [10]})

    tb_norm = read_trial_balance(path)
    result = apply_interval_mapping(tb_norm, iv)

    assert sorted(result.unmapped_konto) == ["5000", "8000"]


def test_aggregate_empty_regnr_gives_zero(tmp_path: Path) -> None:
    """Regnskapslinjer uten treff i SB får beløp = 0."""
    from regnskap_mapping import apply_interval_mapping, aggregate_by_regnskapslinje

    tb = pd.DataFrame({"konto": ["1000"], "ub": [500.0]})
    iv = pd.DataFrame({"fra": [1000], "til": [1999], "regnr": [10]})

    rl = pd.DataFrame(
        {
            "Nr": [10, 20],
            "Regnskapslinje": ["Balanse", "Gjeld"],
            "Sumpost": ["nei", "nei"],
            "Formel": ["", ""],
        }
    )

    mapped = apply_interval_mapping(tb, iv)
    agg = aggregate_by_regnskapslinje(mapped.mapped, rl, amount_col="ub")

    gjeld = float(agg.loc[agg["regnr"] == 20, "belop"].iloc[0])
    assert gjeld == pytest.approx(0.0)

"""Tests for Fase A — heuristikker i trial_balance_reader.

Dekker:
  - header-deteksjon når Excel har tittel-rader over den reelle headeren
  - utvidede norske alias (Kontobetegnelse, Endelig, Saldo)
  - embedded-year-parsing ("Endelig 2024", "Saldo 2023")
  - rolle-prioritering: Endelig vinner over Foreløpig/Korreksjon
  - netto-fallback kun når IB/UB mangler
  - Maestro-akseptansetest mot ekte fil
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import trial_balance_reader as tbr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_excel_with_title_rows(path: Path, header: list, rows: list[list]) -> None:
    """Skriv en xlsx med 3 tittel-rader FØR den reelle headeren."""
    raw = [
        ["Foretaksrapport", None, None, None],
        ["Periode: 01.01.2024 - 31.12.2024", None, None, None],
        [None, None, None, None],
        header,
    ] + rows
    df = pd.DataFrame(raw)
    df.to_excel(path, index=False, header=False)


# ---------------------------------------------------------------------------
# A1 — header deteksjon
# ---------------------------------------------------------------------------

def test_reads_file_with_title_rows(tmp_path: Path):
    path = tmp_path / "tb_titles.xlsx"
    _write_excel_with_title_rows(
        path,
        header=["Konto", "Kontonavn", "IB", "UB"],
        rows=[
            [3000, "Salgsinntekt", 0, -100000.0],
            [1500, "Kundefordringer", 1000.0, 2000.0],
        ],
    )

    out = tbr.read_trial_balance(path)
    assert set(["konto", "kontonavn", "ib", "ub", "netto"]).issubset(out.columns)
    assert len(out) == 2
    row = out.loc[out["konto"] == "3000"].iloc[0]
    assert row["ub"] == pytest.approx(-100000.0)


# ---------------------------------------------------------------------------
# A2 — utvidede aliaser
# ---------------------------------------------------------------------------

def test_kontobetegnelse_maps_to_kontonavn(tmp_path: Path):
    df = pd.DataFrame({
        "Konto": [3000, 1500],
        "Kontobetegnelse": ["Salgsinntekt", "Kundefordringer"],
        "UB": [-100.0, 200.0],
    })
    path = tmp_path / "tb.xlsx"
    df.to_excel(path, index=False)

    out = tbr.read_trial_balance(path)
    assert list(out["kontonavn"]) == ["Salgsinntekt", "Kundefordringer"]


def test_endelig_year_becomes_ub(tmp_path: Path):
    df = pd.DataFrame({
        "Konto": [3000],
        "Kontonavn": ["Salg"],
        "Endelig 2024": [-100.0],
    })
    path = tmp_path / "tb.xlsx"
    df.to_excel(path, index=False)

    out = tbr.read_trial_balance(path)
    assert out["ub"].iloc[0] == pytest.approx(-100.0)


def test_saldo_year_becomes_ib_when_prev_year(tmp_path: Path):
    df = pd.DataFrame({
        "Konto": [3000],
        "Kontonavn": ["Salg"],
        "Saldo 2023": [-50.0],
        "Saldo 2024": [-100.0],
    })
    path = tmp_path / "tb.xlsx"
    df.to_excel(path, index=False)

    out = tbr.read_trial_balance(path)
    assert out["ib"].iloc[0] == pytest.approx(-50.0)
    assert out["ub"].iloc[0] == pytest.approx(-100.0)


def test_saldo_prev_year_becomes_ib_with_explicit_ub(tmp_path: Path):
    """Maestro-mønster: én 'Saldo <fjor>'-kolonne + 'Endelig <i år>' UB.

    Regression-sikring: IB skal komme direkte fra 'Saldo 2023'-kolonnen,
    ikke derivere som `ub - netto`. Derfor setter vi netto til en verdi
    som *ikke* stemmer med (ub - ib), slik at derivering ville gi feil
    ib-verdi hvis koden tok feil sti.
    """
    df = pd.DataFrame({
        "Kontonr": [3000],
        "Kontobetegnelse": ["Salg"],
        "Saldo 2023": [-40.0],
        "Endelig 2024": [-100.0],
        "Endring fra fjoråret": [-99.0],  # bevisst avvik fra ub-ib=-60
    })
    path = tmp_path / "tb.xlsx"
    df.to_excel(path, index=False)

    # Bekreft hvilken kildekolonne readeren faktisk plukker
    from trial_balance_reader import (
        _read_sheet_with_detected_header,
        infer_columns_with_year_detection,
        _clean_frame,
    )
    raw = _clean_frame(_read_sheet_with_detected_header(path, None))
    cols, _ = infer_columns_with_year_detection(raw)
    assert cols.ib == "Saldo 2023", f"ib skulle være 'Saldo 2023', fikk {cols.ib!r}"
    assert cols.ub == "Endelig 2024", f"ub skulle være 'Endelig 2024', fikk {cols.ub!r}"

    out = tbr.read_trial_balance(path)
    assert out["ib"].iloc[0] == pytest.approx(-40.0)
    assert out["ub"].iloc[0] == pytest.approx(-100.0)


# ---------------------------------------------------------------------------
# A3 — embedded year og rolle-prioritet
# ---------------------------------------------------------------------------

def test_endelig_wins_over_forelobig(tmp_path: Path):
    """Tre kolonner for samme år — kun 'Endelig' skal velges som UB."""
    df = pd.DataFrame({
        "Konto": [3000],
        "Kontonavn": ["Salg"],
        "Foreløpig 2024": [-50.0],
        "Korreksjon 2024": [-10.0],
        "Endelig 2024": [-100.0],
    })
    path = tmp_path / "tb.xlsx"
    df.to_excel(path, index=False)

    out = tbr.read_trial_balance(path)
    assert out["ub"].iloc[0] == pytest.approx(-100.0)


def test_embedded_year_parsed():
    year, role = tbr._classify_year_column("Sluttsaldo 2024")
    # "sluttsaldo" har ikke endelig-keyword, men "saldo" matcher
    # som saldo-rolle (som senere blir ub pga kronologi).
    assert year == 2024
    assert role in {"ub", "saldo"}


def test_classify_forelobig_is_skip():
    year, role = tbr._classify_year_column("Foreløpig 2024")
    assert year == 2024
    assert role == "skip"


def test_classify_endelig_is_ub():
    year, role = tbr._classify_year_column("Endelig 2024")
    assert (year, role) == (2024, "ub")


def test_classify_plain_year_has_no_role():
    year, role = tbr._classify_year_column("2024")
    assert year == 2024
    assert role is None


def test_classify_non_year_returns_none():
    assert tbr._classify_year_column("Kontonavn") == (None, None)
    assert tbr._classify_year_column("Beskrivelse") == (None, None)


# ---------------------------------------------------------------------------
# A4 — netto fallback
# ---------------------------------------------------------------------------

def test_netto_fallback_only_when_no_ib_ub(tmp_path: Path):
    """Når kun 'Endring 2024' finnes uten IB/UB: netto brukes som UB (IB=0)."""
    df = pd.DataFrame({
        "Konto": [3000],
        "Kontonavn": ["Salg"],
        "Endring 2024": [-100.0],
    })
    path = tmp_path / "tb.xlsx"
    df.to_excel(path, index=False)

    out = tbr.read_trial_balance(path)
    # _standardize antar IB=0 og UB=netto for ren bevegelsesfil
    assert out["netto"].iloc[0] == pytest.approx(-100.0)


def test_ub_wins_over_netto_same_year(tmp_path: Path):
    """Hvis både UB og netto finnes for samme år, UB skal beholdes."""
    df = pd.DataFrame({
        "Konto": [3000],
        "Kontonavn": ["Salg"],
        "Endelig 2024": [-100.0],
        "Endring 2024": [-30.0],
    })
    path = tmp_path / "tb.xlsx"
    df.to_excel(path, index=False)

    out = tbr.read_trial_balance(path)
    assert out["ub"].iloc[0] == pytest.approx(-100.0)


# ---------------------------------------------------------------------------
# A5 — Maestro-akseptansetest
# ---------------------------------------------------------------------------

_MAESTRO_PATH = Path(__file__).resolve().parents[1] / "doc" / "files" / "Kontoplan Way Nor 2024 Maestro.xlsx"


@pytest.mark.skipif(not _MAESTRO_PATH.exists(), reason="Maestro-referansefil ikke tilgjengelig")
def test_maestro_acceptance():
    out = tbr.read_trial_balance(_MAESTRO_PATH)

    assert not out.empty, "Maestro-import ga tom DataFrame"
    assert set(["konto", "kontonavn", "ib", "ub"]).issubset(out.columns)

    # Minst én rad skal ha ikke-tomt konto og kontonavn
    konto_mask = out["konto"].astype(str).str.len() > 0
    navn_mask = out["kontonavn"].astype(str).str.len() > 0
    assert (konto_mask & navn_mask).any(), "Ingen rader med både konto og kontonavn"

    # Minst én rad med UB != 0 (ellers er parseringen åpenbart feil)
    assert (out["ub"].abs() > 0).any(), "UB er 0 for alle rader — parsering feilet"


@pytest.mark.skipif(not _MAESTRO_PATH.exists(), reason="Maestro-referansefil ikke tilgjengelig")
def test_maestro_ib_comes_from_source_column():
    """Bekreft at IB i Maestro-filen mappes til en faktisk fjor-kolonne,
    ikke kun derives via ub - netto.
    """
    from trial_balance_reader import (
        _read_sheet_with_detected_header,
        infer_columns_with_year_detection,
        _clean_frame,
    )

    raw = _clean_frame(_read_sheet_with_detected_header(_MAESTRO_PATH, None))
    cols, year_map = infer_columns_with_year_detection(raw)

    assert cols.konto, "Fant ikke konto-kolonne i Maestro-filen"
    assert cols.ub, "Fant ikke UB-kolonne i Maestro-filen"
    assert cols.ib is not None, "IB-kolonne skulle være detektert fra Maestro-filen"

    # IB-kolonnenavnet skal referere til enten 'Saldo'/'fjor' eller et eksplisitt
    # eldre år — ikke en 'Endelig'/'Foreløpig'-kolonne.
    ib_low = str(cols.ib).lower()
    ub_low = str(cols.ub).lower()
    assert ib_low != ub_low, "IB og UB peker på samme kolonne"
    assert not any(k in ib_low for k in ("foreløpig", "forelopig", "korreksjon")), (
        f"IB mappet til en forkastet kolonne: {cols.ib}"
    )

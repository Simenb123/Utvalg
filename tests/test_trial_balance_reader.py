from __future__ import annotations

from pathlib import Path

import pandas as pd


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name)


def test_read_trial_balance_excel_basic(tmp_path: Path) -> None:
    from trial_balance_reader import read_trial_balance

    tb = pd.DataFrame(
        {
            "AccountID": [1000, 3000, 3100],
            "AccountDescription": ["Bank", "Salg", "Annen inntekt"],
            "IB": [10.0, 0.0, 0.0],
            "Movement": [5.0, -100.0, -20.0],
            "UB": [15.0, -100.0, -20.0],
        }
    )
    other = pd.DataFrame({"x": [1, 2, 3]})

    p = tmp_path / "trial_balance.xlsx"
    _write_xlsx(p, {"Accounts": other, "TrialBalance": tb})

    out = read_trial_balance(p)
    assert list(out.columns) == ["konto", "kontonavn", "ib", "ub", "netto"]
    assert out["konto"].tolist() == ["1000", "3000", "3100"]
    assert out.loc[0, "kontonavn"] == "Bank"
    assert out.loc[0, "ib"] == 10.0
    assert out.loc[0, "ub"] == 15.0
    assert out.loc[1, "netto"] == -100.0


def test_read_trial_balance_infers_netto_from_ub_minus_ib(tmp_path: Path) -> None:
    from trial_balance_reader import read_trial_balance

    tb = pd.DataFrame(
        {
            "Konto": [1000, 1500],
            "Kontonavn": ["Bank", "Kundefordringer"],
            "IB": [100.0, 200.0],
            "UB": [110.0, 150.0],
        }
    )
    p = tmp_path / "sb.xlsx"
    _write_xlsx(p, {"Saldobalanse": tb})

    out = read_trial_balance(p)
    assert out.loc[0, "netto"] == 10.0
    assert out.loc[1, "netto"] == -50.0


def test_read_trial_balance_missing_required_columns_raises(tmp_path: Path) -> None:
    import pytest

    from trial_balance_reader import read_trial_balance

    tb = pd.DataFrame({"Something": [1, 2, 3], "IB": [0, 0, 0], "UB": [0, 0, 0]})
    p = tmp_path / "sb.xlsx"
    _write_xlsx(p, {"TrialBalance": tb})

    with pytest.raises(ValueError):
        _ = read_trial_balance(p)


# ---------------------------------------------------------------------------
# Alias expansion tests
# ---------------------------------------------------------------------------


def test_saldo_i_aar_maps_to_ub(tmp_path: Path) -> None:
    """'Saldo i år' should be detected as UB."""
    from trial_balance_reader import read_trial_balance

    tb = pd.DataFrame({
        "Konto": [1000, 3000],
        "Kontonavn": ["Bank", "Salg"],
        "Saldo i fjor": [100.0, 0.0],
        "Saldo i år": [150.0, -200.0],
    })
    p = tmp_path / "sb.xlsx"
    _write_xlsx(p, {"Saldobalanse": tb})

    out = read_trial_balance(p)
    assert out.loc[0, "ib"] == 100.0
    assert out.loc[0, "ub"] == 150.0
    assert out.loc[0, "netto"] == 50.0


def test_aarets_bevegelse_maps_to_netto(tmp_path: Path) -> None:
    """'Årets bevegelse' should be detected as netto."""
    from trial_balance_reader import read_trial_balance

    tb = pd.DataFrame({
        "Konto": [1000],
        "Kontonavn": ["Bank"],
        "IB": [100.0],
        "Årets bevegelse": [50.0],
    })
    p = tmp_path / "sb.xlsx"
    _write_xlsx(p, {"Saldobalanse": tb})

    out = read_trial_balance(p)
    assert out.loc[0, "netto"] == 50.0
    assert out.loc[0, "ub"] == 150.0  # derived: IB + netto


def test_bevegelse_maps_to_netto(tmp_path: Path) -> None:
    """'Bevegelse' alone should be detected as netto."""
    from trial_balance_reader import infer_trial_balance_columns

    df = pd.DataFrame({
        "Konto": [1000],
        "IB": [0],
        "Bevegelse": [100],
    })
    cols = infer_trial_balance_columns(df)
    assert cols.netto == "Bevegelse"


def test_debet_kredit_still_works(tmp_path: Path) -> None:
    """Debet + Kredit should produce correct netto AND derive UB from netto."""
    from trial_balance_reader import read_trial_balance

    tb = pd.DataFrame({
        "Konto": [1000, 3000],
        "Kontonavn": ["Bank", "Salg"],
        "Debet": [500.0, 0.0],
        "Kredit": [0.0, 300.0],
    })
    p = tmp_path / "sb.xlsx"
    _write_xlsx(p, {"Saldobalanse": tb})

    out = read_trial_balance(p)
    assert out.loc[0, "netto"] == 500.0
    assert out.loc[1, "netto"] == -300.0
    # IB should be 0 (no IB column in source), UB should equal netto
    assert out.loc[0, "ib"] == 0.0
    assert out.loc[0, "ub"] == 500.0
    assert out.loc[1, "ub"] == -300.0


# ---------------------------------------------------------------------------
# Netto-only derivation tests (IB=0, UB=netto)
# ---------------------------------------------------------------------------


def test_netto_only_derives_ub(tmp_path: Path) -> None:
    """When source has only Netto column (no IB, no UB), UB should equal Netto."""
    from trial_balance_reader import read_trial_balance

    tb = pd.DataFrame({
        "Konto": [1000, 3000, 4000],
        "Kontonavn": ["Bank", "Salg", "Varekjop"],
        "Netto": [150.0, -800.0, 300.0],
    })
    p = tmp_path / "sb.xlsx"
    _write_xlsx(p, {"Saldobalanse": tb})

    out = read_trial_balance(p)
    # IB should default to 0; UB should be derived as IB + netto = netto
    assert out.loc[0, "ib"] == 0.0
    assert out.loc[0, "ub"] == 150.0
    assert out.loc[0, "netto"] == 150.0
    assert out.loc[1, "ub"] == -800.0
    assert out.loc[2, "ub"] == 300.0


def test_netto_only_consolidation_uses_ub(tmp_path: Path) -> None:
    """Consolidation engine must see correct UB even for netto-only TBs."""
    import pytest
    from trial_balance_reader import read_trial_balance

    # Simulate a netto-only export (common for Norwegian systems)
    tb = pd.DataFrame({
        "Konto": [1000, 3000],
        "Kontonavn": ["Bank", "Salg"],
        "Endring": [100.0, -500.0],
    })
    p = tmp_path / "sb.xlsx"
    _write_xlsx(p, {"Saldobalanse": tb})

    out = read_trial_balance(p)
    # UB must NOT be zero — it should equal netto
    assert out.loc[0, "ub"] == pytest.approx(100.0)
    assert out.loc[1, "ub"] == pytest.approx(-500.0)


def test_session_import_normalizes(tmp_path: Path) -> None:
    """Verify that _normalize_columns produces canonical TB format."""
    from src.pages.consolidation.backend.tb_import import _normalize_columns

    # Simulate a session TB with mixed casing
    raw = pd.DataFrame({
        "Konto": ["1000", "3000"],
        "Kontonavn": ["Bank", "Salg"],
        "IB": [0.0, 0.0],
        "UB": [100.0, -200.0],
        "Netto": [100.0, -200.0],
        "extra_col": ["a", "b"],  # should be dropped
    })
    out = _normalize_columns(raw)
    assert list(out.columns) == ["konto", "kontonavn", "ib", "ub", "netto"]
    assert out.loc[0, "konto"] == "1000"  # string type
    assert out.loc[0, "ub"] == 100.0


def test_normalize_columns_derives_ub_from_netto() -> None:
    """_normalize_columns must derive UB = IB + Netto when UB is all zero."""
    from src.pages.consolidation.backend.tb_import import _normalize_columns

    # Simulate a netto-only TB (IB=0, UB missing, Netto=values)
    raw = pd.DataFrame({
        "konto": ["1000", "3000", "4000"],
        "kontonavn": ["Bank", "Salg", "Varekjop"],
        "netto": [150.0, -800.0, 300.0],
    })
    out = _normalize_columns(raw)
    # UB should be derived: IB(0) + Netto = Netto
    assert out.loc[0, "ub"] == 150.0
    assert out.loc[1, "ub"] == -800.0
    assert out.loc[2, "ub"] == 300.0
    assert out.loc[0, "ib"] == 0.0


def test_normalize_columns_preserves_existing_ub() -> None:
    """_normalize_columns must NOT overwrite UB when it already has values."""
    from src.pages.consolidation.backend.tb_import import _normalize_columns

    raw = pd.DataFrame({
        "konto": ["1000"],
        "kontonavn": ["Bank"],
        "ib": [100.0],
        "ub": [250.0],
        "netto": [150.0],
    })
    out = _normalize_columns(raw)
    assert out.loc[0, "ub"] == 250.0  # must stay untouched
    assert out.loc[0, "ib"] == 100.0


# ---------------------------------------------------------------------------
# Year-column detection tests
# ---------------------------------------------------------------------------


def test_detect_year_columns_basic() -> None:
    from trial_balance_reader import _detect_year_columns

    result = _detect_year_columns(["Konto", "Kontonavn", "2024", "2025"])
    assert result == {"2024": "ib", "2025": "ub"}


def test_detect_year_columns_no_years() -> None:
    from trial_balance_reader import _detect_year_columns

    result = _detect_year_columns(["Konto", "IB", "UB"])
    assert result == {}


def test_detect_year_columns_single_year_ignored() -> None:
    from trial_balance_reader import _detect_year_columns

    result = _detect_year_columns(["Konto", "2025"])
    assert result == {}


def test_infer_with_year_detection() -> None:
    """Year columns as only numeric columns should be detected as IB/UB."""
    from trial_balance_reader import infer_columns_with_year_detection

    df = pd.DataFrame({
        "Konto": [1000, 3000],
        "Kontonavn": ["Bank", "Salg"],
        "2024": [100.0, 0.0],
        "2025": [150.0, -200.0],
    })
    cols, year_map = infer_columns_with_year_detection(df)

    assert year_map == {"2024": "ib", "2025": "ub"}
    assert cols.konto == "Konto"
    # The IB/UB should map to the original year-column names
    assert cols.ib == "2024"
    assert cols.ub == "2025"


# ---------------------------------------------------------------------------
# read_raw_trial_balance tests
# ---------------------------------------------------------------------------


def test_read_raw_returns_uncleaned_columns(tmp_path: Path) -> None:
    from trial_balance_reader import read_raw_trial_balance

    tb = pd.DataFrame({
        "Konto": [1000, 3000],
        "Saldo i år": [100.0, -200.0],
        "Saldo i fjor": [50.0, 0.0],
    })
    p = tmp_path / "sb.xlsx"
    _write_xlsx(p, {"Saldobalanse": tb})

    raw = read_raw_trial_balance(p, max_rows=10)
    # Should have original column names, not normalized
    assert "Konto" in raw.columns
    assert "Saldo i år" in raw.columns or "Saldo i fjor" in raw.columns
    assert len(raw) == 2


# ---------------------------------------------------------------------------
# P6: Netto invariant — netto == ub - ib must hold after normalization
# ---------------------------------------------------------------------------

import pytest


@pytest.mark.parametrize("scenario,input_cols", [
    ("ib_ub_netto", {"ib": [100.0, 0.0], "ub": [250.0, -500.0], "netto": [150.0, -500.0]}),
    ("ib_ub_only", {"ib": [100.0, 200.0], "ub": [110.0, 150.0]}),
    ("netto_only", {"netto": [150.0, -800.0]}),
    ("ib_netto_only", {"ib": [100.0, 0.0], "netto": [50.0, -300.0]}),
    ("debet_kredit", {"debet": [500.0, 0.0], "kredit": [0.0, 300.0]}),
])
def test_netto_invariant_after_normalize(scenario: str, input_cols: dict) -> None:
    """netto == ub - ib must hold for all normalization paths.

    Definition: netto = ub - ib (endring i perioden).
    This is the canonical invariant for all TB data in the consolidation pipeline.
    """
    from src.pages.consolidation.backend.tb_import import _normalize_columns

    raw = pd.DataFrame({
        "konto": ["1000", "3000"],
        "kontonavn": ["Bank", "Salg"],
        **input_cols,
    })
    out = _normalize_columns(raw)

    for i in range(len(out)):
        ib = out.loc[i, "ib"]
        ub = out.loc[i, "ub"]
        netto = out.loc[i, "netto"]
        assert netto == pytest.approx(ub - ib), (
            f"[{scenario}] row {i}: netto={netto} != ub-ib={ub}-{ib}={ub - ib}"
        )


@pytest.mark.parametrize("scenario,input_cols", [
    ("ib_ub_netto", {"IB": [100.0, 0.0], "UB": [250.0, -500.0], "Netto": [150.0, -500.0]}),
    ("ib_ub_only", {"IB": [100.0, 200.0], "UB": [110.0, 150.0]}),
    ("netto_only", {"Netto": [150.0, -800.0]}),
    ("saldo_i_aar", {"Saldo i fjor": [100.0, 0.0], "Saldo i år": [150.0, -200.0]}),
    ("debet_kredit", {"Debet": [500.0, 0.0], "Kredit": [0.0, 300.0]}),
])
def test_netto_invariant_after_read(scenario: str, input_cols: dict, tmp_path: Path) -> None:
    """netto == ub - ib must hold for all read_trial_balance paths."""
    from trial_balance_reader import read_trial_balance

    raw = pd.DataFrame({
        "Konto": [1000, 3000],
        "Kontonavn": ["Bank", "Salg"],
        **input_cols,
    })
    p = tmp_path / f"tb_{scenario}.xlsx"
    _write_xlsx(p, {"Saldobalanse": raw})

    out = read_trial_balance(p)

    for i in range(len(out)):
        ib = out.loc[i, "ib"]
        ub = out.loc[i, "ub"]
        netto = out.loc[i, "netto"]
        assert netto == pytest.approx(ub - ib), (
            f"[{scenario}] row {i}: netto={netto} != ub-ib={ub}-{ib}={ub - ib}"
        )

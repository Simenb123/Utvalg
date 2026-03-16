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

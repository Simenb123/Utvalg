from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd

_ROOT = Path(__file__).resolve().parent
if (_ROOT / "host_views_konto_klassifisering.py").exists():
    _MODULE_PATH = _ROOT / "host_views_konto_klassifisering.py"
    _IMPORT_ROOT = _ROOT.parent / "Utvalg-1"
else:
    _MODULE_PATH = _ROOT.parent / "views_konto_klassifisering.py"
    _IMPORT_ROOT = _ROOT.parent
sys.path.insert(0, str(_IMPORT_ROOT))
_SPEC = importlib.util.spec_from_file_location("host_views_konto_klassifisering", _MODULE_PATH)
assert _SPEC and _SPEC.loader
vkk = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vkk)


def test_build_account_rows_from_dataframe_preserves_amounts() -> None:
    df = pd.DataFrame(
        [
            {"Konto": "2600", "Navn": "Forskuddstrekk", "IB": -100.0, "Endring": 25.0, "UB": -75.0},
            {"Konto": "2770", "Navn": "Skyldig arbeidsgiveravgift", "IB": 0.0, "Endring": -10.0, "UB": -10.0},
        ]
    )

    rows = vkk._build_account_rows(df)

    assert rows == [
        {"konto": "2600", "navn": "Forskuddstrekk", "ib": -100.0, "endring": 25.0, "ub": -75.0},
        {"konto": "2770", "navn": "Skyldig arbeidsgiveravgift", "ib": 0.0, "endring": -10.0, "ub": -10.0},
    ]


def test_build_account_rows_from_tuples_defaults_amounts_to_zero() -> None:
    rows = vkk._build_account_rows([("1000", "Kasse"), ("2000", "Aksjekapital")])

    assert rows == [
        {"konto": "1000", "navn": "Kasse", "ib": 0.0, "endring": 0.0, "ub": 0.0},
        {"konto": "2000", "navn": "Aksjekapital", "ib": 0.0, "endring": 0.0, "ub": 0.0},
    ]


def test_has_amounts_detects_zero_rows() -> None:
    assert vkk._has_amounts({"ib": 0.0, "endring": 0.0, "ub": 0.0}) is False
    assert vkk._has_amounts({"ib": 0.0, "endring": 10.0, "ub": 0.0}) is True

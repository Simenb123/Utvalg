"""Tester for _resolve_target_kontoer: fjor-konto-inklusjon i RL-modus."""

from __future__ import annotations

import pandas as pd

import analyse_sb_refresh


class _StubVar:
    def __init__(self, value):
        self._v = value

    def get(self):
        return self._v


class _StubTreeOneSelection:
    """Minimal pivot-tree stub med én valgt RL."""

    def __init__(self, regnr: int, rl_navn: str):
        self._regnr = regnr
        self._navn = rl_navn

    def selection(self):
        return ("i0",)

    def set(self, item, col):
        if col == "Konto":
            return self._regnr
        if col == "Kontonavn":
            return self._navn
        return ""


def _intervals() -> pd.DataFrame:
    return pd.DataFrame({"fra": [1000, 3000], "til": [1999, 3999], "regnr": [10, 20]})


def _regnskapslinjer() -> pd.DataFrame:
    return pd.DataFrame({
        "nr": [10, 20],
        "regnskapslinje": ["Eiendeler", "Inntekter"],
        "sumpost": ["nei", "nei"],
        "Formel": ["", ""],
    })


def test_resolve_target_kontoer_includes_prior_only_accounts() -> None:
    """Konto som kun finnes i sb_prev skal bli med når vi velger dens RL."""
    sb_df = pd.DataFrame({
        "konto": ["1000"], "kontonavn": ["Bank"],
        "ib": [0.0], "ub": [100.0], "netto": [100.0],
    })
    sb_prev_df = pd.DataFrame({
        "konto": ["1000", "3000"], "kontonavn": ["Bank", "Salg"],
        "ib": [0.0, 0.0], "ub": [50.0, -900.0], "netto": [50.0, -900.0],
    })

    class _Page:
        pass

    page = _Page()
    page._var_aggregering = _StubVar("Regnskapslinje")
    page._pivot_tree = _StubTreeOneSelection(20, "Inntekter")
    page._rl_sb_prev_df = sb_prev_df
    page._rl_intervals = _intervals()
    page._rl_regnskapslinjer = _regnskapslinjer()

    result = analyse_sb_refresh._resolve_target_kontoer(
        page=page, sb_df=sb_df, konto_src="konto",
    )
    assert "3000" in result, (
        "Konto 3000 (kun i fjor-SB, mappet til RL 20) skal inkluderes"
    )


def test_resolve_target_kontoer_no_prev_df_is_harmless() -> None:
    """Hvis sb_prev_df mangler, skal funksjonen oppføre seg som før."""
    sb_df = pd.DataFrame({
        "konto": ["1000", "3000"], "kontonavn": ["Bank", "Salg"],
        "ib": [0.0, 0.0], "ub": [100.0, -500.0], "netto": [100.0, -500.0],
    })

    class _Page:
        pass

    page = _Page()
    page._var_aggregering = _StubVar("Regnskapslinje")
    page._pivot_tree = _StubTreeOneSelection(20, "Inntekter")
    page._rl_sb_prev_df = None
    page._rl_intervals = _intervals()
    page._rl_regnskapslinjer = _regnskapslinjer()

    result = analyse_sb_refresh._resolve_target_kontoer(
        page=page, sb_df=sb_df, konto_src="konto",
    )
    assert result == {"3000"}

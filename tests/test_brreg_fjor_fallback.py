"""Tester for BRREG som fjor-fallback i RL-pivot."""
from __future__ import annotations

import pandas as pd
import pytest

import src.shared.brreg.fjor_fallback as _bff


def _regnskapslinjer_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "nr": [19, 79, 80, 665, 715, 820],
            "regnskapslinje": [
                "Sum driftsinntekter",
                "Sum driftskostnader",
                "Driftsresultat",
                "Sum eiendeler",
                "Sum egenkapital",
                "Sum gjeld",
            ],
            "sumpost": ["ja"] * 6,
        }
    )


def _pivot_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "regnr": [19, 79, 80, 665, 715, 820],
            "regnskapslinje": [
                "Sum driftsinntekter",
                "Sum driftskostnader",
                "Driftsresultat",
                "Sum eiendeler",
                "Sum egenkapital",
                "Sum gjeld",
            ],
            "UB": [-1_000_000, 800_000, -200_000, 500_000, -200_000, -300_000],
        }
    )


def _brreg_multiyear(fjor: dict) -> dict:
    """Bygg _nk_brreg_data med year 2024 (current) og year 2023 (fjor)."""
    return {
        "orgnr": "123456789",
        "regnskapsaar": "2024",
        "linjer": {"driftsinntekter": 1_100_000.0},
        "years": {
            2024: {
                "regnskapsaar": "2024",
                "linjer": {"driftsinntekter": 1_100_000.0},
                "driftsinntekter": 1_100_000.0,
            },
            2023: {
                "regnskapsaar": "2023",
                "linjer": fjor,
                **fjor,
            },
        },
        "available_years": [2024, 2023],
    }


def test_has_brreg_for_year_true_when_year_present() -> None:
    brreg = _brreg_multiyear({"driftsinntekter": 900_000.0})
    assert _bff.has_brreg_for_year(brreg, 2023) is True
    assert _bff.has_brreg_for_year(brreg, 2024) is True


def test_has_brreg_for_year_false_when_year_missing() -> None:
    brreg = _brreg_multiyear({"driftsinntekter": 900_000.0})
    assert _bff.has_brreg_for_year(brreg, 2020) is False
    assert _bff.has_brreg_for_year(None, 2023) is False
    assert _bff.has_brreg_for_year({}, 2023) is False


def test_build_brreg_fjor_fills_ub_fjor() -> None:
    brreg = _brreg_multiyear({
        "driftsinntekter": 900_000.0,
        "driftskostnader": 700_000.0,
        "sum_eiendeler": 450_000.0,
    })
    out = _bff.build_brreg_fjor_pivot_columns(
        _pivot_df(), _regnskapslinjer_df(), brreg, 2023,
    )
    assert {"UB_fjor", "Endring_fjor", "Endring_pct"}.issubset(out.columns)

    row = out.loc[out["regnr"] == 19].iloc[0]
    # BRREG inntekter for 2023 = 900_000 → RL-fortegn −
    assert row["UB_fjor"] == pytest.approx(-900_000.0)
    # Endring = UB − UB_fjor = -1_000_000 − (-900_000) = -100_000
    assert row["Endring_fjor"] == pytest.approx(-100_000.0)
    # Endring % = -100_000 / 900_000 * 100 ≈ -11.11
    assert row["Endring_pct"] == pytest.approx(-100_000 / 900_000 * 100)


def test_build_brreg_fjor_leaves_none_without_data() -> None:
    out = _bff.build_brreg_fjor_pivot_columns(
        _pivot_df(), _regnskapslinjer_df(), None, 2023,
    )
    assert out["UB_fjor"].isna().all()
    assert out["Endring_fjor"].isna().all()
    assert out["Endring_pct"].isna().all()


def test_build_brreg_fjor_leaves_none_when_year_missing() -> None:
    brreg = _brreg_multiyear({"driftsinntekter": 900_000.0})
    # fjor_year 2020 finnes ikke i brreg
    out = _bff.build_brreg_fjor_pivot_columns(
        _pivot_df(), _regnskapslinjer_df(), brreg, 2020,
    )
    assert out["UB_fjor"].isna().all()


# ---------------------------------------------------------------------------
# Integrasjonstester via refresh_rl_pivot-flyten
# ---------------------------------------------------------------------------


class _FakeTree:
    def __init__(self) -> None:
        self.headings: dict[str, str] = {}
        self.rows: list[tuple] = []
        self._cols: tuple = ()

    def heading(self, col_id, text=None, **_kw):
        if text is not None:
            self.headings[col_id] = text
            return text
        return self.headings.get(col_id, "")

    def column(self, *_a, **_kw):
        return None

    def insert(self, parent, where, values, tags=()):
        self.rows.append(tuple(values))

    def __getitem__(self, key):
        if key == "columns":
            return self._cols
        raise KeyError(key)

    def delete(self, *children):
        self.rows.clear()

    def get_children(self, *_a, **_kw):
        return ()


def test_refresh_rl_pivot_fjor_source_is_sb_when_prev_loaded(monkeypatch) -> None:
    """Med sb_prev lastet skal fjor_source være 'sb' og ingen BRREG-fallback."""
    from types import SimpleNamespace
    import session as _session
    monkeypatch.setattr(_session, "year", "2024", raising=False)
    monkeypatch.setattr(_session, "client", "testklient", raising=False)

    tree = _FakeTree()
    sb_prev = pd.DataFrame({
        "konto": ["1920"], "kontonavn": ["Bank"],
        "ib": [0.0], "ub": [100_000.0], "netto": [100_000.0],
    })
    page = SimpleNamespace(
        _pivot_tree=tree,
        _df_filtered=pd.DataFrame({"Konto": ["1920"], "Beløp": [50.0], "Bilag": ["B1"]}),
        _rl_intervals=pd.DataFrame({"regnr": [665], "fra": [1000], "til": [1999]}),
        _rl_regnskapslinjer=_regnskapslinjer_df(),
        _rl_sb_prev_df=sb_prev,
        _nk_brreg_data=_brreg_multiyear({"driftsinntekter": 900_000.0}),
        _rl_fjor_source=None,
        _clear_tree=lambda t: None,
    )

    from page_analyse_rl_render import refresh_rl_pivot
    refresh_rl_pivot(page=page)
    assert page._rl_fjor_source == "sb"


def test_refresh_rl_pivot_fjor_source_is_brreg_when_sb_missing(monkeypatch) -> None:
    """Uten sb_prev men med BRREG-fjor-data skal fjor_source = 'brreg'."""
    from types import SimpleNamespace
    import session as _session
    monkeypatch.setattr(_session, "year", "2024", raising=False)
    monkeypatch.setattr(_session, "client", "testklient", raising=False)

    from page_analyse_rl_data import ensure_sb_prev_loaded  # noqa: F401
    import page_analyse_rl_render as _rlr
    monkeypatch.setattr(_rlr, "ensure_sb_prev_loaded", lambda *, page: None)

    tree = _FakeTree()
    page = SimpleNamespace(
        _pivot_tree=tree,
        _df_filtered=pd.DataFrame({"Konto": ["1920"], "Beløp": [50.0], "Bilag": ["B1"]}),
        _rl_intervals=pd.DataFrame({"regnr": [665], "fra": [1000], "til": [1999]}),
        _rl_regnskapslinjer=_regnskapslinjer_df(),
        _rl_sb_prev_df=None,
        _nk_brreg_data=_brreg_multiyear({
            "driftsinntekter": 900_000.0,
            "driftskostnader": 700_000.0,
            "sum_eiendeler": 450_000.0,
        }),
        _rl_fjor_source=None,
        _clear_tree=lambda t: None,
    )

    _rlr.refresh_rl_pivot(page=page)
    assert page._rl_fjor_source == "brreg"
    # Heading index 10 får (BRREG)-suffix
    assert "(BRREG)" in page._pivot_tree.headings.get("UB_fjor", "")


def test_refresh_rl_pivot_fjor_source_none_when_no_data(monkeypatch) -> None:
    """Verken sb_prev eller BRREG-år N-1 → fjor_source = None."""
    from types import SimpleNamespace
    import session as _session
    monkeypatch.setattr(_session, "year", "2024", raising=False)
    monkeypatch.setattr(_session, "client", "testklient", raising=False)

    import page_analyse_rl_render as _rlr
    monkeypatch.setattr(_rlr, "ensure_sb_prev_loaded", lambda *, page: None)

    tree = _FakeTree()
    page = SimpleNamespace(
        _pivot_tree=tree,
        _df_filtered=pd.DataFrame({"Konto": ["1920"], "Beløp": [50.0], "Bilag": ["B1"]}),
        _rl_intervals=pd.DataFrame({"regnr": [665], "fra": [1000], "til": [1999]}),
        _rl_regnskapslinjer=_regnskapslinjer_df(),
        _rl_sb_prev_df=None,
        _nk_brreg_data=None,
        _rl_fjor_source=None,
        _clear_tree=lambda t: None,
    )

    _rlr.refresh_rl_pivot(page=page)
    assert page._rl_fjor_source is None

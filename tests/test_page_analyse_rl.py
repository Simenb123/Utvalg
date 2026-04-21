"""Tester for regnskapslinje-pivot i Analyse-fanen.

Tester page_analyse_rl uten GUI (headless).
"""
from __future__ import annotations

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Testdata-hjelpere
# ---------------------------------------------------------------------------

def _make_hb() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Konto": ["1000", "1000", "1500", "3000", "3000", "9999"],
            "Beløp": [100.0, 200.0, 50.0, -400.0, -600.0, 10.0],
        }
    )


def _make_intervals() -> pd.DataFrame:
    return pd.DataFrame({"fra": [1000, 3000], "til": [1999, 3999], "regnr": [10, 20]})


def _make_regnskapslinjer() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "nr": [10, 20],
            "regnskapslinje": ["Eiendeler", "Inntekter"],
            "sumpost": ["nei", "nei"],
            "Formel": ["", ""],
        }
    )


def _make_regnskapslinjer_with_sum() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "nr": [10, 20, 30],
            "regnskapslinje": ["Eiendeler", "Inntekter", "Sum"],
            "sumpost": ["nei", "nei", "ja"],
            "Formel": ["", "", "=10+20"],
        }
    )


def _make_regnskapslinjer_with_hierarchy_sum() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "nr": [10, 20, 30, 40],
            "regnskapslinje": ["Eiendeler", "Inntekter", "Sum driftsinntekter", "Driftsresultat"],
            "sumpost": ["nei", "nei", "ja", "ja"],
            "sumnivå": [1, 1, 2, 3],
            "delsumnr": [30, 30, None, None],
            "sumnr": [40, 40, None, None],
            "Formel": ["", "", "", "=30"],
        }
    )


def _make_sb() -> pd.DataFrame:
    """Normalisert SB med IB og UB per konto."""
    return pd.DataFrame(
        {
            "konto": ["1000", "1500", "3000"],
            "kontonavn": ["Bank", "Kunder", "Salg"],
            "ib": [500.0, 200.0, 0.0],
            "ub": [600.0, 180.0, -1000.0],
            "netto": [100.0, -20.0, -1000.0],
        }
    )


def _make_sb_prev() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "konto": ["1000", "1500", "3000"],
            "kontonavn": ["Bank", "Kunder", "Salg"],
            "ib": [400.0, 250.0, 0.0],
            "ub": [500.0, 200.0, -900.0],
            "netto": [100.0, -50.0, -900.0],
        }
    )


# ---------------------------------------------------------------------------
# build_rl_pivot – uten SB (fallback)
# ---------------------------------------------------------------------------

def test_build_rl_pivot_no_sb_filters_zero_antall() -> None:
    """Uten SB skal linjer med antall=0 filtreres ut."""
    from page_analyse_rl import build_rl_pivot

    df_hb = pd.DataFrame({"Konto": ["1000"], "Beløp": [500.0]})
    regn = pd.DataFrame(
        {
            "nr": [10, 20],
            "regnskapslinje": ["Balanse", "Gjeld"],
            "sumpost": ["nei", "nei"],
            "Formel": ["", ""],
        }
    )
    pivot = build_rl_pivot(df_hb, _make_intervals(), regn, sb_df=None)

    # regnr 20 har ingen HB-transaksjoner → skal ikke vises
    assert set(pivot["regnr"].tolist()) == {10}


def test_build_rl_pivot_no_sb_basic() -> None:
    from page_analyse_rl import build_rl_pivot

    pivot = build_rl_pivot(_make_hb(), _make_intervals(), _make_regnskapslinjer(), sb_df=None)
    assert set(pivot.columns) == {"regnr", "regnskapslinje", "IB", "Endring", "UB", "Antall", "Antall_bilag"}
    assert set(pivot["regnr"].tolist()) == {10, 20}

    ub_10 = float(pivot.loc[pivot["regnr"] == 10, "UB"].iloc[0])
    assert ub_10 == pytest.approx(350.0)   # HB sum: 100+200+50

    endring_10 = float(pivot.loc[pivot["regnr"] == 10, "Endring"].iloc[0])
    assert endring_10 == pytest.approx(350.0)


def test_build_rl_pivot_includes_sumlinjer() -> None:
    from page_analyse_rl import build_rl_pivot

    pivot = build_rl_pivot(_make_hb(), _make_intervals(), _make_regnskapslinjer_with_sum(), sb_df=None)

    assert set(pivot["regnr"].tolist()) == {10, 20, 30}
    ub_sum = float(pivot.loc[pivot["regnr"] == 30, "UB"].iloc[0])
    antall_sum = int(pivot.loc[pivot["regnr"] == 30, "Antall"].iloc[0])
    assert ub_sum == pytest.approx(-650.0)
    assert antall_sum == 5


def test_build_rl_pivot_includes_hierarchy_sumlinjer_without_formula() -> None:
    from page_analyse_rl import build_rl_pivot

    df_hb = pd.DataFrame(
        {
            "Konto": ["1000", "3000", "3000"],
            "BelÃ¸p": [100.0, -25.0, -75.0],
        }
    )
    intervals = pd.DataFrame({"fra": [1000, 3000], "til": [1999, 3999], "regnr": [10, 20]})

    pivot = build_rl_pivot(df_hb, intervals, _make_regnskapslinjer_with_hierarchy_sum(), sb_df=None)

    assert set(pivot["regnr"].tolist()) == {10, 20, 30, 40}
    assert float(pivot.loc[pivot["regnr"] == 30, "UB"].iloc[0]) == pytest.approx(0.0)
    assert float(pivot.loc[pivot["regnr"] == 40, "UB"].iloc[0]) == pytest.approx(0.0)
    assert int(pivot.loc[pivot["regnr"] == 30, "Antall"].iloc[0]) == 3


# ---------------------------------------------------------------------------
# build_rl_pivot – med SB
# ---------------------------------------------------------------------------

def test_build_rl_pivot_with_sb_uses_sb_ub() -> None:
    """Med SB skal UB komme fra saldobalansen, ikke HB."""
    from page_analyse_rl import build_rl_pivot

    pivot = build_rl_pivot(_make_hb(), _make_intervals(), _make_regnskapslinjer(), sb_df=_make_sb())

    assert set(pivot["regnr"].tolist()) == {10, 20}

    # regnr 10: konto 1000 (UB=600) + konto 1500 (UB=180) = 780
    ub_10 = float(pivot.loc[pivot["regnr"] == 10, "UB"].iloc[0])
    assert ub_10 == pytest.approx(780.0)

    # regnr 20: konto 3000 (UB=-1000) = -1000
    ub_20 = float(pivot.loc[pivot["regnr"] == 20, "UB"].iloc[0])
    assert ub_20 == pytest.approx(-1000.0)


def test_build_rl_pivot_with_sb_ib() -> None:
    """Med SB skal IB-kolonnen fylles korrekt."""
    from page_analyse_rl import build_rl_pivot

    pivot = build_rl_pivot(_make_hb(), _make_intervals(), _make_regnskapslinjer(), sb_df=_make_sb())

    # regnr 10: konto 1000 (IB=500) + konto 1500 (IB=200) = 700
    ib_10 = float(pivot.loc[pivot["regnr"] == 10, "IB"].iloc[0])
    assert ib_10 == pytest.approx(700.0)

    endring_10 = float(pivot.loc[pivot["regnr"] == 10, "Endring"].iloc[0])
    assert endring_10 == pytest.approx(80.0)


def test_build_rl_pivot_with_sb_antall_from_hb() -> None:
    """Antall skal alltid komme fra HB-transaksjoner, ikke SB."""
    from page_analyse_rl import build_rl_pivot

    pivot = build_rl_pivot(_make_hb(), _make_intervals(), _make_regnskapslinjer(), sb_df=_make_sb())

    # regnr 10: 3 tx i HB (1000+1000+1500)
    ant_10 = int(pivot.loc[pivot["regnr"] == 10, "Antall"].iloc[0])
    assert ant_10 == 3


def test_build_rl_pivot_with_previous_year_columns() -> None:
    from page_analyse_rl import build_rl_pivot

    pivot = build_rl_pivot(
        _make_hb(),
        _make_intervals(),
        _make_regnskapslinjer(),
        sb_df=_make_sb(),
        sb_prev_df=_make_sb_prev(),
    )

    assert {"UB_fjor", "Endring_fjor", "Endring_pct"} <= set(pivot.columns)
    row_10 = pivot.loc[pivot["regnr"] == 10].iloc[0]
    assert float(row_10["UB_fjor"]) == pytest.approx(700.0)
    assert float(row_10["Endring_fjor"]) == pytest.approx(80.0)
    assert float(row_10["Endring_pct"]) == pytest.approx(11.4, abs=0.1)


def test_build_rl_pivot_includes_rl_with_only_prior_year_data() -> None:
    """RL som kun har fjorårsdata (ingen UB/HB i år) skal vises i pivot.

    Speiler bruker-rapportert feil: konto mappet til RL 10 i fjor, men ikke
    i år, slik at RL 10 blir borte selv om fjorårstallet er vesentlig.
    """
    from page_analyse_rl import build_rl_pivot

    df_hb = pd.DataFrame({"Konto": ["1000"], "Beløp": [100.0]})
    sb_current = pd.DataFrame(
        {
            "konto": ["1000"],
            "kontonavn": ["Bank"],
            "ib": [500.0],
            "ub": [600.0],
            "netto": [100.0],
        }
    )
    sb_prev = pd.DataFrame(
        {
            "konto": ["1000", "3000"],
            "kontonavn": ["Bank", "Salg"],
            "ib": [400.0, 0.0],
            "ub": [500.0, -900.0],
            "netto": [100.0, -900.0],
        }
    )

    pivot = build_rl_pivot(
        df_hb,
        _make_intervals(),
        _make_regnskapslinjer(),
        sb_df=sb_current,
        sb_prev_df=sb_prev,
    )

    regnr_list = set(pivot["regnr"].tolist())
    assert 20 in regnr_list, "RL 20 med kun fjorårs-UB skal vises"
    row_20 = pivot.loc[pivot["regnr"] == 20].iloc[0]
    assert float(row_20["UB"]) == pytest.approx(0.0)
    assert float(row_20["UB_fjor"]) == pytest.approx(-900.0)


def test_add_adjustment_columns_shows_before_after_and_delta() -> None:
    from page_analyse_rl import _add_adjustment_columns

    current = pd.DataFrame(
        {
            "regnr": [10, 20],
            "regnskapslinje": ["Eiendeler", "Inntekter"],
            "IB": [700.0, 0.0],
            "Endring": [80.0, -900.0],
            "UB": [780.0, -900.0],
            "Antall": [3, 2],
        }
    )
    before = pd.DataFrame(
        {
            "regnr": [10, 20],
            "UB": [700.0, -1000.0],
        }
    )
    after = pd.DataFrame(
        {
            "regnr": [10, 20, 30],
            "UB": [780.0, -900.0, 50.0],
        }
    )

    out = _add_adjustment_columns(
        current,
        base_pivot_df=before,
        adjusted_pivot_df=after,
    )

    row_10 = out.loc[out["regnr"] == 10].iloc[0]
    row_20 = out.loc[out["regnr"] == 20].iloc[0]

    assert float(row_10["UB_for_ao"]) == pytest.approx(700.0)
    assert float(row_10["UB_etter_ao"]) == pytest.approx(780.0)
    assert float(row_10["AO_belop"]) == pytest.approx(80.0)
    assert float(row_20["UB_for_ao"]) == pytest.approx(-1000.0)
    assert float(row_20["UB_etter_ao"]) == pytest.approx(-900.0)
    assert float(row_20["AO_belop"]) == pytest.approx(100.0)


def test_build_rl_pivot_with_sb_shows_zero_ub_with_transactions() -> None:
    """Regnskapslinjer med Antall>0 men UB=0 skal vises (0-saldo er reell info)."""
    from page_analyse_rl import build_rl_pivot

    sb = pd.DataFrame(
        {
            "konto": ["1000"],
            "kontonavn": ["Bank"],
            "ib": [100.0],
            "ub": [0.0],  # Null UB
            "netto": [-100.0],
        }
    )
    pivot = build_rl_pivot(_make_hb(), _make_intervals(), _make_regnskapslinjer(), sb_df=sb)

    # regnr 10 har UB=0 men Antall>0 → skal vises
    assert 10 in pivot["regnr"].tolist()


def test_build_rl_pivot_with_sb_hides_zero_ub_no_transactions() -> None:
    """Regnskapslinjer med UB=0 og Antall=0 skal skjules."""
    from page_analyse_rl import build_rl_pivot

    sb = pd.DataFrame(
        {
            "konto": ["3000"],
            "kontonavn": ["Salg"],
            "ib": [0.0],
            "ub": [-1000.0],
            "netto": [-1000.0],
        }
    )
    # HB har bare konto 1000-serien
    df_hb = pd.DataFrame({"Konto": ["1000"], "Beløp": [500.0]})

    pivot = build_rl_pivot(df_hb, _make_intervals(), _make_regnskapslinjer(), sb_df=sb)

    # regnr 10: HB-transaksjoner finnes, men ingen SB for 1000-serien → UB=0
    # regnr 20: SB UB=-1000, ingen HB-tx → skal vises (UB != 0)
    regnr_list = set(pivot["regnr"].tolist())
    assert 20 in regnr_list  # SB-saldo er reell


def test_build_rl_pivot_tom_hb_returnerer_tom() -> None:
    from page_analyse_rl import build_rl_pivot

    empty = pd.DataFrame(columns=["Konto", "Beløp"])
    pivot = build_rl_pivot(empty, _make_intervals(), _make_regnskapslinjer(), sb_df=None)
    assert pivot.empty


# ---------------------------------------------------------------------------
# get_selected_rl_accounts
# ---------------------------------------------------------------------------

class _FakePage:
    def __init__(self, selected_regnr, df_filtered, intervals, regnskapslinjer=None):
        self._df_filtered = df_filtered
        self._rl_intervals = intervals
        self._rl_regnskapslinjer = regnskapslinjer
        self._pivot_tree = _FakeTree(selected_regnr)


class _FakeTree:
    def __init__(self, regnr_list):
        self._items = {f"item{i}": str(r) for i, r in enumerate(regnr_list)}

    def selection(self):
        return list(self._items.keys())

    def get_children(self):
        return list(self._items.keys())

    def set(self, item, col):
        if col == "Konto":
            return self._items.get(item, "")
        return ""


class _InsertTree:
    def __init__(self):
        self.rows = []

    def heading(self, *_a, **_k):
        return None

    def column(self, *_a, **_k):
        return None

    def get_children(self, *_a, **_k):
        return []

    def delete(self, *_a, **_k):
        return None

    def insert(self, _parent, _index, values=(), tags=()):
        self.rows.append({"values": values, "tags": tags})
        return None


class _RefreshTree:
    def __init__(self):
        self.rows = {"old10": {"Konto": "10", "Kontonavn": "Eiendeler"}}
        self._selection = ["old10"]

    def selection(self):
        return list(self._selection)

    def focus(self):
        return self._selection[0] if self._selection else ""

    def get_children(self, *_a, **_k):
        return list(self.rows.keys())

    def set(self, item, col):
        return self.rows.get(item, {}).get(col, "")

    def delete(self, item):
        self.rows.pop(item, None)

    def insert(self, _parent, _index, values=(), tags=()):
        item = f"row{len(self.rows) + 1}"
        self.rows[item] = {
            "Konto": values[0] if len(values) > 0 else "",
            "Kontonavn": values[1] if len(values) > 1 else "",
        }
        return item


def test_get_selected_rl_accounts_basic() -> None:
    from page_analyse_rl import get_selected_rl_accounts

    page = _FakePage(selected_regnr=[10], df_filtered=_make_hb(), intervals=_make_intervals())
    accounts = get_selected_rl_accounts(page=page)
    assert sorted(accounts) == ["1000", "1500"]


def test_get_selected_rl_accounts_multiple() -> None:
    from page_analyse_rl import get_selected_rl_accounts

    page = _FakePage(selected_regnr=[10, 20], df_filtered=_make_hb(), intervals=_make_intervals())
    accounts = get_selected_rl_accounts(page=page)
    assert sorted(accounts) == ["1000", "1500", "3000"]


def test_get_selected_rl_accounts_no_intervals_returns_empty() -> None:
    from page_analyse_rl import get_selected_rl_accounts

    page = _FakePage(selected_regnr=[10], df_filtered=_make_hb(), intervals=None)
    assert get_selected_rl_accounts(page=page) == []


def test_get_selected_rl_accounts_sumline_expands_to_leaf_accounts() -> None:
    from page_analyse_rl import get_selected_rl_accounts

    page = _FakePage(
        selected_regnr=[30],
        df_filtered=_make_hb(),
        intervals=_make_intervals(),
        regnskapslinjer=_make_regnskapslinjer_with_sum(),
    )
    accounts = get_selected_rl_accounts(page=page)
    assert sorted(accounts) == ["1000", "1500", "3000"]


def test_get_selected_rl_accounts_hierarchy_sumline_expands_to_leaf_accounts() -> None:
    from page_analyse_rl import get_selected_rl_accounts

    df_hb = pd.DataFrame(
        {
            "Konto": ["1000", "3000"],
            "BelÃ¸p": [100.0, -100.0],
        }
    )
    intervals = pd.DataFrame({"fra": [1000, 3000], "til": [1999, 3999], "regnr": [10, 20]})
    page = _FakePage(
        selected_regnr=[30],
        df_filtered=df_hb,
        intervals=intervals,
        regnskapslinjer=_make_regnskapslinjer_with_hierarchy_sum(),
    )

    assert sorted(get_selected_rl_accounts(page=page)) == ["1000", "3000"]


def test_get_unmapped_rl_accounts_returns_missing_accounts() -> None:
    from page_analyse_rl import get_unmapped_rl_accounts

    accounts = get_unmapped_rl_accounts(_make_hb(), _make_intervals())
    assert accounts == ["9999"]


def test_get_unmapped_rl_accounts_respects_overrides() -> None:
    from page_analyse_rl import get_unmapped_rl_accounts

    accounts = get_unmapped_rl_accounts(_make_hb(), _make_intervals(), account_overrides={"9999": 20})
    assert accounts == []


def test_build_rl_account_drilldown_with_sb() -> None:
    from page_analyse_rl import build_rl_account_drilldown

    out = build_rl_account_drilldown(
        _make_hb(),
        _make_intervals(),
        _make_regnskapslinjer(),
        sb_df=_make_sb(),
        regnr_filter=[10],
    )

    assert list(out.columns) == ["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"]
    assert set(out["Konto"]) == {"1000", "1500"}
    row_1000 = out.loc[out["Konto"] == "1000"].iloc[0]
    assert float(row_1000["IB"]) == pytest.approx(500.0)
    assert float(row_1000["UB"]) == pytest.approx(600.0)
    assert int(row_1000["Antall"]) == 2


def test_build_rl_account_drilldown_without_sb_uses_hb_sum() -> None:
    from page_analyse_rl import build_rl_account_drilldown

    out = build_rl_account_drilldown(
        _make_hb(),
        _make_intervals(),
        _make_regnskapslinjer(),
        sb_df=None,
        regnr_filter=[20],
    )

    row_3000 = out.loc[out["Konto"] == "3000"].iloc[0]
    assert float(row_3000["IB"]) == pytest.approx(0.0)
    assert float(row_3000["Endring"]) == pytest.approx(-1000.0)
    assert float(row_3000["UB"]) == pytest.approx(-1000.0)


def test_build_rl_account_drilldown_sumline_expands_to_leaf_accounts() -> None:
    from page_analyse_rl import build_rl_account_drilldown

    out = build_rl_account_drilldown(
        _make_hb(),
        _make_intervals(),
        _make_regnskapslinjer_with_sum(),
        sb_df=None,
        regnr_filter=[30],
    )

    assert set(out["Konto"]) == {"1000", "1500", "3000"}


def test_build_rl_pivot_respects_account_overrides() -> None:
    from page_analyse_rl import build_rl_pivot

    pivot = build_rl_pivot(
        _make_hb(),
        _make_intervals(),
        _make_regnskapslinjer(),
        sb_df=None,
        account_overrides={"9999": 20},
    )

    ub_20 = float(pivot.loc[pivot["regnr"] == 20, "UB"].iloc[0])
    assert ub_20 == pytest.approx(-990.0)


def test_refresh_rl_pivot_marks_sumline_rows_visually() -> None:
    from page_analyse_rl import refresh_rl_pivot

    class _Page:
        def __init__(self):
            self._pivot_tree = _InsertTree()
            self._df_filtered = _make_hb()
            self._rl_intervals = _make_intervals()
            self._rl_regnskapslinjer = _make_regnskapslinjer_with_sum()
            self._rl_sb_df = None
            self._rl_mapping_warning = ""

        @staticmethod
        def _clear_tree(_tree):
            return None

        def _maybe_auto_fit_pivot_tree(self):
            return None

    page = _Page()
    refresh_rl_pivot(page=page)

    sum_rows = [row for row in page._pivot_tree.rows if row["values"][0] == "30"]
    assert len(sum_rows) == 1
    assert sum_rows[0]["values"][1].startswith("Σ ")
    assert sum_rows[0]["tags"] == ("sumline",)


# ---------------------------------------------------------------------------
# load_sb_for_session – graceful ved manglende klient/SB
# ---------------------------------------------------------------------------

def test_load_sb_returns_none_when_no_client(monkeypatch) -> None:
    import session as _session
    monkeypatch.setattr(_session, "client", None, raising=False)
    monkeypatch.setattr(_session, "year", None, raising=False)

    from page_analyse_rl import load_sb_for_session
    assert load_sb_for_session() is None


def test_load_sb_returns_none_when_no_active_version(monkeypatch, tmp_path) -> None:
    import session as _session
    monkeypatch.setattr(_session, "client", "TestKlient", raising=False)
    monkeypatch.setattr(_session, "year", "2025", raising=False)
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    # Ingen klientmappe → get_active_version returnerer None
    from page_analyse_rl import load_sb_for_session
    result = load_sb_for_session()
    assert result is None


# ---------------------------------------------------------------------------
# load_rl_config – graceful når filer mangler
# ---------------------------------------------------------------------------

def test_load_rl_config_returns_none_when_not_configured(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))
    from page_analyse_rl import load_rl_config
    intervals, regnskapslinjer = load_rl_config()
    assert intervals is None
    assert regnskapslinjer is None


def test_refresh_rl_pivot_restores_selected_regnskapslinje(monkeypatch) -> None:
    import page_analyse_rl

    restore_calls = []

    class _Page:
        def __init__(self):
            self._pivot_tree = _RefreshTree()
            self._df_filtered = _make_hb()
            self._rl_intervals = _make_intervals()
            self._rl_regnskapslinjer = _make_regnskapslinjer()
            self._rl_sb_df = None
            self._rl_mapping_warning = ""

        @staticmethod
        def _clear_tree(tree):
            for item in list(tree.get_children("")):
                tree.delete(item)

        def _maybe_auto_fit_pivot_tree(self):
            return None

        def _restore_rl_pivot_selection(self, values):
            restore_calls.append(list(values))

    monkeypatch.setattr(page_analyse_rl, "update_pivot_headings", lambda **_k: None)

    page = _Page()
    page_analyse_rl.refresh_rl_pivot(page=page)

    assert restore_calls == [[10]]

"""Tester for ny standard RL-visning og dynamiske kolonneoverskrifter.

Dekker:
- PIVOT_COLS_DEFAULT_RL (med fjorårsdata) inneholder ikke intern "Endring"
  (som er UB - IB = Bevegelse i år), men beholder prev-year-kolonnene.
- pivot_default_for_mode gir riktig kolonneliste med og uten fjorårsdata.
- update_pivot_headings bygger "UB <år>" / "UB <år-1>"-labels fra
  session.year og bruker ny label-samling ("Bevegelse i år", "Endring",
  "Endring %").
- _LEGACY_RL_VISIBLE_DEFAULTS inneholder forrige default slik at
  adapt_pivot_columns_for_mode migrerer brukere som hadde gamle defaults.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any


# ---------------------------------------------------------------------------
# PIVOT_COLS_DEFAULT_RL
# ---------------------------------------------------------------------------

def test_pivot_cols_default_rl_excludes_internal_endring() -> None:
    """Intern 'Endring' (= UB - IB) skal ikke være synlig som standard i RL
    når fjorårsdata finnes — fjorårs-'Endring_fjor' tar den rollen."""
    from page_analyse import AnalysePage

    default_rl = AnalysePage.PIVOT_COLS_DEFAULT_RL
    assert "Endring" not in default_rl
    assert default_rl == (
        "Konto",
        "Kontonavn",
        "Sum",
        "UB_fjor",
        "Endring_fjor",
        "Endring_pct",
        "Antall",
    )


# ---------------------------------------------------------------------------
# pivot_default_for_mode
# ---------------------------------------------------------------------------

def _make_page(*, aggregering: str, has_prev: bool) -> Any:
    """Bygg en minimal duck-typed page for pivot_default_for_mode."""
    import pandas as pd
    from page_analyse import AnalysePage

    pivot_df = pd.DataFrame({"UB_fjor": [1.0]}) if has_prev else pd.DataFrame()
    return SimpleNamespace(
        _var_aggregering=SimpleNamespace(get=lambda: aggregering),
        _pivot_df_last=pivot_df,
        _rl_sb_prev_df=None,
        PIVOT_COLS_DEFAULT_VISIBLE=AnalysePage.PIVOT_COLS_DEFAULT_VISIBLE,
        PIVOT_COLS_DEFAULT_KONTO=AnalysePage.PIVOT_COLS_DEFAULT_KONTO,
        PIVOT_COLS_DEFAULT_HB_KONTO=AnalysePage.PIVOT_COLS_DEFAULT_HB_KONTO,
        PIVOT_COLS_DEFAULT_SB_KONTO=AnalysePage.PIVOT_COLS_DEFAULT_SB_KONTO,
        PIVOT_COLS_DEFAULT_RL=AnalysePage.PIVOT_COLS_DEFAULT_RL,
    )


def test_pivot_default_for_mode_rl_with_prev_year_matches_new_default() -> None:
    from page_analyse_columns import pivot_default_for_mode

    page = _make_page(aggregering="Regnskapslinje", has_prev=True)
    cols = pivot_default_for_mode(page=page)
    assert cols == (
        "Konto",
        "Kontonavn",
        "Sum",
        "UB_fjor",
        "Endring_fjor",
        "Endring_pct",
        "Antall",
    )


def test_pivot_default_for_mode_rl_without_prev_year_is_slim() -> None:
    """Uten fjorårsdata skal default vise slank visning uten 'Endring'
    (Bevegelse i år) — fallback-kolonnen er ikke standard synlig, men
    forblir tilgjengelig via kolonne-menyen."""
    from page_analyse_columns import pivot_default_for_mode

    page = _make_page(aggregering="Regnskapslinje", has_prev=False)
    cols = pivot_default_for_mode(page=page)
    assert "Endring" not in cols
    assert cols == (
        "Konto",
        "Kontonavn",
        "Sum",
        "Antall",
    )


def test_pivot_default_for_mode_legacy_konto_maps_to_sb_konto_with_prev() -> None:
    """Legacy 'Konto'-verdi skal migreres til SB-konto-default."""
    from page_analyse_columns import pivot_default_for_mode
    from page_analyse import AnalysePage

    page = _make_page(aggregering="Konto", has_prev=True)
    assert pivot_default_for_mode(page=page) == AnalysePage.PIVOT_COLS_DEFAULT_SB_KONTO


def test_pivot_default_for_mode_hb_konto_legacy_maps_to_sb_konto() -> None:
    """Legacy 'HB-konto'-verdi skal migreres til SB-konto-default etter at
    Aggregering-dropdownen er redusert til Saldobalanse/Regnskapslinje."""
    from page_analyse_columns import pivot_default_for_mode
    from page_analyse import AnalysePage

    page = _make_page(aggregering="HB-konto", has_prev=True)
    assert pivot_default_for_mode(page=page) == AnalysePage.PIVOT_COLS_DEFAULT_SB_KONTO


def test_pivot_default_for_mode_sb_konto_with_prev_year() -> None:
    from page_analyse_columns import pivot_default_for_mode

    page = _make_page(aggregering="SB-konto", has_prev=True)
    cols = pivot_default_for_mode(page=page)
    assert cols == (
        "Konto",
        "Kontonavn",
        "Sum",
        "UB_fjor",
        "Endring_fjor",
        "Endring_pct",
        "Antall",
    )


def test_pivot_default_for_mode_sb_konto_without_prev_year_is_slim() -> None:
    """SB-konto uten fjorsdata: slank visning uten intern 'Endring' —
    fallback-kolonnen er tilgjengelig via kolonne-menyen."""
    from page_analyse_columns import pivot_default_for_mode

    page = _make_page(aggregering="SB-konto", has_prev=False)
    cols = pivot_default_for_mode(page=page)
    assert "Endring" not in cols
    assert cols == (
        "Konto",
        "Kontonavn",
        "Sum",
        "Antall",
    )


def test_normalize_aggregation_mode_maps_legacy_konto() -> None:
    from page_analyse_columns import normalize_aggregation_mode

    assert normalize_aggregation_mode("Konto") == "SB-konto"
    assert normalize_aggregation_mode("SB-konto") == "SB-konto"
    # Legacy GUI-moduser som nå er fjernet kollapses til SB-konto.
    assert normalize_aggregation_mode("HB-konto") == "SB-konto"
    assert normalize_aggregation_mode("MVA-kode") == "SB-konto"
    # Nytt user-facing label.
    assert normalize_aggregation_mode("Saldobalanse") == "SB-konto"
    assert normalize_aggregation_mode("Regnskapslinje") == "Regnskapslinje"
    assert normalize_aggregation_mode("") == "SB-konto"
    assert normalize_aggregation_mode(None) == "SB-konto"


# ---------------------------------------------------------------------------
# Legacy-migrering
# ---------------------------------------------------------------------------

def test_legacy_rl_defaults_include_previous_default_tuple() -> None:
    """Forrige PIVOT_COLS_DEFAULT_RL (med intern Endring) skal fanges
    av _LEGACY_RL_VISIBLE_DEFAULTS slik at brukere som hadde den
    migreres til ny default ved modusbytte."""
    from page_analyse_columns import _LEGACY_RL_VISIBLE_DEFAULTS

    prev_default = (
        "Konto",
        "Kontonavn",
        "Sum",
        "UB_fjor",
        "Endring",
        "Endring_fjor",
        "Endring_pct",
        "Antall",
    )
    assert prev_default in _LEGACY_RL_VISIBLE_DEFAULTS


# ---------------------------------------------------------------------------
# update_pivot_headings — dynamiske år-labels
# ---------------------------------------------------------------------------

class _FakeTree:
    def __init__(self) -> None:
        self.headings: dict[str, str] = {}

    def heading(self, col_id: str, text: str | None = None, **_kw: Any) -> str:
        if text is not None:
            self.headings[col_id] = text
            return text
        return self.headings.get(col_id, "")

    def column(self, *_a: Any, **_kw: Any) -> None:
        return None


def _make_heading_page() -> Any:
    tree = _FakeTree()
    return SimpleNamespace(
        _pivot_tree=tree,
        _rl_sb_prev_df=None,
        _nk_brreg_data=None,
    )


def test_update_pivot_headings_substitutes_active_year(monkeypatch) -> None:
    import session as _session
    monkeypatch.setattr(_session, "year", "2025", raising=False)

    from page_analyse_rl import update_pivot_headings

    page = _make_heading_page()
    update_pivot_headings(page=page, mode="Regnskapslinje")

    assert page._pivot_tree.headings["Sum"] == "UB 2025"
    assert page._pivot_tree.headings["UB_fjor"] == "UB 2024"
    # Med år: kompakt 2-sifret endringsformat
    assert page._pivot_tree.headings["Endring"] == "Δ UB-IB 25"
    assert page._pivot_tree.headings["Endring_fjor"] == "Δ UB 25/24"
    assert page._pivot_tree.headings["Endring_pct"] == "Δ % UB 25/24"


def test_update_pivot_headings_falls_back_when_year_missing(monkeypatch) -> None:
    import session as _session
    monkeypatch.setattr(_session, "year", None, raising=False)

    from page_analyse_rl import update_pivot_headings

    page = _make_heading_page()
    update_pivot_headings(page=page, mode="Regnskapslinje")

    # Uten år: UB og UB_fjor beholder statiske labels
    assert page._pivot_tree.headings["Sum"] == "UB"
    assert page._pivot_tree.headings["UB_fjor"] == "UB i fjor"
    assert page._pivot_tree.headings["Endring"] == "Δ UB-IB"
    assert page._pivot_tree.headings["Endring_fjor"] == "Δ UB"


def test_update_pivot_headings_hb_konto_uses_hb_bevegelse(monkeypatch) -> None:
    import session as _session
    monkeypatch.setattr(_session, "year", "2025", raising=False)

    from page_analyse_rl import update_pivot_headings

    page = _make_heading_page()
    update_pivot_headings(page=page, mode="HB-konto")

    assert page._pivot_tree.headings["Konto"] == "Konto"
    assert page._pivot_tree.headings["Kontonavn"] == "Kontonavn"
    # HB-konto: heading skal være "HB-bevegelse", ikke "Sum"
    assert page._pivot_tree.headings["Sum"] == "HB-bevegelse"
    assert page._pivot_tree.headings["Antall"] == "Antall"
    # Ingen komparative kolonner i HB-konto
    assert page._pivot_tree.headings["UB_fjor"] == ""


def test_update_pivot_headings_sb_konto_injects_active_year(monkeypatch) -> None:
    import session as _session
    monkeypatch.setattr(_session, "year", "2025", raising=False)

    from page_analyse_rl import update_pivot_headings

    page = _make_heading_page()
    update_pivot_headings(page=page, mode="SB-konto")

    assert page._pivot_tree.headings["Konto"] == "Konto"
    assert page._pivot_tree.headings["Kontonavn"] == "Kontonavn"
    assert page._pivot_tree.headings["Sum"] == "UB 2025"
    assert page._pivot_tree.headings["UB_fjor"] == "UB 2024"
    assert page._pivot_tree.headings["Endring_fjor"] == "Δ UB 25/24"
    assert page._pivot_tree.headings["Endring_pct"] == "Δ % UB 25/24"
    assert page._pivot_tree.headings["Antall"] == "Antall"


def test_update_pivot_headings_legacy_konto_maps_to_sb_konto(monkeypatch) -> None:
    """Legacy mode 'Konto' skal behandles som 'SB-konto' (år injiseres)."""
    import session as _session
    monkeypatch.setattr(_session, "year", "2025", raising=False)

    from page_analyse_rl import update_pivot_headings

    page = _make_heading_page()
    update_pivot_headings(page=page, mode="Konto")

    assert page._pivot_tree.headings["Sum"] == "UB 2025"
    assert page._pivot_tree.headings["UB_fjor"] == "UB 2024"


def test_rl_headings_with_year_helper() -> None:
    from page_analyse_rl import _rl_headings_with_year

    headings = _rl_headings_with_year(2025)
    # Index 5 = UB aktivt år (kolonne-ID "Sum"), index 10 = UB_fjor.
    assert headings[5] == "UB 2025"
    assert headings[10] == "UB 2024"
    # Øvrige labels uendret
    assert headings[0] == "Nr"
    assert headings[1] == "Regnskapslinje"
    assert headings[2] == ""               # OK — ikke relevant for RL
    assert headings[3] == "IB 2025"
    assert headings[4] == "Δ UB-IB 25"
    assert headings[9] == "Antall"
    assert headings[11] == "Δ UB 25/24"
    assert headings[12] == "Δ % UB 25/24"


def test_rl_headings_with_year_none_returns_static() -> None:
    from page_analyse_rl import _rl_headings_with_year, RL_PIVOT_HEADINGS

    assert _rl_headings_with_year(None) == RL_PIVOT_HEADINGS


def test_rl_headings_injects_brreg_year_at_index_13() -> None:
    from page_analyse_rl import _rl_headings_with_year

    headings = _rl_headings_with_year(2025, brreg_year=2024)
    assert headings[13] == "BRREG 2024"
    # Uendrede indekser
    assert headings[5] == "UB 2025"
    assert headings[10] == "UB 2024"
    assert headings[14] == "Avvik mot BRREG"


def test_rl_headings_without_brreg_year_keeps_static() -> None:
    from page_analyse_rl import _rl_headings_with_year

    headings = _rl_headings_with_year(2025)
    assert headings[13] == "BRREG"


def test_update_pivot_headings_reads_brreg_year_from_data(monkeypatch) -> None:
    import session as _session
    monkeypatch.setattr(_session, "year", "2025", raising=False)

    from page_analyse_rl import update_pivot_headings

    page = _make_heading_page()
    page._nk_brreg_data = {
        "regnskapsaar": "2023",
        "available_years": [2023, 2022],
        "linjer": {"driftsinntekter": 100.0},
        "years": {
            2023: {"linjer": {"driftsinntekter": 100.0}, "regnskapsaar": "2023"},
            2022: {"linjer": {"driftsinntekter": 90.0}, "regnskapsaar": "2022"},
        },
    }
    update_pivot_headings(page=page, mode="Regnskapslinje")

    assert page._pivot_tree.headings["BRREG"] == "BRREG 2023"


def test_analysis_heading_brreg_year() -> None:
    import page_analyse_columns as _cols

    assert _cols.analysis_heading("BRREG") == "BRREG"
    assert _cols.analysis_heading("BRREG", brreg_year=2024) == "BRREG 2024"


# ---------------------------------------------------------------------------
# update_pivot_columns_for_prev_year — lazy-loaded fjorårsdata
# ---------------------------------------------------------------------------

class _LazyPrevTree:
    def __init__(self) -> None:
        self._cols = (
            "Konto", "Kontonavn", "IB", "Endring", "Sum", "AO_belop",
            "UB_for_ao", "UB_etter_ao", "Antall", "UB_fjor", "Endring_fjor",
            "Endring_pct", "BRREG", "Avvik_brreg", "Avvik_brreg_pct",
        )

    def __getitem__(self, key: str) -> tuple[str, ...]:
        if key == "columns":
            return self._cols
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        return None


def test_update_pivot_columns_for_prev_year_adds_endring_fjor(monkeypatch) -> None:
    """Når fjorårsdata lastes lazy skal Endring_fjor også legges til
    (ikke bare UB_fjor og Endring_pct som før)."""
    import pandas as pd
    from page_analyse import AnalysePage
    import page_analyse_columns

    monkeypatch.setattr(page_analyse_columns, "persist_pivot_visible_columns", lambda **_: None)

    page = SimpleNamespace(
        _var_aggregering=SimpleNamespace(get=lambda: "Regnskapslinje"),
        _pivot_df_last=pd.DataFrame({"UB_fjor": [1.0]}),
        _rl_sb_prev_df=None,
        _pivot_visible_cols=["Konto", "Kontonavn", "IB", "Sum", "Antall"],
        _pivot_tree=_LazyPrevTree(),
        PIVOT_COLS_DEFAULT_VISIBLE=AnalysePage.PIVOT_COLS_DEFAULT_VISIBLE,
    )

    page_analyse_columns.update_pivot_columns_for_prev_year(page=page)

    # IB er fjernet, UB_fjor/Endring_fjor/Endring_pct er lagt til i riktig rekkefølge
    assert "IB" not in page._pivot_visible_cols
    for col in ("UB_fjor", "Endring_fjor", "Endring_pct"):
        assert col in page._pivot_visible_cols
    sum_idx = page._pivot_visible_cols.index("Sum")
    assert page._pivot_visible_cols[sum_idx + 1] == "UB_fjor"
    assert page._pivot_visible_cols[sum_idx + 2] == "Endring_fjor"
    assert page._pivot_visible_cols[sum_idx + 3] == "Endring_pct"


# ---------------------------------------------------------------------------
# SB-konto pivot-builder
# ---------------------------------------------------------------------------

def test_build_sb_konto_pivot_uses_sb_ub_as_sum() -> None:
    """SB-konto pivot skal ta UB fra effektiv SB som "Sum beløp"."""
    import pandas as pd
    from page_analyse_pivot import _build_sb_konto_pivot

    sb = pd.DataFrame({
        "konto": ["1920", "3000"],
        "kontonavn": ["Bank", "Salg"],
        "ib": [0.0, 0.0],
        "ub": [100.0, -500.0],
        "netto": [100.0, -500.0],
    })

    page = SimpleNamespace(
        _get_effective_sb_df=lambda: sb,
        _rl_sb_prev_df=None,
        _df_filtered=None,
    )

    out = _build_sb_konto_pivot(page=page)
    row_bank = out.loc[out["Konto"] == "1920"].iloc[0]
    assert row_bank["Sum beløp"] == 100.0
    assert row_bank["Kontonavn"] == "Bank"
    # Uten fjorsdata: UB_fjor er NA, fallback Endring = netto
    assert pd.isna(row_bank["UB_fjor"])
    assert row_bank["Endring"] == 100.0


def test_build_sb_konto_pivot_comparative_with_prev_year() -> None:
    """Når fjorårs SB er lastet skal UB_fjor, Endring_fjor og Endring_pct beregnes."""
    import pandas as pd
    from page_analyse_pivot import _build_sb_konto_pivot

    sb = pd.DataFrame({
        "konto": ["1920"],
        "kontonavn": ["Bank"],
        "ib": [50.0],
        "ub": [120.0],
        "netto": [70.0],
    })
    sb_prev = pd.DataFrame({
        "konto": ["1920"],
        "kontonavn": ["Bank"],
        "ib": [0.0],
        "ub": [100.0],
        "netto": [100.0],
    })

    page = SimpleNamespace(
        _get_effective_sb_df=lambda: sb,
        _rl_sb_prev_df=sb_prev,
        _df_filtered=None,
    )

    out = _build_sb_konto_pivot(page=page)
    row = out.iloc[0]
    assert row["Sum beløp"] == 120.0
    assert row["UB_fjor"] == 100.0
    assert row["Endring_fjor"] == 20.0
    assert round(float(row["Endring_pct"]), 2) == 20.0


def test_build_sb_konto_pivot_maps_antall_from_hb_pivot() -> None:
    """Antall bilag skal tas fra build_pivot_by_account(df_filtered) (nunique Bilag)."""
    import pandas as pd
    from page_analyse_pivot import _build_sb_konto_pivot

    sb = pd.DataFrame({
        "konto": ["1920", "3000"],
        "kontonavn": ["Bank", "Salg"],
        "ib": [0.0, 0.0],
        "ub": [100.0, -500.0],
        "netto": [100.0, -500.0],
    })
    df_filtered = pd.DataFrame({
        "Konto": ["1920", "1920", "1920", "3000"],
        "Kontonavn": ["Bank", "Bank", "Bank", "Salg"],
        "Bilag": ["B1", "B2", "B2", "B9"],  # 1920 har 2 unike bilag
        "Beløp": [50.0, 30.0, 20.0, -500.0],
    })

    page = SimpleNamespace(
        _get_effective_sb_df=lambda: sb,
        _rl_sb_prev_df=None,
        _df_filtered=df_filtered,
    )

    out = _build_sb_konto_pivot(page=page)
    row_bank = out.loc[out["Konto"] == "1920"].iloc[0]
    assert int(row_bank["Antall bilag"]) == 2
    row_salg = out.loc[out["Konto"] == "3000"].iloc[0]
    assert int(row_salg["Antall bilag"]) == 1

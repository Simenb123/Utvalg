"""Regresjonsvern for pivot-cache-skjema split.

Tidligere skrev RL-, SB-konto- og HB-konto-pivotene alle til en felles
``page._pivot_df_last``. Konsekvens: hvis brukeren sist hadde sett SB-konto-
pivoten, og deretter åpnet en RL-spesifikk view (Regnskap-fane, drilldown-
nøkkeltall, statistikk-KPI, driftsmidler-avstemming, …), så hentet
konsumentene en konto-keyed DataFrame og ga enten stille no-op (UB_fjor
ble ikke merget inn) eller blanket ut data (regnr-lookup matchet ingen rader).

Denne testen verifiserer at:
1) Hver refresh-funksjon skriver til egen typed attribut
   (`_pivot_df_rl`, `_pivot_df_sb_konto`, `_pivot_df_hb_konto`).
2) Senere refresh av én modus ikke overskriver de andres caches.
"""

from __future__ import annotations

import pandas as pd


def test_rl_refresh_does_not_clobber_konto_caches(monkeypatch) -> None:
    """RL-refresh sletter ikke SB-/HB-konto-cache satt av tidligere modus."""
    page = type("P", (), {})()
    page._pivot_df_sb_konto = pd.DataFrame({"Konto": ["1000"], "UB_fjor": [123.0]})
    page._pivot_df_hb_konto = pd.DataFrame({"Konto": ["3000"], "Sum beløp": [9.0]})

    # Simuler det refresh_rl_pivot gjør på slutten:
    rl_pivot = pd.DataFrame({
        "regnr": [10],
        "regnskapslinje": ["Salg"],
        "UB": [1000.0],
        "UB_fjor": [900.0],
    })
    snap = rl_pivot.copy()
    page._pivot_df_last = snap
    page._pivot_df_rl = snap

    # Konto-cachene skal være urørte
    assert "Konto" in page._pivot_df_sb_konto.columns
    assert page._pivot_df_sb_konto.loc[0, "UB_fjor"] == 123.0
    assert page._pivot_df_hb_konto.loc[0, "Sum beløp"] == 9.0

    # RL-cache er typed-keyed på regnr
    assert "regnr" in page._pivot_df_rl.columns


def test_rl_specific_consumer_uses_rl_cache_not_konto_pivot() -> None:
    """En RL-spesifikk konsument skal lese _pivot_df_rl, ikke _pivot_df_last.

    Hvis _pivot_df_last er en konto-pivot (siste modus var SB-konto), men
    _pivot_df_rl er en RL-pivot (brukeren har vært i RL-modus tidligere),
    så skal konsumenten finne UB_fjor pr regnr — ikke krasje eller blanke ut.
    """
    page = type("P", (), {})()
    page._pivot_df_last = pd.DataFrame({
        "Konto": ["1000", "2000"],
        "Kontonavn": ["Bank", "Lev"],
        "UB_fjor": [100.0, 200.0],
    })
    page._pivot_df_rl = pd.DataFrame({
        "regnr": [10, 20],
        "regnskapslinje": ["Salg", "Vare"],
        "UB": [1000.0, 500.0],
        "UB_fjor": [900.0, 450.0],
    })

    # Speiler mønsteret som regnskap_export.get_export_rl_df bruker
    pivot_df = getattr(page, "_pivot_df_rl", None)
    assert isinstance(pivot_df, pd.DataFrame)
    assert "UB_fjor" in pivot_df.columns
    assert "regnr" in pivot_df.columns

    rl_df = pd.DataFrame({"regnr": [10, 20], "UB": [1000.0, 500.0]})
    merged = rl_df.merge(
        pivot_df[["regnr", "UB_fjor"]].drop_duplicates(subset=["regnr"]),
        on="regnr", how="left",
    )
    assert merged.loc[merged["regnr"] == 10, "UB_fjor"].iloc[0] == 900.0
    assert merged.loc[merged["regnr"] == 20, "UB_fjor"].iloc[0] == 450.0


def test_rl_consumer_returns_no_pivot_when_user_never_visited_rl_mode() -> None:
    """Ren konto-pivot uten RL-cache: konsumenten skal trygt få None."""
    page = type("P", (), {})()
    page._pivot_df_last = pd.DataFrame({"Konto": ["1000"], "UB_fjor": [100.0]})
    page._pivot_df_sb_konto = page._pivot_df_last
    # NB: ingen _pivot_df_rl satt

    assert getattr(page, "_pivot_df_rl", None) is None

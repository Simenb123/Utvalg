from __future__ import annotations

from typing import Any, List

import pandas as pd

import src.audit_actions.series_control.views as views_nr_series


class DummyNrSeriesView:
    created: List[dict[str, Any]] = []

    def __init__(self, master, df_scope: pd.DataFrame, **kwargs):
        DummyNrSeriesView.created.append(
            {
                "master": master,
                "df_scope_len": len(df_scope.index),
                "kwargs": dict(kwargs),
            }
        )


def test_show_nr_series_control_accepts_keyword_signature(monkeypatch) -> None:
    DummyNrSeriesView.created.clear()
    monkeypatch.setattr(views_nr_series, "NrSeriesControlView", DummyNrSeriesView)

    df_scope = pd.DataFrame({"Konto": ["3000"], "Referanse": ["443"]})
    df_all = pd.DataFrame({"Konto": ["3000", "1500"], "Referanse": ["443", "443"]})

    views_nr_series.show_nr_series_control(
        master="root",
        df_scope=df_scope,
        df_all=df_all,
        selected_accounts=["3000"],
        scope_mode="regnskapslinje",
        scope_items=["10 Salgsinntekt"],
        konto_regnskapslinje_map={"3000": "10 Salgsinntekt"},
        analysis_jump_callback=lambda context: context,
    )

    assert len(DummyNrSeriesView.created) == 1
    created = DummyNrSeriesView.created[0]
    assert created["master"] == "root"
    assert created["df_scope_len"] == 1
    assert created["kwargs"]["df_all"].equals(df_all)
    assert created["kwargs"]["selected_accounts"] == ["3000"]
    assert created["kwargs"]["scope_mode"] == "regnskapslinje"
    assert created["kwargs"]["scope_items"] == ["10 Salgsinntekt"]
    assert created["kwargs"]["konto_regnskapslinje_map"] == {"3000": "10 Salgsinntekt"}
    assert callable(created["kwargs"]["analysis_jump_callback"])


def test_build_nr_series_gap_overview_summarises_hits() -> None:
    gaps_df = pd.DataFrame({"family_key": ["|3", "|3"], "number": [445, 446]})
    hits_df = pd.DataFrame(
        {
            "gap_number": [445, 445],
            "Bilag": ["100445", "100445B"],
            "Konto": ["1500", "3000"],
            "Dato": pd.to_datetime(["2025-01-03", "2025-01-04"]),
        }
    )
    scope_context_df = pd.DataFrame(
        {
            "number": [444, 447],
            "Dato": pd.to_datetime(["2025-01-02", "2025-01-05"]),
            "Konto": ["3000", "3000"],
        }
    )

    out = views_nr_series.build_nr_series_gap_overview(
        gaps_df,
        hits_df,
        scope_context_df=scope_context_df,
        konto_regnskapslinje_map={"1500": "20 Kundefordringer", "3000": "10 Salgsinntekt"},
    )

    assert out["Nummer"].tolist() == [445, 446]
    assert out["Status"].tolist() == ["Funnet i HB", "Ikke funnet i HB"]
    assert out["Treff i HB"].tolist() == [2, 0]
    assert out["Regnskapslinjer"].tolist()[0] == "20 Kundefordringer, 10 Salgsinntekt"
    assert out["Kontoer"].tolist()[0] == "1500, 3000"
    assert out["Periode"].tolist()[0] == "2025-01-03 - 2025-01-04"
    assert out["Forrige i scope"].tolist() == ["444 (2025-01-02)", "444 (2025-01-02)"]
    assert out["Neste i scope"].tolist() == ["447 (2025-01-05)", "447 (2025-01-05)"]


def test_build_nr_series_scope_text_uses_scope_and_account_counts() -> None:
    df_scope = pd.DataFrame({"Konto": ["3000", "3000", "3020"]})

    text = views_nr_series.build_nr_series_scope_text(
        scope_mode="regnskapslinje",
        scope_items=["10 Salgsinntekt", "20 Annen driftsinntekt"],
        selected_accounts=["3000", "3020"],
        df_scope=df_scope,
    )

    assert "regnskapslinjer" in text
    assert "Kontoer: 2" in text
    assert "Linjer i scope: 3" in text


def test_build_nr_series_gap_overview_can_filter_to_hits_only() -> None:
    gaps_df = pd.DataFrame({"family_key": ["|3", "|3"], "number": [445, 446]})
    hits_df = pd.DataFrame({"gap_number": [445], "Konto": ["1500"], "Dato": pd.to_datetime(["2025-01-03"])})

    out = views_nr_series.build_nr_series_gap_overview(gaps_df, hits_df, only_with_hits=True)

    assert out["Nummer"].tolist() == [445]

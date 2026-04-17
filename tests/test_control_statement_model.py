from __future__ import annotations

import pandas as pd

from a07_feature.control_statement_model import (
    CONTROL_STATEMENT_VIEW_ALL,
    CONTROL_STATEMENT_VIEW_LABELS,
    CONTROL_STATEMENT_VIEW_LEGACY,
    CONTROL_STATEMENT_VIEW_PAYROLL,
    CONTROL_STATEMENT_VIEW_UNCLASSIFIED,
    control_statement_view_requires_unclassified,
    filter_control_statement_df,
    normalize_control_statement_df,
    normalize_control_statement_view,
)


def test_normalize_control_statement_df_fills_missing_columns_and_names() -> None:
    frame = pd.DataFrame(
        [
            {
                "Gruppe": "__unclassified__",
                "Endring": "10",
                "AntallKontoer": "2",
            }
        ]
    )

    out = normalize_control_statement_df(frame)

    assert out.loc[0, "Navn"] == "Uklassifisert"
    assert out.loc[0, "Endring"] == 10.0
    assert out.loc[0, "AntallKontoer"] == 2
    assert "Kontoer" in out.columns
    assert "Kilder" in out.columns


def test_filter_control_statement_df_payroll_view_keeps_payroll_and_unclassified() -> None:
    frame = pd.DataFrame(
        [
            {"Gruppe": "Skyldig pensjon", "Navn": "Skyldig pensjon"},
            {"Gruppe": "Bankkonto", "Navn": "Bankkonto"},
            {"Gruppe": "__unclassified__", "Navn": "Uklassifisert"},
            {"Gruppe": "100_loenn_ol", "Navn": "Post 100"},
        ]
    )

    out = filter_control_statement_df(frame, view=CONTROL_STATEMENT_VIEW_PAYROLL)

    assert out["Gruppe"].tolist() == ["100_loenn_ol", "Skyldig pensjon", "__unclassified__"]


def test_filter_control_statement_df_other_views_split_legacy_and_unclassified() -> None:
    frame = pd.DataFrame(
        [
            {"Gruppe": "Skyldig pensjon", "Navn": "Skyldig pensjon"},
            {"Gruppe": "Bankkonto", "Navn": "Bankkonto"},
            {"Gruppe": "__unclassified__", "Navn": "Uklassifisert"},
        ]
    )

    legacy = filter_control_statement_df(frame, view=CONTROL_STATEMENT_VIEW_LEGACY)
    unclassified = filter_control_statement_df(frame, view=CONTROL_STATEMENT_VIEW_UNCLASSIFIED)
    all_rows = filter_control_statement_df(frame, view=CONTROL_STATEMENT_VIEW_ALL)

    assert legacy["Gruppe"].tolist() == ["Bankkonto"]
    assert unclassified["Gruppe"].tolist() == ["__unclassified__"]
    assert set(all_rows["Gruppe"].tolist()) == {"Skyldig pensjon", "Bankkonto", "__unclassified__"}


def test_control_statement_view_helpers_accept_keys_and_labels() -> None:
    assert normalize_control_statement_view("legacy") == CONTROL_STATEMENT_VIEW_LEGACY
    assert normalize_control_statement_view(CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_ALL]) == CONTROL_STATEMENT_VIEW_ALL
    assert control_statement_view_requires_unclassified(CONTROL_STATEMENT_VIEW_UNCLASSIFIED) is True
    assert control_statement_view_requires_unclassified(CONTROL_STATEMENT_VIEW_PAYROLL) is False

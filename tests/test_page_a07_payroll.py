from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from a07_feature.control_statement_model import (
    CONTROL_STATEMENT_VIEW_ALL,
    CONTROL_STATEMENT_VIEW_LEGACY,
    CONTROL_STATEMENT_VIEW_PAYROLL,
    CONTROL_STATEMENT_VIEW_UNCLASSIFIED,
)
from account_profile import AccountProfile, AccountProfileDocument
import page_a07


def test_load_code_profile_state_tracks_missing_rf1022_fields(monkeypatch) -> None:
    document = AccountProfileDocument(
        client="Test",
        year=2025,
        profiles={
            "5000": AccountProfile(
                account_no="5000",
                a07_code="fastloenn",
                source="manual",
                confidence=0.9,
            ),
            "5210": AccountProfile(
                account_no="5210",
                a07_code="elektroniskKommunikasjon",
                control_group="111_naturalytelser",
                control_tags=("naturalytelse",),
                source="manual",
                confidence=0.8,
            ),
        },
    )
    api = SimpleNamespace(load_document=lambda **_kwargs: document)
    monkeypatch.setattr(page_a07, "_account_profile_api_for_a07", lambda: api)

    out = page_a07._load_code_profile_state(
        "Test",
        2025,
        {
            "5000": "fastloenn",
            "5210": "elektroniskKommunikasjon",
        },
    )

    assert out["fastloenn"]["missing_control_group"] is True
    assert out["elektroniskKommunikasjon"]["missing_control_tags"] is True


def test_load_code_profile_state_keeps_human_why_summary(monkeypatch) -> None:
    document = AccountProfileDocument(
        client="Test",
        year=2025,
        profiles={
            "5210": AccountProfile(
                account_no="5210",
                a07_code="elektroniskKommunikasjon",
                source="manual",
                confidence=0.8,
            ),
        },
    )
    api = SimpleNamespace(load_document=lambda **_kwargs: document)
    monkeypatch.setattr(page_a07, "_account_profile_api_for_a07", lambda: api)

    out = page_a07._load_code_profile_state(
        "Test",
        2025,
        {"5210": "elektroniskKommunikasjon"},
        gl_df=pd.DataFrame([{"Konto": "5210", "Navn": "Fri telefon", "Endring": 38064.0, "IB": 0.0, "UB": 38064.0}]),
    )

    why_summary = str(out["elektroniskKommunikasjon"].get("why_summary") or "")
    assert why_summary
    assert "RF-1022:" in why_summary or "A07:" in why_summary or "Flagg:" in why_summary
    assert not why_summary.startswith("R; ")


def test_build_control_queue_df_surfaces_rf1022_follow_up() -> None:
    a07_overview_df = pd.DataFrame(
        [
            {
                "Kode": "fastloenn",
                "Navn": "Fast lønn",
                "Belop": 100.0,
                "GL_Belop": 100.0,
                "Diff": 0.0,
                "Status": "OK",
                "AntallKontoer": 1,
            }
        ]
    )
    suggestions_df = pd.DataFrame()

    out = page_a07.build_control_queue_df(
        a07_overview_df,
        suggestions_df,
        mapping_current={"5000": "fastloenn"},
        mapping_previous={},
        gl_df=pd.DataFrame({"Konto": ["5000"]}),
        code_profile_state={
            "fastloenn": {
                "source": "manual",
                "missing_control_group": True,
                "missing_control_tags": False,
                "control_conflict": False,
            }
        },
    )

    row = out.iloc[0]
    assert row["Status"] == "Manuell"
    assert row["Anbefalt"] == "RF-1022"
    assert row["NesteHandling"] == "Tildel RF-1022-post i Saldobalanse."


def test_build_rf1022_statement_summary_includes_payroll_tag_totals() -> None:
    rf1022_df = pd.DataFrame(
        [
            {"GL_Belop": 100.0, "A07": 90.0, "Diff": 10.0},
            {"GL_Belop": 50.0, "A07": 50.0, "Diff": 0.0},
        ]
    )

    text = page_a07.build_rf1022_statement_summary(
        rf1022_df,
        tag_totals={
            "opplysningspliktig": 150.0,
            "aga_pliktig": 120.0,
            "finansskatt_pliktig": 0.0,
        },
    )

    assert "Poster 2" in text
    assert "Opplysningspliktig 150,00" in text
    assert "AGA-pliktig 120,00" in text


def test_rf1022_post_for_group_supports_new_payroll_post_ids() -> None:
    assert page_a07.rf1022_post_for_group("100_refusjon") == (100, "Refusjon")
    assert page_a07.rf1022_post_for_group("111_naturalytelser") == (111, "Naturalytelser")


def test_a07_suggestion_is_strict_auto_for_history_or_rulebook() -> None:
    history_row = pd.Series(
        {
            "WithinTolerance": True,
            "HistoryAccounts": "5000",
            "Explain": "basis=Endring | historikk=5000",
            "Score": 0.7,
        }
    )
    heuristic_row = pd.Series(
        {
            "WithinTolerance": True,
            "HistoryAccounts": "",
            "Explain": "basis=Endring | regel=kontonr | diff=0.00",
            "Score": 0.91,
        }
    )
    weak_row = pd.Series(
        {
            "WithinTolerance": True,
            "HistoryAccounts": "",
            "Explain": "basis=Endring | navn=telefon",
            "Score": 0.88,
        }
    )

    assert page_a07.a07_suggestion_is_strict_auto(history_row) is True
    assert page_a07.a07_suggestion_is_strict_auto(heuristic_row) is True
    assert page_a07.a07_suggestion_is_strict_auto(weak_row) is False


def test_filter_control_statement_mvp_df_keeps_unclassified_rows_when_requested() -> None:
    from a07_feature.page_control_data import filter_control_statement_mvp_df

    control_statement_df = pd.DataFrame(
        [
            {
                "Gruppe": "100_loenn_ol",
                "Navn": "Post 100",
                "Endring": 100.0,
                "AntallKontoer": 1,
            },
            {
                "Gruppe": "__unclassified__",
                "Navn": "Uklassifisert",
                "Endring": 10.0,
                "AntallKontoer": 2,
            },
        ]
    )

    out = filter_control_statement_mvp_df(control_statement_df)

    assert out["Gruppe"].tolist() == ["100_loenn_ol", "__unclassified__"]


def test_build_rf1022_source_df_filters_cached_control_statement_base_by_view() -> None:
    base_df = pd.DataFrame(
        [
            {"Gruppe": "100_loenn_ol", "Navn": "Post 100", "Endring": 100.0, "AntallKontoer": 1},
            {"Gruppe": "Skyldig MVA", "Navn": "Skyldig MVA", "Endring": 50.0, "AntallKontoer": 1},
            {"Gruppe": "__unclassified__", "Navn": "Uklassifisert", "Endring": 10.0, "AntallKontoer": 2},
        ]
    )
    dummy = SimpleNamespace(
        workspace=SimpleNamespace(gl_df=pd.DataFrame([{"Konto": "5000"}])),
        control_statement_base_df=base_df,
        _rf1022_state=None,
    )
    dummy._selected_rf1022_view = lambda: page_a07.A07Page._selected_rf1022_view(dummy)
    dummy._sync_rf1022_view_vars = lambda view: page_a07.A07Page._sync_rf1022_view_vars(dummy, view)

    payroll = page_a07.A07Page._build_rf1022_source_df(dummy, view=CONTROL_STATEMENT_VIEW_PAYROLL)
    legacy = page_a07.A07Page._build_rf1022_source_df(dummy, view=CONTROL_STATEMENT_VIEW_LEGACY)
    unclassified = page_a07.A07Page._build_rf1022_source_df(dummy, view=CONTROL_STATEMENT_VIEW_UNCLASSIFIED)

    assert payroll["Gruppe"].tolist() == ["100_loenn_ol", "__unclassified__"]
    assert legacy["Gruppe"].tolist() == ["Skyldig MVA"]
    assert unclassified["Gruppe"].tolist() == ["__unclassified__"]


def test_selected_rf1022_view_uses_local_view_state_and_labels() -> None:
    dummy = SimpleNamespace(
        _rf1022_state={
            "view_var": SimpleNamespace(get=lambda: CONTROL_STATEMENT_VIEW_PAYROLL),
            "view_label_var": SimpleNamespace(get=lambda: "Legacy analyse"),
        }
    )

    out = page_a07.A07Page._selected_rf1022_view(dummy)

    assert out == CONTROL_STATEMENT_VIEW_LEGACY


def test_selected_control_statement_window_view_uses_local_view_state_and_labels() -> None:
    dummy = SimpleNamespace(
        _control_statement_window_state={
            "view_var": SimpleNamespace(get=lambda: CONTROL_STATEMENT_VIEW_PAYROLL),
            "view_label_var": SimpleNamespace(get=lambda: "Uklassifisert"),
        }
    )

    out = page_a07.A07Page._selected_control_statement_window_view(dummy)

    assert out == CONTROL_STATEMENT_VIEW_UNCLASSIFIED


def test_build_rf1022_source_df_builds_full_base_then_filters_when_no_cached_base(monkeypatch) -> None:
    calls: dict[str, object] = {}

    dummy = SimpleNamespace(
        workspace=SimpleNamespace(gl_df=pd.DataFrame([{"Konto": "5000"}])),
        control_statement_base_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        _rf1022_state=None,
        _session_context=lambda _session: ("Demo Client", "2025"),
        _effective_mapping=lambda: {"5000": "fastloenn"},
    )
    dummy._selected_rf1022_view = lambda: page_a07.A07Page._selected_rf1022_view(dummy)
    dummy._sync_rf1022_view_vars = lambda view: page_a07.A07Page._sync_rf1022_view_vars(dummy, view)

    monkeypatch.setattr(
        page_a07._rf1022,
        "build_control_statement_export_df",
        lambda **kwargs: calls.update(kwargs) or pd.DataFrame(
            [
                {"Gruppe": "100_loenn_ol", "Navn": "Post 100", "Endring": 100.0, "AntallKontoer": 1},
                {"Gruppe": "__unclassified__", "Navn": "Uklassifisert", "Endring": 10.0, "AntallKontoer": 1},
            ]
        ),
    )

    out = page_a07.A07Page._build_rf1022_source_df(dummy, view=CONTROL_STATEMENT_VIEW_ALL)

    assert calls["client"] == "Demo Client"
    assert calls["year"] == "2025"
    assert calls["include_unclassified"] is True
    assert out["Gruppe"].tolist() == ["100_loenn_ol", "__unclassified__"]


def test_a07_page_init_sets_control_statement_view_vars_without_nameerror(monkeypatch) -> None:
    class _Var:
        def __init__(self, value=None):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    monkeypatch.setattr(page_a07.ttk.Frame, "__init__", lambda self, parent: None)
    monkeypatch.setattr(page_a07.tk, "StringVar", _Var)
    monkeypatch.setattr(page_a07.tk, "BooleanVar", _Var)
    monkeypatch.setattr(page_a07.A07Page, "_build_ui", lambda self: None)
    monkeypatch.setattr(page_a07.A07Page, "_schedule_session_refresh", lambda self: None)
    monkeypatch.setattr(page_a07.A07Page, "_diag", lambda self, *_args, **_kwargs: None)
    monkeypatch.setattr(page_a07.A07Page, "bind", lambda self, *_args, **_kwargs: None)
    monkeypatch.setattr(page_a07, "_A07_DIAGNOSTICS_ENABLED", False)

    page = page_a07.A07Page(SimpleNamespace(bind=lambda *_args, **_kwargs: None))

    assert page.control_statement_view_var.get() == CONTROL_STATEMENT_VIEW_PAYROLL
    assert page.control_statement_view_label_var.get() == "Payroll"
    assert page._control_statement_window is None
    assert page._control_statement_window_state is None


def test_build_control_statement_export_df_returns_empty_when_profile_store_is_unavailable(monkeypatch) -> None:
    from a07_feature import page_control_data

    def _raise(*_args, **_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(
        page_control_data,
        "build_current_control_statement_rows",
        _raise,
    )

    out = page_control_data.build_control_statement_export_df(
        client="Demo Client",
        year="2025",
        gl_df=pd.DataFrame([{"Konto": "5000", "Navn": "Lonn", "IB": 0.0, "UB": 100.0, "Endring": 100.0}]),
        mapping_current={},
    )

    assert out.empty


def test_build_control_statement_export_df_preserves_columns_and_status_for_modern_rows(monkeypatch) -> None:
    from a07_feature import page_control_data
    from account_profile_reporting import ControlStatementRow

    def _rows(*_args, **_kwargs):
        return [
            ControlStatementRow(
                group_id="Loenn",
                label="Lonn",
                ib=0.0,
                movement=100.0,
                ub=100.0,
                account_count=1,
                accounts=("5000",),
                source_breakdown=("manual",),
            ),
        ]

    monkeypatch.setattr(page_control_data, "build_current_control_statement_rows", _rows)

    reconcile = pd.DataFrame(
        [{"Kode": "fastloenn", "A07_Belop": 100.0, "Diff": 0.0, "WithinTolerance": True}]
    )

    out = page_control_data.build_control_statement_export_df(
        client="Demo Client",
        year="2025",
        gl_df=pd.DataFrame([{"Konto": "5000", "Navn": "Lonn", "IB": 0.0, "UB": 100.0, "Endring": 100.0}]),
        mapping_current={"5000": "fastloenn"},
        reconcile_df=reconcile,
    )

    assert list(out.columns) == [
        "Gruppe",
        "Navn",
        "IB",
        "Endring",
        "UB",
        "A07",
        "Diff",
        "Status",
        "AntallKontoer",
        "Kontoer",
        "Kilder",
    ]
    assert len(out) == 1
    row = out.iloc[0]
    assert row["Gruppe"] == "Loenn"
    assert row["Status"] == "Ferdig"
    assert row["Kontoer"] == "5000"
    assert row["Kilder"] == "manual"

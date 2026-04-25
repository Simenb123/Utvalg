from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from a07_feature import page_control_data
import page_a07


class _Var:
    def __init__(self, value: object = "") -> None:
        self.value = value

    def get(self) -> object:
        return self.value

    def set(self, value: object) -> None:
        self.value = value


def test_build_control_statement_accounts_df_preserves_group_order_and_defaults() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Fast lonn", "IB": 0.0, "Endring": 100.0, "UB": 100.0, "Kode": "fastloenn"},
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "IB": -10.0, "Endring": -5.0, "UB": -15.0, "Kode": ""},
        ]
    )
    control_statement_df = pd.DataFrame(
        [{"Gruppe": "100_loenn_ol", "Navn": "Post 100", "Kontoer": "2940, 5000"}]
    )

    out = page_a07.build_control_statement_accounts_df(gl_df, control_statement_df, "100_loenn_ol")

    assert out["Konto"].tolist() == ["2940", "5000"]
    assert out["BelopAktiv"].tolist() == [-5.0, 100.0]
    assert out["Kol"].tolist() == ["Endring", "Endring"]


def test_apply_mapping_audit_to_control_gl_df_projects_audit_columns() -> None:
    control_gl_df = pd.DataFrame(
        [{"Konto": "5000", "Navn": "Fast lonn", "IB": 0.0, "Endring": 100.0, "UB": 100.0, "BelopAktiv": 100.0, "Kol": "Endring", "Kode": "fastloenn"}]
    )
    mapping_audit_df = pd.DataFrame(
        [{"Konto": "5000", "AliasStatus": "Regelbok", "Status": "Trygg", "Reason": "Match mot lonn."}]
    )

    out = page_a07.apply_mapping_audit_to_control_gl_df(control_gl_df, mapping_audit_df)

    row = out.iloc[0]
    assert row["AliasStatus"] == "Regelbok"
    assert row["MappingAuditStatus"] == "Trygg"
    assert row["MappingAuditReason"] == "Match mot lonn."


def test_apply_mapping_audit_to_mapping_df_projects_and_sorts_status() -> None:
    mapping_df = pd.DataFrame(
        [
            {"Konto": "6000", "Navn": "Refusjon", "Kode": "sumAvgiftsgrunnlagRefusjon"},
            {"Konto": "5000", "Navn": "Fast lonn", "Kode": "fastloenn"},
        ]
    )
    mapping_audit_df = pd.DataFrame(
        [
            {
                "Konto": "6000",
                "CurrentRf1022GroupId": "100_refusjon",
                "AliasStatus": "Regelbok",
                "Kol": "Endring",
                "Status": "Trygg",
                "Reason": "Ser riktig ut.",
            },
            {
                "Konto": "5000",
                "CurrentRf1022GroupId": "uavklart_rf1022",
                "AliasStatus": "Navnetreff",
                "Kol": "Endring",
                "Status": "Feil",
                "Reason": "Mangler RF-1022-bro.",
            },
        ]
    )

    out = page_a07.apply_mapping_audit_to_mapping_df(mapping_df, mapping_audit_df)

    assert out["Konto"].tolist() == ["5000", "6000"]
    assert out.iloc[0]["Rf1022GroupId"] == "uavklart_rf1022"
    assert out.iloc[0]["Status"] == "Feil"
    assert out.iloc[1]["Status"] == "Trygg"


def test_rf1022_candidate_tree_tag_distinguishes_safe_and_review_rows() -> None:
    assert page_a07.rf1022_candidate_tree_tag(pd.Series({"Forslagsstatus": "Trygt forslag"})) == "suggestion_ok"
    assert page_a07.rf1022_candidate_tree_tag(pd.Series({"Forslagsstatus": "Manuell vurdering"})) == "suggestion_review"


def test_rf1022_overview_and_control_gl_family_tree_tags_cover_new_helpers() -> None:
    assert page_control_data.rf1022_overview_tree_tag(pd.Series({"GroupId": "uavklart_rf1022"})) == "family_warning"
    assert page_control_data.control_gl_family_tree_tag(pd.Series({"Kode": "fastloenn"})) == "family_payroll"
    assert (
        page_control_data.control_gl_family_tree_tag(
            pd.Series({"Kode": "fastloenn", "MappingAuditStatus": "Feil"})
        )
        == "family_warning"
    )


def test_apply_context_restore_payload_sets_workspace_and_triggers_core_refresh() -> None:
    gl_df = pd.DataFrame([{"Konto": "5000"}])
    a07_df = pd.DataFrame([{"Kode": "fastloenn"}])
    basis_var = _Var()
    started: list[str] = []

    dummy = SimpleNamespace(
        _diag=lambda *_args, **_kwargs: None,
        workspace=SimpleNamespace(),
        basis_var=basis_var,
        _session_context=lambda _session: ("Demo", "2025"),
        _current_context_snapshot=lambda client, year: (("snapshot", len(client), len(year)),),
        _start_core_refresh=lambda: started.append("core"),
    )
    payload = {
        "warnings": [{"scope": "mapping", "message": "fallback", "detail": "bruker cache"}],
        "gl_df": gl_df,
        "tb_path": "tb.xlsx",
        "source_a07_df": a07_df,
        "a07_df": a07_df,
        "a07_path": "a07.json",
        "mapping": {"5000": "fastloenn"},
        "mapping_path": "mapping.json",
        "groups": {"A07_GROUP:test": ["fastloenn"]},
        "groups_path": "groups.json",
        "locks": {"fastloenn"},
        "locks_path": "locks.json",
        "project_meta": {"name": "demo"},
        "project_path": "project.json",
        "basis_col": "Endring",
        "previous_mapping": {"5000": "fastloenn"},
        "previous_mapping_path": "prev.json",
        "previous_mapping_year": "2024",
        "rulebook_path": "rulebook.json",
        "pending_focus_code": "fastloenn",
    }

    page_a07.A07Page._apply_context_restore_payload(dummy, payload)

    assert dummy._a07_refresh_warnings == [{"scope": "mapping", "message": "fallback", "detail": "bruker cache"}]
    assert dummy.workspace.gl_df is gl_df
    assert dummy.workspace.a07_df is a07_df
    assert dummy.workspace.mapping == {"5000": "fastloenn"}
    assert basis_var.get() == "Endring"
    assert dummy._context_snapshot == (("snapshot", 4, 4),)
    assert started == ["core"]


def test_apply_support_refresh_payload_sets_history_ready_and_updates_ui() -> None:
    history_df = pd.DataFrame([{"Kode": "fastloenn"}])
    calls: list[str] = []

    dummy = SimpleNamespace(
        history_compare_df=pd.DataFrame(),
        _history_compare_ready=False,
        _support_views_ready=False,
        _support_views_dirty=True,
        _loaded_support_tabs={"history", "mapping"},
        _loaded_support_context_keys={"history": "old", "mapping": "keep"},
        _control_details_visible=True,
        _active_support_tab_key=lambda: "history",
        _refresh_control_support_trees=lambda: calls.append("refresh_support"),
        _render_active_support_tab=lambda force=False: calls.append(f"render:{force}"),
        _update_history_details_from_selection=lambda: calls.append("history_details"),
        _update_control_panel=lambda: calls.append("panel"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _update_summary=lambda: calls.append("summary"),
        after_idle=lambda callback: callback(),
    )

    page_a07.A07Page._apply_support_refresh_payload(dummy, {"history_compare_df": history_df})

    assert dummy.history_compare_df is history_df
    assert dummy._history_compare_ready is True
    assert dummy._support_views_ready is True
    assert dummy._support_views_dirty is False
    assert "history" not in dummy._loaded_support_tabs
    assert dummy._loaded_support_context_keys == {"mapping": "keep"}
    assert calls == ["refresh_support", "render:True", "history_details", "panel", "buttons", "summary"]

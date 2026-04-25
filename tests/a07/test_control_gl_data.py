from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_build_control_gl_df_shows_assigned_code_on_account_rows() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "IB": -100.0, "Endring": -50.0, "UB": -150.0},
            {"Konto": "5000", "Navn": "Lonn", "IB": 10.0, "Endring": 1190.0, "UB": 1200.0},
            {"Konto": "6990", "Navn": "Telefon", "IB": 0.0, "Endring": 250.0, "UB": 250.0},
        ]
    )

    out = page_a07.build_control_gl_df(gl_df, {"5000": "fastloenn", "2940": "feriepenger"})

    assert out["Konto"].tolist() == ["2940", "5000", "6990"]
    assert out.loc[out["Konto"] == "2940", "Kol"].iloc[0] == "Endring"
    assert out.loc[out["Konto"] == "2940", "BelopAktiv"].iloc[0] == -50.0
    assert out.loc[out["Konto"] == "5000", "Kol"].iloc[0] == "UB"
    assert out.loc[out["Konto"] == "5000", "BelopAktiv"].iloc[0] == 1200.0
    assert out.loc[out["Konto"] == "5000", "Kode"].iloc[0] == "fastloenn"
    assert out.loc[out["Konto"] == "6990", "Kode"].iloc[0] == ""

def test_build_control_gl_df_shows_alias_status_from_effective_rulebook(monkeypatch) -> None:
    monkeypatch.setattr(
        a07_control_data,
        "load_rulebook",
        lambda _path: {
            "fastloenn": RulebookRule(keywords=("Lonn",)),
            "annet": RulebookRule(exclude_keywords=("Honorar revisjon",)),
        },
    )
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn til ansatte", "IB": 0.0, "Endring": 10.0, "UB": 10.0},
            {"Konto": "6701", "Navn": "Honorar revisjon", "IB": 0.0, "Endring": 20.0, "UB": 20.0},
        ]
    )

    out = page_a07.build_control_gl_df(gl_df, {"5000": "fastloenn", "6701": "annet"})

    assert out.loc[out["Konto"] == "5000", "AliasStatus"].iloc[0] == "Inkludert"
    assert out.loc[out["Konto"] == "6701", "AliasStatus"].iloc[0] == "Ekskludert"

def test_apply_mapping_audit_to_control_gl_df_uses_avstemt_display_status_for_zero_diff() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "2984", "Navn": "Avsetning Styrehonorar", "Kode": "styrehonorarOgGodtgjoerelseVerv"},
            {"Konto": "6701", "Navn": "Honorar revisjon", "Kode": "annet"},
        ]
    )
    audit_df = pd.DataFrame(
        [
            {"Konto": "2984", "AliasStatus": "", "Status": "Feil", "Reason": "Raa faglig audit."},
            {"Konto": "6701", "AliasStatus": "Ekskludert", "Status": "Feil", "Reason": "Utenfor A07-lonn."},
        ]
    )
    overview_df = pd.DataFrame(
        [
            {"Kode": "styrehonorarOgGodtgjoerelseVerv", "Diff": 0.0},
            {"Kode": "annet", "Diff": 100.0},
        ]
    )

    out = page_a07.apply_mapping_audit_to_control_gl_df(control_gl_df, audit_df, a07_overview_df=overview_df)
    by_account = out.set_index("Konto")

    assert by_account.loc["2984", "MappingAuditStatus"] == "Avstemt"
    assert by_account.loc["2984", "MappingAuditRawStatus"] == "Feil"
    assert by_account.loc["2984", "MappingAuditRawReason"] == "Raa faglig audit."
    assert by_account.loc["2984", "A07CodeDiff"] == 0.0
    assert by_account.loc["6701", "MappingAuditStatus"] == "Feil"
    assert by_account.loc["6701", "MappingAuditRawStatus"] == "Feil"

def test_control_main_columns_hide_status_and_left_gl_keeps_regnskap_columns() -> None:
    left_columns = [column_id for column_id, *_rest in a07_constants._CONTROL_GL_COLUMNS]
    a07_columns = [column_id for column_id, *_rest in a07_constants._CONTROL_COLUMNS]
    rf1022_columns = [column_id for column_id, *_rest in a07_constants._CONTROL_RF1022_COLUMNS]

    assert left_columns == [
        "Konto",
        "Navn",
        "Kode",
        "Rf1022GroupId",
        "AliasStatus",
        "Kol",
        "MappingAuditStatus",
        "IB",
        "Endring",
        "UB",
    ]
    assert "Status" not in a07_columns
    assert "Status" not in rf1022_columns


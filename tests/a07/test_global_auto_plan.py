from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_build_global_auto_mapping_plan_applies_only_strict_and_audit_safe_candidates() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5800", "Navn": "Refusjon av sykepenger", "Endring": -465809.0, "UB": -465809.0},
            {"Konto": "5890", "Navn": "Annen refusjon", "Endring": -58009.0, "UB": -58009.0},
            {"Konto": "6701", "Navn": "Honorar revisjon", "Endring": 72250.4, "UB": 72250.4},
            {"Konto": "5000", "Navn": "Lonn ansatte", "Endring": 1000.0, "UB": 1000.0},
            {"Konto": "5010", "Navn": "Bonus", "Endring": 250.0, "UB": 250.0},
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "Konto": "5800",
                "Navn": "Refusjon av sykepenger",
                "Kode": "sumAvgiftsgrunnlagRefusjon",
                "Rf1022GroupId": "100_refusjon",
                "BelopAktiv": -465809.0,
                "Matchgrunnlag": "Regelbok",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "5890",
                "Navn": "Annen refusjon",
                "Kode": "sumAvgiftsgrunnlagRefusjon",
                "Rf1022GroupId": "100_refusjon",
                "BelopAktiv": -58009.0,
                "Matchgrunnlag": "Regelbok",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "6701",
                "Navn": "Honorar revisjon",
                "Kode": "annet",
                "Rf1022GroupId": "100_loenn_ol",
                "BelopAktiv": 72250.4,
                "Matchgrunnlag": "Regelbok",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "5000",
                "Navn": "Lonn ansatte",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "BelopAktiv": 1000.0,
                "Matchgrunnlag": "Regelbok",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "5010",
                "Navn": "Bonus",
                "Kode": "bonus",
                "Rf1022GroupId": "100_loenn_ol",
                "BelopAktiv": 250.0,
                "Matchgrunnlag": "Regelbok",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
        ]
    )

    plan = page_a07.build_global_auto_mapping_plan(
        candidates,
        gl_df,
        pd.DataFrame(),
        {"5000": "fastloenn"},
        locked_codes={"bonus"},
        basis_col="Endring",
    )

    by_account = plan.set_index("Konto")
    assert by_account.loc["5800", "Action"] == "apply"
    assert by_account.loc["5800", "Status"] == "Trygg"
    assert by_account.loc["5890", "Action"] == "review"
    assert by_account.loc["5890", "Status"] == "Mistenkelig"
    assert by_account.loc["6701", "Action"] == "blocked"
    assert by_account.loc["6701", "Status"] == "Feil"
    assert by_account.loc["5000", "Action"] == "already"
    assert by_account.loc["5010", "Action"] == "locked"

def test_build_global_auto_mapping_plan_blocks_stale_and_thin_candidates() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn ansatte", "Endring": 1000.0, "UB": 1000.0},
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Navn": "Lonn ansatte",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "5999",
                "Navn": "Stale konto",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "Matchgrunnlag": "Regelbok",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
        ]
    )

    plan = page_a07.build_global_auto_mapping_plan(
        candidates,
        gl_df,
        pd.DataFrame(),
        {},
        basis_col="Endring",
    )

    by_account = plan.set_index("Konto")
    assert by_account.loc["5000", "Action"] == "review"
    assert "ikke godkjent" in by_account.loc["5000", "Reason"]
    assert by_account.loc["5999", "Action"] == "invalid"
    assert "aktiv GL" in by_account.loc["5999", "Reason"]


def test_build_global_auto_mapping_plan_skips_codes_that_are_already_zero_diff() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn ansatte", "Endring": 1000.0, "UB": 1000.0},
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Navn": "Lonn ansatte",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "Matchgrunnlag": "Regelbok",
                "Belopsgrunnlag": "Eksakt belop",
                "Forslagsstatus": "Trygt forslag",
            },
        ]
    )

    plan = page_a07.build_global_auto_mapping_plan(
        candidates,
        gl_df,
        pd.DataFrame(),
        {},
        solved_codes={"fastloenn"},
        basis_col="Endring",
    )

    row = plan.iloc[0]
    assert row["Action"] == "already"
    assert row["Status"] == "Allerede avstemt"
    assert "0 i diff" in row["Reason"]


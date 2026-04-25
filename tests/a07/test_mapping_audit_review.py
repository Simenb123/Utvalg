from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_build_mapping_audit_df_flags_known_bad_saved_mappings() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "IB": -743491.69, "Endring": -4207.18, "UB": -747698.87},
            {"Konto": "5800", "Navn": "Refusjon av sykepenger", "IB": 0.0, "Endring": -465809.0, "UB": -465809.0},
            {"Konto": "5890", "Navn": "Annen refusjon", "IB": 0.0, "Endring": -58009.0, "UB": -58009.0},
            {"Konto": "6701", "Navn": "Honorar revisjon", "IB": 0.0, "Endring": 72250.4, "UB": 72250.4},
        ]
    )

    out = page_a07.build_mapping_audit_df(
        gl_df,
        {
            "2940": "feriepenger",
            "5800": "sumAvgiftsgrunnlagRefusjon",
            "5890": "sumAvgiftsgrunnlagRefusjon",
            "6701": "annet",
        },
        basis_col="Endring",
    )

    by_account = out.set_index("Konto")
    assert by_account.loc["2940", "Kol"] == "Endring"
    assert by_account.loc["2940", "Status"] == "Trygg"
    assert by_account.loc["2940", "CurrentRf1022GroupId"] == "100_loenn_ol"
    assert by_account.loc["5800", "Status"] == "Trygg"
    assert by_account.loc["5890", "Status"] == "Mistenkelig"
    assert "Generisk refusjon" in by_account.loc["5890", "Reason"]
    assert by_account.loc["6701", "Kol"] == "UB"
    assert by_account.loc["6701", "Status"] == "Feil"
    assert "utenfor A07-lonn" in by_account.loc["6701", "Reason"]

def test_mapping_audit_accepts_styrehonorar_accrual_in_payroll_scope() -> None:
    gl_df = pd.DataFrame(
        [
            {
                "Konto": "2984",
                "Navn": "Avsetning Styrehonorar",
                "IB": -50000.0,
                "Endring": 50000.0,
                "UB": 0.0,
            },
        ]
    )

    out = page_a07.build_mapping_audit_df(
        gl_df,
        {"2984": "styrehonorarOgGodtgjoerelseVerv"},
        basis_col="Endring",
    )

    row = out.iloc[0]
    assert row["CurrentRf1022GroupId"] == "100_loenn_ol"
    assert row["ExpectedRf1022GroupId"] == "100_loenn_ol"
    assert row["Status"] == "Trygg"
    assert "utenfor A07-lonn" not in row["Reason"]

def test_mapping_audit_never_marks_uavklart_rf1022_as_safe() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn ansatte", "IB": 0.0, "Endring": 1000.0, "UB": 1000.0},
        ]
    )
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "ukjentNyKode",
                "ForslagKontoer": "5000",
                "WithinTolerance": True,
                "SuggestionGuardrail": "accepted",
                "UsedRulebook": True,
                "HitTokens": "lonn",
            }
        ]
    )

    out = page_a07.build_mapping_audit_df(
        gl_df,
        {"5000": "ukjentNyKode"},
        suggestions_df=suggestions_df,
        basis_col="Endring",
    )

    row = out.iloc[0]
    assert row["CurrentRf1022GroupId"] == "uavklart_rf1022"
    assert row["Status"] == "Uavklart"
    assert "RF-1022-bro" in row["Reason"]

def test_mapping_audit_rejects_revenue_account_even_when_code_name_is_payroll() -> None:
    gl_df = pd.DataFrame(
        [
            {
                "Konto": "3090",
                "Navn": "Opptjent, ikke fakturert inntekt",
                "IB": 0.0,
                "Endring": 101_531.86,
                "UB": 101_531.86,
            },
        ]
    )

    out = page_a07.build_mapping_audit_df(
        gl_df,
        {"3090": "feriepenger"},
        suggestions_df=pd.DataFrame(),
        basis_col="UB",
    )

    row = out.iloc[0]
    assert row["Status"] == "Feil"
    assert "utenfor A07-lonn" in row["Reason"]

def test_mapping_audit_treats_excluded_codes_case_insensitively() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5400", "Navn": "Arbeidsgiveravgift", "IB": 0.0, "Endring": 100.0, "UB": 100.0},
        ]
    )

    out = page_a07.build_mapping_audit_df(gl_df, {"5400": "AGA"}, basis_col="Endring")

    row = out.iloc[0]
    assert row["Status"] == "Uavklart"
    assert "ekskludert" in row["Reason"]

def test_mapping_audit_rows_sort_and_filter_by_status_priority() -> None:
    mapping_df = pd.DataFrame(
        [
            {"Konto": "5000", "Status": "Trygg"},
            {"Konto": "6701", "Status": "Feil"},
            {"Konto": "2940", "Status": "Uavklart"},
            {"Konto": "5890", "Status": "Mistenkelig"},
        ]
    )

    sorted_df = page_a07.sort_mapping_rows_by_audit_status(mapping_df)
    critical_df = page_a07.filter_mapping_rows_by_audit_status(mapping_df, "kritiske")

    assert sorted_df["Konto"].tolist() == ["6701", "5890", "2940", "5000"]
    assert critical_df["Konto"].tolist() == ["6701", "5890"]

def test_build_mapping_review_df_prioritizes_cleanup_and_recommends_actions() -> None:
    audit_df = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Navn": "Lonn ansatte",
                "CurrentA07Code": "fastloenn",
                "CurrentRf1022GroupId": "100_loenn_ol",
                "ExpectedRf1022GroupId": "100_loenn_ol",
                "AliasStatus": "",
                "Kol": "UB",
                "Belop": 1000.0,
                "Status": "Trygg",
                "Reason": "Konto og RF-1022-gruppe peker samme faglige vei.",
                "Evidence": "katalog",
            },
            {
                "Konto": "6701",
                "Navn": "Honorar revisjon",
                "CurrentA07Code": "annet",
                "CurrentRf1022GroupId": "100_loenn_ol",
                "ExpectedRf1022GroupId": "",
                "AliasStatus": "Ekskludert",
                "Kol": "UB",
                "Belop": 72250.4,
                "Status": "Feil",
                "Reason": "Konto ser ut som drifts-/honorarkostnad utenfor A07-lonn.",
                "Evidence": "manual",
            },
            {
                "Konto": "5890",
                "Navn": "Annen refusjon",
                "CurrentA07Code": "sumAvgiftsgrunnlagRefusjon",
                "CurrentRf1022GroupId": "100_refusjon",
                "ExpectedRf1022GroupId": "100_refusjon",
                "AliasStatus": "",
                "Kol": "Endring",
                "Belop": -58009.0,
                "Status": "Mistenkelig",
                "Reason": "Generisk refusjon mangler NAV/sykepenger-stotte.",
                "Evidence": "belop",
            },
        ]
    )

    out = page_a07.build_mapping_review_df(audit_df)
    summary = page_a07.build_mapping_review_summary(out)

    assert out["Konto"].tolist() == ["6701", "5890", "5000"]
    assert out.loc[out["Konto"] == "6701", "AnbefaltHandling"].iloc[0] == "Fjern mapping og ekskluder navn"
    assert summary == {"total": 3, "kritiske": 2, "feil": 1, "mistenkelige": 1, "uavklarte": 0, "trygge": 1}
    assert page_a07.next_mapping_review_problem_account(out, "6701") == "5890"
    assert page_a07.next_mapping_review_problem_account(out, "5890") == "6701"

def test_mapping_audit_downgrades_excluded_alias_from_safe_to_suspicious(monkeypatch) -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn ansatte", "IB": 0.0, "Endring": 1000.0, "UB": 1000.0},
        ]
    )
    monkeypatch.setattr(a07_control_data, "load_rulebook", lambda _path: {})
    monkeypatch.setattr(a07_control_data, "evaluate_a07_rule_name_status", lambda _code, _name, _rulebook=None: "Ekskludert")

    out = page_a07.build_mapping_audit_df(
        gl_df,
        {"5000": "fastloenn"},
        suggestions_df=pd.DataFrame(
            [
                {
                    "Kode": "fastloenn",
                    "ForslagKontoer": "5000",
                    "SuggestionGuardrail": "accepted",
                    "UsedRulebook": True,
                }
            ]
        ),
        basis_col="Endring",
    )

    row = out.iloc[0]
    assert row["AliasStatus"] == "Ekskludert"
    assert row["Status"] == "Mistenkelig"
    assert "ekskludert" in row["Reason"]


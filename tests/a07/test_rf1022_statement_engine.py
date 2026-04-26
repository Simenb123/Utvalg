from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_rf1022_flags_model_aga_as_subtrack_of_opplysningspliktig() -> None:
    from a07_feature.control.rf1022_contract import rf1022_flags_from_tags

    flags = rf1022_flags_from_tags(("aga_pliktig",))

    assert flags.opplysningspliktig is True
    assert flags.aga_pliktig is True
    assert flags.feriepengegrunnlag is False


def test_rf1022_post_for_group_maps_payroll_groups_to_expected_sections() -> None:
    assert page_a07.rf1022_post_for_group("Skattetrekk") == (100, "Lønn og trekk")
    assert page_a07.rf1022_post_for_group("Skyldig arbeidsgiveravgift") == (110, "Arbeidsgiveravgift")
    assert page_a07.rf1022_post_for_group("Skyldig pensjon") == (120, "Pensjon og refusjon")
    assert page_a07.rf1022_post_for_group("uavklart_rf1022") == (999, "Uavklart RF-1022")
    assert page_a07.rf1022_post_for_group("ukjent_gruppe", "Naturalytelse") == (
        130,
        "Naturalytelser og styrehonorar",
    )

def test_a07_code_rf1022_group_is_fail_closed_for_unknown_code() -> None:
    assert page_a07.a07_code_rf1022_group("bonus") == "100_loenn_ol"
    assert page_a07.a07_code_rf1022_group("fastTillegg") == "100_loenn_ol"
    assert page_a07.a07_code_rf1022_group("trekkILoennForFerie") == "100_loenn_ol"
    assert page_a07.a07_code_rf1022_group("trekkLoennForFerie") == "100_loenn_ol"
    assert page_a07.a07_code_rf1022_group("sumAvgiftsgrunnlagRefusjon") == "100_refusjon"
    assert page_a07.a07_code_rf1022_group("A07_GROUP:fastloenn+timeloenn") == "100_loenn_ol"
    assert page_a07.a07_code_rf1022_group("A07_GROUP:trekkLoennForFerie+fastloenn") == "100_loenn_ol"
    assert page_a07.a07_code_rf1022_group("A07_GROUP:fastloenn+sumAvgiftsgrunnlagRefusjon") == "uavklart_rf1022"
    assert page_a07.a07_code_rf1022_group("A07_GROUP:ukjentNyKode") == "uavklart_rf1022"
    assert page_a07.a07_code_rf1022_group("ukjentNyKode") == "uavklart_rf1022"

def test_build_rf1022_statement_df_uses_a07_expected_amounts_without_gl_rows() -> None:
    a07_overview_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1000.0},
            {"Kode": "bonus", "Navn": "Bonus", "Belop": 250.0},
            {"Kode": "fastTillegg", "Navn": "Fast tillegg", "Belop": 50.0},
            {"Kode": "sumAvgiftsgrunnlagRefusjon", "Navn": "Refusjon", "Belop": -75.0},
            {"Kode": "elektroniskKommunikasjon", "Navn": "Telefon", "Belop": 40.0},
            {"Kode": "tilskuddOgPremieTilPensjon", "Navn": "Pensjon", "Belop": 500.0},
            {"Kode": "ukjentNyKode", "Navn": "Ukjent", "Belop": 13.0},
        ]
    )

    out = page_a07.build_rf1022_statement_df(
        pd.DataFrame(),
        a07_overview_df=a07_overview_df,
        basis_col="Endring",
    )

    assert out["GroupId"].tolist() == [
        "100_loenn_ol",
        "100_refusjon",
        "111_naturalytelser",
        "112_pensjon",
        "uavklart_rf1022",
    ]
    assert out["GL_Belop"].tolist() == [0.0, 0.0, 0.0, 0.0, 0.0]
    assert out["A07"].tolist() == [1300.0, -75.0, 40.0, 500.0, 13.0]
    assert out["Diff"].tolist() == [1300.0, -75.0, 40.0, 500.0, 13.0]
    assert out["Status"].tolist() == ["Mangler SB", "Mangler SB", "Mangler SB", "Mangler SB", "Mangler SB"]
    unresolved = out.loc[out["GroupId"] == "uavklart_rf1022"].iloc[0]
    assert unresolved["Post"] == ""
    assert unresolved["Kontrollgruppe"] == "A07 uten RF-1022-post"

def test_build_rf1022_statement_df_overlays_a07_expected_amounts_on_control_rows() -> None:
    control_statement_df = pd.DataFrame(
        [
            {
                "Gruppe": "100_loenn_ol",
                "Navn": "Post 100 Lonn o.l.",
                "Endring": 800.0,
                "A07": None,
                "Diff": None,
                "Status": "Manuell",
                "AntallKontoer": 2,
            }
        ]
    )
    a07_overview_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Belop": 1000.0},
            {"Kode": "feriepenger", "Belop": 100.0},
        ]
    )

    out = page_a07.build_rf1022_statement_df(
        control_statement_df,
        a07_overview_df=a07_overview_df,
        basis_col="Endring",
    )

    row = out.loc[out["GroupId"] == "100_loenn_ol"].iloc[0]
    assert row["GL_Belop"] == 800.0
    assert row["SamledeYtelser"] == 800.0
    assert row["A07"] == 1100.0
    assert row["Diff"] == 300.0

def test_build_rf1022_statement_df_separates_opplysningspliktig_and_aga_tracks() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn ansatte", "IB": 0.0, "Endring": 100.0, "UB": 100.0, "Kode": "fastloenn"},
            {
                "Konto": "5330",
                "Navn": "Styrehonorar",
                "IB": 0.0,
                "Endring": 50.0,
                "UB": 50.0,
                "Kode": "styrehonorarOgGodtgjoerelseVerv",
            },
        ]
    )
    control_statement_df = pd.DataFrame(
        [
            {
                "Gruppe": "100_loenn_ol",
                "Navn": "Post 100 Lonn o.l.",
                "Endring": 150.0,
                "A07": 150.0,
                "Diff": 0.0,
                "Status": "Ferdig",
                "AntallKontoer": 2,
                "Kontoer": "5000,5330",
            }
        ]
    )
    a07_overview_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Belop": 100.0, "AgaPliktig": "Ja"},
            {"Kode": "styrehonorarOgGodtgjoerelseVerv", "Belop": 50.0, "AgaPliktig": "Nei"},
        ]
    )
    document = AccountProfileDocument(
        client="Test",
        year=2025,
        profiles={
            "5000": AccountProfile(account_no="5000", control_tags=("opplysningspliktig", "aga_pliktig")),
            "5330": AccountProfile(account_no="5330", control_tags=("opplysningspliktig",)),
        },
    )

    out = page_a07.build_rf1022_statement_df(
        control_statement_df,
        a07_overview_df=a07_overview_df,
        control_gl_df=control_gl_df,
        profile_document=document,
        basis_col="Endring",
    )

    row = out.loc[out["GroupId"] == "100_loenn_ol"].iloc[0]
    assert row["SamledeYtelser"] == 150.0
    assert row["A07"] == 150.0
    assert row["Diff"] == 0.0
    assert row["AgaGrunnlag"] == 100.0
    assert row["A07Aga"] == 100.0
    assert row["AgaDiff"] == 0.0

def test_build_rf1022_statement_df_falls_back_to_control_df_for_a07_aga_totals() -> None:
    control_statement_df = pd.DataFrame(
        [{"Gruppe": "100_loenn_ol", "Navn": "Post 100 Lonn o.l.", "Endring": 100.0, "Kontoer": "5000"}]
    )
    a07_overview_df = pd.DataFrame([{"Kode": "fastloenn", "Belop": 100.0}])
    control_df = pd.DataFrame([{"Kode": "fastloenn", "A07_Belop": 100.0, "AgaPliktig": "Ja"}])

    out = page_a07.build_rf1022_statement_df(
        control_statement_df,
        a07_overview_df=a07_overview_df,
        control_df=control_df,
        basis_col="Endring",
    )

    assert out.loc[0, "A07Aga"] == 100.0

def test_append_rf1022_total_row_sums_report_tracks() -> None:
    rf1022_df = pd.DataFrame(
        [
            {
                "GroupId": "100_loenn_ol",
                "Kontrollgruppe": "Post 100 Lonn o.l.",
                "GL_Belop": 800.0,
                "SamledeYtelser": 750.0,
                "A07": 760.0,
                "Diff": 10.0,
                "AgaGrunnlag": 700.0,
                "A07Aga": 700.0,
                "AgaDiff": 0.0,
                "AntallKontoer": 2,
            },
            {
                "GroupId": "112_pensjon",
                "Kontrollgruppe": "Post 112 Pensjon",
                "GL_Belop": 250.0,
                "SamledeYtelser": 250.0,
                "A07": 250.0,
                "Diff": 0.0,
                "AgaGrunnlag": 250.0,
                "A07Aga": 240.0,
                "AgaDiff": -10.0,
                "AntallKontoer": 1,
            },
        ]
    )

    out = a07_control_data.append_rf1022_total_row(rf1022_df)

    total = out.iloc[-1]
    assert total["GroupId"] == a07_control_data.RF1022_TOTAL_ROW_ID
    assert total["Kontrollgruppe"] == "SUM"
    assert total["SamledeYtelser"] == 1000.0
    assert total["A07"] == 1010.0
    assert total["Diff"] == 10.0
    assert total["AgaGrunnlag"] == 950.0
    assert total["A07Aga"] == 940.0
    assert total["AgaDiff"] == -10.0

def test_build_rf1022_summary_cards_exposes_main_quality_totals() -> None:
    rf1022_df = pd.DataFrame(
        [
            {"GroupId": "100_loenn_ol", "SamledeYtelser": 100.0, "A07": 100.0, "Diff": 0.0, "AgaGrunnlag": 90.0, "A07Aga": 90.0, "AgaDiff": 0.0},
            {"GroupId": "uavklart_rf1022", "SamledeYtelser": 0.0, "A07": 25.0, "Diff": 25.0, "AgaGrunnlag": 0.0, "A07Aga": 0.0, "AgaDiff": 0.0},
        ]
    )

    cards = {card["key"]: card for card in a07_control_data.build_rf1022_summary_cards(rf1022_df)}

    assert cards["opplysning"]["value"] == "Diff 25,00"
    assert cards["opplysning"]["detail"] == "SB 100,00 | A07 125,00"
    assert cards["aga"]["value"] == "Diff 0,00"
    assert cards["uavklart"]["value"] == "25,00"
    assert cards["uavklart"]["status"] == "warning"
    assert cards["status"]["value"] == "1/2 avstemt"

def test_build_rf1022_accounts_df_shapes_workbook_like_rows_for_payroll_accounts() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn ansatte", "IB": 0.0, "Endring": 1200.0, "UB": 1200.0, "Kode": "fastloenn"},
            {"Konto": "2940", "Navn": "Skyldige feriepenger", "IB": 300.0, "Endring": -200.0, "UB": 500.0, "Kode": "feriepenger"},
        ]
    )
    control_statement_df = pd.DataFrame(
        [
            {"Gruppe": "100_loenn_ol", "Navn": "Post 100 Lonn o.l.", "Kontoer": "5000, 2940"},
        ]
    )
    document = AccountProfileDocument(
        client="Test",
        year=2025,
        profiles={
            "5000": AccountProfile(
                account_no="5000",
                account_name="Lonn ansatte",
                control_group="100_loenn_ol",
                control_tags=("opplysningspliktig", "aga_pliktig", "feriepengergrunnlag"),
            ),
            "2940": AccountProfile(
                account_no="2940",
                account_name="Skyldige feriepenger",
                control_group="100_loenn_ol",
                control_tags=("opplysningspliktig", "aga_pliktig"),
            ),
        },
    )

    out = page_a07.build_rf1022_accounts_df(
        control_gl_df,
        control_statement_df,
        "100_loenn_ol",
        basis_col="Endring",
        profile_document=document,
    )

    assert out.columns.tolist() == [
        "Post",
        "Konto",
        "Navn",
        "KostnadsfortYtelse",
        "TilleggTidligereAar",
        "FradragPaalopt",
        "SamledeYtelser",
        "AgaPliktig",
        "AgaGrunnlag",
        "Feriepengegrunnlag",
    ]
    assert out["Konto"].tolist() == ["5000", "2940"]
    assert out.loc[0, "Post"].startswith("Post 100")
    assert out.loc[0, "KostnadsfortYtelse"] == 1200.0
    assert out.loc[0, "SamledeYtelser"] == 1200.0
    assert bool(out.loc[0, "AgaPliktig"]) is True
    assert out.loc[0, "AgaGrunnlag"] == 1200.0
    assert bool(out.loc[0, "Feriepengegrunnlag"]) is True
    assert out.loc[1, "TilleggTidligereAar"] == 300.0
    assert out.loc[1, "FradragPaalopt"] == 500.0
    assert out.loc[1, "SamledeYtelser"] == -200.0

def test_build_rf1022_accounts_df_uses_a07_standard_tags_when_profiles_are_missing() -> None:
    control_gl_df = pd.DataFrame(
        [
            {
                "Konto": "5251",
                "Navn": "Gruppelivsforsikring",
                "IB": 0.0,
                "Endring": 10.0,
                "UB": 10.0,
                "Kode": "skattepliktigDelForsikringer",
            },
            {
                "Konto": "5330",
                "Navn": "Styrehonorar",
                "IB": 0.0,
                "Endring": 20.0,
                "UB": 20.0,
                "Kode": "styrehonorarOgGodtgjoerelseVerv",
            },
        ]
    )
    control_statement_df = pd.DataFrame(
        [
            {"Gruppe": "111_naturalytelser", "Navn": "Post 111 Naturalytelser", "Kontoer": "5251"},
            {"Gruppe": "100_loenn_ol", "Navn": "Post 100 Lonn o.l.", "Kontoer": "5330"},
        ]
    )

    natural = page_a07.build_rf1022_accounts_df(
        control_gl_df,
        control_statement_df,
        "111_naturalytelser",
        basis_col="Endring",
    )
    styre = page_a07.build_rf1022_accounts_df(
        control_gl_df,
        control_statement_df,
        "100_loenn_ol",
        basis_col="Endring",
    )

    assert natural.loc[0, "SamledeYtelser"] == 10.0
    assert bool(natural.loc[0, "AgaPliktig"]) is True
    assert natural.loc[0, "AgaGrunnlag"] == 10.0
    assert styre.loc[0, "SamledeYtelser"] == 20.0
    assert bool(styre.loc[0, "AgaPliktig"]) is True
    assert styre.loc[0, "AgaGrunnlag"] == 20.0

def test_build_rf1022_accounts_df_keeps_refusjon_as_aga_basis_row() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5800", "Navn": "Refusjoner av sykepenger", "IB": 0.0, "Endring": -358842.0, "UB": -358842.0},
        ]
    )
    control_statement_df = pd.DataFrame(
        [
            {"Gruppe": "100_refusjon", "Navn": "Post 100 Refusjon", "Kontoer": "5800"},
        ]
    )
    document = AccountProfileDocument(
        client="Test",
        year=2025,
        profiles={
            "5800": AccountProfile(
                account_no="5800",
                account_name="Refusjoner av sykepenger",
                control_group="100_refusjon",
                control_tags=("refusjon",),
            ),
        },
    )

    out = page_a07.build_rf1022_accounts_df(
        control_gl_df,
        control_statement_df,
        "100_refusjon",
        basis_col="Endring",
        profile_document=document,
    )

    assert out.loc[0, "Post"] == "Post 100 Refusjon"
    assert pd.isna(out.loc[0, "SamledeYtelser"])
    assert pd.isna(out.loc[0, "AgaPliktig"])
    assert out.loc[0, "AgaGrunnlag"] == -358842.0

def test_filter_control_queue_by_rf1022_group_scopes_detail_codes() -> None:
    control_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Rf1022GroupId": "100_loenn_ol"},
            {"Kode": "tilskuddOgPremieTilPensjon", "Rf1022GroupId": "112_pensjon"},
            {"Kode": "elektroniskKommunikasjon", "Rf1022GroupId": "111_naturalytelser"},
        ]
    )

    out = a07_control_data.filter_control_queue_by_rf1022_group(control_df, "112_pensjon")

    assert out["Kode"].tolist() == ["tilskuddOgPremieTilPensjon"]

def test_filter_suggestions_for_rf1022_group_scopes_candidates() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "ForslagKontoer": "5000"},
            {"Kode": "tilskuddOgPremieTilPensjon", "ForslagKontoer": "5930"},
            {"Kode": "elektroniskKommunikasjon", "ForslagKontoer": "5210"},
        ]
    )

    out = a07_control_data.filter_suggestions_for_rf1022_group(suggestions_df, "111_naturalytelser")

    assert out["Kode"].tolist() == ["elektroniskKommunikasjon"]


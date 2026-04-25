from __future__ import annotations

from .shared import *  # noqa: F401,F403


def test_build_control_queue_df_uses_mapping_audit_for_suspicious_saved_mapping() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "6701", "Navn": "Honorar revisjon", "IB": 0.0, "Endring": 72250.4, "UB": 72250.4},
        ]
    )
    mapping = {"6701": "annet"}
    audit_df = page_a07.build_mapping_audit_df(gl_df, mapping)
    overview_df = pd.DataFrame(
        [
            {"Kode": "annet", "Navn": "Annet", "Belop": 72250.4, "GL_Belop": 72250.4, "Diff": 0.0},
        ]
    )

    out = page_a07.build_control_queue_df(
        overview_df,
        page_a07._empty_suggestions_df(),
        mapping_current=mapping,
        mapping_previous={},
        gl_df=gl_df,
        mapping_audit_df=audit_df,
    )

    assert out.loc[0, "GuidetStatus"] == "Mistenkelig kobling"
    assert bool(out.loc[0, "CurrentMappingSuspicious"]) is True
    assert "6701:" in out.loc[0, "CurrentMappingSuspiciousReason"]

def test_control_recommendation_label_is_short_and_list_friendly() -> None:
    safe_best = pd.Series({"WithinTolerance": True})
    weak_best = pd.Series({"WithinTolerance": False})

    assert page_a07.control_recommendation_label(has_history=True, best_suggestion=safe_best) == "Se forslag"
    assert page_a07.control_recommendation_label(has_history=False, best_suggestion=safe_best) == "Se forslag"
    assert page_a07.control_recommendation_label(has_history=False, best_suggestion=weak_best) == "Se forslag"
    assert page_a07.control_recommendation_label(has_history=False, best_suggestion=None) == "Kontroller kobling"

def test_compact_control_next_action_shortens_user_hint() -> None:
    assert page_a07.compact_control_next_action("Se forslag for valgt kode.") == "Forslag"
    assert page_a07.compact_control_next_action("Aapne historikk for valgt kode.") == "Historikk"
    assert (
        page_a07.compact_control_next_action("Tildel RF-1022-post i Saldobalanse.")
        == "Tildel RF-1022-post i Saldobalanse."
    )
    assert page_a07.compact_control_next_action("Ingen handling nodvendig.") == "Ingen"

def test_build_control_queue_df_keeps_single_display_column_for_a07_identity() -> None:
    overview_df = pd.DataFrame(
        [
            {
                "Kode": "tilskuddOgPremieTilPensjon",
                "Navn": "Tilskudd og premie til pensjon",
                "Belop": 690556.0,
                "Status": "Ikke mappet",
            }
        ]
    )

    out = page_a07.build_control_queue_df(
        overview_df,
        pd.DataFrame(),
        mapping_current={},
        mapping_previous={},
        gl_df=pd.DataFrame(columns=["Konto"]),
    )

    assert out.loc[0, "A07Post"] == "Tilskudd og premie til pensjon (tilskuddOgPremieTilPensjon)"
    assert out.loc[0, "Kode"] == "tilskuddOgPremieTilPensjon"
    assert out.loc[0, "Navn"] == "Tilskudd og premie til pensjon"

def test_build_control_queue_df_displays_aga_pliktig_from_source_and_rulebook(monkeypatch) -> None:
    monkeypatch.setattr(
        a07_control_data,
        "load_rulebook",
        lambda _path: {
            "feriepenger": RulebookRule(aga_pliktig=True),
            "sumAvgiftsgrunnlagRefusjon": RulebookRule(aga_pliktig=False),
        },
    )
    overview_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 100.0, "Status": "OK", "AgaPliktig": False},
            {"Kode": "feriepenger", "Navn": "Feriepenger", "Belop": 50.0, "Status": "OK"},
            {"Kode": "sumAvgiftsgrunnlagRefusjon", "Navn": "Refusjon", "Belop": -25.0, "Status": "OK"},
        ]
    )

    out = page_a07.build_control_queue_df(
        overview_df,
        pd.DataFrame(),
        mapping_current={},
        mapping_previous={},
        gl_df=pd.DataFrame(columns=["Konto"]),
    )

    assert out.loc[out["Kode"] == "fastloenn", "AgaPliktig"].iloc[0] == "Nei"
    assert out.loc[out["Kode"] == "feriepenger", "AgaPliktig"].iloc[0] == "Ja"
    assert out.loc[out["Kode"] == "sumAvgiftsgrunnlagRefusjon", "AgaPliktig"].iloc[0] == "Nei"

def test_build_control_queue_df_uses_supplied_rulebook_without_reload(monkeypatch) -> None:
    monkeypatch.setattr(
        a07_control_data,
        "load_rulebook",
        lambda _path: (_ for _ in ()).throw(AssertionError("rulebook should be reused")),
    )
    overview_df = pd.DataFrame(
        [{"Kode": "feriepenger", "Navn": "Feriepenger", "Belop": 50.0, "Status": "OK"}]
    )

    out = page_a07.build_control_queue_df(
        overview_df,
        pd.DataFrame(),
        mapping_current={},
        mapping_previous={},
        gl_df=pd.DataFrame(columns=["Konto"]),
        rulebook={"feriepenger": RulebookRule(aga_pliktig=True)},
    )

    assert out.loc[out["Kode"] == "feriepenger", "AgaPliktig"].iloc[0] == "Ja"

def test_evaluate_current_mapping_suspicion_reuses_account_name_lookup(monkeypatch) -> None:
    monkeypatch.setattr(
        a07_control_matching,
        "build_account_name_lookup",
        lambda _df: (_ for _ in ()).throw(AssertionError("lookup should be reused")),
    )

    suspicious, reason = a07_control_matching.evaluate_current_mapping_suspicion(
        code="pensjon",
        code_name="Pensjon",
        current_accounts=["5420"],
        history_accounts=[],
        gl_df=pd.DataFrame([{"Konto": "5420", "Navn": "Pensjon"}]),
        account_name_lookup={"5420": "Pensjon"},
    )

    assert suspicious is False
    assert reason == ""

def test_build_control_queue_df_flags_mistenkelig_mapping_and_prioritizes_suggestions() -> None:
    overview_df = pd.DataFrame(
        [
            {
                "Kode": "tilskuddOgPremieTilPensjon",
                "Navn": "Tilskudd og premie til pensjon",
                "Belop": 690556.0,
                "Status": "OK",
            }
        ]
    )
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "tilskuddOgPremieTilPensjon",
                "ForslagKontoer": "5420",
                "WithinTolerance": True,
                "Diff": 58318.21,
                "Explain": "regel=rulebook",
                "UsedRulebook": True,
            }
        ]
    )
    gl_df = pd.DataFrame(
        [
            {"Konto": "6300", "Navn": "Leie lokale"},
            {"Konto": "5420", "Navn": "Innberetningspliktig pensjonskostnad"},
        ]
    )

    out = page_a07.build_control_queue_df(
        overview_df,
        suggestions_df,
        mapping_current={"6300": "tilskuddOgPremieTilPensjon"},
        mapping_previous={},
        gl_df=gl_df,
    )

    assert bool(out.loc[0, "CurrentMappingSuspicious"]) is True
    assert out.loc[0, "GuidetStatus"] == "Mistenkelig kobling"
    assert out.loc[0, "Anbefalt"] == "Se forslag"
    assert out.loc[0, "SuggestionGuardrail"] == "accepted"

def test_build_control_queue_df_prioritizes_special_add_suggestion_when_mapped_code_has_avvik() -> None:
    overview_df = pd.DataFrame(
        [
            {
                "Kode": "feriepenger",
                "Navn": "Feriepenger",
                "Belop": 862_608.92,
                "Status": "Avvik",
                "Diff": -11_069.15,
            }
        ]
    )
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "feriepenger",
                "ForslagKontoer": "2932,2940",
                "WithinTolerance": True,
                "SuggestionGuardrail": "accepted",
                "SuggestionGuardrailReason": "Treff paa regelbok",
                "UsedSpecialAdd": True,
            }
        ]
    )

    out = page_a07.build_control_queue_df(
        overview_df,
        suggestions_df,
        mapping_current={"5020": "feriepenger", "5096": "feriepenger"},
        mapping_previous={},
        gl_df=pd.DataFrame(
            [
                {"Konto": "5020", "Navn": "Feriepenger"},
                {"Konto": "5096", "Navn": "Periodisering av feriepenger"},
                {"Konto": "2932", "Navn": "Feriepenger mer tid"},
                {"Konto": "2940", "Navn": "Skyldig feriepenger"},
            ]
        ),
    )

    assert out.loc[0, "GuidetStatus"] == "Har forslag"
    assert out.loc[0, "Anbefalt"] == "Se forslag"
    assert out.loc[0, "NesteHandling"] == "Treff paa regelbok"

def test_filter_control_queue_df_and_bucket_summary_group_rows_for_human_workflow() -> None:
    control_df = pd.DataFrame(
        [
            {"Kode": "bonus", "Arbeidsstatus": "Ferdig"},
            {"Kode": "telefon", "Arbeidsstatus": "Forslag"},
            {"Kode": "refusjon", "GuidetStatus": "Mistenkelig kobling"},
            {"Kode": "pensjon", "Arbeidsstatus": "Manuell"},
        ]
    )

    next_rows = page_a07.filter_control_queue_df(control_df, "neste")
    suspicious_rows = page_a07.filter_control_queue_df(control_df, "mistenkelig")
    manual_rows = page_a07.filter_control_queue_df(control_df, "manuell")
    summary = page_a07.build_control_bucket_summary(control_df)

    assert next_rows["Kode"].tolist() == ["telefon", "refusjon", "pensjon"]
    assert suspicious_rows["Kode"].tolist() == ["refusjon"]
    assert manual_rows["Kode"].tolist() == ["pensjon"]
    assert summary == "3 åpne"

def test_build_control_queue_df_sorts_by_work_priority_then_amount() -> None:
    overview_df = pd.DataFrame(
        [
            {"Kode": "liten", "Navn": "Liten", "Belop": 100.0, "Status": "Ikke mappet"},
            {"Kode": "stor", "Navn": "Stor", "Belop": 900.0, "Status": "Ikke mappet"},
            {"Kode": "ferdig", "Navn": "Ferdig", "Belop": 5000.0, "Status": "OK"},
        ]
    )
    suggestions_df = pd.DataFrame()
    gl_df = pd.DataFrame([{"Konto": "5000"}])

    out = page_a07.build_control_queue_df(
        overview_df,
        suggestions_df,
        mapping_current={"5000": "ferdig"},
        mapping_previous={},
        gl_df=gl_df,
        locked_codes={"ferdig"},
    )

    assert out["Kode"].tolist() == ["stor", "liten", "ferdig"]


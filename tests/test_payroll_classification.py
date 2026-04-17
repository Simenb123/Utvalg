from __future__ import annotations

import pandas as pd

from account_profile import AccountProfile, AccountProfileDocument
from account_profile_catalog import load_account_classification_catalog
import payroll_classification


def test_suggest_a07_code_can_use_usage_signals(tmp_path) -> None:
    rulebook_path = tmp_path / "rulebook.json"
    rulebook_path.write_text(
        """
        {
          "rules": {
            "tilskuddOgPremieTilPensjon": {
              "label": "Pensjon",
              "keywords": ["pensjon", "otp"]
            }
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    suggestion = payroll_classification.suggest_a07_code(
        account_no="5940",
        account_name="Diverse personalkostnad",
        movement=551590.0,
        usage=payroll_classification.AccountUsageFeatures(
            posting_count=12,
            unique_vouchers=12,
            active_months=12,
            monthly_regularity=1.0,
            repeat_amount_ratio=0.8,
            top_text_tokens=("otp", "pensjon"),
        ),
        rulebook_path=str(rulebook_path),
    )

    assert suggestion is not None
    assert suggestion.value == "tilskuddOgPremieTilPensjon"
    assert "Regelbok:" in str(suggestion.reason)


def test_build_payroll_suggestion_map_prefers_history_for_missing_fields() -> None:
    accounts_df = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Kontonavn": "Lønn til ansatte",
                "Endring": 525000.0,
                "UB": 525000.0,
            }
        ]
    )
    current = AccountProfileDocument(client="Test", year=2025)
    history = AccountProfileDocument(
        client="Test",
        year=2024,
        profiles={
            "5000": AccountProfile(
                account_no="5000",
                a07_code="fastloenn",
                control_group="100_loenn_ol",
                control_tags=("opplysningspliktig", "aga_pliktig", "feriepengergrunnlag"),
                source="history",
                confidence=1.0,
            )
        },
    )

    out = payroll_classification.build_payroll_suggestion_map(
        accounts_df,
        document=current,
        history_document=history,
    )

    result = out["5000"]
    assert result.payroll_relevant is True
    assert result.payroll_status == "Forslag"
    assert result.suggestions["a07_code"].value == "fastloenn"
    assert result.suggestions["control_group"].value == "100_loenn_ol"
    assert payroll_classification.is_strict_auto_suggestion(result.suggestions["a07_code"]) is True


def test_build_payroll_suggestion_map_derives_naturalytelse_from_name() -> None:
    accounts_df = pd.DataFrame(
        [
            {
                "Konto": "5210",
                "Kontonavn": "Fri telefon",
                "Endring": 8784.0,
                "UB": 8784.0,
            }
        ]
    )
    current = AccountProfileDocument(client="Test", year=2025)

    out = payroll_classification.build_payroll_suggestion_map(
        accounts_df,
        document=current,
        history_document=None,
    )

    result = out["5210"]
    assert result.payroll_relevant is True
    assert result.payroll_status == "Forslag"
    assert result.suggestions["a07_code"].value == "elektroniskKommunikasjon"
    assert result.suggestions["control_group"].value == "111_naturalytelser"
    assert "naturalytelse" in result.suggestions["control_tags"].value


def test_default_catalog_contains_full_payroll_group_and_tag_set() -> None:
    catalog = load_account_classification_catalog()

    assert {entry.id for entry in payroll_classification._payroll_group_entries(catalog)} == set(
        payroll_classification.PAYROLL_GROUP_IDS
    )
    assert {entry.id for entry in payroll_classification._payroll_tag_entries(catalog)} == set(
        payroll_classification.PAYROLL_TAG_IDS
    )


def test_default_catalog_aliases_support_direct_payroll_control_suggestions() -> None:
    catalog = load_account_classification_catalog()

    group_suggestion = payroll_classification._suggest_control_group_from_catalog(
        account_no="5210",
        account_name="Fri telefon",
        catalog=catalog,
    )
    tag_suggestion = payroll_classification._suggest_control_tags_from_catalog(
        account_no="5330",
        account_name="Styrehonorar styreverv",
        catalog=catalog,
    )

    assert group_suggestion is not None
    assert group_suggestion.value == "111_naturalytelser"
    assert "navn/alias: telefon" in str(group_suggestion.reason)

    assert tag_suggestion is not None
    assert "styrehonorar" in tuple(tag_suggestion.value or ())
    assert "navn/alias: Styrehonorar" in str(tag_suggestion.reason)


def test_build_payroll_suggestion_map_ignores_weak_heuristic_for_irrelevant_account(monkeypatch) -> None:
    accounts_df = pd.DataFrame(
        [
            {
                "Konto": "1280",
                "Kontonavn": "Kontormaskiner",
                "Endring": 27486.88,
                "UB": 27486.88,
            }
        ]
    )
    current = AccountProfileDocument(client="Test", year=2025)

    monkeypatch.setattr(
        payroll_classification,
        "suggest_a07_code",
        lambda **_kwargs: payroll_classification.AccountProfileSuggestion(
            field_name="a07_code",
            value="fastloenn",
            source="heuristic",
            confidence=0.07,
            reason="Heuristisk treff",
        ),
    )

    out = payroll_classification.build_payroll_suggestion_map(
        accounts_df,
        document=current,
        history_document=None,
    )

    result = out["1280"]
    assert result.suggestions == {}
    assert result.payroll_relevant is False
    assert result.payroll_status == ""
    assert result.is_unclear is False


def test_suggest_a07_code_uses_shared_aliases_for_firmabil() -> None:
    suggestion = payroll_classification.suggest_a07_code(
        account_no="5200",
        account_name="Firmabil",
        movement=466317.48,
    )

    assert suggestion is not None
    assert suggestion.value == "bil"


def test_suggest_a07_code_blocks_bank_and_equity_accounts_from_heuristics() -> None:
    bank_suggestion = payroll_classification.suggest_a07_code(
        account_no="1930",
        account_name="BN Bank - Pensjon",
        movement=55223.0,
    )
    equity_suggestion = payroll_classification.suggest_a07_code(
        account_no="2020",
        account_name="Overkursfond",
        movement=0.0,
    )

    assert bank_suggestion is None
    assert equity_suggestion is None


def test_suggest_a07_code_blocks_weak_balance_sheet_payroll_terms_without_strong_context() -> None:
    suggestion = payroll_classification.suggest_a07_code(
        account_no="1742",
        account_name="Forskuddsbetalt forsikring",
        movement=-26086.0,
    )

    assert suggestion is None


def test_suggest_a07_code_blocks_refusjon_balance_sheet_account_from_a07_lane() -> None:
    suggestion = payroll_classification.suggest_a07_code(
        account_no="1755",
        account_name="Periodisering sykepenger refusjon",
        movement=0.0,
    )

    assert suggestion is None


def test_suspicious_saved_payroll_profile_issue_flags_obvious_non_payroll_accounts() -> None:
    bank_issue = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="1930",
        account_name="BN Bank - Pensjon",
        current_profile=AccountProfile(
            account_no="1930",
            a07_code="fastloenn",
            source="manual",
            confidence=1.0,
        ),
    )
    equity_issue = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="2020",
        account_name="Overkursfond",
        current_profile=AccountProfile(
            account_no="2020",
            a07_code="fastloenn",
            source="manual",
            confidence=1.0,
        ),
    )
    vat_issue = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="2740",
        account_name="Oppgjørskonto merverdiavgift",
        current_profile=AccountProfile(
            account_no="2740",
            a07_code="fastloenn",
            source="manual",
            confidence=1.0,
        ),
    )

    assert bank_issue is not None
    assert equity_issue is not None
    assert vat_issue is not None


def test_suspicious_saved_payroll_profile_issue_allows_clear_payroll_balance_sheet_signal() -> None:
    issue = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="1755",
        account_name="Periodisering sykepenger refusjon",
        current_profile=AccountProfile(
            account_no="1755",
            a07_code="sumAvgiftsgrunnlagRefusjon",
            source="manual",
            confidence=1.0,
        ),
    )

    assert issue is None


def test_suggest_a07_code_blocks_revision_fee_from_bil_and_styrehonorar() -> None:
    suggestion = payroll_classification.suggest_a07_code(
        account_no="6705",
        account_name="Revisjonshonorar",
        movement=180000.0,
    )

    assert suggestion is None or suggestion.value not in {
        "bil",
        "yrkebilTjenstligbehovListepris",
        "styrehonorarOgGodtgjoerelseVerv",
    }


def test_suggest_a07_code_does_not_match_verv_inside_ervervet() -> None:
    suggestion = payroll_classification.suggest_a07_code(
        account_no="1000",
        account_name="Forskning og utvikling, ervervet",
        movement=0.0,
    )

    assert suggestion is None


def test_heuristics_block_anleggsmiddel_accounts_without_payroll_signal() -> None:
    suggestion = payroll_classification.suggest_a07_code(
        account_no="1230",
        account_name="Personbiler/stasjonsvogner",
        movement=0.0,
    )

    assert suggestion is None


def test_suspicious_saved_payroll_profile_issue_flags_immaterial_accounts() -> None:
    issue = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="1000",
        account_name="Forskning og utvikling, ervervet",
        current_profile=AccountProfile(
            account_no="1000",
            a07_code="fastloenn",
            source="manual",
            confidence=1.0,
        ),
    )

    assert issue == "Anleggsmiddel-/immateriell konto har lagret lønnsklassifisering."


def test_suspicious_saved_payroll_profile_issue_flags_non_payroll_operating_expenses() -> None:
    leie_issue = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="6300",
        account_name="Leie lokale",
        current_profile=AccountProfile(
            account_no="6300",
            a07_code="tilskuddOgPremieTilPensjon",
            source="manual",
            confidence=1.0,
        ),
    )
    renhold_issue = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="6360",
        account_name="Renhold",
        current_profile=AccountProfile(
            account_no="6360",
            a07_code="styrehonorarOgGodtgjoerelseVerv",
            source="manual",
            confidence=1.0,
        ),
    )
    regnskap_issue = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="6705",
        account_name="Honorar regnskap",
        current_profile=AccountProfile(
            account_no="6705",
            a07_code="styrehonorarOgGodtgjoerelseVerv",
            source="manual",
            confidence=1.0,
        ),
    )

    assert leie_issue is not None
    assert renhold_issue is not None
    assert regnskap_issue is not None


def test_suspicious_saved_payroll_profile_issue_flags_saved_code_that_mismatches_standard_interval() -> None:
    issue = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="5330",
        account_name="Godtgjorelse til styre- og bedriftsforsamling",
        current_profile=AccountProfile(
            account_no="5330",
            a07_code="tilskuddOgPremieTilPensjon",
            source="manual",
            confidence=1.0,
        ),
    )

    assert issue is not None
    assert "standardintervallet" in issue


def test_suggest_a07_code_blocks_non_payroll_operating_expense_accounts() -> None:
    leie_suggestion = payroll_classification.suggest_a07_code(
        account_no="6300",
        account_name="Leie lokale",
        movement=624825.0,
    )
    regnskap_suggestion = payroll_classification.suggest_a07_code(
        account_no="6705",
        account_name="Honorar regnskap",
        movement=564737.5,
    )

    assert leie_suggestion is None
    assert regnskap_suggestion is None or regnskap_suggestion.value != "styrehonorarOgGodtgjoerelseVerv"


def test_suggest_a07_code_blocks_generic_accrual_without_strong_payroll_signal() -> None:
    suggestion = payroll_classification.suggest_a07_code(
        account_no="2960",
        account_name="Annen påløpt kostnad",
        movement=-295473.0,
    )

    assert suggestion is None


def test_suggest_a07_code_blocks_balance_sheet_accounts_even_with_payroll_tokens() -> None:
    feriepenger = payroll_classification.suggest_a07_code(
        account_no="2940",
        account_name="Skyldig feriepenger",
        movement=-4207.0,
    )
    aga = payroll_classification.suggest_a07_code(
        account_no="2770",
        account_name="Skyldig arbeidsgiveravgift",
        movement=1597.0,
    )
    forskuddstrekk = payroll_classification.suggest_a07_code(
        account_no="2600",
        account_name="Forskuddstrekk",
        movement=-109358.0,
    )

    assert feriepenger is None
    assert aga is None
    assert forskuddstrekk is None


def test_suggest_a07_code_suggests_feriepenger_for_cost_account_5020() -> None:
    suggestion = payroll_classification.suggest_a07_code(
        account_no="5020",
        account_name="Feriepenger",
        movement=866816.10,
    )

    assert suggestion is not None
    assert suggestion.value == "feriepenger"


def test_suggest_a07_code_suggests_feriepenger_for_periodisering_5096() -> None:
    suggestion = payroll_classification.suggest_a07_code(
        account_no="5096",
        account_name="Periodisering av feriepenger",
        movement=6861.97,
    )

    assert suggestion is not None
    assert suggestion.value == "feriepenger"


def test_classify_payroll_account_keeps_direct_rf1022_for_balance_accounts_without_a07_suggestion() -> None:
    catalog = payroll_classification.AccountClassificationCatalog.from_dict(
        {
            "groups": [
                {
                    "id": "100_loenn_ol",
                    "label": "Post 100 Lønn o.l.",
                    "active": True,
                    "sort_order": 10,
                    "applies_to": ["kontrolloppstilling"],
                    "aliases": ["feriepenger"],
                }
            ],
            "tags": [],
        }
    )

    result = payroll_classification.classify_payroll_account(
        account_no="2940",
        account_name="Skyldig feriepenger",
        movement=-4207.0,
        catalog=catalog,
    )

    assert "a07_code" not in result.suggestions
    assert result.suggestions["control_group"].value == "100_loenn_ol"
    assert result.payroll_relevant is True


def test_classify_payroll_account_keeps_direct_refusjon_group_for_balance_account_without_a07_suggestion() -> None:
    catalog = payroll_classification.AccountClassificationCatalog.from_dict(
        {
            "groups": [
                {
                    "id": "100_refusjon",
                    "label": "Post 100 Refusjon",
                    "active": True,
                    "sort_order": 10,
                    "applies_to": ["kontrolloppstilling"],
                    "aliases": ["refusjon", "sykepengerrefusjon"],
                }
            ],
            "tags": [],
        }
    )

    result = payroll_classification.classify_payroll_account(
        account_no="1755",
        account_name="Periodisering sykepenger refusjon",
        movement=0.0,
        catalog=catalog,
    )

    assert "a07_code" not in result.suggestions
    assert result.suggestions["control_group"].value == "100_refusjon"
    assert result.payroll_relevant is True


def test_suspicious_saved_payroll_profile_issue_flags_generic_accrual_and_liability_accounts() -> None:
    generic_accrual = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="2960",
        account_name="Annen påløpt kostnad",
        current_profile=AccountProfile(
            account_no="2960",
            a07_code="fastloenn",
            source="manual",
            confidence=1.0,
        ),
    )
    supplier_liability = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="2400",
        account_name="Leverandørgjeld",
        current_profile=AccountProfile(
            account_no="2400",
            a07_code="fastloenn",
            source="manual",
            confidence=1.0,
        ),
    )

    assert generic_accrual is not None
    assert supplier_liability is not None


def test_suspicious_saved_payroll_profile_issue_does_not_flag_5020_feriepenger_when_rulebook_allows_it() -> None:
    issue = payroll_classification.suspicious_saved_payroll_profile_issue(
        account_no="5020",
        account_name="Feriepenger",
        current_profile=AccountProfile(
            account_no="5020",
            a07_code="feriepenger",
            source="manual",
            confidence=1.0,
        ),
    )

    assert issue is None


def test_normalized_phrase_match_blocks_midword_hits_but_keeps_word_affixes() -> None:
    assert payroll_classification._normalized_phrase_match("forskning og utvikling ervervet", "verv") is False
    assert payroll_classification._normalized_phrase_match("mobiltelefon", "telefon") is True
    assert payroll_classification._normalized_phrase_match("pensjonskostnader", "pensjon") is True


def test_classify_payroll_account_adds_direct_rf1022_from_catalog_alias(tmp_path) -> None:
    rulebook_path = tmp_path / "rulebook.json"
    rulebook_path.write_text(
        """
        {
          "rules": {
            "tilskuddOgPremieTilPensjon": {
              "label": "Pensjon",
              "keywords": ["pensjon", "otp"]
            }
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    catalog = payroll_classification.AccountClassificationCatalog.from_dict(
        {
            "groups": [
                {
                    "id": "112_pensjon",
                    "label": "Post 112 Pensjon",
                    "active": True,
                    "sort_order": 10,
                    "applies_to": ["kontrolloppstilling"],
                    "aliases": ["pensjon", "otp"],
                }
            ],
            "tags": [],
        }
    )

    result = payroll_classification.classify_payroll_account(
        account_no="5940",
        account_name="Pensjonskostnad OTP",
        movement=551590.0,
        usage=payroll_classification.AccountUsageFeatures(
            posting_count=12,
            unique_vouchers=12,
            active_months=12,
            monthly_regularity=1.0,
            repeat_amount_ratio=0.8,
            top_text_tokens=("otp",),
        ),
        catalog=catalog,
        rulebook_path=str(rulebook_path),
    )

    assert result.suggestions["a07_code"].value == "tilskuddOgPremieTilPensjon"
    assert result.suggestions["control_group"].value == "112_pensjon"
    assert str(result.suggestions["control_group"].reason).startswith("Direkte RF-1022:")
    assert "navn/alias: pensjon" in str(result.suggestions["control_group"].reason)


def test_classify_payroll_account_merges_direct_flag_with_a07_standard_tags(tmp_path) -> None:
    rulebook_path = tmp_path / "rulebook.json"
    rulebook_path.write_text(
        """
        {
          "rules": {
            "fastloenn": {
              "label": "Fastlønn",
              "keywords": ["lønn", "lonn"]
            }
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    catalog = payroll_classification.AccountClassificationCatalog.from_dict(
        {
            "groups": [],
            "tags": [
                {
                    "id": "finansskatt_pliktig",
                    "label": "Finansskatt-pliktig",
                    "active": True,
                    "sort_order": 10,
                    "applies_to": ["kontrolloppstilling"],
                    "aliases": ["finansskatt"],
                }
            ],
        }
    )

    result = payroll_classification.classify_payroll_account(
        account_no="5990",
        account_name="Lønn finansskatt",
        movement=100000.0,
        catalog=catalog,
        rulebook_path=str(rulebook_path),
    )

    assert result.suggestions["a07_code"].value == "fastloenn"
    assert set(result.suggestions["control_tags"].value or ()) >= {
        "finansskatt_pliktig",
        "opplysningspliktig",
        "aga_pliktig",
        "feriepengergrunnlag",
    }
    assert str(result.suggestions["control_tags"].reason).startswith("Direkte Flagg:")
    assert "navn/alias: finansskatt" in str(result.suggestions["control_tags"].reason)


def test_rf1022_tag_totals_sums_selected_payroll_flags() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Endring": 100.0},
            {"Konto": "5210", "Endring": 20.0},
            {"Konto": "5940", "Endring": 10.0},
        ]
    )
    document = AccountProfileDocument(
        client="Test",
        year=2025,
        profiles={
            "5000": AccountProfile(account_no="5000", control_tags=("opplysningspliktig", "aga_pliktig")),
            "5210": AccountProfile(account_no="5210", control_tags=("opplysningspliktig", "aga_pliktig", "naturalytelse")),
            "5940": AccountProfile(account_no="5940", control_tags=("pensjon",)),
        },
    )

    out = payroll_classification.rf1022_tag_totals(gl_df, document)

    assert out["opplysningspliktig"] == 120.0
    assert out["aga_pliktig"] == 120.0
    assert out["finansskatt_pliktig"] == 0.0


def test_strict_auto_profile_updates_only_keeps_strict_fields() -> None:
    result = payroll_classification.PayrollSuggestionResult(
        suggestions={
            "a07_code": payroll_classification.AccountProfileSuggestion(
                field_name="a07_code",
                value="fastloenn",
                source="heuristic",
                confidence=0.95,
                reason="Regelbok: konto-intervall",
            ),
            "control_group": payroll_classification.AccountProfileSuggestion(
                field_name="control_group",
                value="100_loenn_ol",
                source="heuristic",
                confidence=0.95,
                reason="Regelbok: konto-intervall",
            ),
            "control_tags": payroll_classification.AccountProfileSuggestion(
                field_name="control_tags",
                value=("opplysningspliktig",),
                source="heuristic",
                confidence=0.6,
                reason="Heuristisk treff",
            ),
        },
        payroll_relevant=True,
        payroll_status="Forslag",
    )

    out = payroll_classification.strict_auto_profile_updates(result)

    assert out == {
        "a07_code": "fastloenn",
        "control_group": "100_loenn_ol",
    }


def _rf1022_lonn_catalog_with_aga_exclude() -> "payroll_classification.AccountClassificationCatalog":
    return payroll_classification.AccountClassificationCatalog.from_dict(
        {
            "groups": [
                {
                    "id": "100_loenn_ol",
                    "label": "Post 100 Lønn o.l.",
                    "active": True,
                    "sort_order": 10,
                    "applies_to": ["kontrolloppstilling"],
                    "aliases": ["lønn", "lonn", "fastlønn", "timelønn"],
                    "exclude_aliases": ["aga", "arbeidsgiveravgift"],
                }
            ],
            "tags": [],
        }
    )


def test_exclude_aliases_block_direct_rf1022_hit_for_aga_account_5422() -> None:
    catalog = _rf1022_lonn_catalog_with_aga_exclude()

    suggestion = payroll_classification._suggest_control_group_from_catalog(
        account_no="5422",
        account_name="AGA av påløpt lønn",
        catalog=catalog,
    )

    assert suggestion is None


def test_exclude_aliases_block_direct_rf1022_hit_for_aga_balance_account_2770() -> None:
    catalog = _rf1022_lonn_catalog_with_aga_exclude()

    suggestion = payroll_classification._suggest_control_group_from_catalog(
        account_no="2770",
        account_name="Skyldig arbeidsgiveravgift",
        catalog=catalog,
    )

    assert suggestion is None


def test_exclude_aliases_block_direct_rf1022_hit_for_aga_balance_account_2785() -> None:
    catalog = _rf1022_lonn_catalog_with_aga_exclude()

    suggestion = payroll_classification._suggest_control_group_from_catalog(
        account_no="2785",
        account_name="Påløpt arbeidsgiveravgift av feriepenger",
        catalog=catalog,
    )

    assert suggestion is None


def test_exclude_aliases_still_allow_hit_for_regular_lonn_account() -> None:
    catalog = _rf1022_lonn_catalog_with_aga_exclude()

    suggestion = payroll_classification._suggest_control_group_from_catalog(
        account_no="5000",
        account_name="Fastlønn til ansatte",
        catalog=catalog,
    )

    assert suggestion is not None
    assert suggestion.value == "100_loenn_ol"


def test_catalog_entry_roundtrip_preserves_exclude_aliases() -> None:
    entry = payroll_classification.AccountClassificationCatalogEntry.from_dict(
        {
            "id": "100_loenn_ol",
            "label": "Post 100 Lønn o.l.",
            "aliases": ["lønn", "fastlønn"],
            "exclude_aliases": ["aga", "arbeidsgiveravgift"],
        }
    )

    assert entry.exclude_aliases == ("aga", "arbeidsgiveravgift")
    assert entry.to_dict()["exclude_aliases"] == ["aga", "arbeidsgiveravgift"]


def test_detect_rf1022_exclude_blocks_reports_blocked_group_for_aga_lonn_account() -> None:
    catalog = _rf1022_lonn_catalog_with_aga_exclude()

    blocks = payroll_classification.detect_rf1022_exclude_blocks(
        account_no="5422",
        account_name="AGA av påløpt lønn",
        catalog=catalog,
    )

    assert blocks == [("Post 100 Lønn o.l.", "aga")]


def test_detect_rf1022_exclude_blocks_returns_empty_when_no_positive_match() -> None:
    catalog = _rf1022_lonn_catalog_with_aga_exclude()

    blocks = payroll_classification.detect_rf1022_exclude_blocks(
        account_no="1500",
        account_name="Kundefordringer",
        catalog=catalog,
    )

    assert blocks == []


def test_detect_rf1022_exclude_blocks_uses_default_catalog_for_aga_account_5422() -> None:
    catalog = load_account_classification_catalog()

    blocks = payroll_classification.detect_rf1022_exclude_blocks(
        account_no="5422",
        account_name="AGA av påløpt lønn",
        catalog=catalog,
    )

    labels = {label for label, _ in blocks}
    assert "Post 100 Lønn o.l." in labels


def test_exclude_aliases_block_usage_signal_hit() -> None:
    catalog = _rf1022_lonn_catalog_with_aga_exclude()

    suggestion = payroll_classification._suggest_control_group_from_catalog(
        account_no="5999",
        account_name="Diverse personalkostnad",
        usage=payroll_classification.AccountUsageFeatures(
            posting_count=12,
            unique_vouchers=12,
            active_months=12,
            monthly_regularity=1.0,
            repeat_amount_ratio=0.8,
            top_text_tokens=("lønn", "aga"),
        ),
        catalog=catalog,
    )

    assert suggestion is None

from __future__ import annotations

import pandas as pd

from account_profile import AccountProfile, AccountProfileDocument
from account_profile_catalog import load_account_classification_catalog
import payroll_classification

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


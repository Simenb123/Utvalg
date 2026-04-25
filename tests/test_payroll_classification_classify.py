from __future__ import annotations

import pandas as pd

from account_profile import AccountProfile, AccountProfileDocument
from account_profile_catalog import load_account_classification_catalog
import payroll_classification

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

def test_classify_payroll_account_does_not_assign_rf1022_directly_without_a07_suggestion() -> None:
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
    assert "control_group" not in result.suggestions
    assert result.payroll_relevant is True

def test_classify_payroll_account_does_not_assign_refusjon_group_without_a07_suggestion() -> None:
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
    assert "control_group" not in result.suggestions
    assert result.payroll_relevant is True

def test_classify_payroll_account_derives_rf1022_from_a07_mapping(tmp_path) -> None:
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
    assert not str(result.suggestions["control_group"].reason).startswith("Direkte RF-1022:")
    assert "Navn/alias: Pensjon" in str(result.suggestions["control_group"].reason)

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


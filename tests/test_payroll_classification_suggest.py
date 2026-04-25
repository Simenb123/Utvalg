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


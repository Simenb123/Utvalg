from __future__ import annotations

import pandas as pd

from account_profile import AccountProfile, AccountProfileDocument
from account_profile_catalog import load_account_classification_catalog
import payroll_classification

def test_default_catalog_contains_full_payroll_group_and_tag_set() -> None:
    catalog = load_account_classification_catalog()

    assert {entry.id for entry in payroll_classification._payroll_group_entries(catalog)} == set(
        payroll_classification.PAYROLL_GROUP_IDS
    )
    assert {entry.id for entry in payroll_classification._payroll_tag_entries(catalog)} == set(
        payroll_classification.PAYROLL_TAG_IDS
    )

def test_default_catalog_aliases_support_direct_payroll_tag_suggestions_only() -> None:
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

    assert group_suggestion is None

    assert tag_suggestion is not None
    assert "styrehonorar" in tuple(tag_suggestion.value or ())
    assert "navn/alias: Styrehonorar" in str(tag_suggestion.reason)

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

def test_default_catalog_no_longer_provides_rf1022_alias_blocks() -> None:
    catalog = load_account_classification_catalog()

    blocks = payroll_classification.detect_rf1022_exclude_blocks(
        account_no="5422",
        account_name="AGA av påløpt lønn",
        catalog=catalog,
    )

    assert blocks == []

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


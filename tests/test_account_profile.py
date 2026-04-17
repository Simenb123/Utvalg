from __future__ import annotations

from pathlib import Path

import pytest

from account_profile import (
    AccountProfile,
    AccountProfileDocument,
    AccountProfileStore,
    normalize_profile_year,
)


def test_normalize_profile_year_accepts_string_year() -> None:
    assert normalize_profile_year("2025") == 2025
    assert normalize_profile_year(" 2025 ") == 2025
    assert normalize_profile_year("ikke-aar") is None


def test_account_profile_document_normalizes_string_year() -> None:
    document = AccountProfileDocument(client="Testklient", year="2025")

    assert document.year == 2025


def test_account_profile_store_load_accepts_string_year(tmp_path: Path) -> None:
    path = tmp_path / "account_profiles.json"
    store = AccountProfileStore(path)
    store.save(AccountProfileDocument(client="Testklient", year=2025))

    loaded = store.load(client="Testklient", year="2025")

    assert loaded.year == 2025


def test_account_profile_store_load_rejects_wrong_normalized_year(tmp_path: Path) -> None:
    path = tmp_path / "account_profiles.json"
    store = AccountProfileStore(path)
    store.save(AccountProfileDocument(client="Testklient", year=2025))

    with pytest.raises(ValueError, match="Expected account profile year '2024', got '2025'"):
        store.load(client="Testklient", year="2024")


def test_account_profile_serializes_detail_class_id() -> None:
    profile = AccountProfile(account_no="2740", detail_class_id="skyldig_mva")
    payload = profile.to_dict()

    assert payload["detail_class_id"] == "skyldig_mva"
    assert AccountProfile.from_dict(payload).detail_class_id == "skyldig_mva"


def test_account_profile_serializes_owned_company_orgnr() -> None:
    profile = AccountProfile(account_no="1380", owned_company_orgnr="123 456 789")
    payload = profile.to_dict()

    assert payload["owned_company_orgnr"] == "123456789"
    assert AccountProfile.from_dict(payload).owned_company_orgnr == "123456789"


def test_account_profile_orgnr_strips_non_digits_and_blank_becomes_none() -> None:
    profile = AccountProfile(account_no="1380", owned_company_orgnr="  NO-123 456 789 ")
    assert profile.owned_company_orgnr == "123456789"

    cleared = AccountProfile(account_no="1380", owned_company_orgnr="   ")
    assert cleared.owned_company_orgnr is None


def test_account_profile_backwards_compat_missing_fields() -> None:
    legacy_payload = {
        "account_no": "2740",
        "account_name": "Utgaaende MVA",
        "a07_code": None,
        "control_group": None,
        "control_tags": [],
        "source": "legacy",
    }
    profile = AccountProfile.from_dict(legacy_payload)

    assert profile.detail_class_id is None
    assert profile.owned_company_orgnr is None


def test_account_profile_with_updates_sets_new_fields() -> None:
    base = AccountProfile(account_no="2740")

    updated = base.with_updates(detail_class_id="skyldig_mva", owned_company_orgnr="987654321")

    assert updated.detail_class_id == "skyldig_mva"
    assert updated.owned_company_orgnr == "987654321"
    # Unrelated fields remain untouched
    assert updated.a07_code is None
    assert updated.control_group is None

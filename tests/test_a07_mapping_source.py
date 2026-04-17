from __future__ import annotations

import json

from account_profile import AccountProfile, AccountProfileDocument
from a07_feature import mapping_source


def _profile_path(tmp_path, client_slug="Air_Management_AS", year="2025"):
    return (
        tmp_path
        / "data"
        / "konto_klassifisering_profiles"
        / client_slug
        / year
        / "account_profiles.json"
    )


def _seed_profile_file(tmp_path, profiles_payload, *, client="Air Management AS", year=2025):
    path = _profile_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "client": client,
        "year": year,
        "profiles": profiles_payload,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_load_current_document_returns_empty_when_json_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")

    document = mapping_source.load_current_document("Air Management AS", year=2025)

    assert isinstance(document, AccountProfileDocument)
    assert document.client == "Air Management AS"
    assert document.year == 2025
    assert document.profiles == {}


def test_load_current_document_reads_existing_json_and_preserves_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")
    _seed_profile_file(
        tmp_path,
        {
            "5000": {
                "account_no": "5000",
                "account_name": "Loenn fast",
                "a07_code": "fastloenn",
                "control_group": "Loenn",
                "control_tags": ["hovedloenn"],
                "source": "manual",
                "confidence": 1.0,
                "locked": True,
                "last_updated": "2025-01-01T00:00:00Z",
            }
        },
    )

    document = mapping_source.load_current_document("Air Management AS", year=2025)

    assert document.client == "Air Management AS"
    assert document.year == 2025
    profile = document.get("5000")
    assert profile is not None
    assert profile.account_name == "Loenn fast"
    assert profile.a07_code == "fastloenn"
    assert profile.control_group == "Loenn"
    assert profile.control_tags == ("hovedloenn",)
    assert profile.locked is True


def test_mapping_from_document_returns_pure_account_to_a07_code():
    document = AccountProfileDocument(
        client="Air Management AS",
        year=2025,
        profiles={
            "5000": AccountProfile(account_no="5000", a07_code="fastloenn"),
            # suspicious by name/code combo — adapter MUST NOT filter
            "6300": AccountProfile(
                account_no="6300",
                account_name="Leie lokale",
                a07_code="tilskuddOgPremieTilPensjon",
            ),
            "5400": AccountProfile(account_no="5400"),  # no a07_code -> dropped
        },
    )

    mapping = mapping_source.mapping_from_document(document)

    assert mapping == {
        "5000": "fastloenn",
        "6300": "tilskuddOgPremieTilPensjon",
    }


def test_document_with_updated_mapping_preserves_other_profile_fields():
    original = AccountProfileDocument(
        client="Air Management AS",
        year=2025,
        profiles={
            "5000": AccountProfile(
                account_no="5000",
                account_name="Loenn fast",
                a07_code="fastloenn",
                control_group="Loenn",
                control_tags=("hovedloenn",),
                source="manual",
                confidence=1.0,
                locked=True,
            )
        },
    )

    updated = mapping_source.document_with_updated_mapping(
        original,
        {"5000": "timeloenn"},
    )

    profile = updated.get("5000")
    assert profile is not None
    assert profile.a07_code == "timeloenn"
    assert profile.account_name == "Loenn fast"
    assert profile.control_group == "Loenn"
    assert profile.control_tags == ("hovedloenn",)
    assert profile.locked is True


def test_save_current_document_roundtrip_is_stable(monkeypatch, tmp_path):
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")
    document = AccountProfileDocument(
        client="Air Management AS",
        year=2025,
        profiles={
            "5000": AccountProfile(
                account_no="5000",
                account_name="Loenn fast",
                a07_code="fastloenn",
                control_group="Loenn",
                control_tags=("hovedloenn",),
                source="manual",
                confidence=1.0,
                locked=False,
            ),
            "5400": AccountProfile(
                account_no="5400",
                account_name="Arbeidsgiveravgift",
                a07_code="aga",
                control_group="AGA",
                source="manual",
                confidence=1.0,
            ),
        },
    )

    saved_path = mapping_source.save_current_document("Air Management AS", 2025, document)
    assert saved_path.exists()

    reloaded = mapping_source.load_current_document("Air Management AS", year=2025)

    assert reloaded.client == document.client
    assert reloaded.year == document.year
    assert set(reloaded.profiles) == {"5000", "5400"}
    for account_no in ("5000", "5400"):
        original = document.get(account_no)
        round_tripped = reloaded.get(account_no)
        assert round_tripped is not None and original is not None
        assert round_tripped.a07_code == original.a07_code
        assert round_tripped.account_name == original.account_name
        assert round_tripped.control_group == original.control_group
        assert round_tripped.control_tags == original.control_tags
        assert round_tripped.locked == original.locked
        assert round_tripped.source == original.source


def test_load_nearest_prior_document_returns_none_when_no_priors(monkeypatch, tmp_path):
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")

    doc, year = mapping_source.load_nearest_prior_document("Air Management AS", 2025)

    assert doc is None
    assert year is None


def test_load_nearest_prior_document_picks_highest_year_below_current(monkeypatch, tmp_path):
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")
    for y, code in ((2022, "fastloenn"), (2023, "timeloenn"), (2024, "bonus")):
        _seed_profile_file(
            tmp_path,
            {"5000": {"account_no": "5000", "a07_code": code}},
            client="Air Management AS",
            year=y,
        )
        # shift path to correct year
    # overwrite path resolution — above helper always writes to 2025 path; rewrite manually
    import shutil
    base = tmp_path / "data" / "konto_klassifisering_profiles" / "Air_Management_AS"
    # Clean bad seed (year=2025 directory) if created
    if (base / "2025").exists():
        shutil.rmtree(base / "2025")

    def _write(year, code):
        d = base / str(year)
        d.mkdir(parents=True, exist_ok=True)
        (d / "account_profiles.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "client": "Air Management AS",
                    "year": year,
                    "profiles": {"5000": {"account_no": "5000", "a07_code": code}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    _write(2022, "fastloenn")
    _write(2023, "timeloenn")
    _write(2024, "bonus")

    doc, year = mapping_source.load_nearest_prior_document("Air Management AS", 2025)

    assert year == 2024
    assert doc is not None
    assert mapping_source.mapping_from_document(doc) == {"5000": "bonus"}


def test_load_nearest_prior_document_skips_corrupt_doc_and_falls_back_to_older(monkeypatch, tmp_path):
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")
    base = tmp_path / "data" / "konto_klassifisering_profiles" / "Air_Management_AS"

    # 2024: corrupt JSON — should be skipped
    d24 = base / "2024"
    d24.mkdir(parents=True, exist_ok=True)
    (d24 / "account_profiles.json").write_text("{not valid json", encoding="utf-8")

    # 2022: valid doc — should be chosen
    d22 = base / "2022"
    d22.mkdir(parents=True, exist_ok=True)
    (d22 / "account_profiles.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "client": "Air Management AS",
                "year": 2022,
                "profiles": {"5000": {"account_no": "5000", "a07_code": "olddoc"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    doc, year = mapping_source.load_nearest_prior_document("Air Management AS", 2025)

    assert year == 2022
    assert doc is not None
    assert mapping_source.mapping_from_document(doc) == {"5000": "olddoc"}


def test_load_nearest_prior_document_returns_none_when_all_candidates_corrupt(monkeypatch, tmp_path):
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")
    base = tmp_path / "data" / "konto_klassifisering_profiles" / "Air_Management_AS"

    for y in (2022, 2023, 2024):
        d = base / str(y)
        d.mkdir(parents=True, exist_ok=True)
        (d / "account_profiles.json").write_text("garbage", encoding="utf-8")

    doc, year = mapping_source.load_nearest_prior_document("Air Management AS", 2025)

    assert doc is None
    assert year is None


def test_load_nearest_prior_document_ignores_current_and_future(monkeypatch, tmp_path):
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")
    base = tmp_path / "data" / "konto_klassifisering_profiles" / "Air_Management_AS"

    def _write(year):
        d = base / str(year)
        d.mkdir(parents=True, exist_ok=True)
        (d / "account_profiles.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "client": "Air Management AS",
                    "year": year,
                    "profiles": {"5000": {"account_no": "5000", "a07_code": f"code{year}"}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    _write(2023)
    _write(2025)
    _write(2026)

    doc, year = mapping_source.load_nearest_prior_document("Air Management AS", 2025)

    assert year == 2023
    assert doc is not None


def test_store_path_for_testing_matches_legacy_layout(tmp_path):
    path = mapping_source._store_path_for_testing(
        tmp_path / "data" / "konto_klassifisering_profiles",
        client="Air Management AS",
        year=2025,
    )

    assert path == _profile_path(tmp_path)

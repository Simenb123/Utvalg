from __future__ import annotations

import json

from a07_feature import storage


def _profile_store_path(tmp_path):
    return (
        tmp_path
        / "data"
        / "konto_klassifisering_profiles"
        / "Air_Management_AS"
        / "2025"
        / "account_profiles.json"
    )


def test_save_mapping_writes_json_only_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(storage.app_paths, "data_dir", lambda: tmp_path / "data")
    path = tmp_path / "clients" / "air" / "years" / "2025" / "a07" / "a07_mapping.json"

    saved = storage.save_mapping(path, {"5000": "fastloenn"}, client="Air Management AS", year="2025")

    assert saved.exists()
    assert json.loads(saved.read_text(encoding="utf-8")) == {"5000": "fastloenn"}
    assert not _profile_store_path(tmp_path).exists()


def test_save_mapping_can_shadow_to_profile_store_when_requested(monkeypatch, tmp_path):
    monkeypatch.setattr(storage.app_paths, "data_dir", lambda: tmp_path / "data")
    path = tmp_path / "clients" / "air" / "years" / "2025" / "a07" / "a07_mapping.json"

    storage.save_mapping(
        path,
        {"5000": "fastloenn"},
        client="Air Management AS",
        year="2025",
        shadow_to_profiles=True,
    )

    payload = json.loads(_profile_store_path(tmp_path).read_text(encoding="utf-8"))
    assert payload["profiles"]["5000"]["a07_code"] == "fastloenn"


def test_load_mapping_prefers_json_when_available_even_if_profiles_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(storage.app_paths, "data_dir", lambda: tmp_path / "data")
    path = tmp_path / "clients" / "air" / "years" / "2025" / "a07" / "a07_mapping.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"5000": "jsonkode"}', encoding="utf-8")

    storage.save_mapping(
        path,
        {"5000": "fastloenn", "5400": "aga"},
        client="Air Management AS",
        year="2025",
        shadow_to_profiles=True,
    )
    path.write_text('{"5000": "jsonkode"}', encoding="utf-8")

    loaded = storage.load_mapping(path, client="Air Management AS", year="2025")

    assert loaded == {"5000": "jsonkode"}


def test_load_mapping_uses_profile_seed_only_when_json_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(storage.app_paths, "data_dir", lambda: tmp_path / "data")
    path = tmp_path / "clients" / "air" / "years" / "2025" / "a07" / "a07_mapping.json"

    storage.save_mapping(
        path,
        {"5000": "fastloenn", "5400": "aga"},
        client="Air Management AS",
        year="2025",
        shadow_to_profiles=True,
    )
    path.unlink()

    loaded = storage.load_mapping(path, client="Air Management AS", year="2025")

    assert loaded["5000"] == "fastloenn"
    assert loaded["5400"] == "aga"


def test_load_mapping_profile_seed_filters_suspicious_saved_profile_codes(monkeypatch, tmp_path):
    monkeypatch.setattr(storage.app_paths, "data_dir", lambda: tmp_path / "data")
    path = tmp_path / "clients" / "air" / "years" / "2025" / "a07" / "a07_mapping.json"

    storage.save_mapping(
        path,
        {"6300": "tilskuddOgPremieTilPensjon", "5945": "tilskuddOgPremieTilPensjon"},
        client="Air Management AS",
        year="2025",
        shadow_to_profiles=True,
    )
    path.unlink()

    profile_path = _profile_store_path(tmp_path)
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["profiles"]["6300"]["account_name"] = "Leie lokale"
    payload["profiles"]["5945"]["account_name"] = "Pensjonsforsikring for ansatte"
    profile_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    loaded = storage.load_mapping(path, client="Air Management AS", year="2025")

    assert "6300" not in loaded
    assert loaded["5945"] == "tilskuddOgPremieTilPensjon"


def test_load_mapping_profile_seed_filters_saved_codes_that_conflict_with_standard_a07_interval(monkeypatch, tmp_path):
    monkeypatch.setattr(storage.app_paths, "data_dir", lambda: tmp_path / "data")
    path = tmp_path / "clients" / "air" / "years" / "2025" / "a07" / "a07_mapping.json"

    storage.save_mapping(
        path,
        {"5330": "tilskuddOgPremieTilPensjon"},
        client="Air Management AS",
        year="2025",
        shadow_to_profiles=True,
    )
    path.unlink()

    profile_path = _profile_store_path(tmp_path)
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["profiles"]["5330"]["account_name"] = "Godtgjorelse til styre- og bedriftsforsamling"
    profile_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    loaded = storage.load_mapping(path, client="Air Management AS", year="2025")

    assert "5330" not in loaded

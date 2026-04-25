from __future__ import annotations

from .shared import *  # noqa: F401,F403

def test_find_previous_year_mapping_path_returns_latest_prior(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    mapping_2023 = tmp_path / "clients" / "air" / "years" / "2023" / "a07" / "a07_mapping.json"
    mapping_2023.parent.mkdir(parents=True, exist_ok=True)
    mapping_2023.write_text('{"5000": "fastloenn"}', encoding="utf-8")

    mapping_2024 = tmp_path / "clients" / "air" / "years" / "2024" / "a07" / "a07_mapping.json"
    mapping_2024.parent.mkdir(parents=True, exist_ok=True)
    mapping_2024.write_text('{"5010": "bonus"}', encoding="utf-8")

    out_path, out_year = page_a07.find_previous_year_mapping_path("Air Management AS", "2025")

    assert out_path == mapping_2024
    assert out_year == "2024"

def test_load_previous_year_mapping_for_context_loads_latest_prior(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    mapping_2024 = tmp_path / "clients" / "air" / "years" / "2024" / "a07" / "a07_mapping.json"
    mapping_2024.parent.mkdir(parents=True, exist_ok=True)
    mapping_2024.write_text('{"5000": "fastloenn"}', encoding="utf-8")

    mapping, out_path, out_year = page_a07.load_previous_year_mapping_for_context("Air Management AS", "2025")

    assert mapping == {"5000": "fastloenn"}
    assert out_path == mapping_2024
    assert out_year == "2024"

def test_find_previous_year_context_finds_latest_prior_without_mapping_files(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    (tmp_path / "clients" / "air" / "years" / "2023").mkdir(parents=True, exist_ok=True)
    (tmp_path / "clients" / "air" / "years" / "2024").mkdir(parents=True, exist_ok=True)

    out_year = page_a07.find_previous_year_context("Air Management AS", "2025")

    assert out_year == "2024"

def test_load_previous_year_mapping_for_context_uses_profile_document_when_no_json(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)
    (tmp_path / "clients" / "air" / "years" / "2024").mkdir(parents=True, exist_ok=True)

    from a07_feature import mapping_source
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")
    _seed_prior_profile_document(
        tmp_path, client_slug="Air_Management_AS", year=2024, mapping={"5000": "fastloenn"}
    )

    mapping, out_path, out_year = page_a07.load_previous_year_mapping_for_context("Air Management AS", "2025")

    assert mapping == {"5000": "fastloenn"}
    assert out_path is None
    assert out_year == "2024"

def test_load_previous_year_mapping_for_context_document_wins_when_same_year_as_json(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    mapping_2024 = tmp_path / "clients" / "air" / "years" / "2024" / "a07" / "a07_mapping.json"
    mapping_2024.parent.mkdir(parents=True, exist_ok=True)
    mapping_2024.write_text('{"5000": "legacyloenn"}', encoding="utf-8")

    from a07_feature import mapping_source
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")
    _seed_prior_profile_document(
        tmp_path, client_slug="Air_Management_AS", year=2024, mapping={"5000": "docloenn"}
    )

    mapping, out_path, out_year = page_a07.load_previous_year_mapping_for_context("Air Management AS", "2025")

    assert mapping == {"5000": "docloenn"}
    assert out_path is None
    assert out_year == "2024"

def test_load_previous_year_mapping_for_context_corrupt_newer_doc_does_not_shadow_older_json(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    # 2023 legacy JSON â€” valid
    mapping_2023 = tmp_path / "clients" / "air" / "years" / "2023" / "a07" / "a07_mapping.json"
    mapping_2023.parent.mkdir(parents=True, exist_ok=True)
    mapping_2023.write_text('{"5000": "oldjson"}', encoding="utf-8")

    # 2024 profile doc â€” corrupt
    from a07_feature import mapping_source
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")
    corrupt_dir = tmp_path / "data" / "konto_klassifisering_profiles" / "Air_Management_AS" / "2024"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    (corrupt_dir / "account_profiles.json").write_text("{broken", encoding="utf-8")

    mapping, out_path, out_year = page_a07.load_previous_year_mapping_for_context("Air Management AS", "2025")

    assert mapping == {"5000": "oldjson"}
    assert out_path == mapping_2023
    assert out_year == "2023"

def test_load_previous_year_mapping_for_context_newer_json_beats_older_document(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    mapping_2024 = tmp_path / "clients" / "air" / "years" / "2024" / "a07" / "a07_mapping.json"
    mapping_2024.parent.mkdir(parents=True, exist_ok=True)
    mapping_2024.write_text('{"5000": "newjson"}', encoding="utf-8")

    from a07_feature import mapping_source
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")
    _seed_prior_profile_document(
        tmp_path, client_slug="Air_Management_AS", year=2022, mapping={"5000": "olddoc"}
    )

    mapping, out_path, out_year = page_a07.load_previous_year_mapping_for_context("Air Management AS", "2025")

    assert mapping == {"5000": "newjson"}
    assert out_path == mapping_2024
    assert out_year == "2024"


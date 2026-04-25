from __future__ import annotations

from .shared import *  # noqa: F401,F403

def test_get_a07_workspace_dir_uses_client_store_years_dir(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    out = page_a07.get_a07_workspace_dir("Air Management AS", "2025")

    assert out == years_dir / "a07"

def test_get_a07_workspace_dir_falls_back_to_namespaced_data_dir_when_client_store_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: (_ for _ in ()).throw(PermissionError("denied")))
    monkeypatch.setattr(page_a07.app_paths, "data_dir", lambda: tmp_path / "data")

    out = page_a07.get_a07_workspace_dir("Air Management AS", "2025")

    assert out == tmp_path / "data" / "a07" / "Air_Management_AS" / "2025"

def test_suggest_default_mapping_path_uses_client_year_workspace(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    out = page_a07.suggest_default_mapping_path(None, client="Air Management AS", year="2025")

    assert out == years_dir / "a07" / "a07_mapping.json"

def test_suggest_default_mapping_path_falls_back_to_a07_sibling_without_context(tmp_path) -> None:
    a07_path = tmp_path / "innrapportering.json"

    out = page_a07.suggest_default_mapping_path(a07_path)

    assert out == tmp_path / "innrapportering_mapping.json"

def test_resolve_autosave_mapping_path_prefers_existing_mapping_path(tmp_path) -> None:
    explicit = tmp_path / "manual_mapping.json"

    out = page_a07.resolve_autosave_mapping_path(
        explicit,
        a07_path=None,
        client="Air Management AS",
        year="2025",
    )

    assert out == explicit

def test_resolve_autosave_mapping_path_uses_client_workspace(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    out = page_a07.resolve_autosave_mapping_path(
        None,
        a07_path=None,
        client="Air Management AS",
        year="2025",
    )

    assert out == years_dir / "a07" / "a07_mapping.json"

def test_default_a07_source_path_uses_workspace_dir(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    out = page_a07.default_a07_source_path("Air Management AS", "2025")

    assert out == years_dir / "a07" / "a07_source.json"

def test_resolve_context_source_path_does_not_auto_read_legacy_global(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)
    monkeypatch.setattr(page_a07.app_paths, "data_dir", lambda: tmp_path / "data")

    legacy_path = tmp_path / "data" / "a07" / "a07_source.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text('{"demo": true}', encoding="utf-8")

    out = page_a07.resolve_context_source_path("Air Management AS", "2025")

    assert out is None

def test_resolve_context_mapping_path_does_not_auto_read_legacy_global(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)
    monkeypatch.setattr(page_a07.app_paths, "data_dir", lambda: tmp_path / "data")

    legacy_path = tmp_path / "data" / "a07" / "a07_mapping.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text('{"5000": "fastloenn"}', encoding="utf-8")

    out = page_a07.resolve_context_mapping_path(None, client="Air Management AS", year="2025")

    assert out == years_dir / "a07" / "a07_mapping.json"

def test_resolve_context_mapping_path_without_context_returns_none(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(page_a07.app_paths, "data_dir", lambda: tmp_path / "data")
    legacy_path = tmp_path / "data" / "a07" / "a07_mapping.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text('{"5000": "fastloenn"}', encoding="utf-8")

    out = page_a07.resolve_context_mapping_path(None, client=None, year=None)

    assert out is None

def test_copy_a07_source_to_workspace_copies_to_client_structure(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    src = tmp_path / "external.json"
    src.write_text('{"demo": true}', encoding="utf-8")

    out = page_a07.copy_a07_source_to_workspace(src, client="Air Management AS", year="2025")

    assert out == years_dir / "a07" / "a07_source.json"
    assert out.read_text(encoding="utf-8") == '{"demo": true}'

def test_build_default_group_name_prefers_labels_and_truncates() -> None:
    out = page_a07.build_default_group_name(
        ["trekkLoennForFerie", "fastloenn", "feriepenger", "aga"],
        code_names={
            "trekkLoennForFerie": "Trekk i loenn for ferie",
            "fastloenn": "Fastloenn",
            "feriepenger": "Feriepenger",
            "aga": "AGA",
        },
    )

    assert out == "Trekk i loenn for ferie + Fastloenn + Feriepenger + ..."


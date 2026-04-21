from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import a07_feature.control.data as a07_control_data
import a07_feature.page_a07_context_menu as a07_context_menu
import a07_feature.page_a07_constants as a07_constants
import a07_feature.page_a07_control_statement as page_a07_control_statement
import a07_feature.ui.canonical_layout as a07_canonical_layout
import classification_workspace
import page_a07
import ui_main
from account_profile import AccountProfile, AccountProfileDocument


def test_get_a07_workspace_dir_uses_client_store_years_dir(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    out = page_a07.get_a07_workspace_dir("Air Management AS", "2025")

    assert out == years_dir / "a07"


def test_get_a07_workspace_dir_falls_back_to_local_data_dir_when_client_store_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: (_ for _ in ()).throw(PermissionError("denied")))
    monkeypatch.setattr(page_a07.app_paths, "data_dir", lambda: tmp_path / "data")

    out = page_a07.get_a07_workspace_dir("Air Management AS", "2025")

    assert out == tmp_path / "data" / "a07"


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


def test_resolve_context_source_path_falls_back_to_legacy_global(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)
    monkeypatch.setattr(page_a07.app_paths, "data_dir", lambda: tmp_path / "data")

    legacy_path = tmp_path / "data" / "a07" / "a07_source.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text('{"demo": true}', encoding="utf-8")

    out = page_a07.resolve_context_source_path("Air Management AS", "2025")

    assert out == legacy_path


def test_resolve_rulebook_path_uses_global_rulebook(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(page_a07.app_paths, "data_dir", lambda: tmp_path / "data")

    global_rulebook = tmp_path / "data" / "a07" / "global_full_a07_rulebook.json"
    global_rulebook.parent.mkdir(parents=True, exist_ok=True)
    global_rulebook.write_text("{}", encoding="utf-8")

    out = page_a07.resolve_rulebook_path("Air Management AS", "2025")

    assert out == global_rulebook


def test_resolve_rulebook_path_bootstraps_bundled_default(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(page_a07.app_paths, "data_dir", lambda: tmp_path / "data")

    bundled = tmp_path / "bundled_rulebook.json"
    bundled.write_text('{"rules": {"fastloenn": {"code": "fastloenn"}}}', encoding="utf-8")
    monkeypatch.setattr(page_a07, "bundled_default_rulebook_path", lambda: bundled)

    out = page_a07.resolve_rulebook_path("Air Management AS", "2025")

    assert out == tmp_path / "data" / "a07" / "global_full_a07_rulebook.json"
    assert out.read_text(encoding="utf-8") == bundled.read_text(encoding="utf-8")


def test_resolve_rulebook_path_falls_back_to_bundled_when_storage_is_blocked(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(page_a07.app_paths, "data_dir", lambda: tmp_path / "data")

    bundled = tmp_path / "bundled_rulebook.json"
    bundled.write_text('{"rules": {"fastloenn": {"code": "fastloenn"}}}', encoding="utf-8")
    monkeypatch.setattr(page_a07, "bundled_default_rulebook_path", lambda: bundled)
    monkeypatch.setattr(
        page_a07._shared.Path,
        "mkdir",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )

    out = page_a07.resolve_rulebook_path("Air Management AS", "2025")

    assert out == bundled


def test_copy_rulebook_to_storage_uses_utvalg_data_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(page_a07.app_paths, "data_dir", lambda: tmp_path / "data")

    src = tmp_path / "external_rulebook.json"
    src.write_text('{"rules": {}}', encoding="utf-8")

    out = page_a07.copy_rulebook_to_storage(src)

    assert out == tmp_path / "data" / "a07" / "global_full_a07_rulebook.json"
    assert out.read_text(encoding="utf-8") == '{"rules": {}}'


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


def _seed_prior_profile_document(tmp_path, *, client_slug: str, year: int, mapping: dict[str, str]) -> Path:
    import json
    path = (
        tmp_path
        / "data"
        / "konto_klassifisering_profiles"
        / client_slug
        / str(year)
        / "account_profiles.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    profiles = {
        account_no: {"account_no": account_no, "a07_code": code}
        for account_no, code in mapping.items()
    }
    payload = {
        "schema_version": 1,
        "client": "Air Management AS",
        "year": year,
        "profiles": profiles,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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


def test_copy_a07_source_to_workspace_copies_to_client_structure(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    src = tmp_path / "external.json"
    src.write_text('{"demo": true}', encoding="utf-8")

    out = page_a07.copy_a07_source_to_workspace(src, client="Air Management AS", year="2025")

    assert out == years_dir / "a07" / "a07_source.json"
    assert out.read_text(encoding="utf-8") == '{"demo": true}'


def test_get_active_trial_balance_path_for_context_uses_active_version(monkeypatch, tmp_path) -> None:
    tb_path = tmp_path / "clients" / "air" / "years" / "2025" / "versions" / "sb.xlsx"
    monkeypatch.setattr(
        page_a07.client_store,
        "get_active_version",
        lambda client, year, dtype: SimpleNamespace(path=tb_path),
    )

    out = page_a07.get_active_trial_balance_path_for_context("Air Management AS", "2025")

    assert out == tb_path


def test_load_active_trial_balance_cached_falls_back_to_session_tb(monkeypatch) -> None:
    original_tb_df = getattr(page_a07.session, "tb_df", None)
    monkeypatch.setattr(
        page_a07.session,
        "tb_df",
        pd.DataFrame(
            [
                {"konto": "5000", "kontonavn": "Lonn", "ib": 0.0, "ub": 100.0, "netto": 100.0},
            ]
        ),
    )

    class DummyPage:
        def _get_cached_active_trial_balance_path(self, client, year, *, refresh=False):
            return None

        def _invalidate_active_tb_path_cache(self, client=None, year=None):
            return None

    try:
        gl_df, tb_path = page_a07.A07Page._load_active_trial_balance_cached(DummyPage(), "Air Management AS", "2025")
    finally:
        monkeypatch.setattr(page_a07.session, "tb_df", original_tb_df)

    assert tb_path is None
    assert gl_df.to_dict("records") == [
        {"Konto": "5000", "Navn": "Lonn", "IB": 0.0, "UB": 100.0, "Endring": 100.0, "Belop": 100.0}
    ]


def test_get_context_snapshot_tracks_workspace_and_tb(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    tb_path = years_dir / "versions" / "sb.xlsx"
    tb_path.parent.mkdir(parents=True, exist_ok=True)
    tb_path.write_text("demo", encoding="utf-8")
    monkeypatch.setattr(
        page_a07.client_store,
        "get_active_version",
        lambda client, year, dtype: SimpleNamespace(path=tb_path),
    )

    source_path = years_dir / "a07" / "a07_source.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text('{"demo": true}', encoding="utf-8")

    mapping_path = years_dir / "a07" / "a07_mapping.json"
    mapping_path.write_text('{"1000": "fastloenn"}', encoding="utf-8")

    out = page_a07.get_context_snapshot("Air Management AS", "2025")

    assert out[0][0] == str(tb_path)
    assert out[1][0] == str(source_path)
    assert out[2][0] == str(mapping_path)


def test_build_gl_picker_options_includes_account_name_and_amount() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "1920", "Navn": "Bank", "Endring": 1250.5},
            {"Konto": "5000", "Navn": "Lonn", "Endring": -50.0},
        ]
    )

    out = page_a07.build_gl_picker_options(gl_df)

    assert [option.key for option in out] == ["1920", "5000"]
    assert out[0].label.startswith("1920 | Bank | ")


def test_build_a07_picker_options_includes_code_name_and_amount() -> None:
    a07_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1000.0},
            {"Kode": "feriepenger", "Navn": "Feriepenger", "Belop": 250.25},
        ]
    )

    out = page_a07.build_a07_picker_options(a07_df)

    assert [option.key for option in out] == ["fastloenn", "feriepenger"]
    assert out[0].label.startswith("fastloenn | Fastloenn | ")


class _DummyVar:
    def __init__(self) -> None:
        self.value = None

    def set(self, value) -> None:
        self.value = value


def test_load_mapping_clicked_uses_default_path_for_profile_only_context(monkeypatch, tmp_path) -> None:
    default_path = tmp_path / "clients" / "air" / "years" / "2025" / "a07" / "a07_mapping.json"
    page = object.__new__(page_a07.A07Page)
    page.a07_path = None
    page.workspace = SimpleNamespace(mapping={}, groups={}, locks=set())
    page.mapping_path_var = _DummyVar()
    page.status_var = _DummyVar()
    page.mapping_path = None
    page.groups_path = None
    page.locks_path = None
    page._session_context = lambda _session: ("Air Management AS", "2025")

    calls = {"dialog": 0, "refresh": 0}

    monkeypatch.setattr(
        page_a07,
        "suggest_default_mapping_path",
        lambda a07_path, client=None, year=None: default_path,
    )
    monkeypatch.setattr(
        page,
        "_load_mapping_file_cached",
        lambda path, client=None, year=None: {"5000": "fastloenn"},
    )
    monkeypatch.setattr(page, "_refresh_core", lambda: calls.__setitem__("refresh", calls["refresh"] + 1))
    monkeypatch.setattr(page_a07, "default_a07_groups_path", lambda client, year: tmp_path / "groups.json")
    monkeypatch.setattr(page_a07, "load_a07_groups", lambda path: {"demo": "group"})
    monkeypatch.setattr(page_a07, "default_a07_locks_path", lambda client, year: tmp_path / "locks.json")
    monkeypatch.setattr(page_a07, "load_locks", lambda path: {"fastloenn"})
    monkeypatch.setattr(
        page_a07.filedialog,
        "askopenfilename",
        lambda **kwargs: calls.__setitem__("dialog", calls["dialog"] + 1) or "",
    )

    page_a07.A07Page._load_mapping_clicked(page)

    assert page.workspace.mapping == {"5000": "fastloenn"}
    assert page.mapping_path == default_path
    assert page.mapping_path_var.value == f"Mapping: {default_path}"
    assert page.status_var.value == f"Lastet mapping fra {default_path.name}."
    assert page.workspace.groups == {"demo": "group"}
    assert page.workspace.locks == {"fastloenn"}
    assert calls["dialog"] == 0
    assert calls["refresh"] == 1


def test_invalidate_active_tb_path_cache_clears_mapping_file_cache() -> None:
    dummy = SimpleNamespace(
        _active_tb_cache_key=lambda client, year: ("Air Management AS", "2025"),
        _active_tb_path_cache={("Air Management AS", "2025"): Path("tb.xlsx")},
        _mapping_file_cache={((None, None, None), "Air Management AS", "2025"): {"5000": "fastloenn"}},
        _previous_mapping_cache={("Air Management AS", "2025"): ({}, None, None)},
        _rulebook_path_cache={("Air Management AS", "2025"): Path("rulebook.json")},
    )

    page_a07.A07Page._invalidate_active_tb_path_cache(dummy, "Air Management AS", "2025")

    assert dummy._active_tb_path_cache == {}
    assert dummy._mapping_file_cache == {}
    assert dummy._previous_mapping_cache == {}
    assert dummy._rulebook_path_cache == {}


def test_load_a07_clicked_loads_json_and_triggers_refresh(monkeypatch, tmp_path) -> None:
    source_path = tmp_path / "input_a07.json"
    source_path.write_text(
        '{"inntekter":[{"loennsinntekt":{"type":"fastloenn","beskrivelse":"Fastloenn"},"beloep":1000}]}',
        encoding="utf-8",
    )
    stored_path = tmp_path / "workspace_a07.json"
    stored_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")

    page = object.__new__(page_a07.A07Page)
    page.workspace = SimpleNamespace(source_a07_df=None, a07_df=None)
    page.a07_path = None
    page.a07_path_var = _DummyVar()
    page.status_var = _DummyVar()
    page._a07_source_cache = {}
    page._session_context = lambda _session: ("Air Management AS", "2025")
    page._current_context_snapshot = lambda client, year: ("snapshot", client, year)

    calls = {"refresh_reason": None, "showerror": 0}

    monkeypatch.setattr(
        page_a07.filedialog,
        "askopenfilename",
        lambda **kwargs: str(source_path),
    )
    monkeypatch.setattr(page_a07, "get_a07_workspace_dir", lambda client, year: tmp_path)
    monkeypatch.setattr(
        page_a07,
        "copy_a07_source_to_workspace",
        lambda path, client=None, year=None: stored_path,
    )
    monkeypatch.setattr(
        page_a07.messagebox,
        "showerror",
        lambda *args, **kwargs: calls.__setitem__("showerror", calls["showerror"] + 1),
    )
    monkeypatch.setattr(
        page,
        "_refresh_core",
        lambda reason=None: calls.__setitem__("refresh_reason", reason),
    )

    page_a07.A07Page._load_a07_clicked(page)

    assert calls["showerror"] == 0
    assert calls["refresh_reason"] == "load_a07"
    assert page.a07_path == stored_path
    assert page.a07_path_var.value == f"A07: {stored_path}"
    assert page.status_var.value == f"Lastet A07 fra {source_path.name} og lagret kopi i klientmappen."
    assert isinstance(page.workspace.source_a07_df, pd.DataFrame)
    assert list(page.workspace.source_a07_df["Kode"]) == ["fastloenn"]
    assert list(page.workspace.a07_df["Kode"]) == ["fastloenn"]


def test_normalize_matcher_settings_and_build_suggest_config_use_defaults_and_overrides() -> None:
    normalized = page_a07.normalize_matcher_settings(
        {
            "tolerance_rel": "0.05",
            "tolerance_abs": "250",
            "max_combo": "3",
            "historical_account_boost": "0.2",
        }
    )
    config = page_a07.build_suggest_config("C:/demo/rulebook.json", normalized)

    assert normalized["tolerance_rel"] == 0.05
    assert normalized["tolerance_abs"] == 250.0
    assert normalized["max_combo"] == 3
    assert normalized["top_suggestions_per_code"] == 5
    assert config.rulebook_path == "C:/demo/rulebook.json"
    assert config.tolerance_rel == 0.05
    assert config.tolerance_abs == 250.0
    assert config.max_combo == 3
    assert config.historical_account_boost == 0.2


def test_build_rule_payload_and_alias_helpers_roundtrip_editor_values() -> None:
    code, payload = page_a07.build_rule_payload(
        {
            "code": "fastloenn",
            "label": "FastlÃ¸nn",
            "category": "LÃ¸nn",
            "allowed_ranges": "5000-5099\n5900",
            "keywords": "lÃ¸nn, fastlÃ¸nn",
            "boost_accounts": "5000, 5001",
            "basis": "Endring",
            "expected_sign": "1",
            "special_add": "5940 | Endring | 1.0",
        }
    )
    aliases = page_a07._parse_aliases_editor("fastloenn = lÃ¸nn, fast lÃ¸nn")
    aliases_text = page_a07._format_aliases_editor(aliases)

    assert code == "fastloenn"
    assert payload["allowed_ranges"] == ["5000-5099", "5900"]
    assert payload["keywords"] == ["lÃ¸nn", "fastlÃ¸nn"]
    assert payload["boost_accounts"] == [5000, 5001]
    assert payload["basis"] == "Endring"
    assert payload["expected_sign"] == 1
    assert payload["special_add"] == [{"account": "5940", "basis": "Endring"}]
    assert "fastloenn = lÃ¸nn, fast lÃ¸nn" in aliases_text


def test_apply_manual_mapping_choice_trims_and_updates_mapping() -> None:
    mapping = {"1920": "annet"}

    konto, kode = page_a07.apply_manual_mapping_choice(mapping, " 5000 ", " fastloenn ")

    assert (konto, kode) == ("5000", "fastloenn")
    assert mapping["5000"] == "fastloenn"


def test_build_a07_overview_df_marks_ok_avvik_unmapped_and_excluded() -> None:
    a07_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1000.0},
            {"Kode": "bonus", "Navn": "Bonus", "Belop": 500.0},
            {"Kode": "aga", "Navn": "AGA", "Belop": 100.0},
        ]
    )
    reconcile_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "WithinTolerance": True, "AntallKontoer": 1, "Kontoer": "5000"},
            {"Kode": "bonus", "WithinTolerance": False, "AntallKontoer": 1, "Kontoer": "5090"},
        ]
    )

    out = page_a07.build_a07_overview_df(a07_df, reconcile_df)

    assert out.loc[out["Kode"] == "fastloenn", "Status"].iloc[0] == "OK"
    assert out.loc[out["Kode"] == "bonus", "Status"].iloc[0] == "Avvik"
    assert out.loc[out["Kode"] == "aga", "Status"].iloc[0] == "Ekskludert"


def test_count_unsolved_a07_codes_ignores_ok_and_excluded() -> None:
    overview_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Status": "OK"},
            {"Kode": "bonus", "Status": "Avvik"},
            {"Kode": "aga", "Status": "Ekskludert"},
            {"Kode": "feriepenger", "Status": "Ikke mappet"},
        ]
    )

    out = page_a07.count_unsolved_a07_codes(overview_df)

    assert out == 2


def test_filter_a07_overview_df_supports_unsolved_and_specific_statuses() -> None:
    overview_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Status": "OK"},
            {"Kode": "bonus", "Status": "Avvik"},
            {"Kode": "aga", "Status": "Ekskludert"},
            {"Kode": "feriepenger", "Status": "Ikke mappet"},
        ]
    )

    unresolved = page_a07.filter_a07_overview_df(overview_df, "uloste")
    only_deviation = page_a07.filter_a07_overview_df(overview_df, "avvik")
    only_unmapped = page_a07.filter_a07_overview_df(overview_df, "ikke_mappet")

    assert unresolved["Kode"].tolist() == ["bonus", "feriepenger"]
    assert only_deviation["Kode"].tolist() == ["bonus"]
    assert only_unmapped["Kode"].tolist() == ["feriepenger"]


def test_build_mapping_history_details_compares_current_and_previous_accounts() -> None:
    out = page_a07.build_mapping_history_details(
        "fastloenn",
        mapping_current={"5000": "fastloenn", "5090": "bonus"},
        mapping_previous={"5000": "fastloenn", "5001": "fastloenn"},
        previous_year="2024",
    )

    assert "fastloenn |" in out
    assert "I aar: 5000" in out
    assert "2024: 5000, 5001" in out
    assert "Avviker fra historikk." in out


def test_safe_previous_accounts_for_code_requires_available_nonconflicting_accounts() -> None:
    gl_df = pd.DataFrame([{"Konto": "6990"}, {"Konto": "5940"}])

    out_ready = page_a07.safe_previous_accounts_for_code(
        "telefon",
        mapping_current={},
        mapping_previous={"6990": "telefon"},
        gl_df=gl_df,
    )
    out_conflict = page_a07.safe_previous_accounts_for_code(
        "pensjon",
        mapping_current={"5940": "annet"},
        mapping_previous={"5940": "pensjon"},
        gl_df=gl_df,
    )
    out_missing = page_a07.safe_previous_accounts_for_code(
        "fastloenn",
        mapping_current={},
        mapping_previous={"5000": "fastloenn"},
        gl_df=gl_df,
    )

    assert out_ready == ["6990"]
    assert out_conflict == []
    assert out_missing == []


def test_build_history_comparison_df_marks_same_ready_conflict_and_missing() -> None:
    a07_df = pd.DataFrame(
        [
            {"Kode": "bonus", "Navn": "Bonus"},
            {"Kode": "telefon", "Navn": "Telefon"},
            {"Kode": "pensjon", "Navn": "Pensjon"},
            {"Kode": "fastloenn", "Navn": "Fastloenn"},
            {"Kode": "feriepenger", "Navn": "Feriepenger"},
        ]
    )
    gl_df = pd.DataFrame(
        [
            {"Konto": "5090"},
            {"Konto": "6990"},
            {"Konto": "5940"},
        ]
    )

    out = page_a07.build_history_comparison_df(
        a07_df,
        gl_df,
        mapping_current={"5090": "bonus", "5940": "annet"},
        mapping_previous={
            "5090": "bonus",
            "6990": "telefon",
            "5940": "pensjon",
            "5000": "fastloenn",
        },
    )

    assert out.loc[out["Kode"] == "bonus", "Status"].iloc[0] == "Samme"
    assert out.loc[out["Kode"] == "telefon", "Status"].iloc[0] == "Klar fra historikk"
    assert bool(out.loc[out["Kode"] == "telefon", "KanBrukes"].iloc[0]) is True
    assert out.loc[out["Kode"] == "pensjon", "Status"].iloc[0] == "Konflikt"
    assert out.loc[out["Kode"] == "fastloenn", "Status"].iloc[0] == "Mangler konto"
    assert out.loc[out["Kode"] == "feriepenger", "Status"].iloc[0] == "Ingen historikk"


def test_select_safe_history_codes_returns_unique_ready_codes_only() -> None:
    history_df = pd.DataFrame(
        [
            {"Kode": "telefon", "KanBrukes": True},
            {"Kode": "telefon", "KanBrukes": True},
            {"Kode": "pensjon", "KanBrukes": False},
            {"Kode": "fastloenn", "KanBrukes": True},
        ]
    )

    out = page_a07.select_safe_history_codes(history_df)

    assert out == ["telefon", "fastloenn"]


def test_best_suggestion_row_for_code_returns_first_matching_row() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "bonus", "ForslagKontoer": "5000", "WithinTolerance": True},
            {"Kode": "bonus", "ForslagKontoer": "5001", "WithinTolerance": False},
            {"Kode": "telefon", "ForslagKontoer": "6990", "WithinTolerance": True},
        ]
    )

    out = page_a07.best_suggestion_row_for_code(suggestions_df, "bonus")

    assert out is not None
    assert str(out["ForslagKontoer"]) == "5000"


def test_build_control_suggestion_summary_describes_selected_row() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "bonus", "ForslagKontoer": "5000,5001", "Diff": Decimal("12.50"), "WithinTolerance": True},
            {"Kode": "bonus", "ForslagKontoer": "5090", "Diff": Decimal("100.00"), "WithinTolerance": False},
        ]
    )

    out = page_a07.build_control_suggestion_summary("bonus", suggestions_df, suggestions_df.iloc[1])
    diff_text = page_a07._format_picker_amount(Decimal("100.00"))

    assert out == f"Beste forslag for bonus | 2 kandidat(er) | Naa valgt: 5090 | Maa vurderes | Diff {diff_text}"


def test_build_control_suggestion_effect_summary_describes_new_mapping() -> None:
    row = pd.Series({"ForslagKontoer": "5000,5001", "Diff": Decimal("12.50"), "WithinTolerance": True})

    out = page_a07.build_control_suggestion_effect_summary("bonus", [], row)
    diff_text = page_a07._format_picker_amount(Decimal("12.50"))

    assert out == f"Vil mappe 5000,5001 til bonus | Maa vurderes | Diff {diff_text}"


def test_build_control_suggestion_effect_summary_describes_replacement() -> None:
    row = pd.Series({"ForslagKontoer": "5000,5001", "Diff": Decimal("100.00"), "WithinTolerance": False})

    out = page_a07.build_control_suggestion_effect_summary("bonus", ["5090"], row)
    diff_text = page_a07._format_picker_amount(Decimal("100.00"))

    assert out == f"Vil erstatte mapping 5090 med 5000,5001. Diff {diff_text}. Sjekk diff fÃ¸r bruk."


def test_build_control_suggestion_effect_summary_handles_matching_current_mapping() -> None:
    row = pd.Series({"ForslagKontoer": "5001,5000", "Diff": Decimal("0"), "WithinTolerance": True})

    out = page_a07.build_control_suggestion_effect_summary("bonus", ["5000", "5001"], row)
    diff_text = page_a07._format_picker_amount(Decimal("0"))

    assert out == f"Matcher dagens mapping: 5001,5000 | Maa vurderes | Diff {diff_text}"


def test_build_control_accounts_summary_describes_selected_accounts() -> None:
    accounts_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn", "IB": Decimal("0"), "Endring": Decimal("1200"), "UB": Decimal("1200")},
            {"Konto": "5001", "Navn": "Bonus", "IB": Decimal("0"), "Endring": Decimal("300"), "UB": Decimal("300")},
        ]
    )

    out = page_a07.build_control_accounts_summary(accounts_df, "fastloenn")

    assert out == "2 kontoer koblet | Endring 1 500,00 | 5000 Lonn, 5001 Bonus"


def test_build_control_accounts_summary_handles_empty_state() -> None:
    assert (
        page_a07.build_control_accounts_summary(pd.DataFrame(), "fastloenn")
        == "Ingen kontoer er koblet til fastloenn ennÃ¥. Velg kontoer til venstre og trykk ->."
    )
    assert (
        page_a07.build_control_accounts_summary(pd.DataFrame(), None)
        == "Velg A07-kode til hoyre for aa se hva som er koblet na."
    )

def test_rf1022_post_for_group_maps_payroll_groups_to_expected_sections() -> None:
    assert page_a07.rf1022_post_for_group("Skattetrekk") == (100, "Lonn og trekk")
    assert page_a07.rf1022_post_for_group("Skyldig arbeidsgiveravgift") == (110, "Arbeidsgiveravgift")
    assert page_a07.rf1022_post_for_group("Skyldig pensjon") == (120, "Pensjon og refusjon")
    assert page_a07.rf1022_post_for_group("ukjent_gruppe", "Naturalytelse") == (
        130,
        "Naturalytelser og styrehonorar",
    )


def test_build_rf1022_statement_df_sorts_rows_by_post_and_uses_selected_basis() -> None:
    control_statement_df = pd.DataFrame(
        [
            {
                "Gruppe": "Skyldig pensjon",
                "Navn": "Skyldig pensjon",
                "Endring": 300.0,
                "A07": 250.0,
                "Diff": 50.0,
                "Status": "Manuell",
                "AntallKontoer": 1,
            },
            {
                "Gruppe": "Skattetrekk",
                "Navn": "Skattetrekk",
                "Endring": 200.0,
                "A07": 200.0,
                "Diff": 0.0,
                "Status": "Ferdig",
                "AntallKontoer": 2,
            },
            {
                "Gruppe": "Skyldig arbeidsgiveravgift",
                "Navn": "Skyldig arbeidsgiveravgift",
                "Endring": 100.0,
                "A07": 90.0,
                "Diff": 10.0,
                "Status": "Manuell",
                "AntallKontoer": 1,
            },
        ]
    )

    out = page_a07.build_rf1022_statement_df(control_statement_df, basis_col="Endring")

    assert out["Post"].tolist() == ["100", "110", "120"]
    assert out["Kontrollgruppe"].tolist() == [
        "Skattetrekk",
        "Skyldig arbeidsgiveravgift",
        "Skyldig pensjon",
    ]
    assert out["GL_Belop"].tolist() == [200.0, 100.0, 300.0]


def test_build_rf1022_accounts_df_shapes_workbook_like_rows_for_payroll_accounts() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn ansatte", "IB": 0.0, "Endring": 1200.0, "UB": 1200.0, "Kode": "fastloenn"},
            {"Konto": "2940", "Navn": "Skyldige feriepenger", "IB": 300.0, "Endring": -200.0, "UB": 500.0, "Kode": "feriepenger"},
        ]
    )
    control_statement_df = pd.DataFrame(
        [
            {"Gruppe": "100_loenn_ol", "Navn": "Post 100 Lonn o.l.", "Kontoer": "5000, 2940"},
        ]
    )
    document = AccountProfileDocument(
        client="Test",
        year=2025,
        profiles={
            "5000": AccountProfile(
                account_no="5000",
                account_name="Lonn ansatte",
                control_group="100_loenn_ol",
                control_tags=("opplysningspliktig", "aga_pliktig", "feriepengergrunnlag"),
            ),
            "2940": AccountProfile(
                account_no="2940",
                account_name="Skyldige feriepenger",
                control_group="100_loenn_ol",
                control_tags=("opplysningspliktig", "aga_pliktig"),
            ),
        },
    )

    out = page_a07.build_rf1022_accounts_df(
        control_gl_df,
        control_statement_df,
        "100_loenn_ol",
        basis_col="Endring",
        profile_document=document,
    )

    assert out.columns.tolist() == [
        "Post",
        "Konto",
        "Navn",
        "KostnadsfortYtelse",
        "TilleggTidligereAar",
        "FradragPaalopt",
        "SamledeYtelser",
        "AgaPliktig",
        "AgaGrunnlag",
        "Feriepengegrunnlag",
    ]
    assert out["Konto"].tolist() == ["5000", "2940"]
    assert out.loc[0, "Post"].startswith("Post 100")
    assert out.loc[0, "KostnadsfortYtelse"] == 1200.0
    assert out.loc[0, "SamledeYtelser"] == 1200.0
    assert bool(out.loc[0, "AgaPliktig"]) is True
    assert out.loc[0, "AgaGrunnlag"] == 1200.0
    assert bool(out.loc[0, "Feriepengegrunnlag"]) is True
    assert out.loc[1, "TilleggTidligereAar"] == 300.0
    assert out.loc[1, "FradragPaalopt"] == 500.0
    assert out.loc[1, "SamledeYtelser"] == -200.0


def test_build_rf1022_accounts_df_keeps_refusjon_as_aga_basis_row() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5800", "Navn": "Refusjoner av sykepenger", "IB": 0.0, "Endring": -358842.0, "UB": -358842.0},
        ]
    )
    control_statement_df = pd.DataFrame(
        [
            {"Gruppe": "100_refusjon", "Navn": "Post 100 Refusjon", "Kontoer": "5800"},
        ]
    )
    document = AccountProfileDocument(
        client="Test",
        year=2025,
        profiles={
            "5800": AccountProfile(
                account_no="5800",
                account_name="Refusjoner av sykepenger",
                control_group="100_refusjon",
                control_tags=("refusjon",),
            ),
        },
    )

    out = page_a07.build_rf1022_accounts_df(
        control_gl_df,
        control_statement_df,
        "100_refusjon",
        basis_col="Endring",
        profile_document=document,
    )

    assert out.loc[0, "Post"] == "Post 100 Refusjon"
    assert pd.isna(out.loc[0, "SamledeYtelser"])
    assert pd.isna(out.loc[0, "AgaPliktig"])
    assert out.loc[0, "AgaGrunnlag"] == -358842.0


def test_control_recommendation_label_is_short_and_list_friendly() -> None:
    safe_best = pd.Series({"WithinTolerance": True})
    weak_best = pd.Series({"WithinTolerance": False})

    assert page_a07.control_recommendation_label(has_history=True, best_suggestion=safe_best) == "Se forslag"
    assert page_a07.control_recommendation_label(has_history=False, best_suggestion=safe_best) == "Se forslag"
    assert page_a07.control_recommendation_label(has_history=False, best_suggestion=weak_best) == "Se forslag"
    assert page_a07.control_recommendation_label(has_history=False, best_suggestion=None) == "Kontroller kobling"


def test_control_next_action_label_prioritizes_history_then_safe_suggestion() -> None:
    best_row = pd.Series({"WithinTolerance": True})
    weak_row = pd.Series({"WithinTolerance": False})

    assert (
        page_a07.control_next_action_label("Ikke mappet", has_history=True, best_suggestion=best_row)
        == "Se forslag for valgt kode."
    )
    assert (
        page_a07.control_next_action_label("Ikke mappet", has_history=False, best_suggestion=best_row)
        == "Se forslag for valgt kode."
    )
    assert (
        page_a07.control_next_action_label("Avvik", has_history=False, best_suggestion=weak_row)
        == "Se forslag for valgt kode."
    )
    assert (
        page_a07.control_next_action_label("OK", has_history=True, best_suggestion=best_row)
        == "Ingen handling nodvendig."
    )


def test_compact_control_next_action_shortens_user_hint() -> None:
    assert page_a07.compact_control_next_action("Se forslag for valgt kode.") == "Forslag"
    assert page_a07.compact_control_next_action("Aapne historikk for valgt kode.") == "Historikk"
    assert (
        page_a07.compact_control_next_action("Tildel RF-1022-post i Saldobalanse.")
        == "Tildel RF-1022-post i Saldobalanse."
    )
    assert page_a07.compact_control_next_action("Ingen handling nodvendig.") == "Ingen"


def test_build_control_queue_df_summarizes_mapping_history_and_best_suggestion() -> None:
    overview_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Navn": "Fastloenn", "Belop": 1000.0, "Status": "Ikke mappet"},
            {"Kode": "telefon", "Navn": "Telefon", "Belop": 500.0, "Status": "Ikke mappet"},
            {"Kode": "bonus", "Navn": "Bonus", "Belop": 250.0, "Status": "OK"},
        ]
    )
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "telefon", "ForslagKontoer": "6990", "WithinTolerance": True, "Diff": 0.0},
            {"Kode": "bonus", "ForslagKontoer": "5090", "WithinTolerance": True, "Diff": 0.0},
        ]
    )
    gl_df = pd.DataFrame([{"Konto": "5000"}, {"Konto": "6990"}, {"Konto": "5090"}])

    out = page_a07.build_control_queue_df(
        overview_df,
        suggestions_df,
        mapping_current={"5090": "bonus"},
        mapping_previous={"5000": "fastloenn"},
        gl_df=gl_df,
        code_profile_state={"bonus": {"source": "manual"}},
    )

    assert out.loc[out["Kode"] == "fastloenn", "A07Post"].iloc[0] == "Fastloenn"
    assert out.loc[out["Kode"] == "fastloenn", "Anbefalt"].iloc[0] == "Se historikk"
    assert out.loc[out["Kode"] == "fastloenn", "NesteHandling"].iloc[0] == "Aapne historikk for valgt kode."
    assert out.loc[out["Kode"] == "fastloenn", "Status"].iloc[0] == "Har historikk"
    assert out.loc[out["Kode"] == "fastloenn", "GuidetStatus"].iloc[0] == "Har historikk"
    assert out.loc[out["Kode"] == "telefon", "Anbefalt"].iloc[0] == "Se forslag"
    assert out.loc[out["Kode"] == "telefon", "NesteHandling"].iloc[0] == "Belop uten stotte"
    assert out.loc[out["Kode"] == "telefon", "Status"].iloc[0] == "Har forslag"
    assert out.loc[out["Kode"] == "telefon", "GuidetStatus"].iloc[0] == "Har forslag"
    assert out.loc[out["Kode"] == "telefon", "SuggestionGuardrail"].iloc[0] == "review"
    assert out.loc[out["Kode"] == "fastloenn", "Arbeidsstatus"].iloc[0] == "Forslag"
    assert out.loc[out["Kode"] == "telefon", "Arbeidsstatus"].iloc[0] == "Forslag"
    assert out.loc[out["Kode"] == "bonus", "DagensMapping"].iloc[0] == "5090"
    assert out.loc[out["Kode"] == "bonus", "Status"].iloc[0] == "Kontroller kobling"
    assert out.loc[out["Kode"] == "bonus", "GuidetStatus"].iloc[0] == "Kontroller kobling"
    assert out.loc[out["Kode"] == "bonus", "Arbeidsstatus"].iloc[0] == "Manuell"
    assert out.loc[out["Kode"] == "bonus", "NesteHandling"].iloc[0] == "Kontroller dagens kobling."


def test_build_control_queue_df_keeps_single_display_column_for_a07_identity() -> None:
    overview_df = pd.DataFrame(
        [
            {
                "Kode": "tilskuddOgPremieTilPensjon",
                "Navn": "Tilskudd og premie til pensjon",
                "Belop": 690556.0,
                "Status": "Ikke mappet",
            }
        ]
    )

    out = page_a07.build_control_queue_df(
        overview_df,
        pd.DataFrame(),
        mapping_current={},
        mapping_previous={},
        gl_df=pd.DataFrame(columns=["Konto"]),
    )

    assert out.loc[0, "A07Post"] == "Tilskudd og premie til pensjon (tilskuddOgPremieTilPensjon)"
    assert out.loc[0, "Kode"] == "tilskuddOgPremieTilPensjon"
    assert out.loc[0, "Navn"] == "Tilskudd og premie til pensjon"


def test_build_control_queue_df_flags_mistenkelig_mapping_and_prioritizes_suggestions() -> None:
    overview_df = pd.DataFrame(
        [
            {
                "Kode": "tilskuddOgPremieTilPensjon",
                "Navn": "Tilskudd og premie til pensjon",
                "Belop": 690556.0,
                "Status": "OK",
            }
        ]
    )
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "tilskuddOgPremieTilPensjon",
                "ForslagKontoer": "5420",
                "WithinTolerance": True,
                "Diff": 58318.21,
                "Explain": "regel=rulebook",
                "UsedRulebook": True,
            }
        ]
    )
    gl_df = pd.DataFrame(
        [
            {"Konto": "6300", "Navn": "Leie lokale"},
            {"Konto": "5420", "Navn": "Innberetningspliktig pensjonskostnad"},
        ]
    )

    out = page_a07.build_control_queue_df(
        overview_df,
        suggestions_df,
        mapping_current={"6300": "tilskuddOgPremieTilPensjon"},
        mapping_previous={},
        gl_df=gl_df,
    )

    assert bool(out.loc[0, "CurrentMappingSuspicious"]) is True
    assert out.loc[0, "GuidetStatus"] == "Mistenkelig kobling"
    assert out.loc[0, "Anbefalt"] == "Se forslag"
    assert out.loc[0, "SuggestionGuardrail"] == "accepted"


def test_build_control_gl_df_shows_assigned_code_on_account_rows() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "IB": -100.0, "Endring": -50.0, "UB": -150.0},
            {"Konto": "5000", "Navn": "Lonn", "IB": 10.0, "Endring": 1190.0, "UB": 1200.0},
            {"Konto": "6990", "Navn": "Telefon", "IB": 0.0, "Endring": 250.0, "UB": 250.0},
        ]
    )

    out = page_a07.build_control_gl_df(gl_df, {"5000": "fastloenn", "2940": "feriepenger"})

    assert out["Konto"].tolist() == ["2940", "5000", "6990"]
    assert out.loc[out["Konto"] == "2940", "Kol"].iloc[0] == "Endring"
    assert out.loc[out["Konto"] == "2940", "BelopAktiv"].iloc[0] == -50.0
    assert out.loc[out["Konto"] == "5000", "Kol"].iloc[0] == "UB"
    assert out.loc[out["Konto"] == "5000", "BelopAktiv"].iloc[0] == 1200.0
    assert out.loc[out["Konto"] == "5000", "Kode"].iloc[0] == "fastloenn"
    assert out.loc[out["Konto"] == "6990", "Kode"].iloc[0] == ""


def test_build_control_selected_account_df_filters_accounts_for_selected_code() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn", "IB": 0.0, "Endring": 1200.0, "UB": 1200.0},
            {"Konto": "5001", "Navn": "Bonus", "IB": 0.0, "Endring": 300.0, "UB": 300.0},
            {"Konto": "6990", "Navn": "Telefon", "IB": 0.0, "Endring": 250.0, "UB": 250.0},
        ]
    )

    out = page_a07.build_control_selected_account_df(
        gl_df,
        {"5000": "fastloenn", "5001": "fastloenn", "6990": "telefon"},
        "fastloenn",
    )

    assert out["Konto"].tolist() == ["5000", "5001"]
    assert out.columns.tolist() == ["Konto", "Navn", "IB", "Endring", "UB"]
    assert out["Endring"].tolist() == [1200.0, 300.0]


def test_build_control_selected_account_df_uses_requested_basis_as_active_amount() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn", "IB": 10.0, "Endring": 1200.0, "UB": 1210.0},
            {"Konto": "5001", "Navn": "Bonus", "IB": 5.0, "Endring": 300.0, "UB": 305.0},
        ]
    )

    out = page_a07.build_control_selected_account_df(
        gl_df,
        {"5000": "fastloenn", "5001": "fastloenn"},
        "fastloenn",
        basis_col="UB",
    )

    assert out["IB"].tolist() == [10.0, 5.0]
    assert out["Endring"].tolist() == [1200.0, 300.0]
    assert out["UB"].tolist() == [1210.0, 305.0]


def test_filter_control_queue_by_rf1022_group_scopes_detail_codes() -> None:
    control_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "Rf1022GroupId": "100_loenn_ol"},
            {"Kode": "tilskuddOgPremieTilPensjon", "Rf1022GroupId": "112_pensjon"},
            {"Kode": "elektroniskKommunikasjon", "Rf1022GroupId": "111_naturalytelser"},
        ]
    )

    out = a07_control_data.filter_control_queue_by_rf1022_group(control_df, "112_pensjon")

    assert out["Kode"].tolist() == ["tilskuddOgPremieTilPensjon"]


def test_filter_suggestions_for_rf1022_group_scopes_candidates() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "ForslagKontoer": "5000"},
            {"Kode": "tilskuddOgPremieTilPensjon", "ForslagKontoer": "5930"},
            {"Kode": "elektroniskKommunikasjon", "ForslagKontoer": "5210"},
        ]
    )

    out = a07_control_data.filter_suggestions_for_rf1022_group(suggestions_df, "111_naturalytelser")

    assert out["Kode"].tolist() == ["elektroniskKommunikasjon"]


def test_control_main_columns_hide_status_and_left_gl_keeps_regnskap_columns() -> None:
    left_columns = [column_id for column_id, *_rest in a07_constants._CONTROL_GL_COLUMNS]
    a07_columns = [column_id for column_id, *_rest in a07_constants._CONTROL_COLUMNS]
    rf1022_columns = [column_id for column_id, *_rest in a07_constants._CONTROL_RF1022_COLUMNS]

    assert left_columns == ["Konto", "Navn", "Rf1022GroupId", "Kode", "Kol", "IB", "Endring", "UB"]
    assert "Status" not in a07_columns
    assert "Status" not in rf1022_columns


def test_filter_control_gl_df_supports_search_and_only_unmapped() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Fast lonn", "IB": 0.0, "Endring": 1200.0, "UB": 1200.0, "Kode": "fastloenn"},
            {"Konto": "6990", "Navn": "Telefon", "IB": 0.0, "Endring": 250.0, "UB": 250.0, "Kode": ""},
            {"Konto": "7100", "Navn": "Bonus", "IB": 0.0, "Endring": 300.0, "UB": 300.0, "Kode": ""},
        ]
    )

    out = page_a07.filter_control_gl_df(control_gl_df, search_text="tele", only_unmapped=True)

    assert out["Konto"].tolist() == ["6990"]


def test_filter_control_gl_df_supports_active_only_and_keeps_mapped_rows() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "1000", "Navn": "Tom konto", "IB": 0.0, "Endring": 0.0, "UB": 0.0, "Kode": ""},
            {"Konto": "1020", "Navn": "Mapped nullkonto", "IB": 0.0, "Endring": 0.0, "UB": 0.0, "Kode": "fastloenn"},
            {"Konto": "5000", "Navn": "Lonn", "IB": 0.0, "Endring": 1200.0, "UB": 1200.0, "Kode": ""},
        ]
    )

    out = page_a07.filter_control_gl_df(control_gl_df, active_only=True)

    assert out["Konto"].tolist() == ["1020", "5000"]


class _ScopeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _ScopeWidget:
    def __init__(self, value: str = "") -> None:
        self.value = value
        self.config: dict[str, object] = {}

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value

    def configure(self, **kwargs) -> None:
        self.config.update(kwargs)


def _control_gl_scope_page(scope: str, *, work_level: str = "a07", group_id: str = ""):
    page = object.__new__(page_a07.A07Page)
    page.control_gl_scope_var = _ScopeVar(scope)
    page.control_gl_scope_label_var = _ScopeVar("")
    page.control_gl_scope_widget = None
    page._selected_control_work_level = lambda: work_level
    page._selected_rf1022_group = lambda: group_id
    page._selected_control_suggestion_accounts = lambda: []
    return page


def test_apply_control_gl_scope_rf1022_selected_post_uses_group_only() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Kode": "fastloenn", "Rf1022GroupId": "100"},
            {"Konto": "6300", "Kode": "annet", "Rf1022GroupId": "112"},
            {"Konto": "6990", "Kode": "", "Rf1022GroupId": ""},
        ]
    )
    page = _control_gl_scope_page("koblede", work_level="rf1022", group_id="100")

    out = page_a07.A07Page._apply_control_gl_scope(page, control_gl_df, selected_code="fastloenn")

    assert out["Konto"].tolist() == ["5000"]


def test_apply_control_gl_scope_a07_linked_ignores_history_and_suggestion_union() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Kode": "fastloenn", "Rf1022GroupId": "100"},
            {"Konto": "6300", "Kode": "annet", "Rf1022GroupId": "100"},
            {"Konto": "6990", "Kode": "", "Rf1022GroupId": "100"},
        ]
    )
    page = _control_gl_scope_page("relevante", work_level="a07")
    page._selected_control_suggestion_accounts = lambda: ["6300", "6990"]

    out = page_a07.A07Page._apply_control_gl_scope(page, control_gl_df, selected_code="fastloenn")

    assert page_a07.A07Page._selected_control_gl_scope(page) == "koblede"
    assert out["Konto"].tolist() == ["5000"]


def test_apply_control_gl_scope_a07_suggestions_uses_selected_suggestion_accounts_only() -> None:
    control_gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Kode": "fastloenn", "Rf1022GroupId": "100"},
            {"Konto": "6300", "Kode": "annet", "Rf1022GroupId": "112"},
        ]
    )
    page = _control_gl_scope_page("forslag", work_level="a07")
    page._selected_control_suggestion_accounts = lambda: ["6300"]

    out = page_a07.A07Page._apply_control_gl_scope(page, control_gl_df, selected_code="fastloenn")

    assert out["Konto"].tolist() == ["6300"]


def test_sync_control_gl_scope_widget_hides_suggestion_scope_in_rf1022_mode() -> None:
    page = _control_gl_scope_page("forslag", work_level="rf1022", group_id="100")
    page.control_gl_scope_widget = _ScopeWidget("Forslag for valgt A07-kode")

    page_a07.A07Page._sync_control_gl_scope_widget(page)

    assert page.control_gl_scope_var.get() == "alle"
    assert page.control_gl_scope_label_var.get() == "Alle kontoer"
    assert page.control_gl_scope_widget.value == "Alle kontoer"
    assert page.control_gl_scope_widget.config["values"] == ["Alle kontoer", "Valgt RF-1022-post"]


def test_set_control_details_visible_does_not_move_sash_position() -> None:
    sash_calls: list[tuple] = []

    class _Pane:
        def winfo_height(self):
            return 600

        def sashpos(self, *args):
            sash_calls.append(args)
            return 300

    class _Button:
        def configure(self, **_kwargs) -> None:
            return None

    dummy = SimpleNamespace(
        _diag=lambda _message: None,
        control_support_nb=None,
        btn_control_toggle_details=_Button(),
        control_vertical_panes=_Pane(),
        _support_views_ready=False,
        _schedule_support_refresh=lambda: None,
    )

    page_a07.A07Page._set_control_details_visible(dummy, False)
    page_a07.A07Page._set_control_details_visible(dummy, True)

    assert sash_calls == []


def test_filter_control_queue_df_and_bucket_summary_group_rows_for_human_workflow() -> None:
    control_df = pd.DataFrame(
        [
            {"Kode": "bonus", "Arbeidsstatus": "Ferdig"},
            {"Kode": "telefon", "Arbeidsstatus": "Forslag"},
            {"Kode": "pensjon", "Arbeidsstatus": "Manuell"},
        ]
    )

    next_rows = page_a07.filter_control_queue_df(control_df, "neste")
    manual_rows = page_a07.filter_control_queue_df(control_df, "manuell")
    summary = page_a07.build_control_bucket_summary(control_df)

    assert next_rows["Kode"].tolist() == ["telefon", "pensjon"]
    assert manual_rows["Kode"].tolist() == ["pensjon"]
    assert summary == "2 åpne"


def test_build_control_queue_df_sorts_by_work_priority_then_amount() -> None:
    overview_df = pd.DataFrame(
        [
            {"Kode": "liten", "Navn": "Liten", "Belop": 100.0, "Status": "Ikke mappet"},
            {"Kode": "stor", "Navn": "Stor", "Belop": 900.0, "Status": "Ikke mappet"},
            {"Kode": "ferdig", "Navn": "Ferdig", "Belop": 5000.0, "Status": "OK"},
        ]
    )
    suggestions_df = pd.DataFrame()
    gl_df = pd.DataFrame([{"Konto": "5000"}])

    out = page_a07.build_control_queue_df(
        overview_df,
        suggestions_df,
        mapping_current={"5000": "ferdig"},
        mapping_previous={},
        gl_df=gl_df,
        locked_codes={"ferdig"},
    )

    assert out["Kode"].tolist() == ["stor", "liten", "ferdig"]


def test_a07_page_format_value_formats_numeric_strings_with_thousands_separator() -> None:
    out = page_a07.A07Page._format_value(object(), "17036305.83", "Belop")

    assert out == "17 036 305,83"


def test_a07_page_format_value_formats_decimal_values_with_thousands_separator() -> None:
    out = page_a07.A07Page._format_value(object(), Decimal("-765740.42"), "Belop")

    assert out == "-765 740,42"


def test_build_source_overview_rows_keeps_source_labels_in_stable_order() -> None:
    out = page_a07.build_source_overview_rows(
        a07_text="A07: a07_source.json",
        tb_text="Saldobalanse: trial_balance.xlsx",
        mapping_text="Mapping: a07_mapping.json",
        rulebook_text="Rulebook: global_full_a07_rulebook.json",
        history_text="Historikk: ingen tidligere A07-mapping funnet",
    )

    assert out == [
        ("A07-kilde", "A07: a07_source.json"),
        ("Saldobalanse", "Saldobalanse: trial_balance.xlsx"),
        ("Mapping", "Mapping: a07_mapping.json"),
        ("Rulebook", "Rulebook: global_full_a07_rulebook.json"),
        ("Historikk", "Historikk: ingen tidligere A07-mapping funnet"),
    ]


def test_control_tree_tag_maps_work_statuses_to_visual_tags() -> None:
    assert page_a07.control_tree_tag("Ferdig") == "control_done"
    assert page_a07.control_tree_tag("Forslag") == "control_review"
    assert page_a07.control_tree_tag("Historikk") == "control_review"
    assert page_a07.control_tree_tag("Har forslag") == "control_review"
    assert page_a07.control_tree_tag("Har historikk") == "control_review"
    assert page_a07.control_tree_tag("Manuell") == "control_manual"
    assert page_a07.control_tree_tag("Kontroller kobling") == "control_manual"
    assert page_a07.control_tree_tag("UlÃ¸st") == "control_manual"
    assert page_a07.control_tree_tag("Annet") == "control_default"


def test_control_gl_tree_tag_marks_unmapped_and_mapped_rows() -> None:
    unmapped = pd.Series({"Kode": ""})
    mapped = pd.Series({"Kode": "fastloenn"})

    assert page_a07.control_gl_tree_tag(unmapped, "fastloenn") == "control_gl_unmapped"
    assert page_a07.control_gl_tree_tag(mapped, "fastloenn") == "control_gl_mapped"


def test_payroll_family_tag_uses_visible_sage_color() -> None:
    source = Path(a07_canonical_layout.__file__).read_text(encoding="utf-8")

    assert source.count('"family_payroll": ("SAGE_WASH", "FOREST")') >= 5


def test_control_queue_tree_tag_uses_diff_first_for_green_and_red() -> None:
    assert page_a07.control_queue_tree_tag(pd.Series({"Diff": 0.0, "Arbeidsstatus": "Ulost"})) == "control_done"
    assert page_a07.control_queue_tree_tag(pd.Series({"Diff": 10.0, "Arbeidsstatus": "Historikk"})) == "control_review"
    assert page_a07.control_queue_tree_tag(pd.Series({"Diff": None, "Arbeidsstatus": "Forslag"})) == "control_review"
    assert page_a07.control_queue_tree_tag(pd.Series({"Diff": None, "GuidetStatus": "Kontroller kobling"})) == "control_manual"


def test_filter_control_visible_codes_df_hides_non_matching_codes_for_this_view() -> None:
    control_df = pd.DataFrame(
        [
            {"Kode": "forskuddstrekk", "Navn": "Forskuddstrekk"},
            {"Kode": "aga", "Navn": "AGA"},
            {"Kode": "finansskattloenn", "Navn": "FinansskattLonn"},
            {"Kode": "feriepenger", "Navn": "Feriepenger"},
        ]
    )

    out = page_a07.filter_control_visible_codes_df(control_df)

    assert list(out["Kode"]) == ["feriepenger"]


def test_selected_code_from_tree_prefers_tree_focus_for_a07_work_code() -> None:
    class DummyTree:
        def focus(self):
            return "sumAvgiftsgrunnlagRefusjon"

        def selection(self):
            return ("feriepenger",)

        def item(self, iid, option):
            if iid == "feriepenger" and option == "values":
                return ("feriepenger", "Feriepenger")
            if iid == "sumAvgiftsgrunnlagRefusjon" and option == "values":
                return ("sumAvgiftsgrunnlagRefusjon", "Sum avgiftsgrunnlag refusjon")
            return ()

    tree = DummyTree()
    dummy = SimpleNamespace(tree_a07=tree)

    out = page_a07.A07Page._selected_code_from_tree(dummy, tree)

    assert out == "sumAvgiftsgrunnlagRefusjon"


def test_control_action_style_maps_work_labels() -> None:
    assert page_a07.control_action_style("Ferdig") == "Ready.TLabel"
    assert page_a07.control_action_style("Forslag") == "Warning.TLabel"
    assert page_a07.control_action_style("Historikk") == "Warning.TLabel"
    assert page_a07.control_action_style("Manuell") == "Warning.TLabel"
    assert page_a07.control_action_style("UlÃ¸st") == "Warning.TLabel"
    assert page_a07.control_action_style("Annet") == "Muted.TLabel"


def test_control_intro_text_guides_user_toward_best_next_step() -> None:
    safe_best = pd.Series({"WithinTolerance": True})

    assert (
        page_a07.control_intro_text("Ferdig", has_history=False, best_suggestion=None)
        == "Ser ferdig ut. Kontroller kort og gaa videre hvis du er enig."
    )
    assert (
        page_a07.control_intro_text("Historikk", has_history=True, best_suggestion=None)
        == "Historikk finnes for posten. Sammenlign kort for du godkjenner."
    )
    assert (
        page_a07.control_intro_text("Forslag", has_history=False, best_suggestion=safe_best)
        == "Det finnes et forslag som bor vurderes."
    )
    assert (
        page_a07.control_intro_text("Manuell", has_history=False, best_suggestion=None)
        == "Posten er koblet, men bor kontrolleres."
    )
    assert (
        page_a07.control_intro_text("UlÃ¸st", has_history=False, best_suggestion=None)
        == "Velg koblinger eller jobb videre i forslagene nederst."
    )


def test_manual_mapping_defaults_prefers_selected_control_gl_and_control_code() -> None:
    class DummyPage:
        tree_control_gl = object()
        tree_unmapped = object()
        tree_mapping = object()
        tree_control_accounts = object()
        tree_a07 = object()
        tree_control_suggestions = object()
        tree_suggestions = object()

        def _selected_tree_values(self, tree):
            if tree is self.tree_control_gl:
                return ("5000", "Lonn", "0,00", "1 200,00", "1 200,00", "")
            return ()

        def _selected_code_from_tree(self, tree):
            if tree is self.tree_a07:
                return "fastloenn"
            return None

    konto, kode = page_a07.A07Page._manual_mapping_defaults(DummyPage())

    assert konto == "5000"
    assert kode == "fastloenn"


def test_apply_manual_mapping_choices_assigns_multiple_accounts_to_same_code() -> None:
    mapping = {"4000": "bonus"}

    out = page_a07.apply_manual_mapping_choices(mapping, ["5000", "5001", "5000"], "fastloenn")

    assert out == ["5000", "5001"]
    assert mapping == {"4000": "bonus", "5000": "fastloenn", "5001": "fastloenn"}


def test_remove_mapping_accounts_only_removes_selected_existing_accounts() -> None:
    mapping = {"5000": "fastloenn", "5001": "fastloenn", "6990": "telefon"}

    out = page_a07.remove_mapping_accounts(mapping, ["5001", "5001", "8888"])

    assert out == ["5001"]
    assert mapping == {"5000": "fastloenn", "6990": "telefon"}


def test_run_selected_control_gl_action_assigns_when_code_is_selected() -> None:
    calls: list[str] = []

    class DummyPage:
        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _selected_control_code(self):
            return "fastloenn"

        def _assign_selected_control_mapping(self):
            calls.append("assign")

        def _open_manual_mapping_clicked(self):
            calls.append("manual")

    page_a07.A07Page._run_selected_control_gl_action(DummyPage())

    assert calls == ["assign"]


def test_run_selected_control_gl_action_guides_user_without_selected_code() -> None:
    focused: list[str] = []
    statuses: list[str] = []

    class DummyPage:
        class DummyTree:
            def focus_set(self) -> None:
                focused.append("a07")

        tree_a07 = DummyTree()

        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _selected_control_code(self):
            return None

        @property
        def status_var(self):
            return SimpleNamespace(set=lambda value: statuses.append(value))

        def _assign_selected_control_mapping(self):
            raise AssertionError("should not assign without selected code")

    page_a07.A07Page._run_selected_control_gl_action(DummyPage())

    assert focused == ["a07"]
    assert statuses == ["Velg en A07-kode til hoyre for du tildeler kontoer fra GL-listen."]


def test_run_selected_control_gl_action_assigns_to_selected_rf1022_group() -> None:
    calls: list[tuple[str, tuple[str, ...], str]] = []

    class DummyPage:
        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _selected_control_work_level(self):
            return "rf1022"

        def _selected_rf1022_group(self):
            return "100_loenn_ol"

        def _assign_accounts_to_rf1022_group(self, accounts, group_id, *, source_label="RF-1022-mapping"):
            calls.append((source_label, tuple(accounts), group_id))

    page_a07.A07Page._run_selected_control_gl_action(DummyPage())

    assert calls == [("RF-1022-mapping", ("5000",), "100_loenn_ol")]


def test_assign_selected_control_mapping_guides_user_without_gl_selection() -> None:
    focused: list[str] = []
    statuses: list[str] = []

    class DummyTree:
        def focus_set(self) -> None:
            focused.append("gl")

    class DummyPage:
        tree_control_gl = DummyTree()
        tree_a07 = object()

        def _selected_control_gl_accounts(self):
            return []

        def _selected_control_code(self):
            return "fastloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)
            if focus_widget is not None:
                focus_widget.focus_set()

    page_a07.A07Page._assign_selected_control_mapping(DummyPage())

    assert statuses == ["Velg en eller flere GL-kontoer til venstre forst."]
    assert focused == ["gl"]


def test_assign_selected_control_mapping_guides_user_without_selected_code() -> None:
    focused: list[str] = []
    statuses: list[str] = []

    class DummyTree:
        def focus_set(self) -> None:
            focused.append("a07")

    class DummyPage:
        tree_control_gl = object()
        tree_a07 = DummyTree()

        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _selected_control_code(self):
            return None

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)
            if focus_widget is not None:
                focus_widget.focus_set()

    page_a07.A07Page._assign_selected_control_mapping(DummyPage())

    assert statuses == ["Velg en A07-kode til hoyre forst."]
    assert focused == ["a07"]


def test_assign_selected_control_mapping_uses_selected_rf1022_group_when_in_rf_mode() -> None:
    calls: list[tuple[tuple[str, ...], str, str]] = []

    class DummyPage:
        tree_control_gl = object()
        tree_a07 = object()

        def _selected_control_gl_accounts(self):
            return ["5800", "5890"]

        def _selected_control_work_level(self):
            return "rf1022"

        def _selected_rf1022_group(self):
            return "100_refusjon"

        def _assign_accounts_to_rf1022_group(self, accounts, group_id, *, source_label="RF-1022-mapping"):
            calls.append((tuple(accounts), group_id, source_label))

    page_a07.A07Page._assign_selected_control_mapping(DummyPage())

    assert calls == [(("5800", "5890"), "100_refusjon", "RF-1022-mapping")]


def test_a07_code_menu_choices_use_control_queue_before_workspace_fallback() -> None:
    dummy = SimpleNamespace(
        control_df=pd.DataFrame(
            [
                {"Kode": "fastloenn", "Navn": "Fast lonn"},
                {"Kode": "A07_GROUP:demo", "Navn": "Gruppe"},
            ]
        ),
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(
                [
                    {"Kode": "fastloenn", "Navn": "Fast lonn", "Belop": 100.0},
                    {"Kode": "elektroniskKommunikasjon", "Navn": "Elektronisk kommunikasjon", "Belop": 50.0},
                ]
            )
        ),
    )

    out = page_a07.A07Page._a07_code_menu_choices(dummy)

    assert out[0] == ("fastloenn", "fastloenn - Fast lonn")
    assert out[1][0] == "elektroniskKommunikasjon"
    assert all(not code.startswith("A07_GROUP:") for code, _label in out)


def test_assign_selected_accounts_to_a07_code_maps_and_focuses() -> None:
    calls: list[tuple[str, object]] = []
    statuses: list[str] = []

    class DummyPage:
        tree_control_gl = object()
        tree_a07 = object()

        def __init__(self) -> None:
            self.workspace = SimpleNamespace(mapping={}, locks=set(), membership={})
            self.status_var = SimpleNamespace(set=lambda value: statuses.append(value))

        def _selected_control_gl_accounts(self):
            return ["5000", "5001"]

        def _assign_accounts_to_a07_code(self, accounts, code, *, source_label="Mapping"):
            return page_a07.A07Page._assign_accounts_to_a07_code(
                self,
                accounts,
                code,
                source_label=source_label,
            )

        def _autosave_mapping(self):
            return False

        def _refresh_core(self, *, focus_code=None):
            calls.append(("refresh", focus_code))

        def _focus_mapping_account(self, account):
            calls.append(("account", account))

        def _activate_a07_code_for_explicit_account_action(self, code):
            calls.append(("code", code))

        def _select_primary_tab(self):
            calls.append(("tab", "primary"))

    page = DummyPage()

    page_a07.A07Page._assign_selected_accounts_to_a07_code(page, "fastloenn")

    assert page.workspace.mapping == {"5000": "fastloenn", "5001": "fastloenn"}
    assert calls == [
        ("refresh", "fastloenn"),
        ("account", "5000"),
        ("code", "fastloenn"),
        ("tab", "primary"),
    ]
    assert statuses == ["Mapping: tildelte 2 konto(er) til fastloenn."]


def test_apply_selected_suggestion_uses_selected_rf1022_candidate() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _selected_control_work_level=lambda: "rf1022",
        _apply_selected_rf1022_candidate=lambda: calls.append("candidate"),
    )

    page_a07.A07Page._apply_selected_suggestion(dummy)

    assert calls == ["candidate"]


def test_apply_batch_suggestions_clicked_uses_rf1022_candidates_in_rf_mode() -> None:
    calls: list[tuple[str, object]] = []
    statuses: list[str] = []
    candidate_df = pd.DataFrame(
        [
            {
                "Konto": "2940",
                "Kode": "feriepenger",
                "Rf1022GroupId": "100_loenn_ol",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "5000",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "5001",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "Forslagsstatus": "Maa vurderes",
            },
        ]
    )

    class DummyPage:
        tree_control_suggestions = object()
        workspace = SimpleNamespace(mapping={}, locks=set(), membership={})
        rf1022_candidate_df = candidate_df
        rf1022_all_candidate_df = candidate_df

        def __init__(self) -> None:
            self.status_var = SimpleNamespace(set=lambda value: statuses.append(value))

        def _selected_control_work_level(self):
            return "rf1022"

        def _apply_rf1022_candidate_suggestions(self):
            return page_a07.A07Page._apply_rf1022_candidate_suggestions(self)

        def _current_rf1022_candidate_df(self):
            return page_a07.A07Page._current_rf1022_candidate_df(self)

        def _all_rf1022_candidate_df(self):
            return page_a07.A07Page._all_rf1022_candidate_df(self)

        def _effective_mapping(self):
            return {}

        def _autosave_mapping(self):
            return False

        def _refresh_core(self, *, focus_code=None):
            calls.append(("refresh", focus_code))

        def _focus_mapping_account(self, account):
            calls.append(("account", account))

        def _focus_control_code(self, code):
            calls.append(("code", code))

        def _select_primary_tab(self):
            calls.append(("tab", "primary"))

        def _notify_inline(self, message, **_kwargs):
            statuses.append(message)

    page = DummyPage()

    page_a07.A07Page._apply_batch_suggestions_clicked(page)

    assert page.workspace.mapping == {"2940": "feriepenger", "5000": "fastloenn"}
    assert calls == [
        ("refresh", "feriepenger"),
        ("account", "2940"),
        ("code", "feriepenger"),
        ("tab", "primary"),
    ]
    assert statuses == ["Automatisk RF-1022-matching: brukte 2 sikre forslag (1 post(er), 1 maa vurderes)."]


def test_apply_rf1022_candidate_suggestions_uses_all_groups_not_only_visible_group() -> None:
    calls: list[tuple[str, object]] = []
    statuses: list[str] = []
    visible_df = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "Forslagsstatus": "Trygt forslag",
            }
        ]
    )
    all_df = pd.DataFrame(
        [
            {
                "Konto": "5000",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "Forslagsstatus": "Trygt forslag",
            },
            {
                "Konto": "5940",
                "Kode": "tilskuddOgPremieTilPensjon",
                "Rf1022GroupId": "112_pensjon",
                "Forslagsstatus": "Trygt forslag",
            },
        ]
    )

    class DummyPage:
        tree_control_suggestions = object()
        workspace = SimpleNamespace(mapping={}, locks=set(), membership={})
        rf1022_candidate_df = visible_df
        rf1022_all_candidate_df = all_df

        def __init__(self) -> None:
            self.status_var = SimpleNamespace(set=lambda value: statuses.append(value))

        def _all_rf1022_candidate_df(self):
            return page_a07.A07Page._all_rf1022_candidate_df(self)

        def _effective_mapping(self):
            return {}

        def _autosave_mapping(self):
            return False

        def _refresh_core(self, *, focus_code=None):
            calls.append(("refresh", focus_code))

        def _focus_mapping_account(self, account):
            calls.append(("account", account))

        def _focus_control_code(self, code):
            calls.append(("code", code))

        def _select_primary_tab(self):
            calls.append(("tab", "primary"))

        def _notify_inline(self, message, **_kwargs):
            statuses.append(message)

    page = DummyPage()

    page_a07.A07Page._apply_rf1022_candidate_suggestions(page)

    assert page.workspace.mapping == {"5000": "fastloenn", "5940": "tilskuddOgPremieTilPensjon"}
    assert calls[0] == ("refresh", "fastloenn")
    assert statuses == ["Automatisk RF-1022-matching: brukte 2 sikre forslag (2 post(er))."]


def test_apply_rf1022_candidate_suggestions_rebuilds_fresh_candidates() -> None:
    calls: list[tuple[str, object]] = []
    statuses: list[str] = []
    stale_df = pd.DataFrame(
        [
            {
                "Konto": "5001",
                "Kode": "fastloenn",
                "Rf1022GroupId": "100_loenn_ol",
                "Forslagsstatus": "Trygt forslag",
            }
        ]
    )
    suggestions_df = pd.DataFrame(
        [
            {
                "Kode": "fastloenn",
                "KodeNavn": "Fastlonn",
                "A07_Belop": 1000.0,
                "ForslagKontoer": "5000",
                "WithinTolerance": True,
                "AmountEvidence": "exact",
                "SuggestionGuardrail": "accepted",
                "UsedRulebook": True,
                "HitTokens": "lonn",
            }
        ]
    )

    class DummyPage:
        tree_control_suggestions = object()
        workspace = SimpleNamespace(mapping={}, locks=set(), membership={}, basis_col="Endring")
        control_gl_df = pd.DataFrame(
            [{"Konto": "5000", "Navn": "Fast lonn", "Endring": 1000.0, "BelopAktiv": 1000.0}]
        )
        rf1022_all_candidate_df = stale_df

        def __init__(self) -> None:
            self.status_var = SimpleNamespace(set=lambda value: statuses.append(value))

        def _all_rf1022_candidate_df(self):
            return page_a07.A07Page._all_rf1022_candidate_df(self)

        def _rf1022_group_menu_choices(self):
            return [("100_loenn_ol", "Lonn")]

        def _ensure_suggestion_display_fields(self):
            return suggestions_df

        def _effective_mapping(self):
            return {}

        def _autosave_mapping(self):
            return False

        def _refresh_core(self, *, focus_code=None):
            calls.append(("refresh", focus_code))

        def _focus_mapping_account(self, account):
            calls.append(("account", account))

        def _focus_control_code(self, code):
            calls.append(("code", code))

        def _select_primary_tab(self):
            calls.append(("tab", "primary"))

        def _notify_inline(self, message, **_kwargs):
            statuses.append(message)

    page = DummyPage()

    page_a07.A07Page._apply_rf1022_candidate_suggestions(page)

    assert page.workspace.mapping == {"5000": "fastloenn"}
    assert "5001" not in page.workspace.mapping
    assert calls[0] == ("refresh", "fastloenn")


def test_apply_best_suggestion_requires_strict_guardrail() -> None:
    statuses: list[str] = []

    class DummyPage:
        tree_a07 = object()
        tree_control_suggestions = object()
        workspace = SimpleNamespace(
            mapping={},
            locks=set(),
            suggestions=pd.DataFrame(),
        )

        def _selected_control_code(self):
            return "annet"

        def _ensure_suggestion_display_fields(self):
            return pd.DataFrame(
                [
                    {
                        "Kode": "annet",
                        "ForslagKontoer": "6701",
                        "WithinTolerance": True,
                        "SuggestionGuardrail": "review",
                        "SuggestionGuardrailReason": "Belop uten stotte",
                    }
                ]
            )

        def _notify_inline(self, message, **_kwargs):
            statuses.append(message)

    page_a07.A07Page._apply_best_suggestion_for_selected_code(DummyPage())

    assert statuses == [
        "Beste forslag er ikke trygt nok for automatisk bruk (Belop uten stotte). Kontroller eller map manuelt."
    ]


def test_clear_selected_control_mapping_checks_lock_before_mutating() -> None:
    statuses: list[str] = []
    autosaves: list[str] = []

    class DummyPage:
        tree_control_gl = object()
        workspace = SimpleNamespace(mapping={"5000": "fastloenn"}, locks={"fastloenn"}, membership={})

        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _effective_mapping(self):
            return self.workspace.mapping

        def _notify_locked_conflicts(self, conflicts, **_kwargs):
            statuses.append(",".join(conflicts))
            return True

        def _autosave_mapping(self):
            autosaves.append("save")
            return False

    page = DummyPage()

    page_a07.A07Page._clear_selected_control_mapping(page)

    assert page.workspace.mapping == {"5000": "fastloenn"}
    assert statuses == ["fastloenn"]
    assert autosaves == []


def test_focus_linked_code_for_selected_gl_account_uses_effective_mapping() -> None:
    calls: list[str] = []
    statuses: list[str] = []
    dummy = SimpleNamespace(
        tree_control_gl=object(),
        _selected_control_gl_accounts=lambda: ["5000"],
        _effective_mapping=lambda: {"5000": "fastloenn"},
        _activate_a07_code_for_explicit_account_action=lambda code: calls.append(code),
        status_var=SimpleNamespace(set=lambda value: statuses.append(value)),
    )

    page_a07.A07Page._focus_linked_code_for_selected_gl_account(dummy)

    assert calls == ["fastloenn"]
    assert statuses == ["Konto 5000 er koblet til A07-kode fastloenn."]


def test_resolve_rf1022_target_code_prefers_single_code_groups() -> None:
    dummy = SimpleNamespace(
        workspace=SimpleNamespace(mapping={}, suggestions=pd.DataFrame(), selected_code=None),
        control_gl_df=pd.DataFrame(),
        _effective_mapping=lambda: {},
    )

    out = page_a07.A07Page._resolve_rf1022_target_code(dummy, "100_refusjon", ["5800"])

    assert out == "sumAvgiftsgrunnlagRefusjon"


def test_resolve_rf1022_target_code_uses_naturalytelse_name_hints() -> None:
    dummy = SimpleNamespace(
        workspace=SimpleNamespace(mapping={}, suggestions=pd.DataFrame(), selected_code=None, gl_df=pd.DataFrame()),
        control_gl_df=pd.DataFrame(
            [
                {"Konto": "5210", "Navn": "Fri telefon"},
                {"Konto": "5251", "Navn": "Gruppelivsforsikring"},
            ]
        ),
        _effective_mapping=lambda: {},
    )

    phone_code = page_a07.A07Page._resolve_rf1022_target_code(dummy, "111_naturalytelser", ["5210"])
    insurance_code = page_a07.A07Page._resolve_rf1022_target_code(dummy, "111_naturalytelser", ["5251"])

    assert phone_code == "elektroniskKommunikasjon"
    assert insurance_code == "skattepliktigDelForsikringer"


def test_drop_unmapped_on_control_assigns_to_rf1022_group_in_rf_mode() -> None:
    calls: list[tuple[tuple[str, ...], str, str]] = []

    class DummyTree:
        def selection_set(self, _iid) -> None:
            return None

        def focus(self, _iid) -> None:
            return None

        def see(self, _iid) -> None:
            return None

    dummy = SimpleNamespace(
        tree_a07=DummyTree(),
        _selected_control_work_level=lambda: "rf1022",
        _current_drag_accounts=lambda: ["5800"],
        _tree_iid_from_event=lambda _tree, _event: "100_refusjon",
        _assign_accounts_to_rf1022_group=lambda accounts, group_id, *, source_label="RF-1022-mapping": calls.append(
            (tuple(accounts), group_id, source_label)
        ),
        _clear_control_drag_state=lambda: calls.append((tuple(), "", "cleared")),
    )

    page_a07.A07Page._drop_unmapped_on_control(dummy, event=None)

    assert calls[0] == (("5800",), "100_refusjon", "Drag-and-drop mot RF-1022")
    assert calls[-1] == (tuple(), "", "cleared")


def test_show_control_gl_context_menu_offers_rf1022_group_submenu(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_command(self, *, label, command=None, state=None) -> None:
            self.items.append(("command", label, state))

        def add_cascade(self, *, label, menu) -> None:
            self.items.append(("cascade", label, menu))

        def add_separator(self) -> None:
            self.items.append(("separator", "", None))

    monkeypatch.setattr(a07_context_menu.tk, "Menu", _Menu)

    dummy = SimpleNamespace(
        tree_control_gl=object(),
        _prepare_tree_context_selection=lambda *args, **kwargs: "acct:5800",
        _selected_control_gl_accounts=lambda: ["5800"],
        _selected_control_code=lambda: "",
        _selected_control_work_level=lambda: "rf1022",
        _selected_rf1022_group=lambda: "100_refusjon",
        _effective_mapping=lambda: {},
        _rf1022_group_menu_choices=lambda: [
            ("100_loenn_ol", "Post 100 Lonn o.l."),
            ("100_refusjon", "Post 100 Refusjon"),
            ("111_naturalytelser", "Post 111 Naturalytelser"),
        ],
        _a07_code_menu_choices=lambda: [
            ("fastloenn", "fastloenn - Fast lonn"),
            ("elektroniskKommunikasjon", "elektroniskKommunikasjon - Elektronisk kommunikasjon"),
        ],
        _assign_selected_control_mapping=lambda: None,
        _assign_selected_accounts_to_rf1022_group=lambda _group_id: None,
        _assign_selected_accounts_to_a07_code=lambda _code: None,
        _clear_selected_control_mapping=lambda: None,
        _focus_linked_code_for_selected_gl_account=lambda: None,
        _set_control_gl_scope=lambda _scope: None,
        _run_selected_control_action=lambda: None,
        _apply_best_suggestion_for_selected_code=lambda: None,
        _apply_history_for_selected_code=lambda: None,
        _open_manual_mapping_clicked=lambda: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_gl_context_menu(dummy, SimpleNamespace())

    assert menu is not None
    labels = [label for kind, label, _payload in menu.items if kind in {"command", "cascade"}]
    assert "Velg RF-1022-post" in labels
    assert "Velg A07-kode" in labels
    assert any(
        label.startswith("Tildel til Post 100 Refusjon")
        for kind, label, _payload in menu.items
        if kind == "command"
    )
    rf_menu = next(payload for kind, label, payload in menu.items if kind == "cascade" and label == "Velg RF-1022-post")
    assert [label for kind, label, _payload in rf_menu.items if kind == "command"] == [
        "Post 100 Lonn o.l.",
        "Post 100 Refusjon",
        "Post 111 Naturalytelser",
    ]
    a07_menu = next(payload for kind, label, payload in menu.items if kind == "cascade" and label == "Velg A07-kode")
    assert [label for kind, label, _payload in a07_menu.items if kind == "command"] == [
        "fastloenn - Fast lonn",
        "elektroniskKommunikasjon - Elektronisk kommunikasjon",
    ]


def test_control_account_context_menu_keeps_hidden_button_actions_available(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_command(self, *, label, command=None, state=None) -> None:
            self.items.append(("command", label, state))

        def add_separator(self) -> None:
            self.items.append(("separator", "", None))

    monkeypatch.setattr(a07_context_menu.tk, "Menu", _Menu)
    dummy = SimpleNamespace(
        tree_control_accounts=object(),
        _prepare_tree_context_selection=lambda *args, **kwargs: "5000",
        _selected_control_account_ids=lambda: ["5000"],
        _focus_selected_control_account_in_gl=lambda: None,
        _remove_selected_control_accounts=lambda: None,
        _open_manual_mapping_clicked=lambda: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_accounts_context_menu(dummy, SimpleNamespace())

    assert [label for kind, label, _payload in menu.items if kind == "command"] == [
        "Vis i GL",
        "Fjern valgt",
        "Avansert mapping...",
    ]


def test_control_statement_account_context_menu_keeps_focus_action_available(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_command(self, *, label, command=None, state=None) -> None:
            self.items.append(("command", label, state))

    monkeypatch.setattr(a07_context_menu.tk, "Menu", _Menu)
    dummy = SimpleNamespace(
        tree_control_statement_accounts=object(),
        _prepare_tree_context_selection=lambda *args, **kwargs: "5000",
        _selected_control_statement_account_ids=lambda: ["5000"],
        _focus_selected_control_statement_account_in_gl=lambda: None,
        _post_context_menu=lambda menu, _event: menu,
    )

    menu = page_a07.A07Page._show_control_statement_accounts_context_menu(dummy, SimpleNamespace())

    assert [label for kind, label, _payload in menu.items if kind == "command"] == ["Vis i GL"]


def test_bind_canonical_events_registers_right_click_context_menus() -> None:
    class _Tree:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object, object | None]] = []

        def bind(self, sequence, callback, add=None) -> None:
            self.calls.append((sequence, callback, add))

    tree_control_gl = _Tree()
    tree_a07 = _Tree()
    tree_groups = _Tree()

    dummy = SimpleNamespace(
        tree_control_gl=tree_control_gl,
        tree_a07=tree_a07,
        tree_history=_Tree(),
        tree_control_suggestions=_Tree(),
        tree_suggestions=_Tree(),
        tree_control_accounts=_Tree(),
        tree_control_statement=_Tree(),
        tree_control_statement_accounts=_Tree(),
        tree_unmapped=_Tree(),
        tree_groups=tree_groups,
        tree_mapping=_Tree(),
        _on_control_gl_selection_changed=lambda: None,
        _run_selected_control_gl_action=lambda: None,
        _assign_selected_control_mapping=lambda: None,
        _clear_selected_control_mapping=lambda: None,
        _show_control_gl_context_menu=lambda _event: None,
        _start_control_gl_drag=lambda _event: None,
        _on_control_selection_changed=lambda: None,
        _run_selected_control_action=lambda: None,
        _show_control_code_context_menu=lambda _event: None,
        _track_unmapped_drop_target=lambda _event: None,
        _drop_unmapped_on_control=lambda _event: None,
        _update_history_details_from_selection=lambda: None,
        _apply_selected_history_mapping=lambda: None,
        _apply_selected_suggestion=lambda: None,
        _on_suggestion_selected=lambda: None,
        _focus_selected_control_account_in_gl=lambda: None,
        _open_manual_mapping_clicked=lambda: None,
        _remove_selected_control_accounts=lambda: None,
        _show_control_accounts_context_menu=lambda _event: None,
        _on_control_statement_selected=lambda: None,
        _focus_selected_control_statement_account_in_gl=lambda: None,
        _show_control_statement_accounts_context_menu=lambda _event: None,
        _start_unmapped_drag=lambda _event: None,
        _map_selected_unmapped=lambda: None,
        _on_group_selection_changed=lambda: None,
        _focus_selected_group_code=lambda: None,
        _show_group_context_menu=lambda _event: None,
        _remove_selected_mapping=lambda: None,
    )

    page_a07.A07Page._bind_canonical_events(dummy)

    assert any(sequence == "<Button-3>" for sequence, _callback, _add in tree_control_gl.calls)
    assert any(sequence == "<Button-3>" for sequence, _callback, _add in tree_a07.calls)
    assert any(sequence == "<Button-3>" for sequence, _callback, _add in dummy.tree_control_accounts.calls)
    assert any(sequence == "<Button-3>" for sequence, _callback, _add in dummy.tree_control_statement_accounts.calls)
    assert any(sequence == "<Button-3>" for sequence, _callback, _add in tree_groups.calls)


def test_canonical_control_statement_tab_omits_noisy_header_controls() -> None:
    source = (Path(__file__).resolve().parent.parent / "a07_feature" / "ui" / "canonical_layout.py").read_text(
        encoding="utf-8"
    )
    support_source = source[
        source.index("    def _build_support_notebook") : source.index("    def _build_groups_sidepanel")
    ]

    assert 'control_support_nb.add(self.tab_suggestions, text="Forslag")' in support_source
    assert 'control_support_nb.add(self.tab_mapping, text="Koblinger")' in support_source
    assert "control_support_nb.add(self.tab_history" not in support_source
    assert "control_support_nb.add(self.tab_control_statement" not in support_source
    assert "control_support_nb.add(self.tab_unmapped" not in support_source
    assert "control_statement_top" not in support_source
    assert "control_accounts_top" not in support_source
    assert "control_statement_accounts_top" not in support_source
    assert "RF-1022..." not in support_source
    assert "Åpne vindu" not in support_source
    assert "Visning:" not in support_source
    assert 'text="Vis i GL"' not in support_source
    assert 'text="Fjern valgt"' not in support_source
    assert "suggestions_details" not in support_source
    assert "suggestions_details.pack" not in support_source
    assert "self.tree_control_statement = self._build_tree_tab(self.tab_control_statement" not in support_source
    assert 'text="Konti i kontrolloppstilling"' not in support_source


def test_tools_control_statement_view_menu_routes_to_view_state(monkeypatch) -> None:
    class _Menu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.items: list[tuple[str, str, object | None]] = []

        def add_radiobutton(self, *, label, variable=None, value=None, command=None) -> None:
            self.items.append(("radio", label, (value, command)))

        def add_cascade(self, *, label, menu) -> None:
            self.items.append(("cascade", label, menu))

    monkeypatch.setattr(a07_canonical_layout.tk, "Menu", _Menu)
    calls: list[str] = []
    tools_menu = _Menu()
    dummy = SimpleNamespace(
        control_statement_view_var=object(),
        _set_control_statement_view_from_menu=lambda view: calls.append(view),
    )

    view_menu = page_a07.A07Page._add_control_statement_view_menu(dummy, tools_menu)
    legacy_item = next(payload for kind, label, payload in view_menu.items if kind == "radio" and label == "Legacy analyse")
    legacy_value, legacy_command = legacy_item
    legacy_command()

    assert ("cascade", "Kontrollvisning", view_menu) in tools_menu.items
    assert legacy_value == page_a07.CONTROL_STATEMENT_VIEW_LEGACY
    assert calls == [page_a07.CONTROL_STATEMENT_VIEW_LEGACY]


def test_set_control_statement_view_from_menu_updates_vars_and_refreshes() -> None:
    class _Var:
        def __init__(self, value=None) -> None:
            self.value = value

        def get(self):
            return self.value

        def set(self, value) -> None:
            self.value = value

    calls: list[str] = []
    dummy = SimpleNamespace(
        control_statement_view_var=_Var(),
        control_statement_view_label_var=_Var(),
        control_statement_include_unclassified_var=_Var(False),
        control_statement_view_widget=None,
        _on_control_statement_filter_changed=lambda: calls.append("refresh"),
    )
    dummy._sync_control_statement_view_vars = lambda view: page_a07.A07Page._sync_control_statement_view_vars(dummy, view)

    page_a07.A07Page._set_control_statement_view_from_menu(dummy, page_a07.CONTROL_STATEMENT_VIEW_ALL)

    assert dummy.control_statement_view_var.get() == page_a07.CONTROL_STATEMENT_VIEW_ALL
    assert dummy.control_statement_view_label_var.get() == page_a07._CONTROL_STATEMENT_VIEW_LABELS[page_a07.CONTROL_STATEMENT_VIEW_ALL]
    assert dummy.control_statement_include_unclassified_var.get() is True
    assert calls == ["refresh"]


def test_sync_control_work_level_ui_disables_view_filter_in_rf1022_mode() -> None:
    events: list[tuple[str, str]] = []

    class _Widget:
        def configure(self, **kwargs) -> None:
            if "state" in kwargs:
                events.append(("state", kwargs["state"]))
            if "style" in kwargs:
                events.append(("style", kwargs["style"]))

    dummy = SimpleNamespace(
        _selected_control_work_level=lambda: "rf1022",
        a07_filter_widget=_Widget(),
        lbl_control_view_caption=_Widget(),
    )

    page_a07.A07Page._sync_control_work_level_ui(dummy)

    assert ("state", "disabled") in events
    assert ("style", "Muted.TLabel") in events


def test_track_unmapped_drop_target_marks_drop_target_tag_and_clears_previous() -> None:
    class _Tree:
        def __init__(self) -> None:
            self.rows = {
                "100_loenn_ol": ("family_payroll",),
                "111_naturalytelser": ("family_natural",),
            }

        def get_children(self):
            return tuple(self.rows)

        def item(self, iid, option=None, **kwargs):
            if kwargs:
                if "tags" in kwargs:
                    self.rows[iid] = tuple(kwargs["tags"])
                return None
            if option == "tags":
                return self.rows[iid]
            return {"tags": self.rows[iid]}

        def selection_set(self, _iid) -> None:
            return None

        def focus(self, _iid) -> None:
            return None

        def see(self, _iid) -> None:
            return None

    dummy = SimpleNamespace(
        tree_a07=_Tree(),
        _current_drag_accounts=lambda: ["5800"],
        _tree_iid_from_event=lambda _tree, event: getattr(event, "target", None),
        _set_tree_selection=lambda _tree, _iid: True,
        control_drag_var=SimpleNamespace(set=lambda _value: None),
        lbl_control_drag=SimpleNamespace(configure=lambda **_kwargs: None),
        _control_drop_target_iid=None,
    )
    dummy._set_control_drop_target = lambda iid: page_a07.A07Page._set_control_drop_target(dummy, iid)
    dummy._clear_control_drop_target = lambda: page_a07.A07Page._clear_control_drop_target(dummy)

    page_a07.A07Page._track_unmapped_drop_target(dummy, SimpleNamespace(target="100_loenn_ol"))
    assert dummy.tree_a07.rows["100_loenn_ol"] == ("family_payroll", "drop_target")

    page_a07.A07Page._track_unmapped_drop_target(dummy, SimpleNamespace(target="111_naturalytelser"))
    assert dummy.tree_a07.rows["100_loenn_ol"] == ("family_payroll",)
    assert dummy.tree_a07.rows["111_naturalytelser"] == ("family_natural", "drop_target")

    page_a07.A07Page._clear_control_drag_state(dummy)
    assert dummy.tree_a07.rows["111_naturalytelser"] == ("family_natural",)


def test_apply_best_suggestion_for_selected_code_guides_when_missing() -> None:
    focused: list[str] = []
    statuses: list[str] = []

    class DummyTree:
        def focus_set(self) -> None:
            focused.append("a07")

    class DummyPage:
        tree_a07 = DummyTree()
        tree_control_suggestions = object()
        workspace = SimpleNamespace(suggestions=pd.DataFrame())

        def _selected_control_code(self):
            return "fastloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)
            if focus_widget is not None:
                focus_widget.focus_set()

    page_a07.A07Page._apply_best_suggestion_for_selected_code(DummyPage())

    assert statuses == ["Fant ikke et forslag for valgt kode."]
    assert focused == ["a07"]


def test_apply_best_suggestion_for_selected_code_blocks_locked_code() -> None:
    focused: list[str] = []
    statuses: list[str] = []

    class DummyTree:
        def focus_set(self) -> None:
            focused.append("a07")

    class DummyPage:
        tree_a07 = DummyTree()
        workspace = SimpleNamespace(suggestions=pd.DataFrame([{"Kode": "fastloenn", "WithinTolerance": True}]), locks={"fastloenn"})

        def _selected_control_code(self):
            return "fastloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)
            if focus_widget is not None:
                focus_widget.focus_set()

    page_a07.A07Page._apply_best_suggestion_for_selected_code(DummyPage())

    assert statuses == ["Valgt kode er låst. Lås opp før du bruker forslag."]
    assert focused == ["a07"]


def test_assign_selected_control_mapping_blocks_when_target_code_is_locked() -> None:
    statuses: list[str] = []
    focused: list[str] = []

    class DummyTree:
        def focus_set(self) -> None:
            focused.append("a07")

    class DummyPage:
        tree_control_gl = object()
        tree_a07 = DummyTree()
        workspace = SimpleNamespace(mapping={}, locks={"fastloenn"})

        def _selected_control_gl_accounts(self):
            return ["5000"]

        def _selected_control_code(self):
            return "fastloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)
            if focus_widget is not None:
                focus_widget.focus_set()

    page_a07.A07Page._assign_selected_control_mapping(DummyPage())

    assert statuses == ["Endringen berorer laaste koder: fastloenn. Laas opp for du endrer mapping."]
    assert focused == ["a07"]


def test_remove_selected_group_blocks_when_group_is_still_used_in_mapping() -> None:
    statuses: list[str] = []
    focused_codes: list[str] = []

    class DummyPage:
        tree_groups = object()
        workspace = SimpleNamespace(
            mapping={"5000": "A07_GROUP:fastloenn+timeloenn"},
            groups={"A07_GROUP:fastloenn+timeloenn": object()},
            locks=set(),
        )

        def _selected_group_id(self):
            return "A07_GROUP:fastloenn+timeloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)

        def _focus_control_code(self, code):
            focused_codes.append(code)

    page_a07.A07Page._remove_selected_group(DummyPage())

    assert statuses == ["Kan ikke oppløse gruppe som fortsatt brukes i mapping (1 konto). Fjern eller flytt mapping først."]
    assert focused_codes == ["A07_GROUP:fastloenn+timeloenn"]


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


def test_create_group_from_codes_uses_auto_name_without_prompt(monkeypatch) -> None:
    autosaved: list[bool] = []
    refreshes: list[str | None] = []
    focuses: list[str] = []

    class _Var:
        value = ""

        def set(self, value: str) -> None:
            self.value = value

    def _fail_prompt(*args, **kwargs):
        raise AssertionError("group creation should not prompt for name in the fast path")

    monkeypatch.setattr(page_a07.simpledialog, "askstring", _fail_prompt)

    class DummyPage:
        workspace = SimpleNamespace(groups={})
        tree_a07 = object()
        status_var = _Var()

        def _default_group_name(self, codes):
            assert list(codes) == ["trekkLoennForFerie", "fastloenn"]
            return "Trekk i loenn for ferie + Fastloenn"

        def _next_group_id(self, codes):
            assert list(codes) == ["trekkLoennForFerie", "fastloenn"]
            return "A07_GROUP:trekkLoennForFerie+fastloenn"

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            raise AssertionError(message)

        def _autosave_workspace_state(self) -> None:
            autosaved.append(True)

        def _refresh_core(self, focus_code=None) -> None:
            refreshes.append(focus_code)

        def _focus_control_code(self, code) -> None:
            focuses.append(code)

    dummy = DummyPage()

    out = page_a07.A07Page._create_group_from_codes(dummy, ["trekkLoennForFerie", "fastloenn"])

    assert out == "A07_GROUP:trekkLoennForFerie+fastloenn"
    assert autosaved == [True]
    assert refreshes == ["A07_GROUP:trekkLoennForFerie+fastloenn"]
    assert focuses == ["A07_GROUP:trekkLoennForFerie+fastloenn"]
    assert dummy.workspace.groups[out].group_name == "Trekk i loenn for ferie + Fastloenn"
    assert dummy.workspace.groups[out].member_codes == ["trekkLoennForFerie", "fastloenn"]
    assert "Trekk i loenn for ferie + Fastloenn" in dummy.status_var.value


def test_selected_group_id_falls_back_to_selected_control_group() -> None:
    class _Tree:
        def selection(self):
            return ()

    dummy = SimpleNamespace(
        tree_groups=_Tree(),
        _selected_control_code=lambda: "A07_GROUP:fastloenn+timeloenn",
    )

    out = page_a07.A07Page._selected_group_id(dummy)

    assert out == "A07_GROUP:fastloenn+timeloenn"


def test_locked_mapping_conflicts_uses_effective_group_mapping_and_membership() -> None:
    dummy = type("DummyPage", (), {})()
    dummy.workspace = SimpleNamespace(
        mapping={"5000": "fastloenn"},
        membership={"fastloenn": "A07_GROUP:lonn"},
        locks={"A07_GROUP:lonn"},
    )

    conflicts = page_a07.A07Page._locked_mapping_conflicts(dummy, ["5000"], target_code="fastloenn")

    assert conflicts == ["A07_GROUP:lonn"]


def test_sync_active_tb_clicked_guides_user_inline_when_no_active_trial_balance() -> None:
    statuses: list[str] = []

    class DummyPage:
        tb_path = None

        def _sync_active_trial_balance(self, *, refresh: bool) -> bool:
            assert refresh is True
            return False

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            statuses.append(message)

        @property
        def status_var(self):
            return SimpleNamespace(set=lambda value: statuses.append(value))

    page_a07.A07Page._sync_active_tb_clicked(DummyPage())

    assert statuses == [
        "Fant ingen aktiv saldobalanse for valgt klient/aar. Velg eller opprett den via Dataset -> Versjoner."
    ]


def test_open_saldobalanse_workspace_selects_tab_and_focuses_accounts() -> None:
    selected_pages: list[object] = []
    refresh_calls: list[object] = []
    focus_calls: list[list[str]] = []
    statuses: list[str] = []

    page_saldobalanse = SimpleNamespace(
        refresh_from_session=lambda session_obj=None: refresh_calls.append(session_obj),
        focus_payroll_accounts=lambda accounts: focus_calls.append(list(accounts)),
    )
    host = SimpleNamespace(
        nb=SimpleNamespace(select=lambda page: selected_pages.append(page)),
        page_saldobalanse=page_saldobalanse,
    )
    dummy = SimpleNamespace(
        winfo_toplevel=lambda: host,
        status_var=SimpleNamespace(set=lambda value: statuses.append(value)),
    )

    out = page_a07.A07Page._open_saldobalanse_workspace(
        dummy,
        accounts=["5000", "5210"],
        status_text="Apnet Saldobalanse.",
    )

    assert out is True
    assert selected_pages == [page_saldobalanse]
    assert refresh_calls == [page_a07.session]
    assert focus_calls == [["5000", "5210"]]
    assert statuses == ["Apnet Saldobalanse."]


def test_session_context_falls_back_to_dataset_store_when_session_is_missing() -> None:
    session_obj = SimpleNamespace(client=None, year=None)
    store_section = SimpleNamespace(
        client_var=SimpleNamespace(get=lambda: "Air Management AS"),
        year_var=SimpleNamespace(get=lambda: "2025"),
    )
    host = SimpleNamespace(page_dataset=SimpleNamespace(dp=SimpleNamespace(_store_section=store_section)))
    dummy = SimpleNamespace(winfo_toplevel=lambda: host)

    out = page_a07.A07Page._session_context(dummy, session_obj)

    assert out == ("Air Management AS", "2025")


def test_open_saldobalanse_for_selected_code_classification_uses_selected_code_accounts() -> None:
    calls: list[tuple[list[str], str, str]] = []

    class DummyPage:
        tree_a07 = object()

        def _selected_control_code(self):
            return "fastloenn"

        def _selected_code_accounts(self, code=None):
            assert code == "fastloenn"
            return ["5000", "5001"]

        def _selected_control_row(self):
            return pd.Series({"NesteHandling": "Tildel RF-1022-post i Saldobalanse."})

        def _open_saldobalanse_workspace(self, *, accounts=None, payroll_scope=None, status_text=None):
            calls.append((list(accounts or ()), str(payroll_scope or ""), str(status_text or "")))
            return True

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            raise AssertionError(message)

    page_a07.A07Page._open_saldobalanse_for_selected_code_classification(DummyPage())

    assert calls == [
        (
            ["5000", "5001"],
            classification_workspace.QUEUE_REVIEW,
            "Tildel RF-1022-post i Saldobalanse. A07 viser behovet, men klassifiseringen gjores i Saldobalanse.",
        )
    ]


def test_open_saldobalanse_for_selected_code_classification_uses_suspicious_queue_for_conflicts() -> None:
    calls: list[tuple[list[str], str]] = []

    class DummyPage:
        tree_a07 = object()

        def _selected_control_code(self):
            return "fastloenn"

        def _selected_code_accounts(self, code=None):
            assert code == "fastloenn"
            return ["5000"]

        def _selected_control_row(self):
            return pd.Series({"NesteHandling": "Rydd RF-1022-post for mappede kontoer."})

        def _open_saldobalanse_workspace(self, *, accounts=None, payroll_scope=None, status_text=None):
            calls.append((list(accounts or ()), str(payroll_scope or "")))
            return True

        def _notify_inline(self, message: str, *, focus_widget=None) -> None:
            raise AssertionError(message)

    page_a07.A07Page._open_saldobalanse_for_selected_code_classification(DummyPage())

    assert calls == [(["5000"], classification_workspace.QUEUE_SUSPICIOUS)]


def test_on_control_selection_changed_updates_status_with_connected_accounts_summary() -> None:
    status_calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _is_tree_selection_suppressed=lambda _tree: False,
        tree_a07=object(),
        workspace=SimpleNamespace(selected_code=None, basis_col="Endring"),
        _selected_control_code=lambda: "elektroniskKommunikasjon",
        _update_history_details_from_selection=lambda: None,
        _control_details_visible=False,
        _refresh_in_progress=False,
        _update_control_panel=lambda: None,
        _update_control_transfer_buttons=lambda: None,
        _sync_groups_panel_visibility=lambda: None,
        _schedule_control_selection_followup=lambda: None,
        control_gl_df=pd.DataFrame(
            [
                {"Konto": "5210", "Navn": "Fri telefon", "Endring": 38064.0, "Kode": "elektroniskKommunikasjon"},
            ]
        ),
        status_var=SimpleNamespace(set=lambda value: status_calls.append(value)),
    )

    page_a07.A07Page._on_control_selection_changed(dummy)

    assert dummy.workspace.selected_code == "elektroniskKommunikasjon"
    assert status_calls == [
        "Valgt elektroniskKommunikasjon | 1 konto koblet | Endring 38 064,00 | 5210 Fri telefon"
    ]


def test_focus_selected_control_account_in_gl_focuses_first_account() -> None:
    calls: list[str] = []

    class DummyPage:
        def _selected_control_account_ids(self):
            return ["5000", "5001"]

        def _focus_mapping_account(self, konto):
            calls.append(konto)

    page_a07.A07Page._focus_selected_control_account_in_gl(DummyPage())

    assert calls == ["5000"]


def test_focus_control_code_defers_while_refresh_is_running() -> None:
    dummy = SimpleNamespace(
        _refresh_in_progress=True,
        _pending_focus_code=None,
    )

    page_a07.A07Page._focus_control_code(dummy, "fastloenn")

    assert dummy._pending_focus_code == "fastloenn"


def test_sync_control_account_selection_selects_account_when_present() -> None:
    class DummyTree:
        def __init__(self) -> None:
            self.selected = None
            self.focused = None
            self.seen = None

        def get_children(self) -> tuple[str, ...]:
            return ("5000", "5001")

        def selection_set(self, value: str) -> None:
            self.selected = value

        def focus(self, value: str) -> None:
            self.focused = value

        def see(self, value: str) -> None:
            self.seen = value

    dummy = type("DummyPage", (), {})()
    dummy.tree_control_accounts = DummyTree()

    page_a07.A07Page._sync_control_account_selection(dummy, "5001")

    assert dummy.tree_control_accounts.selected == "5001"
    assert dummy.tree_control_accounts.focused == "5001"
    assert dummy.tree_control_accounts.seen == "5001"


def test_focus_mapping_account_clears_control_gl_filters_when_account_is_hidden() -> None:
    refresh_calls: list[str] = []

    class DummyVar:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

        def set(self, value) -> None:
            self.value = value

    class DummyTree:
        def __init__(self, children=()) -> None:
            self._children = tuple(children)
            self.selected = None
            self.focused = None
            self.seen = None

        def get_children(self):
            return self._children

        def selection_set(self, value: str) -> None:
            self.selected = value

        def focus(self, value: str) -> None:
            self.focused = value

        def see(self, value: str) -> None:
            self.seen = value

    class DummyPage:
        def __init__(self) -> None:
            self.tree_mapping = DummyTree()
            self.tree_control_gl = DummyTree(children=("5000",))
            self.tree_control_accounts = DummyTree(children=("5001",))
            self.control_gl_unmapped_only_var = DummyVar(True)
            self.control_gl_filter_var = DummyVar("bonus")

        def _refresh_control_gl_tree(self) -> None:
            refresh_calls.append("refresh")
            self.tree_control_gl._children = ("5000", "5001")

        def _sync_control_account_selection(self, konto: str) -> None:
            page_a07.A07Page._sync_control_account_selection(self, konto)

    dummy = DummyPage()

    page_a07.A07Page._focus_mapping_account(dummy, "5001")

    assert refresh_calls == ["refresh"]
    assert dummy.control_gl_unmapped_only_var.get() is False
    assert dummy.control_gl_filter_var.get() == ""
    assert dummy.tree_control_gl.selected == "5001"
    assert dummy.tree_control_accounts.selected == "5001"


def test_suggestion_and_reconcile_tree_tags_map_visual_state() -> None:
    suggestion_ok = pd.Series({"WithinTolerance": True, "Score": 0.62, "HistoryAccounts": "5000"})
    suggestion_candidate = pd.Series({"WithinTolerance": True, "Score": 0.62})
    suggestion_review = pd.Series({"WithinTolerance": False, "Score": 0.91})
    suggestion_default = pd.Series({"WithinTolerance": False, "Score": 0.55})
    reconcile_ok = pd.Series({"WithinTolerance": True})
    reconcile_diff = pd.Series({"WithinTolerance": False})

    assert page_a07.suggestion_tree_tag(suggestion_ok) == "suggestion_ok"
    assert page_a07.suggestion_tree_tag(suggestion_candidate) == "suggestion_review"
    assert page_a07.suggestion_tree_tag(suggestion_review) == "suggestion_review"
    assert page_a07.suggestion_tree_tag(suggestion_default) == "suggestion_default"
    assert page_a07.reconcile_tree_tag(reconcile_ok) == "reconcile_ok"
    assert page_a07.reconcile_tree_tag(reconcile_diff) == "reconcile_diff"


def test_tree_iid_from_event_prefers_identified_row_then_selection() -> None:
    class DummyTree:
        def __init__(self) -> None:
            self._selection = ("selected_iid",)

        def identify_row(self, y: int) -> str:
            return "row_from_pointer" if y == 10 else ""

        def selection(self) -> tuple[str, ...]:
            return self._selection

    event = type("Event", (), {"y": 10})()
    fallback_event = type("Event", (), {"y": 0})()
    tree = DummyTree()

    assert page_a07.A07Page._tree_iid_from_event(object(), tree, event) == "row_from_pointer"
    assert page_a07.A07Page._tree_iid_from_event(object(), tree, fallback_event) == "selected_iid"


def test_track_unmapped_drop_target_updates_selection_and_hint() -> None:
    class DummyVar:
        def __init__(self) -> None:
            self.value = ""

        def set(self, value: str) -> None:
            self.value = value

    class DummyLabel:
        def __init__(self) -> None:
            self.style = None

        def configure(self, **kwargs) -> None:
            self.style = kwargs.get("style")

    class DummyTree:
        def __init__(self) -> None:
            self.selected = None
            self.focused = None
            self.seen = None

        def selection_set(self, value: str) -> None:
            self.selected = value

        def focus(self, value: str) -> None:
            self.focused = value

        def see(self, value: str) -> None:
            self.seen = value

    dummy = type("DummyPage", (), {})()
    dummy._drag_unmapped_account = "1000"
    dummy.tree_a07 = DummyTree()
    dummy.control_drag_var = DummyVar()
    dummy.lbl_control_drag = DummyLabel()
    dummy._tree_iid_from_event = lambda tree, event=None: "fastloenn"

    page_a07.A07Page._track_unmapped_drop_target(dummy, object())

    assert dummy.tree_a07.selected == "fastloenn"
    assert dummy.tree_a07.focused == "fastloenn"
    assert dummy.tree_a07.seen == "fastloenn"
    assert dummy.control_drag_var.value == "Slipp konto 1000 paa kode fastloenn."
    assert dummy.lbl_control_drag.style == "Warning.TLabel"


def test_filter_a07_overview_df_keeps_custom_columns_for_control_queue() -> None:
    control_df = pd.DataFrame(
        [
            {"Kode": "bonus", "Status": "Avvik", "NesteHandling": "Map manuelt."},
            {"Kode": "aga", "Status": "Ekskludert", "NesteHandling": "Ingen handling nÃ¸dvendig."},
        ]
    )

    out = page_a07.filter_a07_overview_df(control_df, "uloste")

    assert out.columns.tolist() == ["Kode", "Status", "NesteHandling"]
    assert out["Kode"].tolist() == ["bonus"]


def test_filter_suggestions_df_supports_selected_code_and_unsolved_scope() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "ForslagKontoer": "5000"},
            {"Kode": "bonus", "ForslagKontoer": "5090"},
            {"Kode": "telefon", "ForslagKontoer": "6990"},
        ],
        index=[2, 4, 7],
    )

    selected = page_a07.filter_suggestions_df(
        suggestions_df,
        scope_key="valgt_kode",
        selected_code="bonus",
        unresolved_code_values=["fastloenn", "telefon"],
    )
    unsolved = page_a07.filter_suggestions_df(
        suggestions_df,
        scope_key="uloste",
        selected_code=None,
        unresolved_code_values=["fastloenn", "telefon"],
    )

    assert selected.index.tolist() == [4]
    assert selected["Kode"].tolist() == ["bonus"]
    assert unsolved.index.tolist() == [2, 7]
    assert unsolved["Kode"].tolist() == ["fastloenn", "telefon"]


def test_select_batch_suggestion_rows_picks_only_safe_top_suggestions() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "ForslagKontoer": "5000", "WithinTolerance": True, "Score": 0.93, "SuggestionGuardrail": "accepted"},
            {"Kode": "fastloenn", "ForslagKontoer": "5001", "WithinTolerance": True, "Score": 0.92, "SuggestionGuardrail": "review"},
            {"Kode": "bonus", "ForslagKontoer": "5090", "WithinTolerance": True, "Score": 0.91, "Explain": "regel=bonus"},
            {"Kode": "feriepenger", "ForslagKontoer": "5000", "WithinTolerance": True, "Score": 0.95, "SuggestionGuardrail": "accepted"},
            {"Kode": "telefon", "ForslagKontoer": "6990", "WithinTolerance": False, "Score": 0.99},
            {"Kode": "pensjon", "ForslagKontoer": "5940", "WithinTolerance": True, "Score": 0.70},
        ]
    )

    out = page_a07.select_batch_suggestion_rows(suggestions_df, {"5100": "annet"}, min_score=0.85)

    assert out == [0, 2]


def test_select_magic_wand_suggestion_rows_uses_within_tolerance_without_score_gate() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "ForslagKontoer": "5000", "WithinTolerance": True, "Score": 0.61, "SuggestionGuardrail": "review"},
            {"Kode": "fastloenn", "ForslagKontoer": "5001", "WithinTolerance": True, "Score": 0.95, "SuggestionGuardrail": "accepted"},
            {"Kode": "telefon", "ForslagKontoer": "6990", "WithinTolerance": True, "Score": 0.40, "HistoryAccounts": "6990"},
            {"Kode": "bonus", "ForslagKontoer": "6990", "WithinTolerance": True, "Score": 0.97, "SuggestionGuardrail": "review"},
            {"Kode": "pensjon", "ForslagKontoer": "5940", "WithinTolerance": False, "Score": 0.99, "SuggestionGuardrail": "accepted"},
        ]
    )

    out = page_a07.select_magic_wand_suggestion_rows(
        suggestions_df,
        {"5100": "annet"},
        unresolved_codes=["fastloenn", "telefon", "bonus", "pensjon"],
    )

    assert out == [1, 2]


def test_create_app_exposes_a07_page() -> None:
    app = ui_main.create_app()
    try:
        try:
            app.withdraw()  # type: ignore[attr-defined]
        except Exception:
            pass

        assert hasattr(app, "page_a07")
        assert hasattr(app.page_a07, "refresh_from_session")
        # In headless mode the stub has no real widgets â€” skip detailed checks
        if hasattr(app.page_a07, "nb"):
            assert len(app.page_a07.nb.tabs()) == 0
            assert hasattr(app.page_a07, "tree_control_gl")
            assert hasattr(app.page_a07, "tree_a07")
    finally:
        try:
            app.destroy()  # type: ignore[attr-defined]
        except Exception:
            pass


def test_current_drag_accounts_prefers_control_drag_accounts() -> None:
    dummy = SimpleNamespace(
        _drag_control_accounts=["5000", "5001"],
        _drag_unmapped_account="6990",
    )

    out = page_a07.A07Page._current_drag_accounts(dummy)

    assert out == ["5000", "5001"]


def test_current_drag_accounts_falls_back_to_unmapped_drag_account() -> None:
    dummy = SimpleNamespace(
        _drag_control_accounts=[],
        _drag_unmapped_account="6990",
    )

    out = page_a07.A07Page._current_drag_accounts(dummy)

    assert out == ["6990"]


# Wave-1 compact summary expectations override earlier verbose expectations.
def test_build_control_suggestion_effect_summary_describes_replacement() -> None:
    row = pd.Series({"ForslagKontoer": "5000,5001", "Diff": Decimal("100.00"), "WithinTolerance": False})

    out = page_a07.build_control_suggestion_effect_summary("bonus", ["5090"], row)
    diff_text = page_a07._format_picker_amount(Decimal("100.00"))

    assert out == f"Vil erstatte 5090 med 5000,5001 | Maa vurderes | Diff {diff_text}"


def test_build_control_suggestion_effect_summary_handles_matching_current_mapping() -> None:
    row = pd.Series({"ForslagKontoer": "5001,5000", "Diff": Decimal("0"), "WithinTolerance": True})

    out = page_a07.build_control_suggestion_effect_summary("bonus", ["5000", "5001"], row)
    diff_text = page_a07._format_picker_amount(Decimal("0"))

    assert out == f"Matcher dagens mapping: 5001,5000 | Maa vurderes | Diff {diff_text}"


def test_build_control_accounts_summary_describes_selected_accounts() -> None:
    accounts_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn", "IB": Decimal("0"), "Endring": Decimal("1200"), "UB": Decimal("1200")},
            {"Konto": "5001", "Navn": "Bonus", "IB": Decimal("0"), "Endring": Decimal("300"), "UB": Decimal("300")},
        ]
    )

    out = page_a07.build_control_accounts_summary(accounts_df, "fastloenn")

    assert out == "2 kontoer koblet | Endring 1 500,00 | 5000 Lonn, 5001 Bonus"


def test_build_control_accounts_summary_handles_empty_state() -> None:
    assert (
        page_a07.build_control_accounts_summary(pd.DataFrame(), "fastloenn")
        == "Ingen kontoer er koblet til fastloenn ennÃ¥. Velg kontoer til venstre og trykk ->."
    )
    assert (
        page_a07.build_control_accounts_summary(pd.DataFrame(), None)
        == "Velg A07-kode til hoyre for aa se hva som er koblet na."
    )


def test_poll_support_refresh_clears_state_for_stale_generation() -> None:
    dummy = SimpleNamespace(
        _refresh_generation=3,
        _support_refresh_thread="thread",
        _support_refresh_result={"token": 2},
        _support_views_ready=True,
    )

    page_a07.A07Page._poll_support_refresh(dummy, 2)

    assert dummy._support_refresh_thread is None
    assert dummy._support_refresh_result is None
    assert dummy._support_views_ready is False


def test_refresh_support_views_renders_current_tab_when_payload_is_ready() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _control_details_visible=True,
        _support_views_ready=True,
        _support_views_dirty=False,
        _refresh_in_progress=False,
        _support_refresh_thread=None,
        _render_active_support_tab=lambda: calls.append("render"),
        _schedule_support_refresh=lambda: calls.append("schedule"),
        _start_support_refresh=lambda: calls.append("start"),
    )

    page_a07.A07Page._refresh_support_views(dummy)

    assert calls == ["render"]


def test_refresh_support_views_skips_when_details_are_hidden() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _control_details_visible=False,
        _pending_support_refresh=True,
        _support_views_ready=False,
        _support_views_dirty=True,
        _refresh_in_progress=False,
        _support_refresh_thread=None,
        _render_active_support_tab=lambda: calls.append("render"),
        _schedule_support_refresh=lambda: calls.append("schedule"),
        _start_support_refresh=lambda: calls.append("start"),
    )

    page_a07.A07Page._refresh_support_views(dummy)

    assert calls == []
    assert dummy._pending_support_refresh is False


def test_refresh_support_views_skips_when_support_not_requested() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _control_details_visible=True,
        _support_requested=False,
        _pending_support_refresh=True,
        _support_views_ready=False,
        _support_views_dirty=True,
        _refresh_in_progress=False,
        _support_refresh_thread=None,
        _render_active_support_tab=lambda: calls.append("render"),
        _schedule_support_refresh=lambda: calls.append("schedule"),
        _start_support_refresh=lambda: calls.append("start"),
    )

    page_a07.A07Page._refresh_support_views(dummy)

    assert calls == []
    assert dummy._pending_support_refresh is False


def test_selected_suggestion_row_prefers_control_support_notebook() -> None:
    tab_suggestions = object()
    tree_control = object()

    class _Notebook:
        def select(self) -> str:
            return "suggestions"

        def nametowidget(self, name: str) -> object:
            assert name == "suggestions"
            return tab_suggestions

    def _row_from_tree(tree: object):
        if tree is tree_control:
            return {"Kode": "bonus"}
        return None

    dummy = SimpleNamespace(
        control_support_nb=_Notebook(),
        tab_suggestions=tab_suggestions,
        tree_control_suggestions=tree_control,
        focus_get=lambda: None,
        _selected_suggestion_row_from_tree=_row_from_tree,
    )

    out = page_a07.A07Page._selected_suggestion_row(dummy)

    assert out == {"Kode": "bonus"}


def test_on_control_selection_changed_skips_hidden_detail_refresh() -> None:
    calls: list[str] = []
    workspace = SimpleNamespace(selected_code=None)
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        workspace=workspace,
        _selected_control_code=lambda: "70",
        _update_history_details_from_selection=lambda: calls.append("history"),
        _support_views_ready=False,
        _active_support_tab_key=lambda: "history",
        _refresh_suggestions_tree=lambda: calls.append("support_suggestions"),
        _control_details_visible=False,
        _refresh_control_support_trees=lambda: calls.append("detail_support"),
        _retag_control_gl_tree=lambda: False,
        _refresh_control_gl_tree=lambda: calls.append("gl"),
        _update_control_panel=lambda: calls.append("panel"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
    )

    page_a07.A07Page._on_control_selection_changed(dummy)

    assert workspace.selected_code == "70"
    assert "detail_support" not in calls
    assert calls == ["history", "panel", "buttons"]


def test_schedule_control_selection_followup_skips_support_when_not_requested() -> None:
    calls: list[str] = []

    class _Dummy:
        _skip_initial_control_followup = False
        _control_details_visible = True
        _support_requested = False
        _support_views_ready = False

        def _cancel_scheduled_job(self, *_args, **_kwargs):
            return None

        def after(self, _delay, callback):
            callback()
            return "job"

        def _diag(self, _message):
            return None

        def _active_support_tab_key(self):
            return "history"

        def _refresh_suggestions_tree(self):
            calls.append("suggestions")

        def _refresh_control_support_trees(self):
            calls.append("support")

        def _schedule_support_refresh(self):
            calls.append("schedule_support")

        def _retag_control_gl_tree(self):
            calls.append("retag")
            return True

        def _schedule_control_gl_refresh(self, delay_ms=0):
            calls.append(f"gl:{delay_ms}")

        def _update_control_transfer_buttons(self):
            calls.append("buttons")

    page_a07.A07Page._schedule_control_selection_followup(_Dummy())

    assert calls == ["buttons"]


def test_on_control_gl_selection_changed_skips_code_sync_while_refresh_runs() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _refresh_in_progress=True,
        control_gl_df=pd.DataFrame([{"Konto": "5000", "Kode": "70"}]),
        _selected_control_gl_account=lambda: "5000",
        _sync_control_account_selection=lambda konto: calls.append(f"sync:{konto}"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
    )

    page_a07.A07Page._on_control_gl_selection_changed(dummy)

    assert calls == ["sync:5000", "buttons"]


def test_update_control_transfer_buttons_enables_assign_in_rf1022_mode_when_group_selected() -> None:
    states: list[tuple[str, tuple[str, ...]]] = []

    class _Button:
        def __init__(self, name: str) -> None:
            self.name = name

        def state(self, values):
            states.append((self.name, tuple(values)))

    dummy = SimpleNamespace(
        btn_control_assign=_Button("assign"),
        btn_control_clear=_Button("clear"),
        _selected_control_work_level=lambda: "rf1022",
        _selected_control_gl_accounts=lambda: ["5000"],
        _selected_rf1022_group=lambda: "100_loenn_ol",
        _selected_control_code=lambda: "fastloenn",
        _effective_mapping=lambda: {"5000": "fastloenn"},
    )

    page_a07.A07Page._update_control_transfer_buttons(dummy)

    assert ("assign", ("!disabled",)) in states
    assert ("clear", ("!disabled",)) in states


def test_on_control_gl_selection_changed_keeps_selected_work_code() -> None:
    calls: list[str] = []
    status_calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _refresh_in_progress=False,
        control_gl_df=pd.DataFrame([{"Konto": "5000", "Kode": "fastloenn"}]),
        _selected_control_gl_account=lambda: "5000",
        _sync_control_account_selection=lambda konto: calls.append(f"sync:{konto}"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _selected_control_code=lambda: "feriepenger",
        status_var=SimpleNamespace(set=lambda value: status_calls.append(value)),
    )

    page_a07.A07Page._on_control_gl_selection_changed(dummy)

    assert calls == ["sync:5000", "buttons"]
    assert status_calls == ["Konto 5000 er koblet til fastloenn. HÃ¸yre side er fortsatt valgt arbeidskode."]


def test_on_control_gl_selection_changed_keeps_selected_work_code() -> None:
    calls: list[str] = []
    status_calls: list[str] = []
    focus_calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _refresh_in_progress=False,
        control_gl_df=pd.DataFrame([{"Konto": "5000", "Kode": "fastloenn"}]),
        _selected_control_gl_accounts=lambda: ["5000"],
        _selected_control_gl_account=lambda: "5000",
        _sync_control_account_selection=lambda konto: calls.append(f"sync:{konto}"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _selected_control_code=lambda: "feriepenger",
        _focus_control_code=lambda code: focus_calls.append(code),
        status_var=SimpleNamespace(set=lambda value: status_calls.append(value)),
    )

    page_a07.A07Page._on_control_gl_selection_changed(dummy)

    assert calls == ["sync:5000", "buttons"]
    assert focus_calls == ["fastloenn"]
    assert status_calls == ["Konto 5000 er koblet til fastloenn. Viser den koden til hoyre."]


def test_on_control_gl_selection_changed_keeps_work_code_for_multi_select() -> None:
    calls: list[str] = []
    status_calls: list[str] = []
    focus_calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _refresh_in_progress=False,
        control_gl_df=pd.DataFrame([{"Konto": "5000", "Kode": "fastloenn"}]),
        _selected_control_gl_accounts=lambda: ["5000", "5001"],
        _selected_control_gl_account=lambda: "5000",
        _sync_control_account_selection=lambda konto: calls.append(f"sync:{konto}"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _selected_control_code=lambda: "feriepenger",
        _focus_control_code=lambda code: focus_calls.append(code),
        status_var=SimpleNamespace(set=lambda value: status_calls.append(value)),
    )

    page_a07.A07Page._on_control_gl_selection_changed(dummy)

    assert calls == ["sync:5000", "buttons"]
    assert focus_calls == []
    assert status_calls == ["2 kontoer er valgt. Hoyre side er fortsatt valgt arbeidskode."]


def test_on_control_gl_selection_changed_keeps_selected_work_code() -> None:
    calls: list[str] = []
    status_calls: list[str] = []
    focus_calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _refresh_in_progress=False,
        control_gl_df=pd.DataFrame([{"Konto": "5000", "Kode": "fastloenn"}]),
        _selected_control_gl_accounts=lambda: ["5000"],
        _selected_control_gl_account=lambda: "5000",
        _sync_control_account_selection=lambda konto: calls.append(f"sync:{konto}"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _selected_control_code=lambda: "feriepenger",
        _focus_control_code=lambda code: focus_calls.append(code),
        status_var=SimpleNamespace(set=lambda value: status_calls.append(value)),
    )

    page_a07.A07Page._on_control_gl_selection_changed(dummy)

    assert calls == ["sync:5000", "buttons"]
    assert focus_calls == []
    assert status_calls == ["Konto 5000 er koblet til fastloenn. Bruk hoyreklikk for aa vise koden eller endre kobling."]


def test_on_control_gl_selection_changed_keeps_work_code_for_multi_select() -> None:
    calls: list[str] = []
    status_calls: list[str] = []
    focus_calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _refresh_in_progress=False,
        control_gl_df=pd.DataFrame(
            [
                {"Konto": "5000", "Kode": "fastloenn"},
                {"Konto": "5001", "Kode": "fastloenn"},
            ]
        ),
        _selected_control_gl_accounts=lambda: ["5000", "5001"],
        _selected_control_gl_account=lambda: "5000",
        _sync_control_account_selection=lambda konto: calls.append(f"sync:{konto}"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _selected_control_code=lambda: "feriepenger",
        _focus_control_code=lambda code: focus_calls.append(code),
        status_var=SimpleNamespace(set=lambda value: status_calls.append(value)),
    )

    page_a07.A07Page._on_control_gl_selection_changed(dummy)

    assert calls == ["sync:5000", "buttons"]
    assert focus_calls == []
    assert status_calls == ["2 kontoer er valgt og er koblet til fastloenn."]


def test_on_control_selection_changed_prefers_retagging_gl_tree() -> None:
    calls: list[str] = []
    workspace = SimpleNamespace(selected_code=None)
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        workspace=workspace,
        _selected_control_code=lambda: "70",
        _update_history_details_from_selection=lambda: calls.append("history"),
        _support_views_ready=False,
        _active_support_tab_key=lambda: "history",
        _refresh_suggestions_tree=lambda: calls.append("support_suggestions"),
        _control_details_visible=False,
        _refresh_control_support_trees=lambda: calls.append("detail_support"),
        _retag_control_gl_tree=lambda: True,
        _refresh_control_gl_tree=lambda: calls.append("gl"),
        _update_control_panel=lambda: calls.append("panel"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
    )

    page_a07.A07Page._on_control_selection_changed(dummy)

    assert workspace.selected_code == "70"
    assert calls == ["history", "panel", "buttons"]


def test_on_suggestion_selected_prefers_retagging_gl_tree() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _update_selected_suggestion_details=lambda: calls.append("details"),
        _retag_control_gl_tree=lambda: True,
        _refresh_control_gl_tree=lambda: calls.append("gl"),
        tree_control_suggestions=None,
        _update_history_details_from_selection=lambda: calls.append("history"),
    )

    page_a07.A07Page._on_suggestion_selected(dummy)

    assert calls == ["details", "history"]


def test_on_suggestion_selected_does_not_require_missing_highlight_helper() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _update_selected_suggestion_details=lambda: calls.append("details"),
        _retag_control_gl_tree=lambda: True,
        _refresh_control_gl_tree=lambda: calls.append("gl"),
        tree_control_suggestions=object(),
        tree_a07=object(),
        a07_overview_df=pd.DataFrame(),
        workspace=SimpleNamespace(gl_df=pd.DataFrame(), basis_col="Endring"),
        _selected_code_from_tree=lambda _tree: "fastloenn",
        _selected_suggestion_row_from_tree=lambda _tree: pd.Series({"Kode": "fastloenn", "WithinTolerance": True}),
        _ensure_suggestion_display_fields=lambda: pd.DataFrame([{"Kode": "fastloenn", "WithinTolerance": True}]),
        control_suggestion_summary_var=SimpleNamespace(set=lambda _value: calls.append("summary")),
        control_suggestion_effect_var=SimpleNamespace(set=lambda _value: calls.append("effect")),
        _effective_mapping=lambda: {"5000": "fastloenn"},
        _effective_previous_mapping=lambda: {},
        _update_history_details_from_selection=lambda: calls.append("history"),
    )

    page_a07.A07Page._on_suggestion_selected(dummy)

    assert calls == ["details", "summary", "effect", "history"]


def test_apply_core_refresh_payload_clears_pending_support_refresh() -> None:
    scheduled: list[str] = []

    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value):
            self.value = value

    class _Tree:
        def __init__(self) -> None:
            self._children = ()

        def get_children(self):
            return self._children

    dummy = SimpleNamespace(
        rulebook_path=None,
        matcher_settings={},
        previous_mapping={},
        previous_mapping_path=None,
        previous_mapping_year=None,
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(),
            membership={},
            suggestions=pd.DataFrame(),
            basis_col="Endring",
        ),
        control_gl_df=pd.DataFrame(),
        a07_overview_df=pd.DataFrame(),
        control_df=pd.DataFrame(columns=["Kode"]),
        groups_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        unmapped_df=pd.DataFrame(),
        mapping_df=pd.DataFrame(),
        history_compare_df=pd.DataFrame(),
        tree_groups=_Tree(),
        tree_control_suggestions=_Tree(),
        tree_control_accounts=_Tree(),
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        _refresh_control_gl_tree=lambda: scheduled.append("gl"),
        _refresh_a07_tree=lambda: scheduled.append("a07"),
        _fill_tree=lambda *args, **kwargs: scheduled.append("fill"),
        _update_control_panel=lambda: scheduled.append("panel"),
        _update_control_transfer_buttons=lambda: scheduled.append("buttons"),
        _update_summary=lambda: scheduled.append("summary"),
        _support_views_ready=True,
        _support_views_dirty=False,
        _loaded_support_tabs={"history"},
        _refresh_in_progress=True,
        _pending_focus_code=None,
        _pending_support_refresh=True,
        _control_details_visible=True,
        after_idle=lambda cb: scheduled.append("after_idle"),
        _schedule_support_refresh=lambda: scheduled.append("support"),
        _pending_session_refresh=False,
    )

    payload = {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert dummy._pending_support_refresh is False
    assert "support" not in scheduled


def test_apply_core_refresh_payload_tolerates_missing_optional_support_trees() -> None:
    scheduled: list[str] = []

    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value) -> None:
            self.value = value

    class _Tree:
        def get_children(self):
            return ()

    dummy = SimpleNamespace(
        rulebook_path=None,
        matcher_settings={},
        previous_mapping={},
        previous_mapping_path=None,
        previous_mapping_year=None,
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(),
            membership={},
            suggestions=pd.DataFrame(),
            basis_col="Endring",
        ),
        control_gl_df=pd.DataFrame(),
        a07_overview_df=pd.DataFrame(),
        control_df=pd.DataFrame(columns=["Kode"]),
        groups_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        unmapped_df=pd.DataFrame(),
        mapping_df=pd.DataFrame(),
        history_compare_df=pd.DataFrame(),
        control_statement_base_df=pd.DataFrame(),
        control_statement_df=pd.DataFrame(),
        control_statement_accounts_df=pd.DataFrame(),
        tree_a07=_Tree(),
        tree_control_suggestions=_Tree(),
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        control_statement_accounts_summary_var=_Var(),
        control_statement_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        control_statement_include_unclassified_var=SimpleNamespace(get=lambda: False),
        _build_current_control_statement_df=lambda include_unclassified=False: pd.DataFrame(),
        _refresh_control_gl_tree=lambda: scheduled.append("gl"),
        _refresh_a07_tree=lambda: scheduled.append("a07"),
        _fill_tree=lambda *args, **kwargs: scheduled.append("fill"),
        _update_control_panel=lambda: scheduled.append("panel"),
        _update_control_transfer_buttons=lambda: scheduled.append("buttons"),
        _update_summary=lambda: scheduled.append("summary"),
        _support_views_ready=True,
        _support_views_dirty=False,
        _loaded_support_tabs=set(),
        _refresh_in_progress=True,
        _pending_focus_code=None,
        _pending_support_refresh=False,
        _control_details_visible=True,
        _pending_session_refresh=False,
        _cancel_refresh_watchdog=lambda: scheduled.append("cancel_watchdog"),
        _diag=lambda *_args, **_kwargs: None,
        _context_has_changed=lambda: False,
        _set_control_details_visible=lambda visible: scheduled.append(f"details:{visible}"),
        _selected_control_code=lambda: None,
    )

    payload = {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "effective_mapping": {},
        "effective_previous_mapping": {},
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "reconcile_df": pd.DataFrame(),
        "mapping_df": pd.DataFrame(),
        "unmapped_df": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
        "control_statement_df": pd.DataFrame(),
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert "summary" in scheduled
    assert dummy._refresh_in_progress is False


def test_apply_core_refresh_payload_keeps_full_control_statement_base_for_non_payroll_view() -> None:
    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value) -> None:
            self.value = value

    base_df = pd.DataFrame(
        [
            {"Gruppe": "100_loenn_ol", "Navn": "Post 100", "Endring": 100.0, "AntallKontoer": 1},
            {"Gruppe": "Skyldig MVA", "Navn": "Skyldig MVA", "Endring": 50.0, "AntallKontoer": 1},
        ]
    )
    legacy_df = pd.DataFrame(
        [
            {"Gruppe": "Skyldig MVA", "Navn": "Skyldig MVA", "Endring": 50.0, "AntallKontoer": 1},
        ]
    )

    dummy = SimpleNamespace(
        rulebook_path=None,
        matcher_settings={},
        previous_mapping={},
        previous_mapping_path=None,
        previous_mapping_year=None,
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(),
            membership={},
            suggestions=pd.DataFrame(),
            basis_col="Endring",
        ),
        control_gl_df=pd.DataFrame(),
        a07_overview_df=pd.DataFrame(),
        control_df=pd.DataFrame(columns=["Kode"]),
        groups_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        unmapped_df=pd.DataFrame(),
        mapping_df=pd.DataFrame(),
        history_compare_df=pd.DataFrame(),
        control_statement_base_df=pd.DataFrame(),
        control_statement_df=pd.DataFrame(),
        control_statement_accounts_df=pd.DataFrame(),
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        control_statement_accounts_summary_var=_Var(),
        control_statement_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        _selected_control_statement_view=lambda: page_a07.CONTROL_STATEMENT_VIEW_LEGACY,
        _build_current_control_statement_df=lambda **_kwargs: legacy_df.copy(deep=True),
        _support_views_ready=True,
        _support_views_dirty=False,
        _history_compare_ready=False,
        _loaded_support_tabs=set(),
        _refresh_in_progress=True,
        _pending_focus_code=None,
        _pending_support_refresh=False,
        _pending_session_refresh=False,
        _control_details_visible=False,
        _update_history_details_from_selection=lambda: None,
        _update_control_panel=lambda: None,
        _update_control_transfer_buttons=lambda: None,
        _update_summary=lambda: None,
        _refresh_control_gl_tree=lambda: None,
        _refresh_a07_tree=lambda: None,
        after_idle=lambda _callback: None,
    )

    payload = {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "effective_mapping": {},
        "effective_previous_mapping": {},
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "reconcile_df": pd.DataFrame(),
        "mapping_df": pd.DataFrame(),
        "unmapped_df": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
        "control_statement_base_df": base_df,
        "control_statement_df": base_df.iloc[[0]].copy(deep=True),
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert dummy.control_statement_base_df["Gruppe"].tolist() == ["100_loenn_ol", "Skyldig MVA"]
    assert dummy.control_statement_df["Gruppe"].tolist() == ["Skyldig MVA"]


def test_apply_core_refresh_payload_refreshes_support_windows() -> None:
    scheduled: list[str] = []

    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value) -> None:
            self.value = value

    class _Tree:
        def get_children(self):
            return ()

    dummy = SimpleNamespace(
        rulebook_path=None,
        matcher_settings={},
        previous_mapping={},
        previous_mapping_path=None,
        previous_mapping_year=None,
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(),
            membership={},
            suggestions=pd.DataFrame(),
            basis_col="Endring",
        ),
        control_gl_df=pd.DataFrame(),
        a07_overview_df=pd.DataFrame(),
        control_df=pd.DataFrame(columns=["Kode"]),
        groups_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        unmapped_df=pd.DataFrame(),
        mapping_df=pd.DataFrame(),
        history_compare_df=pd.DataFrame(),
        control_statement_base_df=pd.DataFrame(),
        control_statement_df=pd.DataFrame(),
        control_statement_accounts_df=pd.DataFrame(),
        tree_a07=_Tree(),
        tree_groups=_Tree(),
        tree_control_suggestions=_Tree(),
        tree_control_accounts=_Tree(),
        tree_control_statement_accounts=_Tree(),
        tree_mapping=_Tree(),
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        control_statement_accounts_summary_var=_Var(),
        control_statement_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        _selected_control_statement_view=lambda: page_a07.CONTROL_STATEMENT_VIEW_PAYROLL,
        _selected_control_work_level=lambda: "a07",
        _build_current_control_statement_df=lambda **_kwargs: pd.DataFrame(),
        _support_views_ready=True,
        _support_views_dirty=False,
        _history_compare_ready=False,
        _loaded_support_tabs=set(),
        _refresh_in_progress=True,
        _pending_focus_code=None,
        _pending_support_refresh=False,
        _pending_session_refresh=False,
        _control_details_visible=False,
        _update_history_details_from_selection=lambda: None,
        _update_control_panel=lambda: scheduled.append("panel"),
        _update_control_transfer_buttons=lambda: scheduled.append("buttons"),
        _update_summary=lambda: scheduled.append("summary"),
        _refresh_control_gl_tree=lambda: scheduled.append("gl"),
        _refresh_a07_tree=lambda: scheduled.append("a07"),
        _refresh_rf1022_window=lambda: scheduled.append("rf1022_window"),
        _refresh_control_statement_window=lambda: scheduled.append("control_statement_window"),
        _fill_tree=lambda *args, **kwargs: scheduled.append("fill"),
        _cancel_refresh_watchdog=lambda: scheduled.append("cancel_watchdog"),
        _diag=lambda *_args, **_kwargs: None,
        _context_has_changed=lambda: False,
        _set_control_details_visible=lambda visible: scheduled.append(f"details:{visible}"),
        _selected_control_code=lambda: None,
        after_idle=lambda _callback: None,
    )

    payload = {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "effective_mapping": {},
        "effective_previous_mapping": {},
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "reconcile_df": pd.DataFrame(),
        "mapping_df": pd.DataFrame(),
        "unmapped_df": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
        "control_statement_base_df": pd.DataFrame(),
        "control_statement_df": pd.DataFrame(),
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert "rf1022_window" in scheduled
    assert "control_statement_window" in scheduled


def test_apply_core_refresh_payload_refreshes_support_trees_for_initial_selected_code() -> None:
    scheduled: list[str] = []

    class _Var:
        def __init__(self) -> None:
            self.value = None

        def set(self, value) -> None:
            self.value = value

    class _Tree:
        def __init__(self, children=()) -> None:
            self._children = tuple(children)

        def get_children(self):
            return self._children

    dummy = SimpleNamespace(
        rulebook_path=None,
        matcher_settings={},
        previous_mapping={},
        previous_mapping_path=None,
        previous_mapping_year=None,
        workspace=SimpleNamespace(
            a07_df=pd.DataFrame(),
            membership={},
            suggestions=pd.DataFrame(),
            basis_col="Endring",
            selected_code=None,
        ),
        control_gl_df=pd.DataFrame(),
        a07_overview_df=pd.DataFrame(),
        control_df=pd.DataFrame(columns=["Kode"]),
        groups_df=pd.DataFrame(),
        reconcile_df=pd.DataFrame(),
        unmapped_df=pd.DataFrame(),
        mapping_df=pd.DataFrame(),
        history_compare_df=pd.DataFrame(),
        control_statement_base_df=pd.DataFrame(),
        control_statement_df=pd.DataFrame(),
        control_statement_accounts_df=pd.DataFrame(),
        tree_a07=_Tree(children=("timeleonn",)),
        tree_groups=_Tree(),
        tree_control_suggestions=_Tree(),
        tree_control_accounts=_Tree(),
        tree_control_statement_accounts=_Tree(),
        tree_mapping=_Tree(),
        control_suggestion_summary_var=_Var(),
        control_suggestion_effect_var=_Var(),
        control_accounts_summary_var=_Var(),
        control_statement_accounts_summary_var=_Var(),
        control_statement_summary_var=_Var(),
        status_var=_Var(),
        details_var=_Var(),
        _selected_control_statement_view=lambda: page_a07.CONTROL_STATEMENT_VIEW_PAYROLL,
        _selected_control_work_level=lambda: "a07",
        _build_current_control_statement_df=lambda **_kwargs: pd.DataFrame(),
        _support_views_ready=True,
        _support_views_dirty=False,
        _history_compare_ready=False,
        _loaded_support_tabs=set(),
        _refresh_in_progress=True,
        _pending_focus_code=None,
        _pending_support_refresh=False,
        _pending_session_refresh=False,
        _control_details_visible=True,
        _skip_initial_control_followup=False,
        _update_history_details_from_selection=lambda: scheduled.append("history"),
        _update_control_panel=lambda: scheduled.append("panel"),
        _update_control_transfer_buttons=lambda: scheduled.append("buttons"),
        _update_summary=lambda: scheduled.append("summary"),
        _refresh_control_gl_tree=lambda: scheduled.append("gl"),
        _refresh_a07_tree=lambda: scheduled.append("a07"),
        _refresh_rf1022_window=lambda: scheduled.append("rf1022_window"),
        _refresh_control_statement_window=lambda: scheduled.append("control_statement_window"),
        _refresh_control_support_trees=lambda: scheduled.append("support_trees"),
        _render_active_support_tab=lambda force=False: scheduled.append(f"render:{force}"),
        _active_support_tab_key=lambda: "mapping",
        _fill_tree=lambda *args, **kwargs: scheduled.append("fill"),
        _cancel_refresh_watchdog=lambda: scheduled.append("cancel_watchdog"),
        _diag=lambda *_args, **_kwargs: None,
        _context_has_changed=lambda: False,
        _set_control_details_visible=lambda visible: scheduled.append(f"details:{visible}"),
        _set_tree_selection=lambda _tree, target: scheduled.append(f"select:{target}"),
        after_idle=lambda _callback: None,
    )

    payload = {
        "rulebook_path": None,
        "matcher_settings": {},
        "previous_mapping": {},
        "previous_mapping_path": None,
        "previous_mapping_year": None,
        "effective_mapping": {},
        "effective_previous_mapping": {},
        "grouped_a07_df": pd.DataFrame(),
        "membership": {},
        "suggestions": pd.DataFrame(),
        "reconcile_df": pd.DataFrame(),
        "mapping_df": pd.DataFrame(),
        "unmapped_df": pd.DataFrame(),
        "control_gl_df": pd.DataFrame(),
        "a07_overview_df": pd.DataFrame(),
        "control_df": pd.DataFrame(columns=["Kode"]),
        "groups_df": pd.DataFrame(),
        "control_statement_df": pd.DataFrame(),
    }

    page_a07.A07Page._apply_core_refresh_payload(dummy, payload)

    assert "select:timeleonn" in scheduled
    assert "support_trees" in scheduled
    assert "render:True" in scheduled
    assert dummy.workspace.selected_code == "timeleonn"
    assert dummy._skip_initial_control_followup is False


def test_control_statement_module_exports_tk_for_window_opening() -> None:
    assert getattr(page_a07_control_statement, "tk", None) is not None
    assert getattr(page_a07_control_statement.tk, "Toplevel", None) is not None


def test_sync_control_statement_tab_layout_keeps_overview_hidden_in_compact_tab() -> None:
    class _Frame:
        def __init__(self) -> None:
            self.visible = True

        def winfo_manager(self):
            return "pack" if self.visible else ""

        def pack_forget(self) -> None:
            self.visible = False

        def pack(self, *args, **kwargs) -> None:
            self.visible = True

    class _Panel:
        def __init__(self) -> None:
            self.visible = False

        def winfo_manager(self):
            return "pack" if self.visible else ""

        def pack(self, *args, **kwargs) -> None:
            self.visible = True

    frame = _Frame()
    panel = _Panel()
    dummy = SimpleNamespace(
        tree_control_statement=SimpleNamespace(master=frame),
        control_statement_accounts_panel=panel,
    )

    page_a07.A07Page._sync_control_statement_tab_layout(dummy)

    assert frame.visible is False
    assert panel.visible is True


def test_selected_control_statement_group_follows_rf1022_or_selected_a07_row() -> None:
    dummy = SimpleNamespace(
        _selected_control_work_level=lambda: "rf1022",
        _selected_rf1022_group=lambda: "100_loenn_ol",
        tree_control_statement=SimpleNamespace(selection=lambda: ()),
    )

    assert page_a07.A07Page._selected_control_statement_group(dummy) == "100_loenn_ol"

    dummy = SimpleNamespace(
        _selected_control_work_level=lambda: "a07",
        _selected_control_row=lambda: pd.Series({"Rf1022GroupId": "112_pensjon"}),
        tree_control_statement=SimpleNamespace(selection=lambda: ()),
    )

    assert page_a07.A07Page._selected_control_statement_group(dummy) == "112_pensjon"


def test_selected_control_alternative_mode_falls_back_to_var_without_widget() -> None:
    dummy = SimpleNamespace(
        control_alternative_mode_var=SimpleNamespace(get=lambda: "history"),
    )

    out = page_a07.A07Page._selected_control_alternative_mode(dummy)

    assert out == "history"


def test_sync_control_alternative_view_updates_history_mode_and_summary_without_widget_routing() -> None:
    class _Var:
        def __init__(self, value: str) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

        def set(self, value: str) -> None:
            self.value = value

    class _Notebook:
        def __init__(self, selected):
            self.selected_widget = selected

        def select(self):
            return "current"

        def nametowidget(self, _name):
            return self.selected_widget

    suggestions_frame = object()
    history_frame = object()
    summary_var = _Var("")
    mode_var = _Var("")
    mode_label_var = _Var("")
    dummy = SimpleNamespace(
        _selected_control_alternative_mode=lambda: "history",
        _active_support_tab_key=page_a07.A07Page._active_support_tab_key,
        _control_details_visible=True,
        control_support_nb=_Notebook(history_frame),
        tab_suggestions=suggestions_frame,
        tab_history=history_frame,
        control_alternative_mode_var=mode_var,
        control_alternative_mode_label_var=mode_label_var,
        history_details_var=_Var("Historikk finnes for valgt kode."),
        control_suggestion_summary_var=_Var("Beste forslag"),
        control_alternative_summary_var=summary_var,
    )

    page_a07.A07Page._sync_control_alternative_view(dummy)

    assert mode_var.get() == "history"
    assert mode_label_var.get() == page_a07._CONTROL_ALTERNATIVE_MODE_LABELS["history"]
    assert summary_var.get() == "Historikk finnes for valgt kode."


def test_active_support_tab_key_reads_direct_notebook_tab_keys() -> None:
    class _Notebook:
        def __init__(self, selected):
            self.selected_widget = selected

        def select(self):
            return "current"

        def nametowidget(self, _name):
            return self.selected_widget

    mapping_tab = object()
    dummy = SimpleNamespace(
        _control_details_visible=True,
        control_support_nb=_Notebook(mapping_tab),
        tab_suggestions=object(),
        tab_history=object(),
        tab_mapping=mapping_tab,
        tab_control_statement=object(),
        tab_unmapped=object(),
    )

    out = page_a07.A07Page._active_support_tab_key(dummy)

    assert out == "mapping"


def test_select_support_tab_key_routes_groups_to_side_panel_without_notebook_select() -> None:
    calls: list[str] = []

    class _GroupsTree:
        def focus_set(self) -> None:
            calls.append("focus_groups")

    class _Notebook:
        def select(self, _target) -> None:
            calls.append("select_notebook")

    dummy = SimpleNamespace(
        control_support_nb=_Notebook(),
        tree_groups=_GroupsTree(),
        _refresh_groups_tree=lambda: calls.append("refresh_groups"),
        _sync_groups_panel_visibility=lambda: calls.append("sync_groups"),
    )

    page_a07.A07Page._select_support_tab_key(dummy, "groups")

    assert calls == ["focus_groups", "refresh_groups", "sync_groups"]


def test_select_support_tab_key_routes_legacy_tabs_to_visible_mapping_tab() -> None:
    calls: list[object] = []

    class _Notebook:
        def select(self, target) -> None:
            calls.append(target)

    mapping_tab = object()
    dummy = SimpleNamespace(
        control_support_nb=_Notebook(),
        tab_mapping=mapping_tab,
        _support_views_ready=False,
        _schedule_support_refresh=lambda: calls.append("refresh"),
    )

    page_a07.A07Page._select_support_tab_key(dummy, "reconcile")

    assert calls == [mapping_tab, "refresh"]


def test_sync_support_notebook_tabs_hides_advanced_tabs_by_default() -> None:
    calls: list[tuple[object, str]] = []

    class _Notebook:
        def tab(self, tab, **kwargs):
            for key, value in kwargs.items():
                calls.append((tab, f"{key}:{value}"))

        def select(self, target):
            calls.append((target, "select"))

    history_tab = object()
    unmapped_tab = object()
    mapping_tab = object()
    suggestions_tab = object()
    dummy = SimpleNamespace(
        control_support_nb=_Notebook(),
        _control_advanced_visible=False,
        tab_suggestions=suggestions_tab,
        tab_history=history_tab,
        tab_unmapped=unmapped_tab,
        tab_mapping=mapping_tab,
        _active_support_tab_key=lambda: "history",
    )

    page_a07.A07Page._sync_support_notebook_tabs(dummy)

    assert (suggestions_tab, "text:Forslag") in calls
    assert (mapping_tab, "text:Koblinger") in calls
    assert (suggestions_tab, "select") in calls
    assert not any(call[0] in {history_tab, unmapped_tab} for call in calls)


def test_sync_support_notebook_tabs_updates_labels_for_rf1022_mode() -> None:
    tab_calls: list[tuple[object, str, str]] = []

    class _Notebook:
        def tab(self, tab, **kwargs):
            for key, value in kwargs.items():
                tab_calls.append((tab, key, value))

    suggestions_tab = object()
    mapping_tab = object()
    control_tab = object()
    dummy = SimpleNamespace(
        control_support_nb=_Notebook(),
        _control_advanced_visible=False,
        _selected_control_work_level=lambda: "rf1022",
        tab_suggestions=suggestions_tab,
        tab_mapping=mapping_tab,
        tab_control_statement=control_tab,
        tab_history=None,
        tab_unmapped=None,
        _active_support_tab_key=lambda: "suggestions",
    )

    page_a07.A07Page._sync_support_notebook_tabs(dummy)

    assert (suggestions_tab, "text", "Forslag") in tab_calls
    assert (mapping_tab, "text", "Koblinger") in tab_calls
    assert not any(call[0] is control_tab for call in tab_calls)


def test_on_control_selection_changed_keeps_manual_support_tab_when_details_are_visible() -> None:
    calls: list[str] = []
    workspace = SimpleNamespace(selected_code=None)
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        workspace=workspace,
        _selected_control_code=lambda: "70",
        _update_history_details_from_selection=lambda: calls.append("history"),
        _refresh_in_progress=False,
        _control_details_visible=True,
        _preferred_support_tab_for_selected_code=lambda: "history",
        _select_support_tab_key=lambda key, force_render=False: calls.append(f"tab:{key}:{force_render}"),
        _update_control_panel=lambda: calls.append("panel"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _schedule_control_selection_followup=lambda: calls.append("followup"),
    )

    page_a07.A07Page._on_control_selection_changed(dummy)

    assert workspace.selected_code == "70"
    assert calls == ["history", "panel", "buttons", "followup"]


def test_on_rf1022_selection_changed_does_not_move_support_or_list_focus() -> None:
    calls: list[str] = []
    workspace = SimpleNamespace(selected_code=None)
    dummy = SimpleNamespace(
        _suspend_selection_sync=False,
        _is_tree_selection_suppressed=lambda _tree: False,
        tree_a07=object(),
        workspace=workspace,
        _selected_control_work_level=lambda: "rf1022",
        _selected_rf1022_group=lambda: "100_loenn_ol",
        _selected_control_code=lambda: "fastloenn",
        _update_history_details_from_selection=lambda: calls.append("history"),
        _update_selected_code_status_message=lambda: calls.append("status"),
        _update_control_panel=lambda: calls.append("panel"),
        _update_control_transfer_buttons=lambda: calls.append("buttons"),
        _sync_groups_panel_visibility=lambda: calls.append("groups"),
        _refresh_in_progress=False,
        _control_details_visible=True,
        _schedule_control_selection_followup=lambda: calls.append("followup"),
        _select_support_tab_key=lambda *_args, **_kwargs: calls.append("tab"),
        _set_tree_selection=lambda *_args, **_kwargs: calls.append("tree_selection"),
        _focus_selected_control_account_in_gl=lambda: calls.append("gl_focus"),
    )

    page_a07.A07Page._on_control_selection_changed(dummy)

    assert dummy._selected_rf1022_group_id == "100_loenn_ol"
    assert workspace.selected_code == "fastloenn"
    assert calls == ["history", "panel", "buttons", "groups", "followup"]


def test_sync_control_panel_visibility_hides_compact_guided_labels() -> None:
    class _Widget:
        def __init__(self, visible: bool = False) -> None:
            self.visible = visible

        def winfo_manager(self):
            return "pack" if self.visible else ""

        def pack(self, *args, **kwargs) -> None:
            self.visible = True

        def pack_forget(self) -> None:
            self.visible = False

    class _Var:
        def __init__(self, value: str) -> None:
            self.value = value

        def get(self) -> str:
            return self.value

    dummy = SimpleNamespace(
        _compact_control_status=True,
        lbl_control_summary=_Widget(False),
        lbl_control_meta=_Widget(False),
        lbl_control_next=_Widget(True),
        control_summary_var=_Var("Telefon | Har forslag"),
        control_meta_var=_Var("Matching kjort | Forslag 2"),
        control_next_var=_Var("Neste: Bruk forslag."),
        btn_control_smart=_Widget(False),
        control_panel=_Widget(True),
    )

    page_a07.A07Page._sync_control_panel_visibility(dummy)

    assert dummy.lbl_control_summary.visible is False
    assert dummy.lbl_control_meta.visible is False
    assert dummy.lbl_control_next.visible is False
    assert dummy.control_panel.visible is False


def test_control_smart_button_can_hide_pure_navigation_actions() -> None:
    class _Button:
        def __init__(self) -> None:
            self.visible = True
            self.states: list[tuple[str, ...]] = []
            self.text = ""

        def state(self, values) -> None:
            self.states.append(tuple(values))

        def pack_forget(self) -> None:
            self.visible = False

        def winfo_manager(self):
            return "pack" if self.visible else ""

        def pack(self, *args, **kwargs) -> None:
            self.visible = True

        def configure(self, **kwargs) -> None:
            if "text" in kwargs:
                self.text = kwargs["text"]

    button = _Button()
    dummy = SimpleNamespace(btn_control_smart=button)

    page_a07.A07Page._set_control_smart_button(dummy, visible=False)
    page_a07.A07Page._set_control_smart_button(
        dummy,
        text="Kontroller kobling",
        command=lambda: None,
        enabled=True,
        visible=True,
    )

    assert button.states[0] == ("disabled",)
    assert button.visible is True
    assert button.text == "Kontroller kobling"
    assert button.states[-1] == ("!disabled",)


def test_on_support_tab_changed_requests_support_before_loading() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _control_details_visible=True,
        _support_requested=False,
        _support_views_ready=False,
        _diag=lambda _message: None,
        _active_support_tab_key=lambda: "history",
        _render_active_support_tab=lambda: calls.append("render"),
        _schedule_support_refresh=lambda: calls.append("schedule"),
    )

    page_a07.A07Page._on_support_tab_changed(dummy)

    assert dummy._support_requested is True
    assert calls == ["schedule"]


def test_refresh_all_cancels_pending_core_jobs_before_starting() -> None:
    calls: list[str] = []
    dummy = SimpleNamespace(
        _refresh_in_progress=False,
        _pending_session_refresh=True,
        _pending_support_refresh=True,
        _cancel_core_refresh_jobs=lambda: calls.append("cancel_core"),
        _cancel_support_refresh=lambda: calls.append("cancel_support"),
        _support_views_ready=True,
        _start_core_refresh=lambda: calls.append("start_core"),
    )

    page_a07.A07Page._refresh_all(dummy)

    assert calls == ["cancel_core", "cancel_support", "start_core"]
    assert dummy._refresh_in_progress is True
    assert dummy._pending_session_refresh is False
    assert dummy._pending_support_refresh is False
    assert dummy._support_views_ready is False


def test_refresh_clicked_defers_focus_until_refresh_finishes() -> None:
    calls: list[str] = []
    workspace = SimpleNamespace(a07_df=pd.DataFrame([{"Kode": "70"}]), gl_df=pd.DataFrame([{"Konto": "5000"}]))
    dummy = SimpleNamespace(
        workspace=workspace,
        _selected_control_code=lambda: "fastloenn",
        _refresh_all=lambda: calls.append("refresh_all"),
        _focus_control_code=lambda code: calls.append(f"focus:{code}"),
        _notify_inline=lambda *args, **kwargs: calls.append("notify"),
        status_var=SimpleNamespace(set=lambda value: calls.append(f"status:{value}")),
        _pending_focus_code=None,
    )

    page_a07.A07Page._refresh_clicked(dummy)

    assert dummy._pending_focus_code == "fastloenn"
    assert "refresh_all" in calls
    assert not any(call.startswith("focus:") for call in calls)


def test_sync_shared_refs_updates_env_and_compat_runtime_refs(monkeypatch) -> None:
    from a07_feature import page_a07_env

    app_paths_ref = object()
    client_store_ref = object()
    session_ref = object()
    filedialog_ref = object()
    messagebox_ref = object()
    simpledialog_ref = object()
    konto_klassifisering_ref = object()

    monkeypatch.setattr(page_a07, "app_paths", app_paths_ref)
    monkeypatch.setattr(page_a07, "client_store", client_store_ref)
    monkeypatch.setattr(page_a07, "session", session_ref)
    monkeypatch.setattr(page_a07, "filedialog", filedialog_ref)
    monkeypatch.setattr(page_a07, "messagebox", messagebox_ref)
    monkeypatch.setattr(page_a07, "simpledialog", simpledialog_ref)
    monkeypatch.setattr(page_a07, "konto_klassifisering", konto_klassifisering_ref)

    page_a07._sync_shared_refs()

    assert page_a07_env.app_paths is app_paths_ref
    assert page_a07_env.client_store is client_store_ref
    assert page_a07_env.session is session_ref
    assert page_a07_env.filedialog is filedialog_ref
    assert page_a07_env.messagebox is messagebox_ref
    assert page_a07_env.simpledialog is simpledialog_ref
    assert page_a07_env.konto_klassifisering is konto_klassifisering_ref
    assert page_a07._shared.app_paths is app_paths_ref
    assert page_a07._shared.client_store is client_store_ref


def test_refresh_service_builders_keep_expected_payload_shapes() -> None:
    from a07_feature import page_a07_refresh_services as refresh_services

    context_payload = refresh_services.build_context_restore_payload(
        client=None,
        year=None,
        load_active_trial_balance_cached=lambda client, year: (page_a07._empty_gl_df(), None),
        load_a07_source_cached=lambda path: page_a07._empty_a07_df(),
        load_mapping_file_cached=lambda path, client=None, year=None: {},
        load_previous_year_mapping_cached=lambda client, year: ({}, None, None),
        resolve_rulebook_path_cached=lambda client, year: None,
    )
    assert {
        "gl_df",
        "tb_path",
        "source_a07_df",
        "a07_df",
        "a07_path",
        "mapping",
        "mapping_path",
        "groups",
        "groups_path",
        "locks",
        "locks_path",
        "project_meta",
        "project_path",
        "basis_col",
        "previous_mapping",
        "previous_mapping_path",
        "previous_mapping_year",
        "rulebook_path",
        "pending_focus_code",
    }.issubset(context_payload)

    core_payload = refresh_services.build_core_refresh_payload(
        client=None,
        year=None,
        source_a07_df=page_a07._empty_a07_df(),
        gl_df=page_a07._empty_gl_df(),
        groups={},
        mapping={},
        basis_col="Endring",
        locks=set(),
        previous_mapping={},
        usage_df=None,
        previous_mapping_path=None,
        previous_mapping_year=None,
        rulebook_path=None,
        load_code_profile_state=lambda client, year, mapping_current, gl_df=None: {},
    )
    assert {
        "rulebook_path",
        "matcher_settings",
        "previous_mapping",
        "previous_mapping_path",
        "previous_mapping_year",
        "effective_mapping",
        "effective_previous_mapping",
        "grouped_a07_df",
        "membership",
        "suggestions",
        "reconcile_df",
        "mapping_df",
        "unmapped_df",
        "control_gl_df",
        "a07_overview_df",
        "control_df",
        "groups_df",
        "control_statement_base_df",
        "control_statement_df",
    }.issubset(core_payload)

    support_payload = refresh_services.build_support_refresh_payload(
        a07_df=page_a07._empty_a07_df(),
        gl_df=page_a07._empty_gl_df(),
        effective_mapping={},
        effective_previous_mapping={},
    )
    assert set(support_payload) == {"history_compare_df"}


def test_active_a07_modules_do_not_import_page_a07_shared_directly() -> None:
    project_root = Path(__file__).resolve().parent.parent
    active_modules = (
        project_root / "a07_feature" / "page_a07_background.py",
        project_root / "a07_feature" / "control" / "statement_ui.py",
        project_root / "a07_feature" / "payroll" / "rf1022.py",
        project_root / "a07_feature" / "ui" / "helpers.py",
        project_root / "a07_feature" / "ui" / "selection.py",
    )

    for module_path in active_modules:
        source = module_path.read_text(encoding="utf-8")
        assert "from .page_a07_shared import" not in source

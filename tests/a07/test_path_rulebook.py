from __future__ import annotations

from .shared import *  # noqa: F401,F403

def test_resolve_rulebook_path_uses_global_rulebook(monkeypatch, tmp_path) -> None:
    global_rulebook = tmp_path / "config" / "classification" / "global_full_a07_rulebook.json"
    global_rulebook.parent.mkdir(parents=True, exist_ok=True)
    global_rulebook.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(classification_config, "resolve_rulebook_path", lambda: global_rulebook)

    out = page_a07.resolve_rulebook_path("Air Management AS", "2025")

    assert out == global_rulebook

def test_resolve_rulebook_path_returns_none_when_canonical_is_missing(monkeypatch, tmp_path) -> None:
    missing_rulebook = tmp_path / "config" / "classification" / "global_full_a07_rulebook.json"
    monkeypatch.setattr(classification_config, "resolve_rulebook_path", lambda: missing_rulebook)

    out = page_a07.resolve_rulebook_path("Air Management AS", "2025")

    assert out is None

def test_copy_rulebook_to_storage_uses_canonical_rulebook(monkeypatch, tmp_path) -> None:
    canonical = tmp_path / "config" / "classification" / "global_full_a07_rulebook.json"
    monkeypatch.setattr(classification_config, "resolve_rulebook_path", lambda: canonical)

    src = tmp_path / "external_rulebook.json"
    src.write_text('{"rules": {}}', encoding="utf-8")

    out = page_a07.copy_rulebook_to_storage(src)

    assert out == canonical
    assert out.read_text(encoding="utf-8") == '{"rules": {}}'

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


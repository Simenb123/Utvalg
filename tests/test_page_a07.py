from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import page_a07
import ui_main


def test_get_a07_workspace_dir_uses_client_store_years_dir(monkeypatch, tmp_path) -> None:
    years_dir = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(page_a07.client_store, "years_dir", lambda client, year: years_dir)

    out = page_a07.get_a07_workspace_dir("Air Management AS", "2025")

    assert out == years_dir / "a07"


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
            "label": "Fastlønn",
            "category": "Lønn",
            "allowed_ranges": "5000-5099\n5900",
            "keywords": "lønn, fastlønn",
            "boost_accounts": "5000, 5001",
            "basis": "Endring",
            "expected_sign": "1",
            "special_add": "5940 | Endring | 1.0",
        }
    )
    aliases = page_a07._parse_aliases_editor("fastloenn = lønn, fast lønn")
    aliases_text = page_a07._format_aliases_editor(aliases)

    assert code == "fastloenn"
    assert payload["allowed_ranges"] == ["5000-5099", "5900"]
    assert payload["keywords"] == ["lønn", "fastlønn"]
    assert payload["boost_accounts"] == [5000, 5001]
    assert payload["basis"] == "Endring"
    assert payload["expected_sign"] == 1
    assert payload["special_add"] == [{"account": "5940", "basis": "Endring"}]
    assert "fastloenn = lønn, fast lønn" in aliases_text


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

    assert out == f"Forslag 2 | Valgt 5090 | Diff {diff_text} | Sjekk"


def test_build_control_suggestion_effect_summary_describes_new_mapping() -> None:
    row = pd.Series({"ForslagKontoer": "5000,5001", "Diff": Decimal("12.50"), "WithinTolerance": True})

    out = page_a07.build_control_suggestion_effect_summary("bonus", [], row)
    diff_text = page_a07._format_picker_amount(Decimal("12.50"))

    assert out == f"Mapper 5000,5001 til bonus | Diff {diff_text} | OK"


def test_build_control_suggestion_effect_summary_describes_replacement() -> None:
    row = pd.Series({"ForslagKontoer": "5000,5001", "Diff": Decimal("100.00"), "WithinTolerance": False})

    out = page_a07.build_control_suggestion_effect_summary("bonus", ["5090"], row)
    diff_text = page_a07._format_picker_amount(Decimal("100.00"))

    assert out == f"Vil erstatte mapping 5090 med 5000,5001. Diff {diff_text}. Sjekk diff før bruk."


def test_build_control_suggestion_effect_summary_handles_matching_current_mapping() -> None:
    row = pd.Series({"ForslagKontoer": "5001,5000", "Diff": Decimal("0"), "WithinTolerance": True})

    out = page_a07.build_control_suggestion_effect_summary("bonus", ["5000", "5001"], row)
    diff_text = page_a07._format_picker_amount(Decimal("0"))

    assert out == f"Valgt forslag matcher dagens mapping 5001,5000. Diff {diff_text}. Innenfor toleranse."


def test_build_control_accounts_summary_describes_selected_accounts() -> None:
    accounts_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn", "IB": Decimal("0"), "Endring": Decimal("1200"), "UB": Decimal("1200")},
            {"Konto": "5001", "Navn": "Bonus", "IB": Decimal("0"), "Endring": Decimal("300"), "UB": Decimal("300")},
        ]
    )

    out = page_a07.build_control_accounts_summary(accounts_df, "fastloenn")

    assert out == "2 kontoer mappet til fastloenn. Endring 1 500,00. Kontoer: 5000, 5001."


def test_build_control_accounts_summary_handles_empty_state() -> None:
    assert (
        page_a07.build_control_accounts_summary(pd.DataFrame(), "fastloenn")
        == "Ingen kontoer er mappet til fastloenn ennå."
    )
    assert (
        page_a07.build_control_accounts_summary(pd.DataFrame(), None)
        == "Velg kode i hoyre liste for aa se mappede kontoer."
    )


def test_control_recommendation_label_is_short_and_list_friendly() -> None:
    safe_best = pd.Series({"WithinTolerance": True})
    weak_best = pd.Series({"WithinTolerance": False})

    assert page_a07.control_recommendation_label(has_history=True, best_suggestion=safe_best) == "Historikk"
    assert page_a07.control_recommendation_label(has_history=False, best_suggestion=safe_best) == "Forslag"
    assert page_a07.control_recommendation_label(has_history=False, best_suggestion=weak_best) == "Sjekk"
    assert page_a07.control_recommendation_label(has_history=False, best_suggestion=None) == "Manuell"


def test_control_next_action_label_prioritizes_history_then_safe_suggestion() -> None:
    best_row = pd.Series({"WithinTolerance": True})
    weak_row = pd.Series({"WithinTolerance": False})

    assert (
        page_a07.control_next_action_label("Ikke mappet", has_history=True, best_suggestion=best_row)
        == "Bruk historikk."
    )
    assert (
        page_a07.control_next_action_label("Ikke mappet", has_history=False, best_suggestion=best_row)
        == "Bruk beste forslag."
    )
    assert (
        page_a07.control_next_action_label("Avvik", has_history=False, best_suggestion=weak_row)
        == "Map manuelt."
    )
    assert (
        page_a07.control_next_action_label("OK", has_history=True, best_suggestion=best_row)
        == "Ingen handling nødvendig."
    )


def test_compact_control_next_action_shortens_user_hint() -> None:
    assert page_a07.compact_control_next_action("Bruk historikk.") == "Historikk"
    assert page_a07.compact_control_next_action("Bruk beste forslag.") == "Forslag"
    assert page_a07.compact_control_next_action("Map manuelt.") == "Manuell"
    assert page_a07.compact_control_next_action("Ingen handling nødvendig.") == "Ingen"


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
    )

    assert out.loc[out["Kode"] == "fastloenn", "Anbefalt"].iloc[0] == "Historikk"
    assert out.loc[out["Kode"] == "fastloenn", "NesteHandling"].iloc[0] == "Bruk historikk."
    assert out.loc[out["Kode"] == "fastloenn", "Status"].iloc[0] == "Vurdering"
    assert out.loc[out["Kode"] == "telefon", "Anbefalt"].iloc[0] == "Forslag"
    assert out.loc[out["Kode"] == "telefon", "NesteHandling"].iloc[0] == "Bruk beste forslag."
    assert out.loc[out["Kode"] == "telefon", "Status"].iloc[0] == "Vurdering"
    assert out.loc[out["Kode"] == "fastloenn", "Arbeidsstatus"].iloc[0] == "Trenger vurdering"
    assert out.loc[out["Kode"] == "telefon", "Arbeidsstatus"].iloc[0] == "Trenger vurdering"
    assert out.loc[out["Kode"] == "bonus", "DagensMapping"].iloc[0] == "5090"
    assert out.loc[out["Kode"] == "bonus", "Status"].iloc[0] == "Ferdig"
    assert out.loc[out["Kode"] == "bonus", "Arbeidsstatus"].iloc[0] == "Ferdig"
    assert out.loc[out["Kode"] == "bonus", "NesteHandling"].iloc[0] == "Ingen handling nødvendig."


def test_build_control_gl_df_shows_assigned_code_on_account_rows() -> None:
    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn", "IB": 0.0, "Endring": 1200.0, "UB": 1200.0},
            {"Konto": "6990", "Navn": "Telefon", "IB": 0.0, "Endring": 250.0, "UB": 250.0},
        ]
    )

    out = page_a07.build_control_gl_df(gl_df, {"5000": "fastloenn"})

    assert out["Konto"].tolist() == ["5000", "6990"]
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


def test_filter_control_queue_df_and_bucket_summary_group_rows_for_human_workflow() -> None:
    control_df = pd.DataFrame(
        [
            {"Kode": "bonus", "Arbeidsstatus": "Ferdig"},
            {"Kode": "telefon", "Arbeidsstatus": "Trenger vurdering"},
            {"Kode": "pensjon", "Arbeidsstatus": "Trenger manuell mapping"},
        ]
    )

    next_rows = page_a07.filter_control_queue_df(control_df, "neste")
    manual_rows = page_a07.filter_control_queue_df(control_df, "manuell")
    summary = page_a07.build_control_bucket_summary(control_df)

    assert next_rows["Kode"].tolist() == ["telefon", "pensjon"]
    assert manual_rows["Kode"].tolist() == ["pensjon"]
    assert summary == "Låste 0 | Ferdig 1 | Vurdering 1 | Manuell 1"


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
        mapping_current={},
        mapping_previous={},
        gl_df=gl_df,
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
    assert page_a07.control_tree_tag("Trenger vurdering") == "control_review"
    assert page_a07.control_tree_tag("Trenger manuell mapping") == "control_manual"
    assert page_a07.control_tree_tag("Annet") == "control_default"


def test_control_gl_tree_tag_marks_unmapped_selected_and_other_mapped_rows() -> None:
    unmapped = pd.Series({"Kode": ""})
    selected = pd.Series({"Kode": "fastloenn"})
    other = pd.Series({"Kode": "telefon"})
    suggested = pd.Series({"Konto": "5000", "Kode": ""})

    assert page_a07.control_gl_tree_tag(unmapped, "fastloenn") == "control_gl_unmapped"
    assert page_a07.control_gl_tree_tag(selected, "fastloenn") == "control_gl_selected"
    assert page_a07.control_gl_tree_tag(other, "fastloenn") == "control_gl_mapped"
    assert page_a07.control_gl_tree_tag(suggested, "fastloenn", ["5000", "5001"]) == "control_gl_suggestion"


def test_control_action_style_maps_work_labels() -> None:
    assert page_a07.control_action_style("Ferdig") == "Ready.TLabel"
    assert page_a07.control_action_style("Vurdering") == "Warning.TLabel"
    assert page_a07.control_action_style("Manuell") == "Warning.TLabel"
    assert page_a07.control_action_style("Annet") == "Muted.TLabel"


def test_control_intro_text_guides_user_toward_best_next_step() -> None:
    safe_best = pd.Series({"WithinTolerance": True})

    assert (
        page_a07.control_intro_text("Ferdig", has_history=False, best_suggestion=None)
        == "Ser ferdig ut. Kontroller kort og ga videre hvis du er enig."
    )
    assert (
        page_a07.control_intro_text("Vurdering", has_history=True, best_suggestion=None)
        == "Historikk finnes. Start gjerne med a vurdere historikk."
    )
    assert (
        page_a07.control_intro_text("Vurdering", has_history=False, best_suggestion=safe_best)
        == "Det finnes et trygt forslag. Start gjerne der."
    )
    assert (
        page_a07.control_intro_text("Manuell", has_history=False, best_suggestion=None)
        == "Ingen trygg automatikk funnet ennå. Bruk manuell mapping eller dra konto inn."
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
        tree_reconcile = object()

        def _selected_tree_values(self, tree):
            if tree is self.tree_control_gl:
                return ("5000", "Lonn", "0,00", "1 200,00", "1 200,00", "")
            if tree is self.tree_a07:
                return ("fastloenn",)
            return ()

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
    suggestion_ok = pd.Series({"WithinTolerance": True, "Score": 0.62})
    suggestion_review = pd.Series({"WithinTolerance": False, "Score": 0.91})
    suggestion_default = pd.Series({"WithinTolerance": False, "Score": 0.55})
    reconcile_ok = pd.Series({"WithinTolerance": True})
    reconcile_diff = pd.Series({"WithinTolerance": False})

    assert page_a07.suggestion_tree_tag(suggestion_ok) == "suggestion_ok"
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
            {"Kode": "aga", "Status": "Ekskludert", "NesteHandling": "Ingen handling nødvendig."},
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
            {"Kode": "fastloenn", "ForslagKontoer": "5000", "WithinTolerance": True, "Score": 0.93},
            {"Kode": "fastloenn", "ForslagKontoer": "5001", "WithinTolerance": True, "Score": 0.92},
            {"Kode": "bonus", "ForslagKontoer": "5090", "WithinTolerance": True, "Score": 0.91},
            {"Kode": "feriepenger", "ForslagKontoer": "5000", "WithinTolerance": True, "Score": 0.95},
            {"Kode": "telefon", "ForslagKontoer": "6990", "WithinTolerance": False, "Score": 0.99},
            {"Kode": "pensjon", "ForslagKontoer": "5940", "WithinTolerance": True, "Score": 0.70},
        ]
    )

    out = page_a07.select_batch_suggestion_rows(suggestions_df, {"5100": "annet"}, min_score=0.85)

    assert out == [0, 2]


def test_select_magic_wand_suggestion_rows_uses_within_tolerance_without_score_gate() -> None:
    suggestions_df = pd.DataFrame(
        [
            {"Kode": "fastloenn", "ForslagKontoer": "5000", "WithinTolerance": True, "Score": 0.61},
            {"Kode": "fastloenn", "ForslagKontoer": "5001", "WithinTolerance": True, "Score": 0.95},
            {"Kode": "telefon", "ForslagKontoer": "6990", "WithinTolerance": True, "Score": 0.40},
            {"Kode": "bonus", "ForslagKontoer": "6990", "WithinTolerance": True, "Score": 0.97},
            {"Kode": "pensjon", "ForslagKontoer": "5940", "WithinTolerance": False, "Score": 0.99},
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
        # In headless mode the stub has no real widgets — skip detailed checks
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

    assert out == f"Erstatter 5090 med 5000,5001 | Diff {diff_text} | Sjekk"


def test_build_control_suggestion_effect_summary_handles_matching_current_mapping() -> None:
    row = pd.Series({"ForslagKontoer": "5001,5000", "Diff": Decimal("0"), "WithinTolerance": True})

    out = page_a07.build_control_suggestion_effect_summary("bonus", ["5000", "5001"], row)
    diff_text = page_a07._format_picker_amount(Decimal("0"))

    assert out == f"Matcher dagens mapping 5001,5000 | Diff {diff_text} | OK"


def test_build_control_accounts_summary_describes_selected_accounts() -> None:
    accounts_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Lonn", "IB": Decimal("0"), "Endring": Decimal("1200"), "UB": Decimal("1200")},
            {"Konto": "5001", "Navn": "Bonus", "IB": Decimal("0"), "Endring": Decimal("300"), "UB": Decimal("300")},
        ]
    )

    out = page_a07.build_control_accounts_summary(accounts_df, "fastloenn")

    assert out == "2 kontoer | Endring 1 500,00 | 5000, 5001"


def test_build_control_accounts_summary_handles_empty_state() -> None:
    assert (
        page_a07.build_control_accounts_summary(pd.DataFrame(), "fastloenn")
        == "Ingen kontoer er mappet til fastloenn enna."
    )
    assert (
        page_a07.build_control_accounts_summary(pd.DataFrame(), None)
        == "Velg kode i hoyre liste for aa se mappede kontoer."
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
    tree_support = object()

    class _Notebook:
        def select(self) -> str:
            return "suggestions"

        def nametowidget(self, name: str) -> object:
            assert name == "suggestions"
            return tab_suggestions

    def _row_from_tree(tree: object):
        if tree is tree_support:
            return {"Kode": "bonus"}
        return None

    dummy = SimpleNamespace(
        control_support_nb=_Notebook(),
        tab_suggestions=tab_suggestions,
        tree_control_suggestions=tree_control,
        tree_suggestions=tree_support,
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
    assert calls == ["history", "gl", "panel", "buttons"]


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

    assert calls == ["retag", "buttons"]


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

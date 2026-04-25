from __future__ import annotations

import inspect
from pathlib import Path

import views_settings


def test_format_admin_json_label_with_existing_path() -> None:
    path = Path("shared/config/regnskap/regnskapslinjer.json")
    assert (
        views_settings.format_admin_json_label("regnskapslinjer", path)
        == f"Aktiv regnskapslinjer-fil: {path}"
    )


def test_format_admin_json_label_without_shared_file() -> None:
    assert (
        views_settings.format_admin_json_label("kontoplanmapping", None)
        == "Aktiv kontoplanmapping-fil: (ikke funnet i datamappen)"
    )


def test_general_tab_uses_felles_mapping_and_no_bootstrap_button() -> None:
    source = inspect.getsource(views_settings.SettingsView._build_general_tab)
    assert 'text="Felles mapping"' in source
    assert "Hent fra delt oppsett..." not in source
    assert "Importer og erstatt" not in source


def test_data_sources_tab_uses_clearer_gui_labels() -> None:
    source = inspect.getsource(views_settings.SettingsView._build_data_sources_tab)
    assert "Dette er bare en oversikt" in source
    assert '"Appregler"' in source
    assert '"Delt arbeidsdata"' in source
    assert '"Min profil"' in source
    assert '"Bor normalt i:"' in source


def test_build_data_source_rows_keeps_mapping_as_shared_data() -> None:
    rows = views_settings.build_data_source_rows()
    source_map = {row.id: row for row in rows}

    assert source_map["rules_regnskapslinjer"].group == "Delt klientdata"
    assert source_map["rules_regnskapslinjer"].scope == "shared"
    assert source_map["rules_kontoplanmapping"].group == "Delt klientdata"
    assert source_map["rules_kontoplanmapping"].scope == "shared"
    assert source_map["shared_clients_root"].group == "Delt klientdata"
    assert source_map["profile_preferences"].group == "Lokal brukerprofil"
    assert source_map["brreg_cache"].group == "Lokal mellomlagring"
    assert source_map["brreg_lookup"].group == "Eksterne tjenester"


def test_grouped_sources_keep_only_json_children_for_shared_mapping() -> None:
    rows = views_settings.build_data_source_rows()
    source_map = {row.id: row for row in rows}

    regn_children = {child.id for child in source_map["rules_regnskapslinjer"].advanced_children}
    kontoplan_children = {child.id for child in source_map["rules_kontoplanmapping"].advanced_children}
    brreg_children = {child.id for child in source_map["brreg_lookup"].advanced_children}

    assert regn_children == {"rules_regnskapslinjer_json"}
    assert kontoplan_children == {"rules_kontoplanmapping_json"}
    assert {"brreg_lookup_enhet", "brreg_lookup_roller", "brreg_lookup_regnskap"} <= brreg_children


def test_flatten_data_source_rows_hides_advanced_children_by_default() -> None:
    rows = views_settings.build_data_source_rows()
    visible = views_settings.flatten_data_source_rows(rows)
    keys = {row.id for row in visible}

    assert "workspace_data_dir_hint" not in keys
    assert "rules_regnskapslinjer_json" not in keys
    assert "rules_kontoplanmapping_json" not in keys
    assert "brreg_lookup_enhet" not in keys
    assert "sidecar_sources_dir_hint" not in keys
    assert {"workspace", "rules_regnskapslinjer", "rules_kontoplanmapping", "brreg_lookup"} <= keys


def test_flatten_data_source_rows_shows_advanced_children_when_requested() -> None:
    rows = views_settings.build_data_source_rows()
    visible = views_settings.flatten_data_source_rows(rows, include_advanced=True)
    keys = {row.id for row in visible}

    assert {
        "workspace_data_dir_hint",
        "rules_regnskapslinjer_json",
        "rules_kontoplanmapping_json",
        "brreg_lookup_enhet",
        "sidecar_sources_dir_hint",
    } <= keys


def test_flatten_data_source_rows_can_filter_external_scope() -> None:
    rows = views_settings.build_data_source_rows()
    visible = views_settings.flatten_data_source_rows(rows, scope_filter="external")
    keys = {row.id for row in visible}
    assert "brreg_lookup" in keys
    assert "brreg_cache" not in keys


def test_build_data_source_summary_returns_new_cards() -> None:
    rows = views_settings.build_data_source_rows()
    summary = views_settings.build_data_source_summary(rows)

    assert {"admin", "shared", "profile", "external"} <= set(summary)
    assert "globale kilder" in summary["admin"][0]
    assert "delte kilder" in summary["shared"][0]
    assert "mapping og klientdata" in summary["shared"][1]
    assert "Dine innstillinger" in summary["profile"][1]


def test_group_label_maps_internal_groups_to_clearer_gui_labels() -> None:
    assert views_settings._group_label("Global adminlogikk") == "Appregler"
    assert views_settings._group_label("Delt klientdata") == "Delt arbeidsdata"
    assert views_settings._group_label("Lokal brukerprofil") == "Min profil"
    assert views_settings._group_label("Lokal mellomlagring") == "Lokal cache"


def test_data_source_statuses_use_new_labels() -> None:
    rows = views_settings.flatten_data_source_rows(
        views_settings.build_data_source_rows(),
        include_advanced=True,
    )
    statuses = {row.status for row in rows}
    assert "Mangler" not in statuses
    assert "OK" not in statuses
    assert "Aktiv" not in statuses
    assert statuses & {"I bruk", "Ikke opprettet enna", "Valgfri", "Ekstern", "Feil"}

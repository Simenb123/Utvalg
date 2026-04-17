from __future__ import annotations

import json
from pathlib import Path

import pytest

import account_detail_classification as adc
import classification_config


def _catalog_from_dicts(entries: list[dict]) -> list[adc.DetailClass]:
    normalized = adc.normalize_document({"classes": entries})
    return [
        adc._normalize_class_entry(e)  # type: ignore[attr-defined]
        for e in normalized["classes"]
    ]


def test_parse_ranges_single_account_is_zero_width_range() -> None:
    assert adc.parse_ranges(["2400"]) == ((2400, 2400),)


def test_parse_ranges_reversed_order_is_swapped() -> None:
    assert adc.parse_ranges(["2770-2740"]) == ((2740, 2770),)


def test_parse_ranges_skips_invalid() -> None:
    assert adc.parse_ranges(["", "foo", "2740-2770", "abc-def"]) == ((2740, 2770),)


def test_match_detail_class_by_interval_only() -> None:
    catalog = _catalog_from_dicts(
        [
            {
                "id": "skyldig_mva",
                "navn": "Skyldig MVA",
                "kategori": "forpliktelse",
                "kontointervall": ["2740-2770"],
                "aliaser": [],
                "ekskluder_aliaser": [],
                "aktiv": True,
                "sortering": 10,
            }
        ]
    )
    assert adc.match_detail_class("2740", "Et eller annet navn", catalog) == "skyldig_mva"
    assert adc.match_detail_class("2770", "", catalog) == "skyldig_mva"
    assert adc.match_detail_class("2800", "", catalog) is None


def test_match_detail_class_by_alias_only() -> None:
    catalog = _catalog_from_dicts(
        [
            {
                "id": "skyldig_feriepenger",
                "navn": "Skyldig feriepenger",
                "kategori": "forpliktelse",
                "kontointervall": [],
                "aliaser": ["skyldig feriepenger"],
                "ekskluder_aliaser": [],
                "aktiv": True,
                "sortering": 10,
            }
        ]
    )
    assert adc.match_detail_class("9999", "Avsetning skyldig feriepenger", catalog) == "skyldig_feriepenger"
    assert adc.match_detail_class("9999", "Ikke relevant", catalog) is None


def test_match_detail_class_with_both_interval_and_alias_is_or() -> None:
    catalog = _catalog_from_dicts(
        [
            {
                "id": "skyldig_mva",
                "navn": "Skyldig MVA",
                "kategori": "forpliktelse",
                "kontointervall": ["2740-2770"],
                "aliaser": ["skyldig mva"],
                "ekskluder_aliaser": [],
                "aktiv": True,
                "sortering": 10,
            }
        ]
    )
    # Treffer intervall, ikke alias
    assert adc.match_detail_class("2740", "Noe helt annet", catalog) == "skyldig_mva"
    # Treffer alias, ikke intervall
    assert adc.match_detail_class("9999", "Skyldig mva oppgjør", catalog) == "skyldig_mva"
    # Treffer begge
    assert adc.match_detail_class("2750", "Skyldig mva", catalog) == "skyldig_mva"
    # Ingen treff
    assert adc.match_detail_class("9999", "Noe annet", catalog) is None


def test_match_detail_class_ekskluder_is_hard_block() -> None:
    catalog = _catalog_from_dicts(
        [
            {
                "id": "skyldig_aga",
                "navn": "Skyldig arbeidsgiveravgift",
                "kategori": "forpliktelse",
                "kontointervall": ["2770-2789"],
                "aliaser": ["aga", "arbeidsgiveravgift"],
                "ekskluder_aliaser": ["feriepenger"],
                "aktiv": True,
                "sortering": 10,
            }
        ]
    )
    # Intervall matcher men ekskluder-alias blokkerer
    assert adc.match_detail_class("2780", "Arbeidsgiveravgift av feriepenger", catalog) is None
    # Uten ekskluder-treff: matcher
    assert adc.match_detail_class("2780", "Skyldig arbeidsgiveravgift", catalog) == "skyldig_aga"


def test_match_detail_class_respects_sortering() -> None:
    catalog = _catalog_from_dicts(
        [
            {
                "id": "b_etter",
                "navn": "B",
                "kategori": "forpliktelse",
                "kontointervall": ["2740-2770"],
                "aliaser": [],
                "ekskluder_aliaser": [],
                "aktiv": True,
                "sortering": 50,
            },
            {
                "id": "a_foerst",
                "navn": "A",
                "kategori": "forpliktelse",
                "kontointervall": ["2740-2770"],
                "aliaser": [],
                "ekskluder_aliaser": [],
                "aktiv": True,
                "sortering": 10,
            },
        ]
    )
    # Catalog er ikke sortert her — sorter før matching.
    sorted_catalog = sorted(catalog, key=lambda dc: (dc.sortering, dc.id.casefold()))
    assert adc.match_detail_class("2750", "", sorted_catalog) == "a_foerst"


def test_match_detail_class_ignores_inactive() -> None:
    catalog = _catalog_from_dicts(
        [
            {
                "id": "aktiv_ikke",
                "navn": "X",
                "kategori": "forpliktelse",
                "kontointervall": ["2740-2770"],
                "aliaser": [],
                "ekskluder_aliaser": [],
                "aktiv": False,
                "sortering": 10,
            }
        ]
    )
    assert adc.match_detail_class("2750", "", catalog) is None


def test_match_detail_class_skips_classes_without_interval_or_alias() -> None:
    catalog = _catalog_from_dicts(
        [
            {
                "id": "tom",
                "navn": "Tom",
                "kategori": "forpliktelse",
                "kontointervall": [],
                "aliaser": [],
                "ekskluder_aliaser": [],
                "aktiv": True,
                "sortering": 10,
            }
        ]
    )
    assert adc.match_detail_class("2750", "skyldig mva", catalog) is None


def test_resolve_uses_profile_override_first() -> None:
    catalog = _catalog_from_dicts(
        [
            {
                "id": "skyldig_mva",
                "navn": "Skyldig MVA",
                "kategori": "forpliktelse",
                "kontointervall": ["2740-2770"],
                "aliaser": [],
                "ekskluder_aliaser": [],
                "aktiv": True,
                "sortering": 10,
            }
        ]
    )
    assert (
        adc.resolve_detail_class_for_account(
            "skyldig_forskuddstrekk", "2740", "Skyldig mva", catalog
        )
        == "skyldig_forskuddstrekk"
    )


def test_resolve_falls_back_to_global_match_when_no_override() -> None:
    catalog = _catalog_from_dicts(
        [
            {
                "id": "skyldig_mva",
                "navn": "Skyldig MVA",
                "kategori": "forpliktelse",
                "kontointervall": ["2740-2770"],
                "aliaser": [],
                "ekskluder_aliaser": [],
                "aktiv": True,
                "sortering": 10,
            }
        ]
    )
    assert adc.resolve_detail_class_for_account("", "2740", "", catalog) == "skyldig_mva"
    assert adc.resolve_detail_class_for_account(None, "2740", "", catalog) == "skyldig_mva"


def test_resolve_returns_none_when_no_match() -> None:
    catalog = _catalog_from_dicts(
        [
            {
                "id": "skyldig_mva",
                "navn": "Skyldig MVA",
                "kategori": "forpliktelse",
                "kontointervall": ["2740-2770"],
                "aliaser": [],
                "ekskluder_aliaser": [],
                "aktiv": True,
                "sortering": 10,
            }
        ]
    )
    assert adc.resolve_detail_class_for_account(None, "9999", "", catalog) is None


def test_format_detail_class_label_returns_navn_or_id_fallback() -> None:
    catalog = _catalog_from_dicts(
        [
            {
                "id": "skyldig_mva",
                "navn": "Skyldig MVA",
                "kategori": "forpliktelse",
                "kontointervall": [],
                "aliaser": ["x"],
                "ekskluder_aliaser": [],
                "aktiv": True,
                "sortering": 10,
            }
        ]
    )
    assert adc.format_detail_class_label("skyldig_mva", catalog) == "Skyldig MVA"
    assert adc.format_detail_class_label("ukjent_id", catalog) == "ukjent_id"
    assert adc.format_detail_class_label("", catalog) == ""


def test_normalize_document_deduplicates_and_drops_invalid() -> None:
    normalized = adc.normalize_document(
        {
            "classes": [
                {"id": "dupe", "navn": "A", "kategori": "forpliktelse"},
                {"id": "dupe", "navn": "B", "kategori": "forpliktelse"},
                {"navn": "uten id"},
                "ikke en dict",
            ]
        }
    )
    ids = [entry["id"] for entry in normalized["classes"]]
    assert ids == ["dupe"]


def test_normalize_document_invalid_category_falls_back_to_annet() -> None:
    normalized = adc.normalize_document(
        {"classes": [{"id": "x", "navn": "X", "kategori": "noe_rart"}]}
    )
    assert normalized["classes"][0]["kategori"] == "annet"


def test_seed_bootstraps_when_file_missing(tmp_path, monkeypatch) -> None:
    target = tmp_path / "account_detail_classification.json"
    monkeypatch.setattr(
        classification_config,
        "repo_account_detail_classification_path",
        lambda: target,
    )
    monkeypatch.setattr(
        classification_config,
        "resolve_account_detail_classification_path",
        lambda: target,
    )
    assert not target.exists()
    document = classification_config.load_account_detail_classification_document()
    assert isinstance(document, dict)
    assert target.exists(), "seed skulle skrives til disk"
    class_ids = [entry["id"] for entry in document["classes"]]
    for expected in (
        "skyldig_mva",
        "skyldig_forskuddstrekk",
        "skyldig_arbeidsgiveravgift",
        "skyldig_feriepenger",
        "skyldig_arbeidsgiveravgift_feriepenger",
        "kostnadsfoert_arbeidsgiveravgift",
    ):
        assert expected in class_ids


def test_seed_kostnadsfoert_aga_wins_for_5400_against_skyldig_aga_alias(
    tmp_path, monkeypatch
) -> None:
    """Regresjon: konto 5400 med navn 'Arbeidsgiveravgift' skal matche
    kostnadsført arbeidsgiveravgift (intervall 5400-5499), ikke skyldig
    arbeidsgiveravgift via alias 'arbeidsgiveravgift' / 'aga'."""

    target = tmp_path / "account_detail_classification.json"
    monkeypatch.setattr(
        classification_config,
        "repo_account_detail_classification_path",
        lambda: target,
    )
    monkeypatch.setattr(
        classification_config,
        "resolve_account_detail_classification_path",
        lambda: target,
    )
    catalog = adc.load_detail_class_catalog()
    assert adc.match_detail_class("5400", "Arbeidsgiveravgift", catalog) == (
        "kostnadsfoert_arbeidsgiveravgift"
    )
    assert adc.match_detail_class("5401", "Påløpt arbeidsgiveravgift", catalog) == (
        "kostnadsfoert_arbeidsgiveravgift"
    )


def test_seed_does_not_overwrite_existing_document(tmp_path, monkeypatch) -> None:
    target = tmp_path / "account_detail_classification.json"
    target.write_text(
        json.dumps(
            {
                "classes": [
                    {
                        "id": "egen_klasse",
                        "navn": "Min klasse",
                        "kategori": "forpliktelse",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        classification_config,
        "repo_account_detail_classification_path",
        lambda: target,
    )
    monkeypatch.setattr(
        classification_config,
        "resolve_account_detail_classification_path",
        lambda: target,
    )
    document = classification_config.load_account_detail_classification_document()
    ids = [entry["id"] for entry in document["classes"]]
    assert ids == ["egen_klasse"]


def test_save_and_reload_roundtrip(tmp_path, monkeypatch) -> None:
    target = tmp_path / "account_detail_classification.json"
    monkeypatch.setattr(
        classification_config,
        "repo_account_detail_classification_path",
        lambda: target,
    )
    monkeypatch.setattr(
        classification_config,
        "resolve_account_detail_classification_path",
        lambda: target,
    )
    payload = {
        "classes": [
            {
                "id": "skyldig_mva",
                "navn": "Skyldig MVA",
                "kategori": "forpliktelse",
                "kontointervall": ["2740-2770"],
                "aliaser": ["skyldig mva"],
                "ekskluder_aliaser": [],
                "aktiv": True,
                "sortering": 10,
            }
        ]
    }
    classification_config.save_account_detail_classification_document(payload)
    loaded = classification_config.load_account_detail_classification_document()
    assert loaded["classes"][0]["id"] == "skyldig_mva"
    catalog = adc.load_detail_class_catalog()
    assert catalog[0].id == "skyldig_mva"
    assert catalog[0].kontointervall == ((2740, 2770),)


def test_load_detail_class_catalog_sorts_by_sortering_then_id(tmp_path, monkeypatch) -> None:
    target = tmp_path / "account_detail_classification.json"
    monkeypatch.setattr(
        classification_config,
        "repo_account_detail_classification_path",
        lambda: target,
    )
    monkeypatch.setattr(
        classification_config,
        "resolve_account_detail_classification_path",
        lambda: target,
    )
    classification_config.save_account_detail_classification_document(
        {
            "classes": [
                {"id": "z_sist", "navn": "Z", "kategori": "forpliktelse", "sortering": 100, "aliaser": ["z"]},
                {"id": "a_foerst", "navn": "A", "kategori": "forpliktelse", "sortering": 10, "aliaser": ["a"]},
                {"id": "b_likt", "navn": "B", "kategori": "forpliktelse", "sortering": 10, "aliaser": ["b"]},
            ]
        }
    )
    catalog = adc.load_detail_class_catalog()
    assert [dc.id for dc in catalog] == ["a_foerst", "b_likt", "z_sist"]

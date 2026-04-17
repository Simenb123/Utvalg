"""End-to-end regression for the A07-2 chain.

Exercises mapping_source (current + nearest-prior) together with
page_paths.load_previous_year_mapping_for_context and the modern
control_statement_source, all against the same seeded client/year layout,
to guard against slice-level drift.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from a07_feature import control_statement_source, mapping_source, page_paths
import page_a07


CLIENT_NAME = "Air Management AS"
CLIENT_SLUG = "Air_Management_AS"


def _seed_profile_doc(
    tmp_path: Path,
    *,
    year: int,
    profiles: dict[str, dict[str, object]],
) -> Path:
    path = (
        tmp_path
        / "data"
        / "konto_klassifisering_profiles"
        / CLIENT_SLUG
        / str(year)
        / "account_profiles.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "client": CLIENT_NAME,
        "year": year,
        "profiles": profiles,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _seed_legacy_mapping(
    tmp_path: Path, *, year: int, mapping: dict[str, str]
) -> Path:
    path = tmp_path / "clients" / "air" / "years" / str(year) / "a07" / "a07_mapping.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    return path


def test_a07_chain_current_prior_and_control_statement_are_consistent(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(mapping_source.app_paths, "data_dir", lambda: tmp_path / "data")

    years_dir_2025 = tmp_path / "clients" / "air" / "years" / "2025"
    monkeypatch.setattr(
        page_a07.client_store, "years_dir", lambda client, year: years_dir_2025
    )

    _seed_legacy_mapping(tmp_path, year=2023, mapping={"5000": "legacy2023"})
    _seed_profile_doc(
        tmp_path,
        year=2024,
        profiles={
            "5000": {"account_no": "5000", "a07_code": "doc2024"},
        },
    )
    _seed_profile_doc(
        tmp_path,
        year=2025,
        profiles={
            "5000": {
                "account_no": "5000",
                "account_name": "Loenn fast",
                "a07_code": "fastloenn",
                "control_group": "Loenn",
                "source": "manual",
            },
            "5400": {
                "account_no": "5400",
                "account_name": "Arbeidsgiveravgift",
                "a07_code": "aga",
                "control_group": "AGA",
                "source": "manual",
            },
        },
    )

    current_doc = mapping_source.load_current_document(CLIENT_NAME, year=2025)
    assert current_doc.year == 2025
    assert set(current_doc.profiles) == {"5000", "5400"}
    assert mapping_source.mapping_from_document(current_doc) == {
        "5000": "fastloenn",
        "5400": "aga",
    }

    prior_mapping, prior_path, prior_year = page_paths.load_previous_year_mapping_for_context(
        CLIENT_NAME, "2025"
    )
    assert prior_year == "2024"
    assert prior_path is None
    assert prior_mapping == {"5000": "doc2024"}

    gl_df = pd.DataFrame(
        [
            {"Konto": "5000", "Navn": "Loenn fast", "IB": 0.0, "Endring": 100.0, "UB": 100.0},
            {"Konto": "5400", "Navn": "AGA", "IB": 0.0, "Endring": 14.1, "UB": 14.1},
        ]
    )
    rows = control_statement_source.build_current_control_statement_rows(
        CLIENT_NAME, 2025, gl_df
    )
    by_group = {row.group_id: row for row in rows}
    assert set(by_group) == {"Loenn", "AGA"}
    assert by_group["Loenn"].accounts == ("5000",)
    assert by_group["Loenn"].ub == 100.0
    assert by_group["AGA"].accounts == ("5400",)
    assert "manual" in by_group["Loenn"].source_breakdown

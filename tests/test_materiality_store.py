from __future__ import annotations

from pathlib import Path

import src.pages.materiality.backend.store as mod


def test_build_candidate_client_numbers_handles_visena_prefix() -> None:
    assert mod.build_candidate_client_numbers("147429 Demo AS") == ["7429", "147429"]
    assert mod.build_candidate_client_numbers("154321 Eksempel AS") == ["4321", "154321"]
    assert mod.build_candidate_client_numbers("7429 Demo AS") == ["7429"]


def test_state_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path / "data"))

    payload = {
        "crm_client_number": "7429",
        "selection_threshold_key": "overall_materiality",
        "active_materiality": {
            "source": "crmsystem",
            "overall_materiality": 1200000,
            "performance_materiality": 600000,
            "clearly_trivial": 30000,
        },
    }
    mod.save_state("Demo AS", "2025", payload)

    loaded = mod.load_state("Demo AS", "2025")
    assert loaded["crm_client_number"] == "7429"
    assert loaded["selection_threshold_key"] == "overall_materiality"
    assert loaded["active_materiality"]["overall_materiality"] == 1200000
    assert (tmp_path / "data" / "clients").exists()


def test_resolve_selection_threshold_defaults_to_pm_and_falls_back_when_missing() -> None:
    active = {
        "overall_materiality": 250000,
        "performance_materiality": 175000,
        "clearly_trivial": 17500,
    }

    key, amount = mod.resolve_selection_threshold(active)
    assert key == "performance_materiality"
    assert amount == 175000

    key, amount = mod.resolve_selection_threshold({"overall_materiality": 90000}, "clearly_trivial")
    assert key == "overall_materiality"
    assert amount == 90000

    key, amount = mod.resolve_selection_threshold(active, "manual")
    assert key == "manual"
    assert amount is None

from __future__ import annotations


def test_mapping_review_state_roundtrip(tmp_path, monkeypatch) -> None:
    import regnskap_client_overrides

    monkeypatch.setattr(regnskap_client_overrides.app_paths, "data_dir", lambda: tmp_path)

    regnskap_client_overrides.set_mapping_review_state(
        "Eksempel AS",
        "3000",
        status="rejected",
        suggested_regnr=10,
        note="Avvist i test",
    )

    state = regnskap_client_overrides.load_mapping_review_state("Eksempel AS")

    assert state["3000"]["status"] == "rejected"
    assert state["3000"]["suggested_regnr"] == 10
    assert state["3000"]["note"] == "Avvist i test"


def test_expected_flow_preset_roundtrip(tmp_path, monkeypatch) -> None:
    import regnskap_client_overrides

    monkeypatch.setattr(regnskap_client_overrides.app_paths, "data_dir", lambda: tmp_path)

    regnskap_client_overrides.save_expected_flow_preset(
        "Eksempel AS",
        "sales",
        {"expected_counterparties": ["kundefordringer", "mva"]},
    )

    presets = regnskap_client_overrides.load_expected_flow_presets("Eksempel AS")

    assert presets["sales"]["expected_counterparties"] == ["kundefordringer", "mva"]

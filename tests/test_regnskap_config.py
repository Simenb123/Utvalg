from __future__ import annotations

import json
from pathlib import Path

import pytest


def _configure_paths(tmp_path: Path, monkeypatch):
    import regnskap_config

    shared_root = tmp_path / "shared"
    monkeypatch.setattr(regnskap_config.app_paths, "data_dir", lambda: shared_root)
    monkeypatch.setattr(regnskap_config.app_paths, "is_frozen", lambda: False)
    regnskap_config._invalidate_config_caches()
    return regnskap_config, shared_root / "config" / "regnskap"


def _write_json(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _sample_regnskapslinjer() -> list[dict]:
    return [
        {"nr": 10, "regnskapslinje": "Salgsinntekt", "sumpost": "nei", "Formel": ""},
        {"nr": 19, "regnskapslinje": "Sum driftsinntekter", "sumpost": "ja", "Formel": "+10"},
    ]


def _sample_kontoplan() -> list[dict]:
    return [
        {"fra": 3000, "til": 3299, "regnr": 10, "regnskapslinje": "Salgsinntekt"},
        {"fra": 1500, "til": 1599, "regnr": 1500, "regnskapslinje": "Kundefordringer"},
    ]


def test_paths_use_shared_data_dir_json(tmp_path: Path, monkeypatch) -> None:
    regnskap_config, shared_config = _configure_paths(tmp_path, monkeypatch)

    assert regnskap_config.config_dir() == shared_config
    assert regnskap_config.regnskapslinjer_path() == shared_config / "regnskapslinjer.json"
    assert regnskap_config.kontoplan_mapping_path() == shared_config / "kontoplan_mapping.json"
    assert regnskap_config.legacy_shared_config_dir() == shared_config


def test_import_and_load_regnskap_config_is_json_only(tmp_path: Path, monkeypatch) -> None:
    regnskap_config, shared_config = _configure_paths(tmp_path, monkeypatch)
    regn_src = tmp_path / "regnskapslinjer_source.json"
    map_src = tmp_path / "kontoplan_source.json"
    _write_json(regn_src, _sample_regnskapslinjer())
    _write_json(map_src, _sample_kontoplan())

    dst_regn = regnskap_config.import_regnskapslinjer(regn_src)
    dst_map = regnskap_config.import_kontoplan_mapping(map_src)

    assert dst_regn == shared_config / "regnskapslinjer.json"
    assert dst_map == shared_config / "kontoplan_mapping.json"
    assert regnskap_config.meta_path().exists()

    st = regnskap_config.get_status()
    assert st.regnskapslinjer_meta.get("filename") == regn_src.name
    assert st.kontoplan_mapping_meta.get("filename") == map_src.name

    loaded_regn = regnskap_config.load_regnskapslinjer()
    loaded_map = regnskap_config.load_kontoplan_mapping()
    assert loaded_regn.shape[0] == 2
    assert loaded_map.shape[0] == 2


def test_load_regnskap_config_raises_when_shared_json_missing(tmp_path: Path, monkeypatch) -> None:
    regnskap_config, _ = _configure_paths(tmp_path, monkeypatch)

    with pytest.raises(FileNotFoundError):
        regnskap_config.load_regnskapslinjer()
    with pytest.raises(FileNotFoundError):
        regnskap_config.load_kontoplan_mapping()


def test_get_status_reports_only_json_or_missing(tmp_path: Path, monkeypatch) -> None:
    regnskap_config, shared_config = _configure_paths(tmp_path, monkeypatch)

    st0 = regnskap_config.get_status()
    assert st0.regnskapslinjer_json_path is None
    assert st0.kontoplan_mapping_json_path is None
    assert st0.regnskapslinjer_active_source == regnskap_config.ACTIVE_SOURCE_MISSING
    assert st0.kontoplan_mapping_active_source == regnskap_config.ACTIVE_SOURCE_MISSING

    _write_json(shared_config / "regnskapslinjer.json", _sample_regnskapslinjer())
    _write_json(shared_config / "kontoplan_mapping.json", _sample_kontoplan())
    st1 = regnskap_config.get_status()
    assert st1.regnskapslinjer_json_path == shared_config / "regnskapslinjer.json"
    assert st1.kontoplan_mapping_json_path == shared_config / "kontoplan_mapping.json"
    assert st1.regnskapslinjer_active_source == regnskap_config.ACTIVE_SOURCE_JSON
    assert st1.kontoplan_mapping_active_source == regnskap_config.ACTIVE_SOURCE_JSON

    (shared_config / "regnskapslinjer.json").unlink()
    st2 = regnskap_config.get_status()
    assert st2.regnskapslinjer_json_path is None
    assert st2.regnskapslinjer_active_source == regnskap_config.ACTIVE_SOURCE_MISSING


def test_load_and_save_rl_baseline_document_without_excel(tmp_path: Path, monkeypatch) -> None:
    regnskap_config, _ = _configure_paths(tmp_path, monkeypatch)

    doc = regnskap_config.RLBaselineDocument(
        lines=[
            regnskap_config.RLBaselineLine(
                regnr="10",
                regnskapslinje="Salgsinntekt",
                sumpost=False,
                resultat_balanse="Resultatregnskap",
            ),
            regnskap_config.RLBaselineLine(
                regnr="19",
                regnskapslinje="Sum driftsinntekter",
                sumpost=True,
                formel="+10",
            ),
        ],
        intervals=[
            regnskap_config.RLBaselineInterval(fra=3000, til=3299, regnr="10"),
        ],
    )

    r_path, m_path = regnskap_config.save_rl_baseline_document(doc)
    assert r_path.exists()
    assert m_path.exists()

    reloaded = regnskap_config.load_rl_baseline_document()
    assert [line.regnr for line in reloaded.lines] == ["10", "19"]
    assert reloaded.lines[0].formel == ""
    assert reloaded.lines[1].formel == "+10"
    assert [(iv.fra, iv.til, iv.regnr) for iv in reloaded.intervals] == [(3000, 3299, "10")]


def test_bootstrap_helper_is_noop_when_shared_path_is_already_active(tmp_path: Path, monkeypatch) -> None:
    regnskap_config, shared_config = _configure_paths(tmp_path, monkeypatch)
    _write_json(shared_config / "regnskapslinjer.json", _sample_regnskapslinjer())
    _write_json(shared_config / "kontoplan_mapping.json", _sample_kontoplan())

    imported = regnskap_config.bootstrap_local_json_from_shared(overwrite=False)

    assert imported == {}

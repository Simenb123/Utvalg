from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name)


def _write_sources(tmp_path: Path) -> tuple[Path, Path]:
    regn_src = tmp_path / "Regnskapslinjer.xlsx"
    map_src = tmp_path / "Mapping standard kontoplan.xlsx"

    regn_df = pd.DataFrame(
        {
            "nr": [10, 11],
            "regnskapslinje": ["A", "B"],
            "sumpost": ["nei", "nei"],
            "Formel": ["", ""],
        }
    )
    map_df = pd.DataFrame({"fra": [1000], "til": [1999], "regnr": [10]})

    _write_xlsx(regn_src, {"Sheet1": regn_df})
    _write_xlsx(map_src, {"Intervall": map_df})
    return regn_src, map_src


def test_import_and_load_regnskap_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

    regn_src, map_src = _write_sources(tmp_path)

    dst_regn = regnskap_config.import_regnskapslinjer(regn_src)
    dst_map = regnskap_config.import_kontoplan_mapping(map_src)

    assert dst_regn.exists()
    assert dst_map.exists()
    assert regnskap_config.meta_path().exists()

    st = regnskap_config.get_status()
    assert st.regnskapslinjer_path is not None
    assert st.kontoplan_mapping_path is not None
    assert st.regnskapslinjer_meta.get("filename") == regn_src.name
    assert st.kontoplan_mapping_meta.get("filename") == map_src.name

    loaded_regn = regnskap_config.load_regnskapslinjer()
    loaded_map = regnskap_config.load_kontoplan_mapping()
    assert loaded_regn.shape[0] == 2
    assert loaded_map.shape[0] == 1


def test_first_load_without_json_bootstraps_from_excel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

    regn_src, map_src = _write_sources(tmp_path)

    # Legg Excel direkte inn via _import_file (uten JSON-refresh) slik at vi simulerer
    # en pre-eksisterende Excel uten tilhørende JSON.
    regnskap_config._import_file(
        kind="regnskapslinjer", src_path=regn_src, dst_path=regnskap_config.regnskapslinjer_path()
    )
    regnskap_config._import_file(
        kind="kontoplan_mapping", src_path=map_src, dst_path=regnskap_config.kontoplan_mapping_path()
    )
    assert not regnskap_config.regnskapslinjer_json_path().exists()
    assert not regnskap_config.kontoplan_mapping_json_path().exists()

    df_r = regnskap_config.load_regnskapslinjer()
    df_k = regnskap_config.load_kontoplan_mapping()

    assert df_r.shape[0] == 2
    assert df_k.shape[0] == 1
    assert regnskap_config.regnskapslinjer_json_path().exists()
    assert regnskap_config.kontoplan_mapping_json_path().exists()


def test_second_load_uses_existing_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

    regn_src, _ = _write_sources(tmp_path)
    regnskap_config.import_regnskapslinjer(regn_src)

    # Endre JSON manuelt, slett Excel — skal fortsatt lese fra JSON
    regnskap_config.save_regnskapslinjer_json(
        [{"nr": 99, "regnskapslinje": "FraJSON", "sumpost": "nei", "Formel": ""}]
    )
    regnskap_config.regnskapslinjer_path().unlink()

    df = regnskap_config.load_regnskapslinjer()
    assert df.shape[0] == 1
    assert df.iloc[0]["regnskapslinje"] == "FraJSON"


def test_import_regnskapslinjer_refreshes_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

    regn_src, _ = _write_sources(tmp_path)

    regnskap_config.import_regnskapslinjer(regn_src)
    first_json = regnskap_config.load_regnskapslinjer_json()
    assert first_json.shape[0] == 2

    # Ny Excel med flere rader — ny import skal overskrive JSON
    regn_src2 = tmp_path / "Regnskapslinjer_v2.xlsx"
    regn_df2 = pd.DataFrame(
        {
            "nr": [10, 11, 12, 13],
            "regnskapslinje": ["A", "B", "C", "D"],
            "sumpost": ["nei"] * 4,
            "Formel": [""] * 4,
        }
    )
    _write_xlsx(regn_src2, {"Sheet1": regn_df2})

    regnskap_config.import_regnskapslinjer(regn_src2)
    refreshed_json = regnskap_config.load_regnskapslinjer_json()
    assert refreshed_json.shape[0] == 4


def test_import_kontoplan_mapping_refreshes_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

    _, map_src = _write_sources(tmp_path)

    regnskap_config.import_kontoplan_mapping(map_src)
    first_json = regnskap_config.load_kontoplan_mapping_json()
    assert first_json.shape[0] == 1

    map_src2 = tmp_path / "Mapping_v2.xlsx"
    map_df2 = pd.DataFrame(
        {
            "fra": [1000, 3000, 6000],
            "til": [1999, 3999, 6999],
            "regnr": [10, 20, 30],
        }
    )
    _write_xlsx(map_src2, {"Intervall": map_df2})

    regnskap_config.import_kontoplan_mapping(map_src2)
    refreshed_json = regnskap_config.load_kontoplan_mapping_json()
    assert refreshed_json.shape[0] == 3


def test_import_rolls_back_when_json_refresh_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

    regn_src, _ = _write_sources(tmp_path)
    regnskap_config.import_regnskapslinjer(regn_src)

    prior_excel_bytes = regnskap_config.regnskapslinjer_path().read_bytes()
    prior_json_bytes = regnskap_config.regnskapslinjer_json_path().read_bytes()

    # Lag en "ny" Excel og monkeypatch refresh til å feile
    regn_src2 = tmp_path / "broken.xlsx"
    _write_xlsx(regn_src2, {"Sheet1": pd.DataFrame({"nr": [99], "regnskapslinje": ["x"], "sumpost": ["nei"]})})

    def _fail():
        raise RuntimeError("simulert refresh-feil")

    monkeypatch.setattr(regnskap_config, "refresh_regnskapslinjer_json_from_excel", _fail)

    with pytest.raises(RuntimeError, match="rullet tilbake"):
        regnskap_config.import_regnskapslinjer(regn_src2)

    # Excel og JSON skal være identisk med før
    assert regnskap_config.regnskapslinjer_path().read_bytes() == prior_excel_bytes
    assert regnskap_config.regnskapslinjer_json_path().read_bytes() == prior_json_bytes


def test_get_status_reports_json_paths_and_active_source(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

    st0 = regnskap_config.get_status()
    assert st0.regnskapslinjer_json_path is None
    assert st0.kontoplan_mapping_json_path is None
    assert st0.regnskapslinjer_active_source == regnskap_config.ACTIVE_SOURCE_MISSING
    assert st0.kontoplan_mapping_active_source == regnskap_config.ACTIVE_SOURCE_MISSING

    regn_src, map_src = _write_sources(tmp_path)
    regnskap_config.import_regnskapslinjer(regn_src)
    regnskap_config.import_kontoplan_mapping(map_src)

    st = regnskap_config.get_status()
    assert st.regnskapslinjer_json_path == regnskap_config.regnskapslinjer_json_path()
    assert st.kontoplan_mapping_json_path == regnskap_config.kontoplan_mapping_json_path()
    assert st.regnskapslinjer_active_source == regnskap_config.ACTIVE_SOURCE_JSON
    assert st.kontoplan_mapping_active_source == regnskap_config.ACTIVE_SOURCE_JSON

    # Når JSON slettes skal aktiv source falle tilbake til excel
    regnskap_config.regnskapslinjer_json_path().unlink()
    st2 = regnskap_config.get_status()
    assert st2.regnskapslinjer_active_source == regnskap_config.ACTIVE_SOURCE_EXCEL
    assert st2.regnskapslinjer_json_path is None


def test_load_rl_baseline_document_returns_lines_and_intervals(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

    regn_src, map_src = _write_sources(tmp_path)
    regnskap_config.import_regnskapslinjer(regn_src)
    regnskap_config.import_kontoplan_mapping(map_src)

    doc = regnskap_config.load_rl_baseline_document()
    assert len(doc.lines) == 2
    assert len(doc.intervals) == 1
    assert doc.lines[0].regnr == "10"
    assert doc.lines[0].regnskapslinje == "A"
    assert doc.lines[0].sumpost is False
    iv = doc.intervals[0]
    assert iv.fra == 1000
    assert iv.til == 1999
    assert iv.regnr == "10"


def test_save_rl_baseline_document_writes_both_json_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

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
            regnskap_config.RLBaselineInterval(fra=3000, til=3099, regnr="10"),
        ],
    )
    r_path, m_path = regnskap_config.save_rl_baseline_document(doc)
    assert r_path.exists()
    assert m_path.exists()

    reloaded = regnskap_config.load_rl_baseline_document()
    assert [l.regnr for l in reloaded.lines] == ["10", "19"]
    assert reloaded.lines[1].sumpost is True
    assert reloaded.lines[1].formel == "+10"
    # vanlig linje skal ikke ha formel ved save
    assert reloaded.lines[0].formel == ""
    assert [(iv.fra, iv.til, iv.regnr) for iv in reloaded.intervals] == [
        (3000, 3099, "10")
    ]


def test_save_rl_baseline_document_clears_formel_for_vanlig_linje(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

    doc = regnskap_config.RLBaselineDocument(
        lines=[
            regnskap_config.RLBaselineLine(
                regnr="10",
                regnskapslinje="A",
                sumpost=False,
                formel="skal ikke lagres",
            )
        ]
    )
    regnskap_config.save_rl_baseline_document(doc)
    reloaded = regnskap_config.load_rl_baseline_document()
    assert reloaded.lines[0].formel == ""


def test_save_rl_baseline_document_preserves_extra_columns(
    tmp_path: Path, monkeypatch
) -> None:
    """extra-dict på RLBaselineLine skal round-trippes via JSON."""

    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

    doc = regnskap_config.RLBaselineDocument(
        lines=[
            regnskap_config.RLBaselineLine(
                regnr="10",
                regnskapslinje="A",
                sumpost=False,
                extra={"fortegn": 1, "sumnivå": 1.0},
            )
        ]
    )
    regnskap_config.save_rl_baseline_document(doc)
    reloaded = regnskap_config.load_rl_baseline_document()
    assert reloaded.lines[0].extra.get("fortegn") == 1

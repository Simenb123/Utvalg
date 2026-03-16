from __future__ import annotations

from pathlib import Path

import pandas as pd


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name)


def test_import_and_load_regnskap_config(tmp_path: Path, monkeypatch) -> None:
    # Tving datamappe til temp
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))

    import regnskap_config

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

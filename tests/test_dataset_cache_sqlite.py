from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_dataset_cache_sqlite_roundtrip_preserves_datetime(tmp_path: Path):
    import dataset_cache_sqlite

    df = pd.DataFrame(
        {
            "Konto": [1000, 2000],
            "Bilag": ["A1", "A2"],
            "Beløp": [1.5, -2.0],
            "Dato": pd.to_datetime(["2025-01-01", "2025-01-02"]),
            "Tekst": ["x", "y"],
        }
    )

    db = tmp_path / "cache.sqlite"
    meta = dataset_cache_sqlite.save_cache(df, db, source_sha256="a" * 64, signature="b" * 64)
    assert meta.rows == 2
    assert meta.cols == 5
    df2, meta2 = dataset_cache_sqlite.load_cache(db)
    assert meta2.schema_version == dataset_cache_sqlite.SCHEMA_VERSION
    # Cache loader re-genererer lowercase aliaser for kompatibilitet.
    for c in df.columns:
        assert c in df2.columns
    assert pd.api.types.is_datetime64_any_dtype(df2["Dato"])


def test_dataset_cache_sqlite_store_cache_handles_large_multi_insert_limits(tmp_path: Path):
    """Regression: unngå "too many SQL variables" ved caching.

    Pandas sin to_sql(method="multi") kan bygge én stor INSERT med (rader*kolonner)
    bind-parametre. SQLite har en compile-time grense for hvor mange bind-parametre
    et statement kan ha. Denne testen bygger en DF som er stor nok til å trigge
    problemet i mange miljøer dersom vi bruker `method="multi"` med stor chunksize.
    """

    import dataset_cache_sqlite

    rows = 10_000
    cols = 30

    df = pd.DataFrame({f"c{i}": list(range(rows)) for i in range(cols)})
    db = tmp_path / "big_cache.sqlite"

    dataset_cache_sqlite.save_cache(df, db, source_sha256="a" * 64, signature="b" * 64)
    df2, meta2 = dataset_cache_sqlite.load_cache(db)
    assert meta2.rows == rows
    assert df2.shape == (rows, cols)


def test_build_dataset_uses_cache_on_second_run(tmp_path: Path, monkeypatch):
    # Isoler klientlager under tmp_path
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path))
    # La clients_root være default under data_dir/clients
    # (client_store.get_clients_root faller tilbake til dette)

    import client_store
    from dataset_pane_build import BuildRequest, build_dataset

    # Lag en minimal hovedbok-fil
    df_in = pd.DataFrame(
        {
            "AccountID": [1000, 2000],
            "AccountDescription": ["Salg", "Kost"],
            "VoucherNo": ["V1", "V2"],
            "Amount": [10.0, -10.0],
            "TransactionDate": ["2025-01-01", "2025-01-02"],
            "Description": ["t1", "t2"],
        }
    )
    xlsx = tmp_path / "general_ledger.xlsx"
    df_in.to_excel(xlsx, index=False)

    mapping = {
        "Konto": "AccountID",
        "Kontonavn": "AccountDescription",
        "Bilag": "VoucherNo",
        "Beløp": "Amount",
        "Dato": "TransactionDate",
        "Tekst": "Description",
    }

    req = BuildRequest(
        path=xlsx,
        mapping=mapping,
        sheet_name=None,
        header_row=1,
        store_client="Demo AS",
        store_year="2025",
    )

    # Første gang: bygg + skriv cache
    res1 = build_dataset(req)
    assert res1.stored_version_id
    assert res1.loaded_from_cache is False

    v = client_store.get_version("Demo AS", year="2025", dtype="hb", version_id=res1.stored_version_id)
    assert v is not None
    dc = client_store.get_dataset_cache_meta("Demo AS", year="2025", dtype="hb", version_id=res1.stored_version_id)
    assert isinstance(dc, dict)
    assert dc.get("file")
    db_path = client_store.datasets_dir("Demo AS", year="2025", dtype="hb") / str(dc["file"])
    assert db_path.exists()

    # Andre gang: skal treffe cache og IKKE kalle build_from_file
    def _boom(*args, **kwargs):
        raise AssertionError("build_from_file skal ikke kalles ved cache-hit")

    monkeypatch.setattr("dataset_pane_build.build_from_file", _boom)

    res2 = build_dataset(req)
    assert res2.loaded_from_cache is True
    assert res2.cache_path
    assert Path(res2.cache_path).exists()
    assert pd.api.types.is_datetime64_any_dtype(res2.df["Dato"])


def test_fill_down_bilag_inplace_fills_missing_and_syncs_alias() -> None:
    import dataset_cache_sqlite

    df = pd.DataFrame(
        {
            "Bilag": ["V1", None, "", "V2", None],
            # Alias-kolonne (sånn dataset normalt ser ut i appen)
            "bilag": ["V1", None, "", "V2", None],
            "Beløp": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )

    filled = dataset_cache_sqlite.fill_down_bilag_inplace(df)

    # None + "" + None -> fylles ned
    assert filled == 3
    assert df["Bilag"].tolist() == ["V1", "V1", "V1", "V2", "V2"]
    # Alias skal være i sync
    assert df["bilag"].tolist() == df["Bilag"].tolist()

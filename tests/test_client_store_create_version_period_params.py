from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_create_version_accepts_period_params_and_stores_in_meta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path / "data"))

    import client_store

    importlib.reload(client_store)

    src = tmp_path / "hb.xlsx"
    src.write_text("dummy", encoding="utf-8")

    client_store.ensure_client("Demo AS")

    v = client_store.create_version(
        "Demo AS",
        year="2024",
        dtype="hb",
        src_path=src,
        make_active=True,
        period_from=1,
        period_to=12,
        period_label="2024",
    )

    assert v.meta.get("period_from") == 1
    assert v.meta.get("period_to") == 12
    assert v.meta.get("period_label") == "2024"

    # Fil skal være kopiert inn i klientlageret
    assert v.path is not None
    p = Path(v.path)
    assert p.exists()
    assert p.read_text(encoding="utf-8") == "dummy"

    # SHA256 skal være satt
    sha = v.meta.get("sha256")
    assert isinstance(sha, str)
    assert len(sha) == 64

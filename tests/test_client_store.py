from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _write(p: Path, content: str) -> Path:
    p.write_text(content, encoding="utf-8")
    return p


def _read_audit_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out: list[dict] = []
    for ln in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict):
                out.append(obj)
        except Exception:
            continue
    return out


def test_client_store_create_list_set_active_and_delete(tmp_path: Path, monkeypatch) -> None:
    # Isoler testdata og unngå å skrive i repo-mappen
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path / "data"))

    import client_store

    importlib.reload(client_store)

    assert client_store.list_clients() == []

    cdir = client_store.ensure_client("Demo AS")
    assert cdir.exists()
    assert "Demo AS" in client_store.list_clients()

    audit_p = client_store.audit_log_path("Demo AS")
    assert audit_p.exists()
    events = _read_audit_jsonl(audit_p)
    assert any(e.get("action") == "client_created" for e in events)

    hb1 = _write(tmp_path / "hb.xlsx", "dummy-1")
    v1 = client_store.create_version(
        "Demo AS",
        year="2024",
        dtype="hb",
        src_path=hb1,
        make_active=True,
        period_from=1,
        period_to=12,
        period_label="2024",
    )
    assert Path(v1.path).exists()
    assert any(e.get("action") == "version_created" and e.get("version_id") == v1.id for e in _read_audit_jsonl(audit_p))

    active = client_store.get_active_version("Demo AS", year="2024", dtype="hb")
    assert active is not None
    assert active.id == v1.id

    hb2 = _write(tmp_path / "hb2.xlsx", "dummy-2")
    v2 = client_store.create_version("Demo AS", year="2024", dtype="hb", src_path=hb2, make_active=True)
    assert Path(v2.path).exists()

    active2 = client_store.get_active_version("Demo AS", year="2024", dtype="hb")
    assert active2 is not None
    assert active2.id == v2.id

    ok_set = client_store.set_active_version("Demo AS", year="2024", dtype="hb", version_id=v1.id)
    assert ok_set is True
    active3 = client_store.get_active_version("Demo AS", year="2024", dtype="hb")
    assert active3 is not None and active3.id == v1.id

    # Slett aktiv (v1) -> v2 blir aktiv (nyeste gjenværende)
    ok_del = client_store.delete_version("Demo AS", year="2024", dtype="hb", version_id=v1.id)
    assert ok_del is True
    active4 = client_store.get_active_version("Demo AS", year="2024", dtype="hb")
    assert active4 is not None and active4.id == v2.id

    # Slett som ikke finnes
    assert client_store.delete_version("Demo AS", year="2024", dtype="hb", version_id="does-not-exist") is False


def test_client_store_duplicate_content_raises_and_audits(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path / "data"))

    import client_store

    importlib.reload(client_store)

    client_store.ensure_client("Demo AS")
    audit_p = client_store.audit_log_path("Demo AS")

    hb1 = _write(tmp_path / "hb.xlsx", "SAME")
    v1 = client_store.create_version("Demo AS", year="2024", dtype="hb", src_path=hb1, make_active=True)

    hb2 = _write(tmp_path / "hb2.xlsx", "SAME")
    with pytest.raises(client_store.DuplicateContentError) as ei:
        client_store.create_version("Demo AS", year="2024", dtype="hb", src_path=hb2, make_active=True)

    assert ei.value.existing_id == v1.id

    events = _read_audit_jsonl(audit_p)
    assert any(e.get("action") == "version_duplicate_rejected" and e.get("existing_id") == v1.id for e in events)

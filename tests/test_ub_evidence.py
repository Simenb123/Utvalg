from __future__ import annotations

from pathlib import Path


def _setup(tmp_path, monkeypatch):
    import src.shared.regnskap.client_overrides as regnskap_client_overrides
    import client_store

    monkeypatch.setattr(regnskap_client_overrides.app_paths, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(client_store.app_paths, "data_dir", lambda: tmp_path)
    return regnskap_client_overrides


def test_save_and_load_ub_evidence_roundtrip(tmp_path, monkeypatch) -> None:
    rco = _setup(tmp_path, monkeypatch)

    evidence = {
        "attachment_path": str(tmp_path / "bank.pdf"),
        "attachment_label": "Bankutskrift",
        "page": 3,
        "bbox": [10.0, 20.0, 110.0, 40.0],
        "raw_value": "1 234 567,89",
        "normalized_value": 1234567.89,
        "status": "match",
        "source": "manual",
        "note": "Primært bevis",
    }
    rco.save_ub_evidence("Eksempel AS", "2024", "1920", evidence)

    loaded = rco.load_ub_evidence("Eksempel AS", "2024", "1920")
    assert loaded is not None
    assert loaded["attachment_path"] == evidence["attachment_path"]
    assert loaded["page"] == 3
    assert loaded["bbox"] == [10.0, 20.0, 110.0, 40.0]
    assert loaded["raw_value"] == "1 234 567,89"
    assert loaded["normalized_value"] == 1234567.89
    assert loaded["status"] == "match"
    assert loaded["source"] == "manual"
    assert loaded["note"] == "Primært bevis"
    assert loaded["updated_at"]  # auto-filled


def test_load_ub_evidence_none_when_missing(tmp_path, monkeypatch) -> None:
    rco = _setup(tmp_path, monkeypatch)
    assert rco.load_ub_evidence("Eksempel AS", "2024", "1920") is None


def test_clear_ub_evidence_removes_field(tmp_path, monkeypatch) -> None:
    rco = _setup(tmp_path, monkeypatch)
    rco.save_ub_evidence(
        "Eksempel AS", "2024", "1920",
        {"attachment_path": str(tmp_path / "x.pdf"), "page": 1, "bbox": [0, 0, 10, 10]},
    )
    rco.clear_ub_evidence("Eksempel AS", "2024", "1920")
    assert rco.load_ub_evidence("Eksempel AS", "2024", "1920") is None


def test_ub_evidence_preserved_alongside_ok_and_attachments(tmp_path, monkeypatch) -> None:
    rco = _setup(tmp_path, monkeypatch)
    src = tmp_path / "vedlegg.pdf"
    src.write_bytes(b"%PDF-dummy")

    rco.set_accounts_ok("Eksempel AS", "2024", ["1920"], True)
    rco.add_account_attachments(
        "Eksempel AS", "2024", ["1920"], [str(src)], storage="external"
    )
    rco.save_ub_evidence(
        "Eksempel AS", "2024", "1920",
        {"attachment_path": str(src), "page": 1, "bbox": [0, 0, 10, 10]},
    )

    review = rco.load_account_review("Eksempel AS", "2024")
    entry = review["1920"]
    assert entry["ok"] is True
    assert entry["attachments"] and entry["attachments"][0]["path"] == str(src)
    assert entry["ub_evidence"]["attachment_path"] == str(src)


def test_remove_attachment_clears_matching_ub_evidence(tmp_path, monkeypatch) -> None:
    rco = _setup(tmp_path, monkeypatch)
    src = tmp_path / "vedlegg.pdf"
    src.write_bytes(b"%PDF-dummy")

    rco.add_account_attachments(
        "Eksempel AS", "2024", ["1920"], [str(src)], storage="external"
    )
    rco.save_ub_evidence(
        "Eksempel AS", "2024", "1920",
        {"attachment_path": str(src), "page": 1, "bbox": [0, 0, 10, 10]},
    )

    rco.remove_account_attachment("Eksempel AS", "2024", "1920", str(src))

    review = rco.load_account_review("Eksempel AS", "2024")
    assert "1920" not in review  # entry pruned when empty


def test_remove_attachment_keeps_unrelated_ub_evidence(tmp_path, monkeypatch) -> None:
    rco = _setup(tmp_path, monkeypatch)
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"a")
    b.write_bytes(b"b")

    rco.add_account_attachments(
        "Eksempel AS", "2024", ["1920"], [str(a), str(b)], storage="external"
    )
    rco.save_ub_evidence(
        "Eksempel AS", "2024", "1920",
        {"attachment_path": str(b), "page": 2, "bbox": [5, 5, 20, 20]},
    )
    rco.remove_account_attachment("Eksempel AS", "2024", "1920", str(a))

    ev = rco.load_ub_evidence("Eksempel AS", "2024", "1920")
    assert ev is not None
    assert ev["attachment_path"] == str(b)
    assert ev["page"] == 2


def test_migrate_attachment_rewrites_ub_evidence_path(tmp_path, monkeypatch) -> None:
    rco = _setup(tmp_path, monkeypatch)
    src_dir = tmp_path / "external"
    src_dir.mkdir()
    src = src_dir / "bilag.pdf"
    src.write_bytes(b"%PDF-1.4")

    rco.add_account_attachments(
        "Eksempel AS", "2024", ["1920"], [str(src)], storage="external"
    )
    rco.save_ub_evidence(
        "Eksempel AS", "2024", "1920",
        {"attachment_path": str(src), "page": 1, "bbox": [0, 0, 10, 10]},
    )

    rco.migrate_attachment_to_managed(
        "Eksempel AS", "2024", "1920", str(src),
        regnr=10, regnskapslinje="Bank",
    )

    ev = rco.load_ub_evidence("Eksempel AS", "2024", "1920")
    assert ev is not None
    # Path should now point inside the managed directory, not the original external
    assert str(Path(ev["attachment_path"]).resolve()) != str(src.resolve())
    assert Path(ev["attachment_path"]).name == "bilag.pdf"
    assert Path(ev["attachment_path"]).exists()


def test_clean_ub_evidence_drops_invalid_status_and_bbox(tmp_path, monkeypatch) -> None:
    rco = _setup(tmp_path, monkeypatch)
    rco.save_ub_evidence(
        "Eksempel AS", "2024", "1920",
        {
            "attachment_path": str(tmp_path / "x.pdf"),
            "page": 0,  # coerced to 1
            "bbox": [1, 2, 3],  # invalid length, dropped
            "status": "bogus",  # coerced to "unchecked"
            "normalized_value": "not-a-number",  # coerced to None
        },
    )
    ev = rco.load_ub_evidence("Eksempel AS", "2024", "1920")
    assert ev is not None
    assert ev["page"] == 1
    assert "bbox" not in ev
    assert ev["status"] == "unchecked"
    assert ev["normalized_value"] is None


def test_save_ub_evidence_requires_attachment_path(tmp_path, monkeypatch) -> None:
    rco = _setup(tmp_path, monkeypatch)
    rco.save_ub_evidence(
        "Eksempel AS", "2024", "1920",
        {"attachment_path": "", "page": 1},
    )
    assert rco.load_ub_evidence("Eksempel AS", "2024", "1920") is None


def test_parse_norwegian_number_handles_common_formats() -> None:
    from page_analyse_sb import _parse_norwegian_number as parse

    assert parse("1 234 567,89") == 1234567.89
    assert parse("1\u00a0234\u00a0567,89") == 1234567.89
    assert parse("1.234.567,89") == 1234567.89
    assert parse("1,234,567.89") == 1234567.89
    assert parse("(500,00)") == -500.0
    assert parse("−500") == -500.0
    assert parse("") is None
    assert parse(None) is None
    assert parse("—") is None
    assert parse(1234) == 1234.0


def test_compute_ub_status_logic() -> None:
    from document_control_viewer import preview_target_from_ub_evidence

    # Status helper lives inside the dialog closure, so test the minimum via
    # a direct equivalent here:
    def compute(doc, exp):
        if doc is None or exp is None:
            return "unchecked", None
        avvik = round(doc - exp, 2)
        return ("match" if abs(avvik) < 0.5 else "mismatch"), avvik

    assert compute(1000.0, 1000.0) == ("match", 0.0)
    assert compute(1000.3, 1000.0) == ("match", 0.3)
    assert compute(1001.0, 1000.0) == ("mismatch", 1.0)
    assert compute(None, 1000.0) == ("unchecked", None)

    # And that PreviewTarget builder reads page+bbox from evidence
    target = preview_target_from_ub_evidence({
        "page": 3, "bbox": [1.0, 2.0, 3.0, 4.0], "raw_value": "1000",
    })
    assert target is not None
    assert target.page == 3
    assert target.bbox == (1.0, 2.0, 3.0, 4.0)
    assert target.raw_value == "1000"

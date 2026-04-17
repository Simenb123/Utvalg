"""Tester for account_workpaper_pdf — to-siders kontoarbeidspapir.

- Side 1: kompakt oppsummering (alltid)
- Side 2: full dokumentside med highlight (kun når ub_evidence peker til
  eksisterende PDF med gyldig side)
"""
from __future__ import annotations

from pathlib import Path


def _read_pdf_text(path: Path) -> str:
    import fitz
    doc = fitz.open(path)
    try:
        return "\n".join(doc.load_page(i).get_text("text") for i in range(len(doc)))
    finally:
        doc.close()


def _page_text(path: Path, page_idx: int) -> str:
    import fitz
    doc = fitz.open(path)
    try:
        return doc.load_page(page_idx).get_text("text")
    finally:
        doc.close()


def _page_count(path: Path) -> int:
    import fitz
    doc = fitz.open(path)
    try:
        return len(doc)
    finally:
        doc.close()


def _write_source_pdf(path: Path, value_text: str = "1 234,56", keyword: str = "UB") -> None:
    """Enkel kilde-PDF med én verditekst og nøkkelord like ved."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=595, height=842)
        page.insert_text(fitz.Point(80, 300), keyword, fontname="hebo", fontsize=12)
        page.insert_text(fitz.Point(130, 300), value_text, fontname="helv", fontsize=12)
        doc.save(str(path))
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Side 1 — oppsummering
# ---------------------------------------------------------------------------

def test_export_basic_writes_single_page_when_no_evidence(tmp_path: Path) -> None:
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    out = tmp_path / "wp.pdf"
    data = AccountWorkpaperData(
        client="TestKlient", year="2025",
        konto="1920", kontonavn="Bankinnskudd",
        regnr="17", regnskapslinje="Bankinnskudd, kontanter",
        ib="100 000,00", endring="+25 000,00",
        ub="125 000,00", ub_fjor="100 000,00",
        antall="12", ok=True,
        comment="Avstemt mot kontoutskrift.",
        attachments=[
            {"label": "Kontoutskrift 2025.pdf",
             "path": str(tmp_path / "utskrift.pdf"),
             "storage": "managed"},
        ],
        ub_evidence=None,
    )

    export_account_workpaper(data=data, output_path=str(out))
    assert out.exists() and out.stat().st_size > 0
    assert _page_count(out) == 1

    text = _read_pdf_text(out)
    assert "Kontoarbeidspapir" in text
    assert "1920" in text
    assert "Bankinnskudd" in text
    assert "Kontosammendrag" in text
    assert "Vedlegg" in text
    assert "UB-bevis" in text


def test_export_comment_hidden_when_empty(tmp_path: Path) -> None:
    """Kommentarseksjon skal ikke vises når kommentaren er tom."""
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    out = tmp_path / "nc.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(konto="3000", kontonavn="Salg", comment=""),
        output_path=str(out),
    )
    text = _read_pdf_text(out)
    assert "Kommentar" not in text


def test_export_comment_shown_when_present(tmp_path: Path) -> None:
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    out = tmp_path / "c.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            comment="Avstemt mot bankkonto. Ingen uavklarte poster.",
        ),
        output_path=str(out),
    )
    text = _read_pdf_text(out)
    assert "Kommentar" in text
    assert "Avstemt" in text
    assert "uavklarte poster" in text


def test_export_attachments_show_filenames_not_paths(tmp_path: Path) -> None:
    """Vedlegg skal vises med kun filnavn — ingen trunkert sti, ingen storage-kolonne."""
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    out = tmp_path / "paths.pdf"
    deep_path = str(tmp_path / "a" / "b" / "c" / "Kontoutskrift 2025.pdf")
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            attachments=[
                {"label": "Kontoutskrift 2025.pdf", "path": deep_path,
                 "storage": "managed"},
                {"label": "Revisornotat.pdf",
                 "path": str(tmp_path / "r.pdf"), "storage": "external"},
            ],
        ),
        output_path=str(out),
    )
    text = _read_pdf_text(out)
    assert "Kontoutskrift 2025.pdf" in text
    assert "Revisornotat.pdf" in text
    # Ingen sti, ingen storage-etikett
    assert "Utvalg-lager" not in text
    assert "Ekstern" not in text
    assert str(tmp_path / "a") not in text


def test_export_primary_evidence_marked_in_attachment_list(tmp_path: Path) -> None:
    """Når ub_evidence peker til et vedlegg, skal det merkes som primært bevis."""
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    out = tmp_path / "primary.pdf"
    src = tmp_path / "evidence.pdf"
    _write_source_pdf(src)
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            attachments=[
                {"label": "evidence.pdf", "path": str(src), "storage": "managed"},
                {"label": "extra.pdf", "path": str(tmp_path / "x.pdf"),
                 "storage": "external"},
            ],
            ub_evidence={
                "attachment_path": str(src),
                "attachment_label": "evidence.pdf",
                "page": 1,
                "bbox": [130, 290, 200, 310],
                "status": "match",
                "source": "auto",
            },
        ),
        output_path=str(out),
    )
    text = _page_text(out, 0)
    assert "Primært bevis: evidence.pdf" in text
    # "Øvrige vedlegg" listes
    assert "extra.pdf" in text


def test_export_includes_ub_evidence_metadata(tmp_path: Path) -> None:
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    out = tmp_path / "ev.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920", kontonavn="Bank",
            ub_evidence={
                "attachment_path": str(tmp_path / "missing.pdf"),
                "attachment_label": "Kontoutskrift.pdf",
                "page": 3,
                "bbox": [100, 200, 160, 210],
                "raw_value": "125 000,00",
                "normalized_value": 125000.0,
                "status": "match",
                "source": "auto",
                "note": "OK",
            },
        ),
        output_path=str(out),
    )
    text = _read_pdf_text(out)
    assert "Kontoutskrift.pdf" in text
    assert "Automatisk forslag" in text
    assert "OK - verdi stemmer" in text
    assert "125 000,00" in text


def test_export_ub_evidence_note_hidden_when_empty(tmp_path: Path) -> None:
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    out = tmp_path / "nonote.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            ub_evidence={
                "attachment_path": str(tmp_path / "missing.pdf"),
                "attachment_label": "k.pdf",
                "page": 1, "bbox": [0, 0, 10, 10],
                "status": "unchecked", "source": "manual",
                "note": "",
            },
        ),
        output_path=str(out),
    )
    text = _read_pdf_text(out)
    assert "Notat" not in text


# ---------------------------------------------------------------------------
# Side 2 — full evidensside
# ---------------------------------------------------------------------------

def test_export_with_pdf_evidence_produces_two_pages(tmp_path: Path) -> None:
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper
    import fitz

    src = tmp_path / "source.pdf"
    _write_source_pdf(src)
    out = tmp_path / "two_pages.pdf"

    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            ub_evidence={
                "attachment_path": str(src),
                "attachment_label": "source.pdf",
                "page": 1,
                "bbox": [130, 290, 200, 310],
                "raw_value": "1 234,56",
                "normalized_value": 1234.56,
                "status": "match",
                "source": "auto",
            },
        ),
        output_path=str(out),
    )
    assert _page_count(out) == 2

    # Side 2 skal ha minst ett bilde (dokumentside)
    doc = fitz.open(out)
    try:
        p2 = doc.load_page(1)
        assert len(p2.get_images()) >= 1
        page2_text = p2.get_text("text")
    finally:
        doc.close()
    assert "Dokumentside fra source.pdf" in page2_text
    assert "side 1" in page2_text


def test_export_evidence_page_without_bbox_notes_missing_highlight(tmp_path: Path) -> None:
    """Side uten gyldig bbox skal fortsatt renderes, med kort note om at
    eksakt markering ikke var tilgjengelig."""
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    src = tmp_path / "no_bbox.pdf"
    _write_source_pdf(src)
    out = tmp_path / "wp.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            ub_evidence={
                "attachment_path": str(src),
                "attachment_label": "no_bbox.pdf",
                "page": 1,
                "bbox": None,
                "status": "unchecked",
                "source": "manual",
            },
        ),
        output_path=str(out),
    )
    assert _page_count(out) == 2
    page2 = _page_text(out, 1)
    assert "Dokumentside fra no_bbox.pdf" in page2
    assert "Eksakt markering" in page2


def test_export_evidence_missing_source_yields_single_page_with_fallback(tmp_path: Path) -> None:
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    out = tmp_path / "missing.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            ub_evidence={
                "attachment_path": str(tmp_path / "doesnotexist.pdf"),
                "attachment_label": "doesnotexist.pdf",
                "page": 1,
                "bbox": [10, 10, 20, 20],
                "status": "unchecked",
                "source": "manual",
            },
        ),
        output_path=str(out),
    )
    assert _page_count(out) == 1
    text = _page_text(out, 0)
    assert "Full evidensside kunne ikke genereres" in text


def test_export_non_pdf_attachment_yields_single_page(tmp_path: Path) -> None:
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    fake_img = tmp_path / "snap.png"
    fake_img.write_bytes(b"\x89PNG\r\n\x1a\n")

    out = tmp_path / "img.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            ub_evidence={
                "attachment_path": str(fake_img),
                "attachment_label": "snap.png",
                "page": 1,
                "bbox": [10, 10, 20, 20],
            },
        ),
        output_path=str(out),
    )
    assert _page_count(out) == 1


def test_export_evidence_page_number_out_of_range_yields_single_page(tmp_path: Path) -> None:
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    src = tmp_path / "oneop.pdf"
    _write_source_pdf(src)  # kun 1 side
    out = tmp_path / "wp.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            ub_evidence={
                "attachment_path": str(src),
                "attachment_label": "oneop.pdf",
                "page": 5,  # finnes ikke
                "bbox": [0, 0, 10, 10],
            },
        ),
        output_path=str(out),
    )
    assert _page_count(out) == 1


def test_export_no_evidence_no_fallback_note(tmp_path: Path) -> None:
    """Når det ikke finnes noe UB-bevis, skal heller ikke fallback-notisen vises."""
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    out = tmp_path / "noev.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(konto="1920", ub_evidence=None),
        output_path=str(out),
    )
    text = _page_text(out, 0)
    assert "Full evidensside kunne ikke genereres" not in text
    assert "(ingen UB-bevis lagret)" in text


# ---------------------------------------------------------------------------
# Tittel-robusthet
# ---------------------------------------------------------------------------

def test_export_title_uses_only_konto_and_kontonavn(tmp_path: Path) -> None:
    """Tittellinjen skal kun inneholde konto + kontonavn — ingen
    kommentarer/fritekst skal lekke inn, og linjeskift må håndteres."""
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    out = tmp_path / "title.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            kontonavn="Bankinnskudd",
            comment="Dette er en lang kommentar som IKKE skal være i tittelen.",
        ),
        output_path=str(out),
    )
    first_line = _page_text(out, 0).splitlines()[0]
    assert first_line == "Kontoarbeidspapir - 1920 Bankinnskudd"
    assert "kommentar" not in first_line.lower()


def test_export_title_sanitizes_newlines_in_kontonavn(tmp_path: Path) -> None:
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    out = tmp_path / "title_nl.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            kontonavn="Bank\ninnskudd",
        ),
        output_path=str(out),
    )
    first_line = _page_text(out, 0).splitlines()[0]
    assert first_line == "Kontoarbeidspapir - 1920 Bank innskudd"


# ---------------------------------------------------------------------------
# Trimming av hvite marger på side 2
# ---------------------------------------------------------------------------

def _write_wide_margin_pdf(path: Path) -> None:
    """Enkel kilde-PDF der innholdet er konsentrert midt på siden —
    ytre marger er store og hvite."""
    import fitz
    doc = fitz.open()
    try:
        page = doc.new_page(width=595, height=842)
        page.insert_text(fitz.Point(250, 410), "UB", fontname="hebo", fontsize=12)
        page.insert_text(fitz.Point(290, 410), "1 234,56", fontname="helv", fontsize=12)
        doc.save(str(path))
    finally:
        doc.close()


def test_compute_content_rect_trims_white_margins(tmp_path: Path) -> None:
    import fitz
    from account_workpaper_pdf import _compute_content_rect

    src = tmp_path / "wide.pdf"
    _write_wide_margin_pdf(src)
    doc = fitz.open(str(src))
    try:
        rect = _compute_content_rect(doc.load_page(0))
    finally:
        doc.close()
    page_rect = fitz.Rect(0, 0, 595, 842)
    assert rect.width < page_rect.width
    assert rect.height < page_rect.height
    assert rect.x0 > 100
    assert rect.x1 < 500


def test_compute_content_rect_includes_bbox_via_union(tmp_path: Path) -> None:
    """Når UB-bbox inkluderes, skal rendret region fortsatt dekke bbox slik
    at highlight kan tegnes på side 2."""
    import fitz
    from account_workpaper_pdf import _compute_content_rect

    src = tmp_path / "wide.pdf"
    _write_wide_margin_pdf(src)
    doc = fitz.open(str(src))
    try:
        trimmed = _compute_content_rect(doc.load_page(0))
    finally:
        doc.close()
    bbox = fitz.Rect(245, 400, 360, 420)
    union = trimmed | bbox
    assert union.x0 <= bbox.x0 and union.y0 <= bbox.y0
    assert union.x1 >= bbox.x1 and union.y1 >= bbox.y1


def test_export_evidence_page_trims_margins_and_keeps_highlight(tmp_path: Path) -> None:
    """Etter trimming skal side 2 fortsatt inneholde UB-etikett + caption."""
    from account_workpaper_pdf import AccountWorkpaperData, export_account_workpaper

    src = tmp_path / "wide.pdf"
    _write_wide_margin_pdf(src)
    out = tmp_path / "ev_trim.pdf"
    export_account_workpaper(
        data=AccountWorkpaperData(
            konto="1920",
            ub_evidence={
                "attachment_path": str(src),
                "attachment_label": "wide.pdf",
                "page": 1,
                "bbox": [285, 398, 355, 420],
                "status": "match", "source": "auto",
            },
        ),
        output_path=str(out),
    )
    assert _page_count(out) == 2
    page2 = _page_text(out, 1)
    assert "UB" in page2
    assert "Dokumentside fra wide.pdf" in page2


# ---------------------------------------------------------------------------
# Pakke-eksport: mappe med PDF + kopiert kildefil
# ---------------------------------------------------------------------------

def test_export_package_creates_folder_with_pdf_and_source(tmp_path: Path) -> None:
    from account_workpaper_pdf import (
        AccountWorkpaperData, export_account_workpaper_package,
    )

    src = tmp_path / "source" / "evidence.pdf"
    src.parent.mkdir(parents=True)
    _write_source_pdf(src)

    dest = tmp_path / "exports"
    result = export_account_workpaper_package(
        data=AccountWorkpaperData(
            konto="1920", kontonavn="Bank",
            year="2025",
            ub_evidence={
                "attachment_path": str(src),
                "attachment_label": "evidence.pdf",
                "page": 1,
                "bbox": [130, 290, 200, 310],
                "status": "match", "source": "auto",
            },
        ),
        dest_dir=dest,
        year="2025",
    )
    assert result.folder.exists() and result.folder.is_dir()
    assert result.folder.name == "Kontoarbeidspapir_1920_2025"
    assert result.pdf_path.exists() and result.pdf_path.name.startswith("01_")
    assert result.source_included is True
    assert result.source_path is not None
    # Originalt filnavn skal beholdes — ingen prefiks på kildedokumentet
    assert result.source_path.name == "evidence.pdf"
    # PDF-en er fortsatt to-siders
    assert _page_count(result.pdf_path) == 2


def test_export_package_without_source_still_writes_pdf(tmp_path: Path) -> None:
    from account_workpaper_pdf import (
        AccountWorkpaperData, export_account_workpaper_package,
    )

    dest = tmp_path / "exports"
    result = export_account_workpaper_package(
        data=AccountWorkpaperData(konto="1920", year="2025"),
        dest_dir=dest, year="2025",
    )
    assert result.folder.exists()
    assert result.pdf_path.exists()
    assert result.source_included is False
    assert result.source_path is None


def test_export_package_falls_back_to_first_attachment(tmp_path: Path) -> None:
    """Uten ub_evidence skal første tilgjengelige vedlegg brukes som kildefil."""
    from account_workpaper_pdf import (
        AccountWorkpaperData, export_account_workpaper_package,
    )

    att = tmp_path / "kontoutskrift.pdf"
    _write_source_pdf(att)

    dest = tmp_path / "exports"
    result = export_account_workpaper_package(
        data=AccountWorkpaperData(
            konto="3000", year="2025",
            attachments=[
                {"label": "Kontoutskrift.pdf", "path": str(att),
                 "storage": "managed"},
            ],
            ub_evidence=None,
        ),
        dest_dir=dest, year="2025",
    )
    assert result.source_included is True
    assert result.source_path is not None
    # Originalt filnavn beholdes — ingen prefiks
    assert result.source_path.name == "kontoutskrift.pdf"


def test_export_package_avoids_overwriting_existing_folder(tmp_path: Path) -> None:
    from account_workpaper_pdf import (
        AccountWorkpaperData, export_account_workpaper_package,
    )

    dest = tmp_path / "exports"
    kwargs = dict(
        data=AccountWorkpaperData(konto="1920", year="2025"),
        dest_dir=dest, year="2025",
    )
    first = export_account_workpaper_package(**kwargs)
    second = export_account_workpaper_package(**kwargs)
    assert first.folder != second.folder
    assert first.folder.exists() and second.folder.exists()
    assert second.folder.name.startswith("Kontoarbeidspapir_1920_2025_")


def test_export_package_preserves_original_source_filename(tmp_path: Path) -> None:
    """Selv filnavn med mellomrom, æøå og årstall skal beholdes uendret."""
    from account_workpaper_pdf import (
        AccountWorkpaperData, export_account_workpaper_package,
    )

    src = tmp_path / "Kontoutskrift DNB 2025 - kvartal 4.pdf"
    _write_source_pdf(src)

    dest = tmp_path / "exports"
    result = export_account_workpaper_package(
        data=AccountWorkpaperData(
            konto="1920", year="2025",
            ub_evidence={
                "attachment_path": str(src),
                "attachment_label": "Kontoutskrift DNB 2025 - kvartal 4.pdf",
                "page": 1,
                "bbox": [130, 290, 200, 310],
                "status": "match", "source": "auto",
            },
        ),
        dest_dir=dest, year="2025",
    )
    assert result.source_included is True
    assert result.source_path is not None
    assert result.source_path.name == "Kontoutskrift DNB 2025 - kvartal 4.pdf"


def test_export_package_with_missing_source_file_is_graceful(tmp_path: Path) -> None:
    """Hvis ub_evidence peker til en sti som ikke finnes, skal eksporten
    fortsatt produsere PDF uten å krasje (source_included=False)."""
    from account_workpaper_pdf import (
        AccountWorkpaperData, export_account_workpaper_package,
    )

    dest = tmp_path / "exports"
    result = export_account_workpaper_package(
        data=AccountWorkpaperData(
            konto="1920", year="2025",
            ub_evidence={
                "attachment_path": str(tmp_path / "doesnotexist.pdf"),
                "attachment_label": "doesnotexist.pdf",
                "page": 1, "bbox": [0, 0, 10, 10],
            },
        ),
        dest_dir=dest, year="2025",
    )
    assert result.pdf_path.exists()
    assert result.source_included is False

"""account_workpaper_pdf.py

Enkel PDF-eksport av kontoarbeidspapir for revisjonsdokumentasjon.

Todelt layout:
- Side 1: kort oppsummering (konto, tall, kommentar, vedleggsfilnavn, UB-bevis-metadata)
- Side 2 (valgfri): full dokumentside fra kilde-PDF med highlight på lagret bbox

Side 2 lages kun når `ub_evidence` peker til en eksisterende PDF med gyldig side.
Ellers vises eksporten som én side med tydelig fallback-status.

Bruker PyMuPDF (`fitz`) — samme avhengighet som document_control_viewer.
Ingen ny ekstern avhengighet.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


# A4 portrait i punkt (1 pt = 1/72")
PAGE_W = 595.0
PAGE_H = 842.0
MARGIN_L = 56.0
MARGIN_R = 56.0
MARGIN_TOP = 56.0
MARGIN_BOTTOM = 56.0
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R
CONTENT_H = PAGE_H - MARGIN_TOP - MARGIN_BOTTOM

FONT_BODY = "helv"
FONT_BOLD = "hebo"
SIZE_TITLE = 16.0
SIZE_H2 = 11.0
SIZE_BODY = 10.0
SIZE_SMALL = 9.0

HIGHLIGHT_COLOR = (0.95, 0.65, 0.0)  # rolig oransje
HIGHLIGHT_WIDTH = 1.6


@dataclass
class AccountWorkpaperData:
    """Samlet payload til PDF-eksporten. Alle felter er valgfrie."""
    client: str = ""
    year: str = ""
    konto: str = ""
    kontonavn: str = ""
    regnr: str = ""
    regnskapslinje: str = ""
    ib: str = ""
    endring: str = ""
    ub: str = ""
    ub_fjor: str = ""
    antall: str = ""
    ok: bool = False
    comment: str = ""
    attachments: list[dict] = field(default_factory=list)
    ub_evidence: dict | None = None


# ---------------------------------------------------------------------------
# Side 1 — oppsummering
# ---------------------------------------------------------------------------

def _fmt_date(dt: datetime | None = None) -> str:
    dt = dt or datetime.now()
    return dt.strftime("%Y-%m-%d %H:%M")


def _safe_text(value: Any, placeholder: str = "-") -> str:
    s = "" if value is None else str(value)
    return s if s.strip() else placeholder


def _sanitize_one_line(value: Any) -> str:
    """Fjern linjeskift/tab fra enkelttekstverdier (f.eks. tittel)."""
    if value is None:
        return ""
    s = str(value)
    for ch in ("\r", "\n", "\t"):
        s = s.replace(ch, " ")
    return " ".join(s.split()).strip()


def _draw_header(page: Any, data: AccountWorkpaperData) -> float:
    """Tegn tittelblokk og returner y-posisjon under headeren."""
    import fitz

    y = MARGIN_TOP
    konto_txt = _sanitize_one_line(data.konto)
    navn_txt = _sanitize_one_line(data.kontonavn)
    ident = " ".join(t for t in (konto_txt, navn_txt) if t).strip()
    title = f"Kontoarbeidspapir - {ident}".rstrip(" -").strip()
    page.insert_text(
        fitz.Point(MARGIN_L, y + SIZE_TITLE),
        title, fontname=FONT_BOLD, fontsize=SIZE_TITLE,
    )
    y += SIZE_TITLE + 6

    meta = (
        f"Klient: {_safe_text(data.client)}    "
        f"År: {_safe_text(data.year)}    "
        f"Generert: {_fmt_date()}"
    )
    page.insert_text(
        fitz.Point(MARGIN_L, y + SIZE_SMALL),
        meta, fontname=FONT_BODY, fontsize=SIZE_SMALL, color=(0.45, 0.45, 0.45),
    )
    y += SIZE_SMALL + 10

    page.draw_line(
        fitz.Point(MARGIN_L, y),
        fitz.Point(PAGE_W - MARGIN_R, y),
        color=(0.75, 0.75, 0.75), width=0.5,
    )
    return y + 14


def _draw_section_heading(page: Any, y: float, text: str) -> float:
    import fitz
    page.insert_text(
        fitz.Point(MARGIN_L, y + SIZE_H2),
        text, fontname=FONT_BOLD, fontsize=SIZE_H2,
    )
    return y + SIZE_H2 + 8


def _draw_kv_rows(page: Any, y: float, pairs: Iterable[tuple[str, str]]) -> float:
    import fitz
    label_x = MARGIN_L
    value_x = MARGIN_L + 140
    line_h = SIZE_BODY + 4
    for label, value in pairs:
        page.insert_text(
            fitz.Point(label_x, y + SIZE_BODY),
            label, fontname=FONT_BODY, fontsize=SIZE_BODY,
            color=(0.40, 0.40, 0.40),
        )
        page.insert_text(
            fitz.Point(value_x, y + SIZE_BODY),
            _safe_text(value), fontname=FONT_BODY, fontsize=SIZE_BODY,
        )
        y += line_h
    return y


def _wrap_text_lines(text: str, max_chars: int = 95) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    for raw_line in text.splitlines() or [text]:
        if not raw_line.strip():
            lines.append("")
            continue
        words = raw_line.split(" ")
        cur = ""
        for w in words:
            candidate = (cur + " " + w).strip()
            if len(candidate) > max_chars and cur:
                lines.append(cur)
                cur = w
            else:
                cur = candidate
        if cur:
            lines.append(cur)
    return lines


def _draw_paragraph(page: Any, y: float, text: str) -> float:
    import fitz
    for line in _wrap_text_lines(text):
        page.insert_text(
            fitz.Point(MARGIN_L, y + SIZE_BODY),
            line, fontname=FONT_BODY, fontsize=SIZE_BODY,
        )
        y += SIZE_BODY + 3
    return y


def _attachment_filenames(attachments: list[dict]) -> list[str]:
    """Returner unike vedleggsnavn — label først, fall tilbake til filnavn fra sti."""
    names: list[str] = []
    seen: set[str] = set()
    for att in attachments:
        label = str(att.get("label", "") or "").strip()
        if not label:
            path = str(att.get("path", "") or "")
            label = Path(path).name if path else ""
            label = label.strip()
        if not label or label in seen:
            continue
        seen.add(label)
        names.append(label)
    return names


def _draw_attachment_summary(
    page: Any, y: float,
    attachments: list[dict],
    primary_name: str | None,
) -> float:
    """Tegn kompakt vedleggsoversikt — kun filnavn, ingen stier.

    Primærbeviset markeres dersom det finnes i listen; andre vedlegg
    listes komprimert.
    """
    import fitz

    names = _attachment_filenames(attachments)
    if not names:
        page.insert_text(
            fitz.Point(MARGIN_L, y + SIZE_BODY),
            "(ingen vedlegg)", fontname=FONT_BODY, fontsize=SIZE_BODY,
            color=(0.55, 0.55, 0.55),
        )
        return y + SIZE_BODY + 4

    primary = primary_name or ""
    others = [n for n in names if n != primary]

    if primary and primary in names:
        page.insert_text(
            fitz.Point(MARGIN_L, y + SIZE_BODY),
            f"Primært bevis: {primary}",
            fontname=FONT_BODY, fontsize=SIZE_BODY,
        )
        y += SIZE_BODY + 4

    if others:
        if len(others) <= 3:
            joined = ", ".join(others)
            label = f"Øvrige vedlegg: {joined}"
        else:
            label = f"Øvrige vedlegg: {len(others)}"
        for line in _wrap_text_lines(label):
            page.insert_text(
                fitz.Point(MARGIN_L, y + SIZE_BODY),
                line, fontname=FONT_BODY, fontsize=SIZE_BODY,
                color=(0.40, 0.40, 0.40),
            )
            y += SIZE_BODY + 3
    elif not primary:
        # Ingen primærbevis, men det finnes vedlegg — vis som kort liste
        for n in names[:3]:
            page.insert_text(
                fitz.Point(MARGIN_L, y + SIZE_BODY),
                n, fontname=FONT_BODY, fontsize=SIZE_BODY,
            )
            y += SIZE_BODY + 3
        if len(names) > 3:
            page.insert_text(
                fitz.Point(MARGIN_L, y + SIZE_BODY),
                f"(+ {len(names) - 3} flere)",
                fontname=FONT_BODY, fontsize=SIZE_SMALL,
                color=(0.55, 0.55, 0.55),
            )
            y += SIZE_SMALL + 3
    return y


def _draw_summary_page(page: Any, data: AccountWorkpaperData, *, has_evidence_page: bool) -> None:
    """Tegn side 1 — kompakt kontoarbeidspapir."""
    y = _draw_header(page, data)

    # Kontosammendrag
    y = _draw_section_heading(page, y, "Kontosammendrag")
    rl_line = f"{data.regnr} {data.regnskapslinje}".strip() or "-"
    y = _draw_kv_rows(page, y, [
        ("Konto", f"{data.konto}  {data.kontonavn}".strip()),
        ("Regnskapslinje", rl_line),
        ("IB", data.ib),
        ("Endring", data.endring),
        ("UB", data.ub),
        ("UB i fjor", data.ub_fjor),
        ("Antall", data.antall),
        ("Status", "OK" if data.ok else "Ikke markert OK"),
    ])
    y += 8

    # Kommentar — vises bare hvis den finnes
    if data.comment and data.comment.strip():
        y = _draw_section_heading(page, y, "Kommentar")
        y = _draw_paragraph(page, y, data.comment)
        y += 8

    # Vedlegg (kompakt)
    primary_name = ""
    ev = data.ub_evidence or {}
    if ev:
        primary_name = str(
            ev.get("attachment_label")
            or (Path(str(ev.get("attachment_path") or "")).name if ev.get("attachment_path") else "")
        ).strip()
    y = _draw_section_heading(page, y, "Vedlegg")
    y = _draw_attachment_summary(page, y, data.attachments, primary_name=primary_name)
    y += 8

    # UB-bevis
    y = _draw_section_heading(page, y, "UB-bevis")
    if ev:
        source_txt = {"manual": "Manuell markering", "auto": "Automatisk forslag"}.get(
            str(ev.get("source") or "").lower(), "-",
        )
        status_txt = {
            "match": "OK - verdi stemmer",
            "mismatch": "Avvik",
            "unchecked": "Ikke kontrollert",
        }.get(str(ev.get("status") or "").lower(), "Ikke kontrollert")
        rows: list[tuple[str, Any]] = [
            ("Valgt bevis", primary_name or "-"),
            ("Side", ev.get("page")),
            ("Kilde", source_txt),
            ("Rå verdi", ev.get("raw_value")),
            ("Tolket verdi", ev.get("normalized_value")),
            ("Status", status_txt),
        ]
        note = str(ev.get("note") or "").strip()
        if note:
            rows.append(("Notat", note))
        y = _draw_kv_rows(page, y, rows)
        y += 8

        if not has_evidence_page:
            import fitz
            # Tydelig tekstlig notis når vi ikke klarte å generere evidensside
            page.insert_text(
                fitz.Point(MARGIN_L, y + SIZE_SMALL),
                "Full evidensside kunne ikke genereres (kilde ikke tilgjengelig som PDF).",
                fontname=FONT_BODY, fontsize=SIZE_SMALL, color=(0.55, 0.30, 0.10),
            )
    else:
        y = _draw_paragraph(page, y, "(ingen UB-bevis lagret)")


# ---------------------------------------------------------------------------
# Side 2 — full dokumentside med highlight
# ---------------------------------------------------------------------------

def _can_render_evidence_page(evidence: dict | None) -> bool:
    """Sjekk om ub_evidence peker til en PDF-side vi kan rendere."""
    if not evidence:
        return False
    att_path = str(evidence.get("attachment_path") or "")
    if not att_path or Path(att_path).suffix.lower() != ".pdf":
        return False
    if not Path(att_path).exists():
        return False
    try:
        page_no = int(evidence.get("page") or 0)
    except Exception:
        return False
    if page_no < 1:
        return False
    try:
        import fitz
        doc = fitz.open(att_path)
        try:
            return page_no - 1 < len(doc)
        finally:
            doc.close()
    except Exception:
        return False


def _compute_content_rect(src_page: Any) -> Any:
    """Estimer bounding box for faktisk innhold (tekst + grafikk + bilder).

    Brukes til å trimme ytre hvite marger før side 2 skaleres inn.
    Returnerer `src_page.rect` som fallback hvis intet innhold kan måles.
    """
    import fitz

    rect = src_page.rect
    bounds: Any = None

    def _union(b: Any, extra: Any) -> Any:
        try:
            r = fitz.Rect(extra)
        except Exception:
            return b
        if r.is_empty or not r.is_valid:
            return b
        return r if b is None else b | r

    try:
        for block in src_page.get_text("blocks") or []:
            if len(block) >= 4:
                bounds = _union(bounds, (block[0], block[1], block[2], block[3]))
    except Exception:
        pass
    try:
        for d in src_page.get_drawings() or []:
            bounds = _union(bounds, d.get("rect"))
    except Exception:
        pass
    try:
        for img in src_page.get_image_info(hashes=False) or []:
            bounds = _union(bounds, img.get("bbox"))
    except Exception:
        pass

    if bounds is None or bounds.is_empty:
        return rect
    pad = 12.0
    trimmed = fitz.Rect(
        max(rect.x0, bounds.x0 - pad),
        max(rect.y0, bounds.y0 - pad),
        min(rect.x1, bounds.x1 + pad),
        min(rect.y1, bounds.y1 + pad),
    )
    if trimmed.is_empty or trimmed.width < 20 or trimmed.height < 20:
        return rect
    return trimmed


def _draw_full_evidence_page(doc: Any, evidence: dict) -> None:
    """Legg til ny side i `doc` med full kilde-sidesnutt + highlight.

    Antar at `_can_render_evidence_page(evidence)` returnerte True.
    """
    import fitz

    att_path = str(evidence.get("attachment_path") or "")
    page_no = int(evidence.get("page") or 1) - 1

    src_doc = fitz.open(att_path)
    try:
        src_page = src_doc.load_page(page_no)

        # Trim ytre hvite marger; sørg for at en eventuell bbox inkluderes
        content_rect = _compute_content_rect(src_page)
        bbox = evidence.get("bbox")
        bbox_rect: Any = None
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            try:
                bbox_rect = fitz.Rect(*(float(v) for v in bbox))
                if not bbox_rect.is_empty:
                    content_rect = content_rect | bbox_rect
            except Exception:
                bbox_rect = None

        # Render kun innhold-regionen (2x for lesbarhet)
        matrix = fitz.Matrix(2.0, 2.0)
        pix = src_page.get_pixmap(matrix=matrix, alpha=False, clip=content_rect)
        img_bytes = pix.tobytes("png")

        # Målrektangel på A4 — bevar aspekt
        avail_w = CONTENT_W
        avail_h = CONTENT_H - (SIZE_H2 + SIZE_SMALL + 18)  # rom til caption
        src_w = max(1.0, float(content_rect.width))
        src_h = max(1.0, float(content_rect.height))
        scale = min(avail_w / src_w, avail_h / src_h)
        target_w = src_w * scale
        target_h = src_h * scale
        img_x0 = MARGIN_L + (avail_w - target_w) / 2
        img_y0 = MARGIN_TOP
        img_rect = fitz.Rect(img_x0, img_y0, img_x0 + target_w, img_y0 + target_h)

        out_page = doc.new_page(width=PAGE_W, height=PAGE_H)
        out_page.insert_image(img_rect, stream=img_bytes)

        # Highlight rundt lagret bbox — nå relativt til trimmet innhold
        if bbox_rect is not None:
            try:
                origin_x = float(content_rect.x0)
                origin_y = float(content_rect.y0)
                hl = fitz.Rect(
                    img_x0 + (bbox_rect.x0 - origin_x) * scale,
                    img_y0 + (bbox_rect.y0 - origin_y) * scale,
                    img_x0 + (bbox_rect.x1 - origin_x) * scale,
                    img_y0 + (bbox_rect.y1 - origin_y) * scale,
                )
                if not hl.is_empty:
                    pad = 2.0
                    hl_padded = fitz.Rect(hl.x0 - pad, hl.y0 - pad, hl.x1 + pad, hl.y1 + pad)
                    out_page.draw_rect(
                        hl_padded,
                        color=HIGHLIGHT_COLOR, width=HIGHLIGHT_WIDTH,
                    )
                    label_y = max(img_y0 + 10, hl_padded.y0 - 4)
                    label_x = max(img_x0 + 2, hl_padded.x0 - 22)
                    out_page.insert_text(
                        fitz.Point(label_x, label_y),
                        "UB", fontname=FONT_BOLD, fontsize=SIZE_SMALL,
                        color=HIGHLIGHT_COLOR,
                    )
                    highlight_note = ""
                else:
                    highlight_note = "Eksakt markering ikke tilgjengelig."
            except Exception:
                highlight_note = "Eksakt markering kunne ikke plasseres."
        else:
            highlight_note = "Eksakt markering ikke tilgjengelig."

        # Caption under bildet
        caption_y = img_rect.y1 + 12
        caption = f"Dokumentside fra {Path(att_path).name}, side {page_no + 1}"
        out_page.insert_text(
            fitz.Point(MARGIN_L, caption_y + SIZE_BODY),
            caption, fontname=FONT_BODY, fontsize=SIZE_BODY,
            color=(0.30, 0.30, 0.30),
        )
        if highlight_note:
            out_page.insert_text(
                fitz.Point(MARGIN_L, caption_y + SIZE_BODY + SIZE_SMALL + 4),
                highlight_note,
                fontname=FONT_BODY, fontsize=SIZE_SMALL,
                color=(0.55, 0.30, 0.10),
            )
    finally:
        src_doc.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_account_workpaper(
    *,
    data: AccountWorkpaperData,
    output_path: str,
) -> str:
    """Skriv en kompakt PDF-rapport for én konto.

    Layout:
    - Side 1: oppsummering (alltid)
    - Side 2: full dokumentside med highlight (bare når UB-bevis peker til
      eksisterende PDF-side)

    Returnerer `output_path`. Kaster Exception ved feil.
    """
    try:
        import fitz
    except Exception as exc:
        raise RuntimeError("PyMuPDF (fitz) er ikke tilgjengelig") from exc

    evidence = data.ub_evidence or None
    has_evidence_page = _can_render_evidence_page(evidence)

    doc = fitz.open()
    try:
        summary = doc.new_page(width=PAGE_W, height=PAGE_H)
        _draw_summary_page(summary, data, has_evidence_page=has_evidence_page)

        if has_evidence_page and evidence is not None:
            try:
                _draw_full_evidence_page(doc, evidence)
            except Exception:
                # Feilsikkerhet: hvis evidensside feiler etter at
                # has_evidence_page var True, la PDF-en forbli ettsiders.
                pass

        doc.save(output_path)
        return output_path
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Pakke-eksport: mappe med PDF + kopiert kildefil
# ---------------------------------------------------------------------------

@dataclass
class ExportPackageResult:
    """Resultat fra `export_account_workpaper_package`."""
    folder: Path
    pdf_path: Path
    source_path: Path | None
    source_included: bool


def _slugify_folder_part(value: str) -> str:
    """Fjern tegn som kan krasje med filsystemet i mappe-/filnavn."""
    s = _sanitize_one_line(value)
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    return s.strip(" ._") or "uten_navn"


def _unique_folder(base: Path, name: str) -> Path:
    """Returner første ledige undermappe basert på `name`.

    Blindt overskriv er ikke OK — eksisterende mappe kan ha annet innhold.
    """
    candidate = base / name
    if not candidate.exists():
        return candidate
    for i in range(2, 1000):
        candidate = base / f"{name}_{i}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Fant ikke ledig eksportmappe under {base}")


def _resolve_source_path(
    data: AccountWorkpaperData,
    override: str | None = None,
) -> Path | None:
    """Finn primær kildefil: `ub_evidence.attachment_path`, deretter
    første vedlegg med eksisterende sti."""
    if override:
        p = Path(override)
        return p if p.exists() else None
    ev = data.ub_evidence or {}
    ev_path = str(ev.get("attachment_path") or "").strip()
    if ev_path:
        p = Path(ev_path)
        if p.exists():
            return p
    for att in data.attachments or []:
        raw = str(att.get("path") or "").strip()
        if not raw:
            continue
        p = Path(raw)
        if p.exists():
            return p
    return None


def export_account_workpaper_package(
    *,
    data: AccountWorkpaperData,
    dest_dir: str | Path,
    year: str | None = None,
    source_path: str | Path | None = None,
) -> ExportPackageResult:
    """Bygg en enkel eksportpakke: mappe med PDF + kopiert kildefil.

    Mappen heter `Kontoarbeidspapir_<konto>_<år>` (år hentes fra
    `year`-arg eller `data.year`). Kildefil kopieres som
    `02_Kildebevis_<filnavn>` når den finnes.

    Eksisterende mappe overskrives ikke — et suffiks legges på i stedet.
    Returnerer en `ExportPackageResult` med absolutte stier.
    """
    base = Path(dest_dir)
    base.mkdir(parents=True, exist_ok=True)

    year_txt = _slugify_folder_part(str(year if year is not None else data.year))
    konto_txt = _slugify_folder_part(data.konto) or "konto"
    folder_name = f"Kontoarbeidspapir_{konto_txt}"
    if year_txt:
        folder_name = f"{folder_name}_{year_txt}"
    folder = _unique_folder(base, folder_name)
    folder.mkdir(parents=True, exist_ok=False)

    pdf_name = f"01_Kontoarbeidspapir_{konto_txt}"
    if year_txt:
        pdf_name = f"{pdf_name}_{year_txt}"
    pdf_path = folder / f"{pdf_name}.pdf"
    export_account_workpaper(data=data, output_path=str(pdf_path))

    src = _resolve_source_path(
        data, override=str(source_path) if source_path else None,
    )
    copied: Path | None = None
    if src is not None:
        # Behold originalt filnavn slik revisor ser det i kildesystemet.
        target = folder / src.name
        try:
            shutil.copy2(src, target)
            copied = target
        except Exception:
            copied = None

    return ExportPackageResult(
        folder=folder,
        pdf_path=pdf_path,
        source_path=copied,
        source_included=copied is not None,
    )

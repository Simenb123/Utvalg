from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable


PREVIEW_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


@dataclass
class PreviewTarget:
    field_name: str = ""
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    label: str = ""
    source: str = ""
    raw_value: str = ""
    normalized_value: str = ""


def preview_kind_for_path(path: str | Path | None) -> str:
    if not path:
        return "none"
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in PREVIEW_IMAGE_EXTENSIONS:
        return "image"
    if ext in {".xml", ".txt"}:
        return "text"
    return "unsupported"


def preview_target_from_evidence(
    field_name: str,
    evidence_map: dict[str, Any] | None,
    *,
    label: str = "",
) -> PreviewTarget | None:
    if not evidence_map:
        return None
    evidence = evidence_map.get(field_name)
    if not evidence:
        return None
    if isinstance(evidence, dict):
        page = evidence.get("page")
        bbox = evidence.get("bbox")
        source = str(evidence.get("source", "") or "")
        raw_value = str(evidence.get("raw_value", "") or "")
        normalized_value = str(evidence.get("normalized_value", "") or "")
    else:
        page = getattr(evidence, "page", None)
        bbox = getattr(evidence, "bbox", None)
        source = str(getattr(evidence, "source", "") or "")
        raw_value = str(getattr(evidence, "raw_value", "") or "")
        normalized_value = str(getattr(evidence, "normalized_value", "") or "")
    if page is None and not bbox:
        return None
    bbox_tuple = tuple(bbox) if isinstance(bbox, (list, tuple)) and len(bbox) == 4 else bbox
    return PreviewTarget(
        field_name=field_name,
        page=page,
        bbox=bbox_tuple,
        label=label or field_name,
        source=source,
        raw_value=raw_value,
        normalized_value=normalized_value,
    )


UB_KEYWORDS: tuple[str, ...] = (
    "UB",
    "Utgående balanse",
    "Utgaaende balanse",
    "Saldo",
    "Sum",
    "Total",
    "Balanse",
    "31.12",
)


def generate_amount_search_variants(value: float) -> list[str]:
    """Returner søkevarianter for et beløp i norske/engelske formater.

    Variantene dekker: norsk (`954 386,28`), uten mellomrom (`954386,28`),
    engelsk (`954,386.28`), uten desimaler når integer (`954 386`), og
    tilhørende negative former (prefiks `-` og parentes). Rekkefølgen er
    satt fra mest spesifikk til minst spesifikk.
    """
    if value is None:
        return []
    try:
        v = float(value)
    except Exception:
        return []
    if v != v:  # NaN
        return []

    abs_v = abs(v)
    is_neg = v < 0

    formatted = f"{abs_v:.2f}"
    whole_str, frac_str = formatted.split(".")
    whole = int(whole_str)
    is_integer_amount = frac_str == "00"

    def _group(digits: str, sep: str) -> str:
        if not digits:
            return ""
        neg = digits.startswith("-")
        d = digits[1:] if neg else digits
        rev = d[::-1]
        chunks = [rev[i:i + 3] for i in range(0, len(rev), 3)]
        grouped = sep.join(chunks)[::-1]
        return ("-" + grouped) if neg else grouped

    positive_variants: list[str] = []

    # Norsk: tusenskille = mellomrom, desimaltegn = komma
    positive_variants.append(f"{_group(whole_str, ' ')},{frac_str}")
    positive_variants.append(f"{_group(whole_str, chr(0xa0))},{frac_str}")
    # Norsk uten tusenskille
    positive_variants.append(f"{whole_str},{frac_str}")
    # Norsk med punkt som tusenskille
    positive_variants.append(f"{_group(whole_str, '.')},{frac_str}")
    # Engelsk: komma som tusenskille, punkt som desimaltegn
    positive_variants.append(f"{_group(whole_str, ',')}.{frac_str}")
    # Engelsk uten tusenskille
    positive_variants.append(f"{whole_str}.{frac_str}")

    if is_integer_amount:
        positive_variants.append(_group(whole_str, " "))
        positive_variants.append(_group(whole_str, chr(0xa0)))
        positive_variants.append(_group(whole_str, "."))
        positive_variants.append(_group(whole_str, ","))
        positive_variants.append(whole_str)

    # Dedup mens rekkefølgen bevares
    seen: set[str] = set()
    positive: list[str] = []
    for v2 in positive_variants:
        if v2 and v2 not in seen:
            seen.add(v2)
            positive.append(v2)

    out: list[str] = []
    if is_neg:
        for v2 in positive:
            out.append(f"-{v2}")
            out.append(f"({v2})")
    else:
        out.extend(positive)
    return out


def _bbox_distance(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Minimum euklidsk avstand mellom to akseparallelle rektangler."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = 0.0
    if bx0 > ax1:
        dx = bx0 - ax1
    elif ax0 > bx1:
        dx = ax0 - bx1
    dy = 0.0
    if by0 > ay1:
        dy = by0 - ay1
    elif ay0 > by1:
        dy = ay0 - by1
    return (dx * dx + dy * dy) ** 0.5


def _round_bbox(bbox: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return (round(bbox[0]), round(bbox[1]), round(bbox[2]), round(bbox[3]))


def find_ub_match_in_pdf(
    pdf_doc: Any,
    expected_value: float,
    *,
    keywords: tuple[str, ...] = UB_KEYWORDS,
    proximity_points: float = 220.0,
    min_score_margin: float = 0.6,
) -> dict | None:
    """Finn entydig UB-kandidat i en åpen PyMuPDF (fitz) `Document`.

    Genererer søkevarianter for `expected_value`, henter treff via
    `page.search_for`, og scorer hvert treff basert på nærhet til UB-relaterte
    stikkord på samme side. Returnerer best treff KUN hvis én gruppe
    (samme bbox på samme side) klart utklasserer de andre; ellers None.

    Format på retur: ``{"page": int, "bbox": (x0,y0,x1,y1), "raw_value": str,
    "normalized_value": float, "score": float}``.
    """
    if pdf_doc is None:
        return None
    try:
        page_count = len(pdf_doc)
    except Exception:
        return None
    variants = generate_amount_search_variants(expected_value)
    if not variants:
        return None

    groups: dict[tuple[int, tuple[int, int, int, int]], dict] = {}

    for p_idx in range(page_count):
        try:
            page = pdf_doc.load_page(p_idx)
        except Exception:
            continue

        # Hent stikkord-bboxer én gang per side
        keyword_rects: list[tuple[float, float, float, float]] = []
        for kw in keywords:
            if not kw:
                continue
            try:
                rects = page.search_for(kw, quads=False)
            except Exception:
                continue
            for r in rects:
                keyword_rects.append((float(r.x0), float(r.y0), float(r.x1), float(r.y1)))

        for variant in variants:
            try:
                rects = page.search_for(variant, quads=False)
            except Exception:
                continue
            for r in rects:
                hit_bbox = (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
                score = 1.0
                for kr in keyword_rects:
                    d = _bbox_distance(hit_bbox, kr)
                    if d < proximity_points:
                        score += max(0.0, 1.0 - d / proximity_points)
                key = (p_idx + 1, _round_bbox(hit_bbox))
                existing = groups.get(key)
                if existing is None or score > existing["score"]:
                    groups[key] = {
                        "page": p_idx + 1,
                        "bbox": hit_bbox,
                        "raw_value": variant,
                        "normalized_value": float(expected_value),
                        "score": score,
                    }

    if not groups:
        return None

    ordered = sorted(groups.values(), key=lambda g: g["score"], reverse=True)
    best = ordered[0]
    if len(ordered) == 1:
        return best
    second = ordered[1]
    if (best["score"] - second["score"]) >= min_score_margin:
        return best
    return None


def preview_target_from_ub_evidence(
    evidence: dict[str, Any] | None,
    *,
    label: str = "UB",
) -> PreviewTarget | None:
    """Bygg en PreviewTarget direkte fra et UB-bevis-dict."""
    if not isinstance(evidence, dict):
        return None
    page = evidence.get("page")
    bbox = evidence.get("bbox")
    if page is None and not bbox:
        return None
    bbox_tuple = tuple(bbox) if isinstance(bbox, (list, tuple)) and len(bbox) == 4 else None
    return PreviewTarget(
        field_name="ub",
        page=int(page) if page is not None else None,
        bbox=bbox_tuple,
        label=label,
        source=str(evidence.get("source", "") or ""),
        raw_value=str(evidence.get("raw_value", "") or ""),
        normalized_value=str(evidence.get("normalized_value", "") or ""),
    )


class DocumentPreviewFrame(ttk.Frame):
    def __init__(self, master: tk.Misc, *, show_toolbar: bool = True) -> None:
        """*show_toolbar* can be disabled by callers that render page/zoom
        controls elsewhere (e.g. the review dialog moves them to its
        header strip so the PDF canvas gets more vertical space).
        ``var_page`` and the control methods remain available regardless."""
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._file_path = ""
        self._preview_kind = "none"
        self._page_index = 0
        self._page_count = 0
        self._zoom = 1.0
        self._highlight: PreviewTarget | None = None
        self._photo_image = None
        self._pdf_doc = None
        self._rendered_size: tuple[int, int] = (0, 0)
        self._image_offset: tuple[float, float] = (0.0, 0.0)

        self._marking = False
        self._mark_callback: Callable[[int, tuple[float, float, float, float]], None] | None = None
        self._mark_label = ""
        self._mark_start_doc: tuple[float, float] | None = None
        self._mark_rect_id: int | None = None
        self._prev_cursor = ""

        self.var_page = tk.StringVar(value="0 / 0")
        self.var_status = tk.StringVar(value="Velg et dokument for å vise forhåndsvisning.")

        if show_toolbar:
            toolbar = ttk.Frame(self)
            toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 2))
            toolbar.columnconfigure(4, weight=1)

            ttk.Button(toolbar, text="◄", command=self.show_previous_page, width=3).grid(row=0, column=0)
            ttk.Label(toolbar, textvariable=self.var_page, width=7, anchor="center").grid(row=0, column=1, padx=2)
            ttk.Button(toolbar, text="►", command=self.show_next_page, width=3).grid(row=0, column=2, padx=(0, 8))
            ttk.Button(toolbar, text="−", command=self.zoom_out, width=2).grid(row=0, column=3)
            ttk.Button(toolbar, text="+", command=self.zoom_in, width=2).grid(row=0, column=4)
            ttk.Button(toolbar, text="Tilpass", command=self.fit_to_width, width=7).grid(row=0, column=5, padx=(4, 0))

        canvas_frame = ttk.Frame(self)
        canvas_frame.grid(row=1, column=0, sticky="nsew")
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(canvas_frame, background="#d7dbe0", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        xscroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_mark_press)
        self.canvas.bind("<B1-Motion>", self._on_mark_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mark_release)

    def load_file(self, file_path: str | Path | None) -> None:
        self.clear()
        self._file_path = str(file_path or "").strip()
        self._preview_kind = preview_kind_for_path(self._file_path)
        if not self._file_path:
            self.var_status.set("Velg et dokument for å vise forhåndsvisning.")
            return

        path = Path(self._file_path)
        if not path.exists():
            self.var_status.set("Fant ikke dokumentet for forhåndsvisning.")
            self._draw_message("Fant ikke dokumentet.")
            return

        if self._preview_kind == "pdf":
            self._load_pdf(path)
        elif self._preview_kind == "image":
            self._page_count = 1
            self._page_index = 0
            self._render_page()
        elif self._preview_kind == "text":
            self._page_count = 1
            self._page_index = 0
            self.var_status.set("Tekstdokument vises ikke som sidepreview. Bruk fanen Lest tekst.")
            self._draw_message("Tekstdokument: bruk fanen Lest tekst.")
            self._update_page_label()
        else:
            self.var_status.set("Denne filtypen har ikke innebygd forhåndsvisning.")
            self._draw_message("Ingen forhåndsvisning tilgjengelig for denne filtypen.")

    def clear(self) -> None:
        self.canvas.delete("all")
        self._photo_image = None
        self._highlight = None
        self._page_index = 0
        self._page_count = 0
        self._rendered_size = (0, 0)
        self._image_offset = (0.0, 0.0)
        if self._pdf_doc is not None:
            try:
                self._pdf_doc.close()
            except Exception:
                pass
        self._pdf_doc = None
        self._update_page_label()

    def set_highlight(self, target: PreviewTarget | None) -> bool:
        self._highlight = target
        if target is None:
            self._render_page()
            return False
        if target.page is not None and target.page >= 1:
            self._page_index = max(0, min(self._page_count - 1, target.page - 1))
        self._render_page()
        return True

    def show_previous_page(self) -> None:
        if self._page_count <= 0:
            return
        self._page_index = max(0, self._page_index - 1)
        self._render_page()

    def show_next_page(self) -> None:
        if self._page_count <= 0:
            return
        self._page_index = min(self._page_count - 1, self._page_index + 1)
        self._render_page()

    def show_page(self, page_number: int) -> None:
        """Jump to *page_number* (1-based).  Silently ignored if out of range."""
        if self._page_count <= 0:
            return
        idx = page_number - 1
        if 0 <= idx < self._page_count:
            self._page_index = idx
            self._render_page()

    def zoom_in(self) -> None:
        self._zoom = min(4.0, self._zoom + 0.2)
        self._render_page()

    def zoom_out(self) -> None:
        self._zoom = max(0.4, self._zoom - 0.2)
        self._render_page()

    def reset_zoom(self) -> None:
        self._zoom = 1.0
        self._render_page()

    def fit_to_width(self) -> None:
        if self._preview_kind != "pdf" or self._pdf_doc is None or self._page_count <= 0:
            return
        try:
            page = self._pdf_doc.load_page(self._page_index)
            page_width = float(page.rect.width or 0.0)
        except Exception:
            return
        canvas_width = max(int(self.canvas.winfo_width() or 0) - 24, 100)
        if page_width <= 0:
            return
        self._zoom = max(0.4, min(4.0, canvas_width / page_width))
        self._render_page()

    def _load_pdf(self, path: Path) -> None:
        try:
            import fitz
        except Exception:
            self.var_status.set("PDF-forhåndsvisning krever PyMuPDF.")
            self._draw_message("PDF-forhåndsvisning krever PyMuPDF.")
            return

        try:
            self._pdf_doc = fitz.open(str(path))
            self._page_count = len(self._pdf_doc)
            self._page_index = 0
            self.var_status.set("PDF-forhåndsvisning lastet.")
            self._render_page()
            self.after_idle(self.reset_zoom)
        except Exception as exc:
            self.var_status.set("Kunne ikke laste PDF til forhåndsvisning.")
            self._draw_message(f"PDF kunne ikke vises.\n{exc}")

    def _render_page(self) -> None:
        self.canvas.delete("all")
        if not self._file_path:
            self._draw_message("Velg et dokument for å vise forhåndsvisning.")
            self._update_page_label()
            return

        path = Path(self._file_path)
        if self._preview_kind == "pdf":
            self._render_pdf_page(path)
        elif self._preview_kind == "image":
            self._render_image_page(path)
        elif self._preview_kind == "text":
            self._draw_message("Tekstdokument: bruk fanen Lest tekst.")
        else:
            self._draw_message("Ingen forhåndsvisning tilgjengelig for denne filtypen.")
        self._update_page_label()

    def _render_pdf_page(self, path: Path) -> None:
        if self._pdf_doc is None or self._page_count <= 0:
            self._draw_message("PDF er ikke lastet.")
            return
        try:
            from PIL import Image, ImageTk
        except Exception:
            self._draw_message("Forhåndsvisning krever Pillow.")
            return

        page = self._pdf_doc.load_page(self._page_index)
        pix = page.get_pixmap(matrix=self._pdf_doc_matrix(page), alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self._photo_image = ImageTk.PhotoImage(image)
        self._rendered_size = (pix.width, pix.height)
        self._draw_rendered_image()
        self._draw_highlight_overlay()
        self.var_status.set(f"PDF-side {self._page_index + 1} av {self._page_count}. Zoom {self._zoom:.1f}x.")

    def _render_image_page(self, path: Path) -> None:
        try:
            from PIL import Image, ImageTk
        except Exception:
            self._draw_message("Forhåndsvisning krever Pillow.")
            return

        try:
            image = Image.open(path)
        except Exception as exc:
            self._draw_message(f"Kunne ikke laste bilde.\n{exc}")
            return

        width = max(1, int(image.width * self._zoom))
        height = max(1, int(image.height * self._zoom))
        resized = image.resize((width, height))
        self._photo_image = ImageTk.PhotoImage(resized)
        self._rendered_size = (width, height)
        self._draw_rendered_image()
        self._draw_highlight_overlay()
        self.var_status.set(f"Bildevisning. Zoom {self._zoom:.1f}x.")

    def _pdf_doc_matrix(self, page: Any) -> Any:
        import fitz

        return fitz.Matrix(self._zoom, self._zoom)

    def _draw_highlight_overlay(self) -> None:
        target = self._highlight
        if target is None:
            return
        if target.page is not None and target.page != self._page_index + 1:
            return

        bbox = target.bbox

        # If no bbox from extraction, try to find the text on the page via fitz
        if not bbox and self._pdf_doc is not None:
            bbox = self._search_text_on_page(target)

        if not bbox:
            return

        x0, y0, x1, y1 = bbox
        scale = self._zoom
        offset_x, offset_y = self._image_offset
        pad = 2.0
        rect = (
            x0 * scale + offset_x - pad,
            y0 * scale + offset_y - pad,
            x1 * scale + offset_x + pad,
            y1 * scale + offset_y + pad,
        )

        # Clean rounded-corner effect: outer border + inner accent line (no fill)
        self.canvas.create_rectangle(*rect, outline="#e05500", width=2)

        # Small label tag tucked into top-left corner, outside the box
        tag_text = target.label or target.field_name
        tag_x = rect[0]
        tag_y = rect[1] - 2
        # Background pill for the label so it doesn't clash with PDF content
        tag_id = self.canvas.create_text(
            tag_x, tag_y, anchor="sw",
            text=tag_text, fill="#e05500",
            font=("Segoe UI", 7),
        )
        tb = self.canvas.bbox(tag_id)
        if tb:
            self.canvas.create_rectangle(
                tb[0] - 2, tb[1] - 1, tb[2] + 2, tb[3],
                fill="#ffffff", outline="", width=0,
            )
            # Re-draw text on top of the white pill
            self.canvas.tag_raise(tag_id)

        self._scroll_to_bbox(rect)

    def _search_text_on_page(self, target: PreviewTarget) -> tuple[float, float, float, float] | None:
        """Search for the field's raw/normalized value on the current PDF page."""
        if self._pdf_doc is None:
            return None
        try:
            page = self._pdf_doc.load_page(self._page_index)
        except Exception:
            return None

        search_terms: list[str] = []
        if target.raw_value:
            search_terms.append(target.raw_value)
        if target.normalized_value and target.normalized_value != target.raw_value:
            search_terms.append(target.normalized_value)

        for term in search_terms:
            if not term or len(term) < 2:
                continue
            try:
                rects = page.search_for(term, quads=False)
                if rects:
                    r = rects[0]
                    return (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
            except Exception:
                continue
        return None

    def search_all_pages(self, text: str) -> list[tuple[int, tuple[float, float, float, float]]]:
        """Search for *text* across all PDF pages.

        Returns list of (page_number_1based, bbox) for every match found.
        """
        if self._pdf_doc is None or not text or len(text) < 2:
            return []
        hits: list[tuple[int, tuple[float, float, float, float]]] = []
        for page_idx in range(self._page_count):
            try:
                page = self._pdf_doc.load_page(page_idx)
                rects = page.search_for(text, quads=False)
                for r in rects:
                    hits.append((page_idx + 1, (float(r.x0), float(r.y0), float(r.x1), float(r.y1))))
            except Exception:
                continue
        return hits

    def _scroll_to_bbox(self, rect: tuple[float, float, float, float]) -> None:
        scroll_box = self.canvas.bbox("all")
        if not scroll_box:
            return
        width = max(float(scroll_box[2] - scroll_box[0]), 1.0)
        height = max(float(scroll_box[3] - scroll_box[1]), 1.0)
        center_x = (rect[0] + rect[2]) / 2.0
        center_y = (rect[1] + rect[3]) / 2.0
        visible_width = max(float(self.canvas.winfo_width() or 1), 1.0)
        visible_height = max(float(self.canvas.winfo_height() or 1), 1.0)
        x_fraction = max(0.0, min(1.0, (center_x - visible_width / 2.0) / max(width - visible_width, 1.0)))
        y_fraction = max(0.0, min(1.0, (center_y - visible_height / 2.0) / max(height - visible_height, 1.0)))
        self.canvas.xview_moveto(x_fraction)
        self.canvas.yview_moveto(y_fraction)

    def _draw_message(self, message: str) -> None:
        self.canvas.delete("all")
        width = max(int(self.canvas.winfo_width() or 600), 200)
        height = max(int(self.canvas.winfo_height() or 400), 200)
        self._rendered_size = (0, 0)
        self._image_offset = (0.0, 0.0)
        self.canvas.configure(scrollregion=(0, 0, width, height))
        self.canvas.create_text(
            width / 2.0,
            height / 2.0,
            text=message,
            fill="#39424e",
            width=max(width - 80, 120),
            justify="center",
            font=("Segoe UI", 11),
        )

    def _update_page_label(self) -> None:
        if self._page_count <= 0:
            self.var_page.set("0 / 0")
        else:
            self.var_page.set(f"{self._page_index + 1} / {self._page_count}")

    def _on_canvas_resize(self, _event: tk.Event[tk.Misc]) -> None:
        if not self._file_path or self._preview_kind == "none":
            return
        if self._preview_kind in {"text", "unsupported"}:
            self._render_page()

    def _draw_rendered_image(self) -> None:
        width, height = self._rendered_size
        canvas_width = max(int(self.canvas.winfo_width() or 0), width, 320)
        canvas_height = max(int(self.canvas.winfo_height() or 0), height, 240)
        scroll_width = max(width + 32, canvas_width)
        scroll_height = max(height + 32, canvas_height)
        x_offset = max((scroll_width - width) / 2.0, 16.0)
        y_offset = max((scroll_height - height) / 2.0, 16.0)

        self._image_offset = (x_offset, y_offset)
        self.canvas.configure(scrollregion=(0, 0, scroll_width, scroll_height))
        self.canvas.create_rectangle(
            x_offset - 1,
            y_offset - 1,
            x_offset + width + 1,
            y_offset + height + 1,
            fill="#ffffff",
            outline="#b8bec7",
            width=1,
        )
        self.canvas.create_image(x_offset, y_offset, anchor="nw", image=self._photo_image)

    def _on_mouse_wheel(self, event: tk.Event[tk.Misc]) -> None:
        if event.state & 0x4:
            if event.delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    @property
    def is_marking(self) -> bool:
        return self._marking

    def find_ub_match(self, expected_value: float) -> dict | None:
        """Forsøk å finne UB automatisk i lastet PDF. None hvis ikke-PDF eller ikke entydig."""
        if self._preview_kind != "pdf" or self._pdf_doc is None:
            return None
        return find_ub_match_in_pdf(self._pdf_doc, expected_value)

    def start_marking(
        self,
        callback: Callable[[int, tuple[float, float, float, float]], None],
        *,
        label: str = "",
    ) -> bool:
        """Aktiver manuell markering av et rektangel på siden.

        Krever at et dokument er lastet og at vi står på en side som kan
        tegnes på (PDF eller bilde). Returnerer True hvis modusen aktiveres.
        """
        if self._preview_kind not in {"pdf", "image"} or self._rendered_size == (0, 0):
            return False
        self._marking = True
        self._mark_callback = callback
        self._mark_label = str(label or "")
        self._mark_start_doc = None
        self._cancel_mark_rect()
        try:
            self._prev_cursor = str(self.canvas.cget("cursor") or "")
        except Exception:
            self._prev_cursor = ""
        try:
            self.canvas.configure(cursor="crosshair")
        except Exception:
            pass
        self.var_status.set("Marker UB-felt: dra et rektangel over verdien.")
        return True

    def stop_marking(self) -> None:
        self._marking = False
        self._mark_callback = None
        self._mark_label = ""
        self._mark_start_doc = None
        self._cancel_mark_rect()
        try:
            self.canvas.configure(cursor=self._prev_cursor or "")
        except Exception:
            pass

    def _cancel_mark_rect(self) -> None:
        if self._mark_rect_id is not None:
            try:
                self.canvas.delete(self._mark_rect_id)
            except Exception:
                pass
            self._mark_rect_id = None

    def _canvas_xy(self, event: tk.Event[tk.Misc]) -> tuple[float, float]:
        return (
            float(self.canvas.canvasx(event.x)),
            float(self.canvas.canvasy(event.y)),
        )

    def _canvas_to_doc(self, cx: float, cy: float) -> tuple[float, float] | None:
        scale = float(self._zoom or 1.0)
        if scale <= 0:
            return None
        width, height = self._rendered_size
        if width <= 0 or height <= 0:
            return None
        offset_x, offset_y = self._image_offset
        doc_x = (cx - offset_x) / scale
        doc_y = (cy - offset_y) / scale
        doc_w = width / scale
        doc_h = height / scale
        doc_x = max(0.0, min(doc_w, doc_x))
        doc_y = max(0.0, min(doc_h, doc_y))
        return (doc_x, doc_y)

    def _on_mark_press(self, event: tk.Event[tk.Misc]) -> None:
        if not self._marking:
            return
        cx, cy = self._canvas_xy(event)
        doc = self._canvas_to_doc(cx, cy)
        if doc is None:
            return
        self._mark_start_doc = doc
        self._cancel_mark_rect()
        self._mark_rect_id = self.canvas.create_rectangle(
            cx, cy, cx, cy, outline="#e05500", width=2, dash=(4, 2)
        )

    def _on_mark_drag(self, event: tk.Event[tk.Misc]) -> None:
        if not self._marking or self._mark_start_doc is None or self._mark_rect_id is None:
            return
        scale = float(self._zoom or 1.0)
        offset_x, offset_y = self._image_offset
        start_x = self._mark_start_doc[0] * scale + offset_x
        start_y = self._mark_start_doc[1] * scale + offset_y
        cx, cy = self._canvas_xy(event)
        try:
            self.canvas.coords(self._mark_rect_id, start_x, start_y, cx, cy)
        except Exception:
            pass

    def _on_mark_release(self, event: tk.Event[tk.Misc]) -> None:
        if not self._marking or self._mark_start_doc is None:
            return
        cx, cy = self._canvas_xy(event)
        end_doc = self._canvas_to_doc(cx, cy)
        start_doc = self._mark_start_doc
        callback = self._mark_callback
        self._cancel_mark_rect()
        self._mark_start_doc = None
        self._marking = False
        self._mark_callback = None
        try:
            self.canvas.configure(cursor=self._prev_cursor or "")
        except Exception:
            pass

        if end_doc is None or start_doc is None:
            return
        x0 = min(start_doc[0], end_doc[0])
        y0 = min(start_doc[1], end_doc[1])
        x1 = max(start_doc[0], end_doc[0])
        y1 = max(start_doc[1], end_doc[1])
        if (x1 - x0) < 2.0 or (y1 - y0) < 2.0:
            self.var_status.set("Rektangelet var for lite. Prøv igjen.")
            return

        bbox = (float(x0), float(y0), float(x1), float(y1))
        page_1based = self._page_index + 1

        self._highlight = PreviewTarget(
            field_name=self._mark_label or "ub",
            page=page_1based,
            bbox=bbox,
            label=self._mark_label or "UB",
            source="manual",
        )
        self._render_page()

        if callback is not None:
            try:
                callback(page_1based, bbox)
            except Exception:
                pass

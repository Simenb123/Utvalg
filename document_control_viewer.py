from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any


PREVIEW_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


@dataclass
class PreviewTarget:
    field_name: str = ""
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    label: str = ""
    source: str = ""


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
    else:
        page = getattr(evidence, "page", None)
        bbox = getattr(evidence, "bbox", None)
        source = str(getattr(evidence, "source", "") or "")
    if page is None and not bbox:
        return None
    bbox_tuple = tuple(bbox) if isinstance(bbox, (list, tuple)) and len(bbox) == 4 else bbox
    return PreviewTarget(
        field_name=field_name,
        page=page,
        bbox=bbox_tuple,
        label=label or field_name,
        source=source,
    )


class DocumentPreviewFrame(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._file_path = ""
        self._preview_kind = "none"
        self._page_index = 0
        self._page_count = 0
        self._zoom = 1.2
        self._highlight: PreviewTarget | None = None
        self._photo_image = None
        self._pdf_doc = None
        self._rendered_size: tuple[int, int] = (0, 0)
        self._image_offset: tuple[float, float] = (0.0, 0.0)

        self.var_page = tk.StringVar(value="0 / 0")
        self.var_status = tk.StringVar(value="Velg et dokument for å vise forhåndsvisning.")

        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.columnconfigure(7, weight=1)

        ttk.Button(toolbar, text="Forrige", command=self.show_previous_page).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(toolbar, text="Neste", command=self.show_next_page).grid(row=0, column=1, padx=(0, 12))
        ttk.Label(toolbar, textvariable=self.var_page, width=10).grid(row=0, column=2, padx=(0, 12))
        ttk.Button(toolbar, text="Zoom ut", command=self.zoom_out).grid(row=0, column=3, padx=(0, 4))
        ttk.Button(toolbar, text="Zoom inn", command=self.zoom_in).grid(row=0, column=4, padx=(0, 4))
        ttk.Button(toolbar, text="100%", command=self.reset_zoom).grid(row=0, column=5, padx=(0, 4))
        ttk.Button(toolbar, text="Tilpass bredde", command=self.fit_to_width).grid(row=0, column=6, padx=(0, 12))
        ttk.Label(toolbar, textvariable=self.var_status).grid(row=0, column=7, sticky="w")

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

    def zoom_in(self) -> None:
        self._zoom = min(4.0, self._zoom + 0.2)
        self._render_page()

    def zoom_out(self) -> None:
        self._zoom = max(0.4, self._zoom - 0.2)
        self._render_page()

    def reset_zoom(self) -> None:
        self._zoom = 1.2
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
            self.after_idle(self.fit_to_width)
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
        if not target.bbox:
            return

        x0, y0, x1, y1 = target.bbox
        scale = self._zoom
        offset_x, offset_y = self._image_offset
        rect = (
            x0 * scale + offset_x,
            y0 * scale + offset_y,
            x1 * scale + offset_x,
            y1 * scale + offset_y,
        )
        self.canvas.create_rectangle(*rect, outline="#ff6b35", width=3)
        self.canvas.create_text(
            rect[0] + 6,
            max(12.0, rect[1] - 10),
            anchor="w",
            text=target.label or target.field_name,
            fill="#ffcc80",
            font=("Segoe UI", 9, "bold"),
        )
        self._scroll_to_bbox(rect)

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

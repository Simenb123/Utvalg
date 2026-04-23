"""PDF text extractors and the selection helpers that rank them.

Each extractor takes a ``Path`` and returns ``(text, list[TextSegment])``.
The orchestration function ``_extract_text_from_pdf`` in
:mod:`document_engine.engine` feeds them through ``_append_candidate``
and picks the highest-scoring one via ``_score_text_candidate``.

This module is I/O-heavy but logic-light: there are no field-matching
patterns or scoring heuristics here, only the mechanics of getting
text + geometry out of PDFs.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import ExtractedTextResult, TextSegment

from .patterns import _COMPANY_SUFFIX_RE, _NUMBER_FRAGMENT

_PDF_TEXT_THRESHOLD = 40


def _extract_candidate_lines(text: str, max_lines: int = 25) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _normalize_whitespace(raw_line)
        if not line:
            continue
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines

def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()



@dataclass
class _TextCandidate:
    source: str
    text: str
    ocr_used: bool
    score: float
    segments: list[TextSegment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

def _append_candidate(candidates: list[_TextCandidate], source: str, result: tuple[str, list[TextSegment]], ocr_used: bool) -> None:
    text, segments = result
    normalized = _normalize_text_payload(text)
    if not normalized:
        return
    candidates.append(
        _TextCandidate(
            source=source,
            text=normalized,
            ocr_used=ocr_used,
            score=_score_text_candidate(normalized),
            segments=segments,
            metadata={"ocr_engine": "ocrmypdf" if source.startswith("pdf_ocrmypdf") else ("pytesseract" if ocr_used else "text_layer")},
        )
    )

def _normalize_text_payload(text: str) -> str:
    text = text or ""
    text = text.replace("\x00", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def _score_text_candidate(text: str) -> float:
    lines = _extract_candidate_lines(text, max_lines=250)
    chars = len(text.strip())
    keyword_hits = sum(
        bool(re.search(pattern, text, re.IGNORECASE))
        for pattern in (
            r"faktura",
            r"invoice",
            r"forfallsdato",
            r"due date",
            r"mva",
            r"vat",
            r"org\.?\s*nr",
            r"bel[øo]p",
            r"total",
        )
    )
    amount_hits = len(re.findall(_NUMBER_FRAGMENT, text, re.IGNORECASE))
    company_hits = sum(bool(_COMPANY_SUFFIX_RE.search(line)) for line in lines[:12])

    score = 0.0
    score += min(chars, 6000) / 70.0
    score += min(len(lines), 80) * 0.8
    score += keyword_hits * 12.0
    score += min(amount_hits, 12) * 2.5
    score += company_hits * 5.0
    if chars < _PDF_TEXT_THRESHOLD:
        score -= 25.0
    if len(lines) <= 2:
        score -= 8.0
    return score

def _count_pdf_pages(path: Path) -> int | None:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return len(reader.pages)
    except Exception:
        pass

    try:
        import fitz

        with fitz.open(str(path)) as doc:
            return len(doc)
    except Exception:
        return None

def _extract_pdf_text_with_pypdf(path: Path) -> tuple[str, list[TextSegment]]:
    try:
        from pypdf import PdfReader
    except Exception:
        return "", []

    try:
        reader = PdfReader(str(path))
    except Exception:
        return "", []

    segments: list[TextSegment] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            segments.append(TextSegment(text=text, source="pdf_text_pypdf", page=index))
    return "\n".join(segment.text for segment in segments), segments

def _extract_pdf_text_with_pdfplumber(path: Path) -> tuple[str, list[TextSegment]]:
    try:
        import pdfplumber
    except Exception:
        return "", []

    segments: list[TextSegment] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                try:
                    text = page.extract_text(layout=True) or page.extract_text() or ""
                except Exception:
                    text = ""
                if text.strip():
                    segments.append(TextSegment(text=text, source="pdf_text_pdfplumber", page=index))
    except Exception:
        return "", []
    return "\n".join(segment.text for segment in segments), segments

def _extract_pdf_text_with_fitz_blocks(path: Path) -> tuple[str, list[TextSegment]]:
    try:
        import fitz
    except Exception:
        return "", []

    segments: list[TextSegment] = []
    try:
        with fitz.open(str(path)) as doc:
            for page_index, page in enumerate(doc, start=1):
                blocks = page.get_text("blocks") or []
                ordered = sorted(
                    (
                        (float(block[1]), float(block[0]), str(block[4]).strip(), tuple(float(value) for value in block[:4]))
                        for block in blocks
                        if len(block) >= 5 and str(block[4]).strip()
                    ),
                    key=lambda item: (round(item[0], 1), round(item[1], 1)),
                )
                for _y, _x, text, bbox in ordered:
                    segments.append(TextSegment(text=text, source="pdf_text_fitz_blocks", page=page_index, bbox=bbox))
    except Exception:
        return "", []
    return "\n".join(segment.text for segment in segments), segments

_VALUE_CLUSTER_TOKEN_RE = re.compile(r"\d")

_VALUE_CLUSTER_CURRENCY = {"NOK", "USD", "EUR", "SEK", "DKK", "GBP", "kr", "KR"}

_GAP_SPLIT_MIN_GAP_PT = 40.0

_GAP_SPLIT_MIN_LINE_WIDTH_FRAC = 0.70

def _build_word_segment(
    chunk_words: list[tuple],
    page_index: int,
) -> TextSegment | None:
    """Build a TextSegment from an ordered list of fitz word-records.

    Word records are ``(x0, y0, x1, y1, text, block, line, word)``; only the
    first five entries are used here. Returns None when the chunk has no
    non-empty tokens.
    """
    parts: list[str] = []
    spans: list[tuple[int, int, tuple[float, float, float, float]]] = []
    cursor = 0
    for w in chunk_words:
        token = str(w[4])
        if not token:
            continue
        if parts:
            parts.append(" ")
            cursor += 1
        start = cursor
        parts.append(token)
        cursor += len(token)
        try:
            bbox = (float(w[0]), float(w[1]), float(w[2]), float(w[3]))
        except (TypeError, ValueError):
            continue
        spans.append((start, cursor, bbox))
    text = "".join(parts).strip()
    if not text:
        return None

    # Line-level bbox fallback: tightened around trailing numeric cluster.
    # Callers that know the exact regex match range should prefer word_spans.
    cluster_start = len(chunk_words)
    for i in range(len(chunk_words) - 1, -1, -1):
        token = str(chunk_words[i][4])
        if (_VALUE_CLUSTER_TOKEN_RE.search(token)
            or token in {",", ".", "-"}
            or token in _VALUE_CLUSTER_CURRENCY):
            cluster_start = i
        else:
            break
    cluster = (chunk_words[cluster_start:]
               if cluster_start < len(chunk_words) else chunk_words)
    bbox = (
        min(float(w[0]) for w in cluster),
        min(float(w[1]) for w in cluster),
        max(float(w[2]) for w in cluster),
        max(float(w[3]) for w in cluster),
    )
    return TextSegment(
        text=text,
        source="pdf_text_fitz_words",
        page=page_index,
        bbox=bbox,
        word_spans=spans,
    )

def _split_line_by_gaps(
    line_words: list[tuple],
    page_width: float,
) -> list[list[tuple]]:
    """Split a y-line into label/value chunks when wide with large x-gaps.

    Returns a list of chunks. When no splitting applies (narrow row, single
    word, no large gap, or no chunk contains a digit), returns a
    single-element list containing the input unchanged.
    """
    if len(line_words) < 2:
        return [line_words]
    line_x0 = min(float(w[0]) for w in line_words)
    line_x1 = max(float(w[2]) for w in line_words)
    line_width = line_x1 - line_x0
    if page_width <= 0 or line_width < _GAP_SPLIT_MIN_LINE_WIDTH_FRAC * page_width:
        return [line_words]
    chunks: list[list[tuple]] = [[line_words[0]]]
    for i in range(1, len(line_words)):
        prev_x1 = float(line_words[i - 1][2])
        cur_x0 = float(line_words[i][0])
        if (cur_x0 - prev_x1) > _GAP_SPLIT_MIN_GAP_PT:
            chunks.append([])
        chunks[-1].append(line_words[i])
    if len(chunks) == 1:
        return [line_words]
    if not any(
        any(_VALUE_CLUSTER_TOKEN_RE.search(str(w[4])) for w in chunk)
        for chunk in chunks
    ):
        # No chunk carries a number — splitting serves no amount-matching
        # purpose (and could hurt label-hint matching). Skip.
        return [line_words]
    return chunks

def _extract_pdf_text_with_fitz_words(path: Path) -> tuple[str, list[TextSegment]]:
    """Per-line segments with bbox tightened around the trailing numeric
    cluster, plus gap-split chunks for wide table-style rows.

    Narrow rows (e.g. ``Til betaling 1 000,00 NOK``) become a single
    segment whose ``text`` is the full line (so label-hint matching still
    works) and whose ``bbox`` is tight around the trailing value cluster.

    Wide rows (e.g. ``Beløp 800,00   MVA 200,00   Total 1000,00``) are
    emitted as chunk-segments first, followed by the full-row segment as a
    fallback. Chunks get the lower ``segment_index`` so
    ``_first_match_evidence`` prefers their tight bbox over the full row
    when an amount regex matches inside a chunk.
    """
    try:
        import fitz
    except Exception:
        return "", []

    segments: list[TextSegment] = []
    try:
        with fitz.open(str(path)) as doc:
            for page_index, page in enumerate(doc, start=1):
                try:
                    page_width = float(page.rect.width)
                except Exception:
                    page_width = 0.0
                words = page.get_text("words") or []
                if not words:
                    continue
                # Group by visual y-midpoint (in 2pt buckets) so words placed
                # on the same physical row but in different PDF blocks
                # (table columns, multi-column layouts) still cluster as one
                # line.
                lines: dict[int, list[tuple]] = {}
                for w in words:
                    if len(w) < 5:
                        continue
                    try:
                        y_mid = (float(w[1]) + float(w[3])) / 2.0
                    except (TypeError, ValueError):
                        continue
                    bucket = int(round(y_mid / 2.0))
                    lines.setdefault(bucket, []).append(w)
                for key in sorted(lines.keys()):
                    line_words = sorted(lines[key], key=lambda w: float(w[0]))
                    chunks = _split_line_by_gaps(line_words, page_width)
                    if len(chunks) > 1:
                        for chunk in chunks:
                            seg = _build_word_segment(chunk, page_index)
                            if seg is not None:
                                segments.append(seg)
                    full_seg = _build_word_segment(line_words, page_index)
                    if full_seg is not None:
                        segments.append(full_seg)
    except Exception:
        return "", []
    return "\n".join(segment.text for segment in segments), segments

def _extract_pdf_text_with_fitz(path: Path) -> tuple[str, list[TextSegment]]:
    try:
        import fitz
    except Exception:
        return "", []

    segments: list[TextSegment] = []
    try:
        with fitz.open(str(path)) as doc:
            for page_index, page in enumerate(doc, start=1):
                text = page.get_text() or ""
                if text.strip():
                    segments.append(TextSegment(text=text, source="pdf_text_fitz", page=page_index))
    except Exception:
        return "", []
    return "\n".join(segment.text for segment in segments), segments

def _ocr_pdf_with_ocrmypdf(path: Path, *, mode: str = "skip") -> tuple[str, list[TextSegment]]:
    """Run ocrmypdf against *path* and re-extract text from the output.

    ``mode``:
        ``"skip"``  — pass ``--skip-text`` (default). Only OCRs pages that
                      don't already have a text layer.
        ``"redo"``  — pass ``--redo-ocr``. Re-runs OCR over pages with
                      existing (often low-quality) text layers. Used as a
                      fallback when the native extractors all produced a
                      weak result.
    """
    if shutil.which("ocrmypdf") is None:
        return "", []

    flag = "--redo-ocr" if mode == "redo" else "--skip-text"
    source_tag = "pdf_ocrmypdf_redo" if mode == "redo" else "pdf_ocrmypdf"

    temp_dir = Path(tempfile.mkdtemp(prefix="utvalg_doc_ocr_"))
    out_pdf = temp_dir / "ocr.pdf"
    try:
        subprocess.run(
            [
                "ocrmypdf",
                flag,
                "--deskew",
                "--quiet",
                "--language",
                "nor+eng",
                str(path),
                str(out_pdf),
            ],
            check=True,
            timeout=180,
            capture_output=True,
        )
        # fitz_words first: keeps word_spans + tight per-row bbox after redo
        # OCR, so profile-hint geometry stays precise on OCR-rescued PDFs.
        # Look the extractors up via the ``engine`` module so tests that
        # monkeypatch ``engine._extract_pdf_text_with_fitz_words`` propagate
        # through here too. Falling back to ``globals()`` if engine import
        # is unavailable (import cycle during bootstrap).
        try:
            from . import engine as _engine_mod  # noqa: PLC0415
            _resolve = lambda name: getattr(_engine_mod, name, globals()[name])
        except Exception:
            _resolve = lambda name: globals()[name]
        for extractor in (
            _resolve("_extract_pdf_text_with_fitz_words"),
            _resolve("_extract_pdf_text_with_pypdf"),
            _resolve("_extract_pdf_text_with_pdfplumber"),
            _resolve("_extract_pdf_text_with_fitz_blocks"),
            _resolve("_extract_pdf_text_with_fitz"),
        ):
            text, segments = extractor(out_pdf)
            if len(text.strip()) >= _PDF_TEXT_THRESHOLD:
                remapped = [
                    TextSegment(
                        text=segment.text,
                        source=source_tag,
                        page=segment.page,
                        bbox=segment.bbox,
                        word_spans=list(segment.word_spans or []),
                    )
                    for segment in segments
                ]
                return text, remapped
        return "", []
    except Exception:
        return "", []
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def _ocr_pdf_with_fitz(path: Path) -> tuple[str, list[TextSegment]]:
    try:
        import fitz
    except Exception:
        return "", []

    try:
        from PIL import Image
        import pytesseract
    except Exception:
        return "", []

    segments: list[TextSegment] = []
    try:
        with fitz.open(str(path)) as doc:
            for page_index, page in enumerate(doc, start=1):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                try:
                    text = pytesseract.image_to_string(image, lang="nor+eng") or ""
                except Exception:
                    text = pytesseract.image_to_string(image) or ""
                if text.strip():
                    segments.append(TextSegment(text=text, source="pdf_ocr_fitz", page=page_index))
    except Exception:
        return "", []
    return "\n".join(segment.text for segment in segments), segments

def _ocr_image(path: Path) -> str:
    try:
        from PIL import Image
        import pytesseract
    except Exception as exc:
        raise RuntimeError("OCR krever Pillow og pytesseract.") from exc

    image = Image.open(path)
    try:
        return pytesseract.image_to_string(image, lang="nor+eng") or ""
    except Exception:
        return pytesseract.image_to_string(image) or ""

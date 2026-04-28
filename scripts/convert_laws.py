"""
Convert Norwegian law/regulation PDF and DOCX files to clean plain text for RAG indexing.
Uses PyMuPDF (fitz) for PDFs (with OCR fallback for scanned/image-only pages)
and python-docx for DOCX files.
"""

import re
import os
import sys

import fitz  # PyMuPDF
import docx

SOURCE_DIR = r"c:\Users\ib91\Desktop\DIV\VS CODE PROJECTS\Utvalg-1\doc\fagdatabase\Lover og forskrifter"
OUTPUT_DIR = r"c:\Users\ib91\Desktop\DIV\VS CODE PROJECTS\Utvalg-1\doc\fagdatabase\generated\lover"

TESSERACT_PATH = r"C:\Users\ib91\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
TESSDATA_PATH = r"C:\Users\ib91\AppData\Local\Programs\Tesseract-OCR\tessdata"

FILES = [
    # (source_filename, output_filename, description)
    ("Skatteloven.docx", "SKL.txt", "Skatteloven"),
    ("Skatteforvaltningsloven.pdf", "SKFVL.txt", "Skatteforvaltningsloven"),
    ("Skattebetalingsloven.pdf", "SKBL.txt", "Skattebetalingsloven"),
    ("arbeidsmiljøloven.pdf", "AML.txt", "Arbeidsmiljøloven"),
    ("Hvitvaskingsforskriften.pdf", "HVF.txt", "Hvitvaskingsforskriften"),
    ("Stiftelsesloven.pdf", "STFTL.txt", "Stiftelsesloven"),
    ("Forskrift regnskapsloven.pdf", "RSLF.txt", "Regnskapslovsforskriften"),
]


def clean_text(text: str) -> str:
    """Clean up PDF/DOCX extraction artifacts while preserving structure."""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove form feed characters (page breaks from PDF)
    text = text.replace("\f", "\n")

    # Remove common Lovdata header/footer patterns
    # e.g. "Side 1 av 120", "Lovdata - ..."
    text = re.sub(r"(?mi)^side\s+\d+\s+av\s+\d+\s*$", "", text)
    text = re.sub(r"(?mi)^lovdata\s*[-–].*$", "", text)

    # Remove standalone page numbers (lines that are just a number)
    text = re.sub(r"(?m)^\s*\d{1,4}\s*$", "", text)

    # Remove lines that are just dashes or underscores (decorative separators)
    text = re.sub(r"(?m)^[\s\-_=]{5,}\s*$", "", text)

    # Collapse runs of 3+ blank lines down to 2
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # Remove trailing whitespace on each line
    text = re.sub(r"(?m)[ \t]+$", "", text)

    # Remove leading/trailing whitespace from the whole document
    text = text.strip()

    return text


def extract_docx(filepath: str) -> str:
    """Extract text from a DOCX file, preserving paragraph structure."""
    doc = docx.Document(filepath)
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append(text)
        else:
            # Preserve blank lines for paragraph separation
            paragraphs.append("")
    # Join and clean
    raw = "\n".join(paragraphs)
    return clean_text(raw)


def page_has_text(page) -> bool:
    """Check if a PDF page has extractable text (not image-only)."""
    text = page.get_text("text").strip()
    return len(text) > 20  # More than trivial content


def extract_pdf(filepath: str) -> str:
    """Extract text from a PDF file using PyMuPDF.
    Falls back to OCR (Tesseract with Norwegian) for image-only pages.
    """
    doc = fitz.open(filepath)

    # First, check if the PDF has any text at all
    total_text_len = sum(len(page.get_text("text").strip()) for page in doc)
    needs_ocr = total_text_len < 100

    pages_text = []
    total_pages = len(doc)

    for page_num in range(total_pages):
        page = doc[page_num]

        if needs_ocr or not page_has_text(page):
            # Use OCR for this page
            try:
                tp = page.get_textpage_ocr(
                    language="nor",
                    tessdata=TESSDATA_PATH,
                )
                text = page.get_text("text", textpage=tp)
            except Exception as e:
                print(f"    OCR failed on page {page_num + 1}: {e}")
                text = page.get_text("text")
        else:
            text = page.get_text("text")

        if text and text.strip():
            pages_text.append(text)

        # Progress indicator for OCR (can be slow)
        if needs_ocr and (page_num + 1) % 10 == 0:
            print(f"    OCR progress: {page_num + 1}/{total_pages} pages...")

    doc.close()

    if needs_ocr:
        print(f"    OCR complete: {total_pages} pages processed")

    raw = "\n".join(pages_text)
    return clean_text(raw)


def main():
    # Set Tesseract path for PyMuPDF
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PATH

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = []
    for source_name, output_name, description in FILES:
        source_path = os.path.join(SOURCE_DIR, source_name)
        output_path = os.path.join(OUTPUT_DIR, output_name)

        print(f"\n{'='*60}")
        print(f"Processing: {description}")
        print(f"  Source: {source_name}")
        print(f"  Output: {output_name}")

        if not os.path.exists(source_path):
            msg = f"  ERROR: Source file not found: {source_path}"
            print(msg)
            results.append((description, output_name, "FAILED", msg))
            continue

        try:
            if source_name.lower().endswith(".docx"):
                text = extract_docx(source_path)
            elif source_name.lower().endswith(".pdf"):
                text = extract_pdf(source_path)
            else:
                msg = f"  ERROR: Unsupported file format: {source_name}"
                print(msg)
                results.append((description, output_name, "FAILED", msg))
                continue

            # Write output as UTF-8
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)

            file_size = os.path.getsize(output_path)
            line_count = text.count("\n") + 1
            char_count = len(text)
            msg = f"  OK: {line_count:,} lines, {char_count:,} chars, {file_size:,} bytes"
            print(msg)
            results.append((description, output_name, "OK", msg))

        except Exception as e:
            import traceback
            traceback.print_exc()
            msg = f"  ERROR: {type(e).__name__}: {e}"
            print(msg)
            results.append((description, output_name, "FAILED", msg))

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    ok_count = sum(1 for _, _, status, _ in results if status == "OK")
    fail_count = sum(1 for _, _, status, _ in results if status == "FAILED")
    print(f"Converted: {ok_count}/{len(FILES)}")
    if fail_count:
        print(f"Failed: {fail_count}")
    for desc, out, status, detail in results:
        icon = "OK" if status == "OK" else "FAIL"
        print(f"  [{icon}] {desc} -> {out} {detail.strip()}")


if __name__ == "__main__":
    main()

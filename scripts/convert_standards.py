"""
Convert Norwegian audit/accounting standard PDF files to clean plain text for RAG indexing.
Uses PyMuPDF (fitz) for text extraction with OCR fallback (Tesseract + Norwegian) for scanned pages.
"""

import re
import os
import sys

import fitz  # PyMuPDF

BASE = r"c:\Users\ib91\Desktop\DIV\VS CODE PROJECTS\Utvalg-1\doc\fagdatabase"

TESSERACT_PATH = r"C:\Users\ib91\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
TESSDATA_PATH = r"C:\Users\ib91\AppData\Local\Programs\Tesseract-OCR\tessdata"

# (source_path, output_path, description)
FILES = [
    # ISA / ISAE / ISRE / ISRS
    (
        os.path.join(BASE, r"ISA standardene\ISA for MKE\ISA for MKE pr 07112024.pdf"),
        os.path.join(BASE, r"generated\isa\ISA-MKE.txt"),
        "ISA for MKE",
    ),
    (
        os.path.join(BASE, r"ISA standardene\Attestasjonsstandarder\isae-3000-0121.pdf"),
        os.path.join(BASE, r"generated\isa\ISAE-3000.txt"),
        "ISAE 3000",
    ),
    (
        os.path.join(BASE, r"ISA standardene\Attestasjonsstandarder\isre-2400-0324.pdf"),
        os.path.join(BASE, r"generated\isa\ISRE-2400.txt"),
        "ISRE 2400",
    ),
    (
        os.path.join(BASE, r"ISA standardene\Attestasjonsstandarder\isre-2410-forenklet-revisorkontroll-av-et-delarsregnskap-utfort-av-foretakets-valgte-revisor-280111.pdf"),
        os.path.join(BASE, r"generated\isa\ISRE-2410.txt"),
        "ISRE 2410",
    ),
    (
        os.path.join(BASE, r"ISA standardene\Attestasjonsstandarder\isrs-4400-revidert-oppdrag-om-avtalte-kontrollhandlinger-16022022.pdf"),
        os.path.join(BASE, r"generated\isa\ISRS-4400.txt"),
        "ISRS 4400",
    ),
    # NBS 1-8
    (
        os.path.join(BASE, r"artikler\Bokføringsloven - fag\NBS Standarder\NBS-1-Sikring-av-regnskapsmateriale-april-2025.pdf"),
        os.path.join(BASE, r"generated\nbs\NBS-1.txt"),
        "NBS 1 - Sikring av regnskapsmateriale",
    ),
    (
        os.path.join(BASE, r"artikler\Bokføringsloven - fag\NBS Standarder\NBS-2-Kontrollsporet-april-2025.pdf"),
        os.path.join(BASE, r"generated\nbs\NBS-2.txt"),
        "NBS 2 - Kontrollsporet",
    ),
    (
        os.path.join(BASE, r"artikler\Bokføringsloven - fag\NBS Standarder\NBS-3-Elektronisk-tilgjengelighet-i-35-ar-april-2025.pdf"),
        os.path.join(BASE, r"generated\nbs\NBS-3.txt"),
        "NBS 3 - Elektronisk tilgjengelighet i 3,5 år",
    ),
    (
        os.path.join(BASE, r"artikler\Bokføringsloven - fag\NBS Standarder\NBS-4-Elektronisk-fakturering-april-2025.pdf"),
        os.path.join(BASE, r"generated\nbs\NBS-4.txt"),
        "NBS 4 - Elektronisk fakturering",
    ),
    (
        os.path.join(BASE, r"artikler\Bokføringsloven - fag\NBS Standarder\NBS-5-Dokumentasjon-av-balansen-april-2025.pdf"),
        os.path.join(BASE, r"generated\nbs\NBS-5.txt"),
        "NBS 5 - Dokumentasjon av balansen",
    ),
    (
        os.path.join(BASE, r"artikler\Bokføringsloven - fag\NBS Standarder\NBS-6-Bruk-av-tekstbehandlings-og-regnearkprogrammer-oppdatert-april-2015.pdf"),
        os.path.join(BASE, r"generated\nbs\NBS-6.txt"),
        "NBS 6 - Bruk av tekstbehandlings- og regnearkprogrammer",
    ),
    (
        os.path.join(BASE, r"artikler\Bokføringsloven - fag\NBS Standarder\NBS-7-Dokumentasjon-av-betalingstransaksjoner 02-2015.pdf"),
        os.path.join(BASE, r"generated\nbs\NBS-7.txt"),
        "NBS 7 - Dokumentasjon av betalingstransaksjoner",
    ),
    (
        os.path.join(BASE, r"artikler\Bokføringsloven - fag\NBS Standarder\NBS-8-Sideordnede-spesifikasjoner-vedtatt-april-2015.pdf"),
        os.path.join(BASE, r"generated\nbs\NBS-8.txt"),
        "NBS 8 - Sideordnede spesifikasjoner",
    ),
    # Skatte-ABC
    (
        os.path.join(BASE, r"artikler\Skatt - fag\skatte-abc_2024_2025.pdf"),
        os.path.join(BASE, r"generated\kontekst\SKATTE-ABC-2024-2025.txt"),
        "Skatte-ABC 2024/2025",
    ),
]


def clean_text(text: str) -> str:
    """Clean up PDF extraction artifacts while preserving structure."""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove form feed characters (page breaks from PDF)
    text = text.replace("\f", "\n")

    # Remove common header/footer patterns
    # "Side X av Y" style page indicators
    text = re.sub(r"(?mi)^side\s+\d+\s+av\s+\d+\s*$", "", text)

    # Standalone page numbers (lines that are just a number, possibly with whitespace)
    text = re.sub(r"(?m)^\s*\d{1,4}\s*$", "", text)

    # Lines that are just dashes, underscores, or equals (decorative separators)
    text = re.sub(r"(?m)^[\s\-_=]{5,}\s*$", "", text)

    # Remove repeated header lines that appear on every page (common in ISA standards)
    # e.g. "ISA for SME" appearing alone on many lines
    # We don't remove these generically -- they may be section titles.

    # Collapse runs of 3+ blank lines down to 2
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # Remove trailing whitespace on each line
    text = re.sub(r"(?m)[ \t]+$", "", text)

    # Remove leading/trailing whitespace from the whole document
    text = text.strip()

    return text


def page_has_text(page) -> bool:
    """Check if a PDF page has extractable text (not image-only)."""
    text = page.get_text("text").strip()
    return len(text) > 20  # More than trivial content


def extract_pdf(filepath: str) -> str:
    """Extract text from a PDF file using PyMuPDF.
    Falls back to OCR (Tesseract with Norwegian) for image-only pages.
    """
    doc = fitz.open(filepath)

    # First, check if the PDF has any meaningful text at all
    total_text_len = sum(len(page.get_text("text").strip()) for page in doc)
    needs_ocr = total_text_len < 100

    pages_text = []
    total_pages = len(doc)
    ocr_page_count = 0

    for page_num in range(total_pages):
        page = doc[page_num]

        if needs_ocr or not page_has_text(page):
            # Use OCR for this page
            ocr_page_count += 1
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

        # Progress indicator (especially useful for OCR which is slow)
        if (page_num + 1) % 50 == 0 or page_num + 1 == total_pages:
            print(f"    Progress: {page_num + 1}/{total_pages} pages...", flush=True)

    doc.close()

    if ocr_page_count > 0:
        print(f"    OCR was used on {ocr_page_count}/{total_pages} pages")

    raw = "\n".join(pages_text)
    return clean_text(raw)


def main():
    # Set Tesseract path for PyMuPDF
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PATH

    # Ensure all output directories exist
    output_dirs = set(os.path.dirname(out) for _, out, _ in FILES)
    for d in output_dirs:
        os.makedirs(d, exist_ok=True)

    results = []
    for source_path, output_path, description in FILES:
        print(f"\n{'='*60}")
        print(f"Processing: {description}")
        print(f"  Source: {os.path.basename(source_path)}")
        print(f"  Output: {os.path.basename(output_path)}")

        if not os.path.exists(source_path):
            msg = f"  ERROR: Source file not found: {source_path}"
            print(msg)
            results.append((description, os.path.basename(output_path), "FAILED", msg))
            continue

        try:
            text = extract_pdf(source_path)

            # Write output as UTF-8
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(text)

            file_size = os.path.getsize(output_path)
            line_count = text.count("\n") + 1
            char_count = len(text)
            msg = f"  OK: {line_count:,} lines, {char_count:,} chars, {file_size:,} bytes"
            print(msg)
            results.append((description, os.path.basename(output_path), "OK", msg))

        except Exception as e:
            import traceback
            traceback.print_exc()
            msg = f"  ERROR: {type(e).__name__}: {e}"
            print(msg)
            results.append((description, os.path.basename(output_path), "FAILED", msg))

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

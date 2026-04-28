"""
Convert Norwegian audit professional article PDFs to clean plain text for RAG indexing.
Uses PyMuPDF (fitz) for text extraction with OCR fallback (Tesseract + Norwegian) for scanned pages.
"""

import re
import os
import sys

import fitz  # PyMuPDF

BASE = r"c:\Users\ib91\Desktop\DIV\VS CODE PROJECTS\Utvalg-1\doc\fagdatabase"

TESSERACT_PATH = r"C:\Users\ib91\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
TESSDATA_PATH = r"C:\Users\ib91\AppData\Local\Programs\Tesseract-OCR\tessdata"

OUTPUT_DIR = os.path.join(BASE, r"generated\artikler")

# (source_path, output_filename, description)
FILES = [
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Publisert\Nærstående - Revisjonshandlinger for Nærstående Transaksjoner i SMB (ISA 550 & ISA 240).pdf"),
        "ART-NAERSTAENDE-SMB.txt",
        "Nærstående - Revisjonshandlinger for Nærstående Transaksjoner i SMB",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Publisert\Salg - Revisjonshandlinger for å dekke risiko ved inntektsføring i SMB (NGAAP).pdf"),
        "ART-INNTEKTSFORING-SMB.txt",
        "Salg - Revisjonshandlinger for inntektsføring i SMB",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Publisert\LOK - Revisjonshandlinger mot ledelsens overstyring av kontroller.pdf"),
        "ART-LEDELSENS-OVERSTYRING.txt",
        "LOK - Revisjonshandlinger mot ledelsens overstyring av kontroller",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Revisjon av lønn – revisors krav og Finanstilsynets tilbakemeldinger om mangler.pdf"),
        "ART-REVISJON-LONN.txt",
        "Revisjon av lønn",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Revisjon av anleggskontrakter – fra planlegging til rapportering.pdf"),
        "ART-ANLEGGSKONTRAKTER.txt",
        "Revisjon av anleggskontrakter",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Konsolidering og konsernrevisjon i familieeide grupper.pdf"),
        "ART-KONSERNREVISJON.txt",
        "Konsolidering og konsernrevisjon i familieeide grupper",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\IT-generelle kontroller i SMB-revisjon.pdf"),
        "ART-IT-KONTROLLER-SMB.txt",
        "IT-generelle kontroller i SMB-revisjon",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Stikkprøver i SMB-revisjon.pdf"),
        "ART-STIKKPROVER-SMB.txt",
        "Stikkprøver i SMB-revisjon",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Fortsatt drift i revisjon av SMB-foretak.pdf"),
        "ART-FORTSATT-DRIFT-SMB.txt",
        "Fortsatt drift i revisjon av SMB-foretak",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Dokumentasjon og arbeidspapirer i SMB-revisjon.pdf"),
        "ART-DOKUMENTASJON-SMB.txt",
        "Dokumentasjon og arbeidspapirer i SMB-revisjon",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Revisjon av eiendomsutviklere (pågående prosjekter).pdf"),
        "ART-EIENDOMSUTVIKLERE.txt",
        "Revisjon av eiendomsutviklere (pågående prosjekter)",
    ),
    (
        os.path.join(BASE, r"artikler\Bokføringsloven - fag\Fagartikler\Bokføringsloven og Bokføringsforskriften – En omfattende gjennomgang.pdf"),
        "ART-BOKFORINGSLOVEN-GJENNOMGANG.txt",
        "Bokføringsloven og Bokføringsforskriften – En omfattende gjennomgang",
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

        # Progress indicator
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

    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = []
    for source_path, output_filename, description in FILES:
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        print(f"\n{'='*60}")
        print(f"Processing: {description}")
        print(f"  Source: {os.path.basename(source_path)}")
        print(f"  Output: {output_filename}")

        if not os.path.exists(source_path):
            msg = f"  ERROR: Source file not found: {source_path}"
            print(msg)
            results.append((description, output_filename, "FAILED", msg))
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
            results.append((description, output_filename, "OK", msg))

        except Exception as e:
            import traceback
            traceback.print_exc()
            msg = f"  ERROR: {type(e).__name__}: {e}"
            print(msg)
            results.append((description, output_filename, "FAILED", msg))

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

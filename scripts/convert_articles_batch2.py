"""
Convert Norwegian audit professional article PDFs (batch 2) to clean plain text for RAG indexing.
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
        os.path.join(BASE, r"artikler\Revisjon - fag\Revisjon av regnskapsestimater og usikre forpliktelser.pdf"),
        "ART-REGNSKAPSESTIMATER.txt",
        "Revisjon av regnskapsestimater og usikre forpliktelser",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Revisjon av foretak med krypto-eiendeler.pdf"),
        "ART-KRYPTO-EIENDELER.txt",
        "Revisjon av foretak med krypto-eiendeler",
    ),
    (
        os.path.join(BASE, "artikler\Revisjon - fag\Revisjon av ideelle organisasjoner i SMB-segmentet \u2013 risikoer, regelverk og revisjonsmetodikk.pdf"),
        "ART-IDEELLE-ORGANISASJONER.txt",
        "Revisjon av ideelle organisasjoner i SMB-segmentet",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Test av kontroller vs. substanshandlinger i SMB-revisjon.pdf"),
        "ART-KONTROLLER-VS-SUBSTANS.txt",
        "Test av kontroller vs. substanshandlinger i SMB-revisjon",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Internkontrollsystemet i SMB-revisjon.pdf"),
        "ART-INTERNKONTROLL-SMB.txt",
        "Internkontrollsystemet i SMB-revisjon",
    ),
    (
        os.path.join(BASE, "artikler\Revisjon - fag\Forst\u00e5 virksomheten og bransjen \u2013 kritisk for revisjon av SMB-foretak.pdf"),
        "ART-VIRKSOMHETSFORSTAELSE.txt",
        "Forst\u00e5 virksomheten og bransjen \u2013 kritisk for revisjon av SMB-foretak",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\Hvorfor er revisjonsberetningen kritisk for SMB-revisjon_.pdf"),
        "ART-REVISJONSBERETNING-SMB.txt",
        "Hvorfor er revisjonsberetningen kritisk for SMB-revisjon",
    ),
    (
        os.path.join(BASE, r"artikler\Revisjon - fag\1. Hvorfor er revisjonsstrategi og plan kritisk for SMB-revisjon_.pdf"),
        "ART-REVISJONSSTRATEGI-SMB.txt",
        "Hvorfor er revisjonsstrategi og plan kritisk for SMB-revisjon",
    ),
]


def clean_text(text: str) -> str:
    """Clean up PDF extraction artifacts while preserving structure."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\f", "\n")
    text = re.sub(r"(?mi)^side\s+\d+\s+av\s+\d+\s*$", "", text)
    text = re.sub(r"(?m)^\s*\d{1,4}\s*$", "", text)
    text = re.sub(r"(?m)^[\s\-_=]{5,}\s*$", "", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = re.sub(r"(?m)[ \t]+$", "", text)
    text = text.strip()
    return text


def page_has_text(page) -> bool:
    """Check if a PDF page has extractable text (not image-only)."""
    text = page.get_text("text").strip()
    return len(text) > 20


def extract_pdf(filepath: str) -> str:
    """Extract text from a PDF file using PyMuPDF.
    Falls back to OCR (Tesseract with Norwegian) for image-only pages.
    """
    doc = fitz.open(filepath)

    total_text_len = sum(len(page.get_text("text").strip()) for page in doc)
    needs_ocr = total_text_len < 100

    pages_text = []
    total_pages = len(doc)
    ocr_page_count = 0

    for page_num in range(total_pages):
        page = doc[page_num]

        if needs_ocr or not page_has_text(page):
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

        if (page_num + 1) % 50 == 0 or page_num + 1 == total_pages:
            print(f"    Progress: {page_num + 1}/{total_pages} pages...", flush=True)

    doc.close()

    if ocr_page_count > 0:
        print(f"    OCR was used on {ocr_page_count}/{total_pages} pages")

    raw = "\n".join(pages_text)
    return clean_text(raw)


def main():
    os.environ["TESSDATA_PREFIX"] = TESSDATA_PATH
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

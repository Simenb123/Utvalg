"""document_engine.voucher_zip

Scan PowerOffice GO bilag-eksport-ZIP-arkiver og pakk ut individuelle bilag.

PowerOffice GO eksporterer ett ZIP-arkiv per klient/år/periode der hver
bilag ligger som en separat PDF. Filnavnet starter med bilag-nummeret:

    1000-Faktura 2834 fra Eg Prosjekt AS.pdf
    1022-Manuelt.pdf
    1026-Bank.pdf

Format: ``<bilag_nr>-<beskrivelse>.pdf``

Til forskjell fra Tripletex (én stor PDF som må parses for å finne bilag-
grenser) trenger vi her bare å lese filnavnene i ZIP-en. Bilag-nummeret
matcher direkte mot SAF-T sin TransactionID.

Bruk::

    from document_engine.voucher_zip import scan_voucher_zip, extract_bilag_from_zip

    entries = scan_voucher_zip("path/to/Bilagseksport-...zip")
    for e in entries:
        print(e.bilag_nr, e.description, e.pdf_in_zip)

    path = extract_bilag_from_zip(
        "path/to/Bilagseksport-...zip",
        "1000-Faktura 2834 fra Eg Prosjekt AS.pdf",
        "/tmp/bilag_1000.pdf",
    )
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Optional

from document_engine.voucher_pdf import VoucherEntry, _normalize_nr


# ---------------------------------------------------------------------------
# Format-deteksjon og scanning
# ---------------------------------------------------------------------------

# Filnavnet starter med bilag-nummeret etterfulgt av bindestrek.
# Eksempler: "1000-Faktura X.pdf", "1022-Manuelt.pdf", "1026-Bank.pdf"
_FILENAME_RE = re.compile(r"^(\d+)-(.+)\.pdf$", re.IGNORECASE)


def is_powereoffice_zip(zip_path: str | Path) -> bool:
    """Returner True hvis ZIP-en ser ut som en PowerOffice GO bilag-eksport.

    Vi sjekker at minst én fil i ZIP-en matcher mønsteret
    ``<bilag_nr>-<beskrivelse>.pdf`` på toppnivå (ikke i undermappe)."""
    p = Path(zip_path)
    if not p.exists() or p.suffix.lower() != ".zip":
        return False
    try:
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                # Hopp over undermapper og kataloger
                if "/" in name or name.endswith("/"):
                    continue
                if _FILENAME_RE.match(name):
                    return True
    except (zipfile.BadZipFile, OSError):
        return False
    return False


def scan_voucher_zip(zip_path: str | Path, *, year: str = "") -> list[VoucherEntry]:
    """Scan en PowerOffice GO bilagseksport-ZIP og returner én VoucherEntry per PDF.

    ``year`` settes manuelt — PowerOffice-filnavnene inneholder ikke året
    (det fremgår av selve ZIP-navnet eller av brukerens valg). Hvis ikke
    gitt, blir feltet tomt og kan fylles senere av kalleren.

    Returnerer tom liste hvis fila ikke eksisterer eller ikke er et gyldig
    ZIP-arkiv.
    """
    p = Path(zip_path).expanduser().resolve()
    if not p.exists():
        return []

    try:
        archive = zipfile.ZipFile(p)
    except (zipfile.BadZipFile, OSError):
        return []

    entries: list[VoucherEntry] = []
    seen_bilag: set[str] = set()

    with archive:
        for name in archive.namelist():
            # Skipp undermapper og rene mapper
            if "/" in name or name.endswith("/"):
                continue
            m = _FILENAME_RE.match(name)
            if not m:
                continue

            bilag_nr_raw = m.group(1)
            description_raw = m.group(2).strip()

            # Normaliser bilag-nr og hopp over duplikater (skulle ikke
            # forekomme i ren PowerOffice-eksport, men være defensiv).
            bilag_key = _normalize_nr(bilag_nr_raw)
            if bilag_key in seen_bilag:
                continue
            seen_bilag.add(bilag_key)

            entries.append(
                VoucherEntry(
                    bilag_nr=bilag_nr_raw,
                    year=str(year or ""),
                    start_page=0,
                    end_page=0,
                    date="",  # PowerOffice-filnavnet inneholder ikke dato
                    description=description_raw,
                    source_pdf=str(p),
                    pdf_in_zip=name,
                )
            )

    return entries


# ---------------------------------------------------------------------------
# Ekstraksjon
# ---------------------------------------------------------------------------

def extract_bilag_from_zip(
    zip_path: str | Path,
    name_in_zip: str,
    output_path: str | Path,
) -> Path:
    """Pakk ut én PDF fra ZIP-en til ``output_path``.

    Returnerer output-stien ved suksess.
    Kaster ``RuntimeError`` ved feil (manglende fil, korrupt zip, eller
    PDF-en finnes ikke i arkivet).
    """
    zip_path = Path(zip_path).expanduser().resolve()
    output_path = Path(output_path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not zip_path.exists():
        raise RuntimeError(f"ZIP-fila finnes ikke: {zip_path}")

    try:
        with zipfile.ZipFile(zip_path) as z:
            try:
                with z.open(name_in_zip) as src:
                    output_path.write_bytes(src.read())
            except KeyError as exc:
                raise RuntimeError(
                    f"PDF '{name_in_zip}' finnes ikke i {zip_path.name}"
                ) from exc
    except zipfile.BadZipFile as exc:
        raise RuntimeError(f"Korrupt ZIP-arkiv: {zip_path}") from exc

    return output_path


def extract_entry(entry: VoucherEntry, output_path: str | Path) -> Path:
    """Hent ut PDF-en beskrevet av en ZIP-basert VoucherEntry.

    Forventer at ``entry.is_zip`` er True. Kaster ``ValueError`` hvis
    entry er en Tripletex-entry (uten ``pdf_in_zip``).
    """
    if not entry.is_zip:
        raise ValueError(
            "Denne entry-en er ikke fra et ZIP-arkiv. "
            "Bruk document_engine.voucher_pdf.extract_entry i stedet."
        )
    return extract_bilag_from_zip(entry.source_pdf, entry.pdf_in_zip, output_path)

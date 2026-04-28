"""Haphazard bilag-testing — lagring og henting av kontrollerte bilag.

Lag 1 av planen i ``doc/architecture/haphazard_bilag_testing_plan.md``.

Lagrings-strukturen per klient/år:

    clients/<navn>/years/<år>/audit_tests/
        haphazard.jsonl                       ← én linje per kontroll
    clients/<navn>/years/<år>/documents/bilag/
        <bilag_nr>.pdf                        ← arkivert PDF (valgfritt)

Ren backend — ingen Tk-imports.
"""
from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

try:
    import src.shared.client_store.store as _client_store
    _HAS_CLIENT_STORE = True
except Exception:  # pragma: no cover
    _client_store = None  # type: ignore
    _HAS_CLIENT_STORE = False


@dataclass(frozen=True)
class HaphazardTest:
    """Én haphazard-kontroll av et bilag."""

    test_id: str
    test_method: str  # alltid "haphazard" i Lag 1
    klient: str
    år: str
    bilag_nr: str
    konto: str
    kontonavn: str
    regnr: str          # Regnskapslinje-nummer (fra RL-mapping). Tom hvis konto ikke mappet.
    regnskapslinje: str # Regnskapslinje-navn. Tom hvis konto ikke mappet.
    beløp: float
    dato: str
    konklusjon: str  # "ok" | "avvik" | "ikke_konkluderende"
    notat: str
    granskede_av: str
    granskede_dato: str  # ISO 8601 UTC
    pdf_attached: bool
    pdf_path_relative: str  # relativ til klientmappen, eller "" om ikke lagret


def _audit_tests_dir(client: str, year: str) -> Path:
    if _HAS_CLIENT_STORE:
        return _client_store.years_dir(client, year=year) / "audit_tests"
    raise RuntimeError("client_store er ikke tilgjengelig")


def _bilag_documents_dir(client: str, year: str) -> Path:
    if _HAS_CLIENT_STORE:
        return _client_store.years_dir(client, year=year) / "documents" / "bilag"
    raise RuntimeError("client_store er ikke tilgjengelig")


def _haphazard_jsonl(client: str, year: str) -> Path:
    return _audit_tests_dir(client, year) / "haphazard.jsonl"


def make_test_id() -> str:
    """Generer unik test-ID med tidsstempel-prefix for kronologi."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"ha-{ts}-{short}"


def save_haphazard_test(
    *,
    client: str,
    year: str,
    bilag_nr: str,
    konto: str = "",
    kontonavn: str = "",
    regnr: str = "",
    regnskapslinje: str = "",
    beløp: float = 0.0,
    dato: str = "",
    konklusjon: str,
    notat: str = "",
    granskede_av: str = "",
    pdf_source_path: Optional[Path] = None,
    save_pdf: bool = False,
) -> HaphazardTest:
    """Lagre en haphazard-test og (valgfritt) arkiver PDF-en.

    - Skriver én ny linje i ``haphazard.jsonl`` (append-only).
    - Hvis ``save_pdf=True`` og ``pdf_source_path`` peker på en eksisterende
      PDF, kopieres filen til ``documents/bilag/<bilag_nr>.pdf``.
    - Returnerer den lagrede ``HaphazardTest`` (med fylte felt).
    """
    if not client or not year:
        raise ValueError("client og year må være satt")
    if konklusjon not in ("ok", "avvik", "ikke_konkluderende"):
        raise ValueError(f"Ugyldig konklusjon: {konklusjon}")

    test_id = make_test_id()
    granskede_dato = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    pdf_relative = ""
    pdf_attached = False
    if save_pdf and pdf_source_path is not None:
        src = Path(pdf_source_path)
        if src.exists() and src.is_file():
            dest_dir = _bilag_documents_dir(client, year)
            dest_dir.mkdir(parents=True, exist_ok=True)
            # Bruker bilag_nr som filnavn — ett kontrollert bilag per nr.
            # Hvis fil finnes fra før, overskriv (siste kontroll vinner;
            # historikk holdes i JSONL-en).
            dest = dest_dir / f"{bilag_nr}.pdf"
            shutil.copy2(str(src), str(dest))
            pdf_attached = True
            try:
                pdf_relative = str(dest.relative_to(_client_store.years_dir(client, year=year).parent.parent))
            except Exception:
                pdf_relative = f"documents/bilag/{bilag_nr}.pdf"

    test = HaphazardTest(
        test_id=test_id,
        test_method="haphazard",
        klient=client,
        år=year,
        bilag_nr=str(bilag_nr),
        konto=str(konto),
        kontonavn=str(kontonavn),
        regnr=str(regnr or ""),
        regnskapslinje=str(regnskapslinje or ""),
        beløp=float(beløp) if beløp is not None else 0.0,
        dato=str(dato),
        konklusjon=konklusjon,
        notat=str(notat),
        granskede_av=str(granskede_av),
        granskede_dato=granskede_dato,
        pdf_attached=pdf_attached,
        pdf_path_relative=pdf_relative,
    )

    # Append-only JSONL — sikrer audit-trail (aldri rediger eksisterende
    # linjer). Hvis brukeren vil "rette" en test, lagres en ny test.
    out_path = _haphazard_jsonl(client, year)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(test), ensure_ascii=False) + "\n")

    return test


def load_haphazard_tests(client: str, year: str) -> list[HaphazardTest]:
    """Les alle lagrede haphazard-tester for klient/år. Tom liste hvis ingen."""
    path = _haphazard_jsonl(client, year)
    if not path.exists():
        return []
    out: list[HaphazardTest] = []
    # Felter som ble lagt til i senere versjoner — fyll defaults for
    # gamle JSON-linjer slik at HaphazardTest(**data) ikke feiler.
    _DEFAULTS_FOR_OLDER_VERSIONS = {
        "regnr": "",
        "regnskapslinje": "",
    }
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                for k, v in _DEFAULTS_FOR_OLDER_VERSIONS.items():
                    data.setdefault(k, v)
                out.append(HaphazardTest(**data))
            except Exception:
                continue  # hopper over korrupte linjer
    return out


def has_haphazard_test_for_bilag(client: str, year: str, bilag_nr: str) -> bool:
    """Returnerer True hvis bilaget allerede har minst én lagret test."""
    target = str(bilag_nr).strip()
    if not target:
        return False
    for t in load_haphazard_tests(client, year):
        if t.bilag_nr == target:
            return True
    return False

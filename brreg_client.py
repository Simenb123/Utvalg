"""brreg_client.py — Klient for Brønnøysundregistrenes åpne API-er.

Henter data fra:
  - Enhetsregisteret  : status, MVA-registrering, bransje, adresse
  - Regnskapsregisteret: nøkkeltall fra sist innleverte årsregnskap

Alle svar caches lokalt i JSON (24 t TTL) for å unngå unødvendig nettverksbruk.
Cache lagres i ~/.utvalg/brreg_cache.json.

Ingen tredjeparts avhengigheter — kun stdlib (urllib, json, threading).
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

_ENHET_URL    = "https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}"
_REGNSKAP_URL = "https://data.brreg.no/regnskapsregisteret/regnskap/{orgnr}"
_CACHE_TTL    = 86_400   # 24 timer
_TIMEOUT      = 10       # sekunder per request
_REGNSKAP_SCHEMA_VERSION = "2"   # bump når felt-mappingen endres

# NACE-toppkoder som typisk er unntatt eller utenfor MVA-loven.
# Kilde: mval. §§ 3-2 til 3-20 og Merverdiavgiftshåndboken.
_MVA_EXEMPT_NACE_PREFIXES: frozenset[str] = frozenset({
    "60", "61", "62", "63", "64", "65", "66",   # finans / forsikring
    "68",                                          # fast eiendom (utleie)
    "75",                                          # veterinærtjenester (delvis)
    "84",                                          # offentlig forvaltning
    "85",                                          # undervisning
    "86", "87", "88",                              # helse og sosiale tjenester
    "90", "91",                                    # kunst og kultur (delvis)
    "94",                                          # foreninger og organisasjoner
    "99",                                          # internasjonale organisasjoner
})


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_path() -> Path:
    base = Path(os.path.expanduser("~")) / ".utvalg"
    base.mkdir(parents=True, exist_ok=True)
    return base / "brreg_cache.json"


def _load_cache() -> dict[str, Any]:
    p = _cache_path()
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    try:
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("BRREG cache skriving feilet: %s", e)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _get_json(url: str) -> Any:
    """HTTP GET → parsed JSON, eller None ved feil (inkl. 404)."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Utvalg-revisjonsverktoy/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            log.warning("BRREG HTTP %s: %s", exc.code, url)
        return None
    except Exception as exc:
        log.warning("BRREG feil: %s  url=%s", exc, url)
        return None


# ---------------------------------------------------------------------------
# Hjelpefunksjoner
# ---------------------------------------------------------------------------

def _num(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _fmt_adresse(adr: dict | None) -> str:
    if not adr:
        return ""
    parts: list[str] = []
    adrl = adr.get("adresse") or []
    if isinstance(adrl, list):
        parts.extend(a for a in adrl if a)
    elif adrl:
        parts.append(str(adrl))
    postnr   = adr.get("postnummer", "")
    poststed = adr.get("poststed", "")
    if postnr or poststed:
        parts.append(f"{postnr} {poststed}".strip())
    return ", ".join(filter(None, parts))


def is_likely_exempt(nace_code: str) -> bool:
    """Returner True hvis NACE-koden typisk er unntatt MVA."""
    if not nace_code:
        return False
    prefix = nace_code.split(".")[0].strip()
    return prefix in _MVA_EXEMPT_NACE_PREFIXES


def _valid_orgnr(orgnr: str) -> bool:
    s = orgnr.strip().replace(" ", "")
    return len(s) == 9 and s.isdigit()


# ---------------------------------------------------------------------------
# Enhetsregisteret
# ---------------------------------------------------------------------------

def fetch_enhet(orgnr: str, *, use_cache: bool = True) -> dict[str, Any] | None:
    """Hent enhetsinfo fra Enhetsregisteret.

    Returnerte nøkler:
      orgnr, navn, konkurs, underAvvikling, underTvangsavvikling,
      registrertIMvaregisteret, naeringskode, naeringsnavn,
      organisasjonsform, slettedato, forretningsadresse
    Returnerer None hvis orgnr ikke er gyldig eller ikke funnet.
    """
    orgnr = orgnr.strip().replace(" ", "")
    if not _valid_orgnr(orgnr):
        return None

    cache = _load_cache() if use_cache else {}
    cache_key = f"enhet:{orgnr}"
    entry = cache.get(cache_key)
    if entry and time.time() - entry.get("_ts", 0) < _CACHE_TTL:
        return entry.get("data")

    data = _get_json(_ENHET_URL.format(orgnr=orgnr))
    if data is None:
        result: dict[str, Any] | None = None
    else:
        nk = data.get("naeringskode1") or {}
        result = {
            "orgnr":                    orgnr,
            "navn":                     data.get("navn", ""),
            "konkurs":                  bool(data.get("konkurs")),
            "underAvvikling":           bool(data.get("underAvvikling")),
            "underTvangsavvikling":     bool(
                data.get("underTvangsavviklingEllerTvangsopplosning")),
            "registrertIMvaregisteret": bool(data.get("registrertIMvaregisteret")),
            "naeringskode":             nk.get("kode", ""),
            "naeringsnavn":             nk.get("beskrivelse", ""),
            "organisasjonsform":        (data.get("organisasjonsform") or {}).get(
                "beskrivelse", ""),
            "slettedato":               data.get("slettedato", ""),
            "forretningsadresse":       _fmt_adresse(data.get("forretningsadresse")),
        }

    cache[cache_key] = {"_ts": time.time(), "data": result}
    _save_cache(cache)
    return result


# ---------------------------------------------------------------------------
# Regnskapsregisteret
# ---------------------------------------------------------------------------

def fetch_regnskap(orgnr: str, *, use_cache: bool = True) -> dict[str, Any] | None:
    """Hent nøkkeltall fra siste innleverte årsregnskap.

    Returnerte nøkler:
      fra_dato, til_dato, regnskapsaar, valuta, regnskapstype
      Resultatregnskap: driftsinntekter, driftskostnader, driftsresultat,
        finansinntekter, finanskostnader, netto_finans,
        resultat_for_skatt, aarsresultat
      Balanse: sum_anleggsmidler, sum_omloepsmidler, sum_eiendeler,
        sum_egenkapital, langsiktig_gjeld, kortsiktig_gjeld, sum_gjeld
      Revisjon: ikke_revidert, fravalg_revisjon, revisorberetning
    Returnerer None hvis ingen regnskap er tilgjengelig.
    """
    orgnr = orgnr.strip().replace(" ", "")
    if not _valid_orgnr(orgnr):
        return None

    cache = _load_cache() if use_cache else {}
    cache_key = f"regnskap_v{_REGNSKAP_SCHEMA_VERSION}:{orgnr}"
    entry = cache.get(cache_key)
    if entry and time.time() - entry.get("_ts", 0) < _CACHE_TTL:
        return entry.get("data")

    data = _get_json(_REGNSKAP_URL.format(orgnr=orgnr))
    result: dict[str, Any] | None = None

    if isinstance(data, list) and data:
        # Første element er siste innleverte regnskap
        rec      = data[0]
        rs       = rec.get("regnskapsperiode") or {}
        res      = rec.get("resultatregnskapResultat") or {}
        drift    = res.get("driftsresultat") or {}
        finans   = res.get("finansresultat") or {}
        eiend    = rec.get("eiendeler") or {}
        ek_gjeld = rec.get("egenkapitalGjeld") or {}
        gjeld_ov = ek_gjeld.get("gjeldOversikt") or {}
        revisjon = rec.get("revisjon") or {}

        ikke_rev = bool(revisjon.get("ikkeRevidertAarsregnskap"))
        fravalg  = bool(revisjon.get("fravalgRevisjon"))
        if ikke_rev:
            rev_txt = "Ikke revidert"
        elif fravalg:
            rev_txt = "Fravalgt revisjon"
        else:
            rev_txt = "Revidert"

        result = {
            "fra_dato":           rs.get("fraDato", ""),
            "til_dato":           rs.get("tilDato", ""),
            "regnskapsaar":       (rs.get("fraDato") or "")[:4],
            # Resultatregnskap
            "driftsinntekter":    _num((drift.get("driftsinntekter") or {}).get("sumDriftsinntekter")),
            "driftskostnader":    _num((drift.get("driftskostnad") or {}).get("sumDriftskostnad")),
            "driftsresultat":     _num(drift.get("driftsresultat")),
            "finansinntekter":    _num((finans.get("finansinntekt") or {}).get("sumFinansinntekter")),
            "finanskostnader":    _num((finans.get("finanskostnad") or {}).get("sumFinanskostnad")),
            "netto_finans":       _num(finans.get("nettoFinans")),
            "resultat_for_skatt": _num(res.get("ordinaertResultatFoerSkattekostnad")),
            "aarsresultat":       _num(res.get("aarsresultat")),
            # Balanse
            "sum_anleggsmidler":  _num((eiend.get("anleggsmidler") or {}).get("sumAnleggsmidler")),
            "sum_omloepsmidler":  _num((eiend.get("omloepsmidler") or {}).get("sumOmloepsmidler")),
            "sum_eiendeler":      _num(eiend.get("sumEiendeler")),
            "sum_egenkapital":    _num((ek_gjeld.get("egenkapital") or {}).get("sumEgenkapital")),
            "langsiktig_gjeld":   _num((gjeld_ov.get("langsiktigGjeld") or {}).get("sumLangsiktigGjeld")),
            "kortsiktig_gjeld":   _num((gjeld_ov.get("kortsiktigGjeld") or {}).get("sumKortsiktigGjeld")),
            "sum_gjeld":          _num(gjeld_ov.get("sumGjeld")),
            # Meta
            "valuta":             rec.get("valuta", "NOK"),
            "regnskapstype":      rec.get("regnskapstype", ""),
            "ikke_revidert":      ikke_rev,
            "fravalg_revisjon":   fravalg,
            "revisorberetning":   rev_txt,
        }

    cache[cache_key] = {"_ts": time.time(), "data": result}
    _save_cache(cache)
    return result


# ---------------------------------------------------------------------------
# Bulk-henting
# ---------------------------------------------------------------------------

def fetch_many(
    orgnrs: list[str],
    *,
    progress_cb: Callable[[int, int], None] | None = None,
    include_regnskap: bool = True,
) -> dict[str, dict[str, Any]]:
    """Hent BRREG-data for en liste av orgnumre.

    Args:
        orgnrs:           Liste av 9-sifrede orgnumre.
        progress_cb:      Kalt med (ferdig, totalt) etter hvert orgnr.
        include_regnskap: Om regnskapstall skal hentes (kan slå av for hastighet).

    Returns:
        Dict {orgnr: {"enhet": dict|None, "regnskap": dict|None}}.
    """
    results: dict[str, dict] = {}
    unique = [o for o in dict.fromkeys(orgnrs)
              if o and _valid_orgnr(o)]
    total = len(unique)
    for i, orgnr in enumerate(unique, 1):
        enhet    = fetch_enhet(orgnr)
        regnskap = fetch_regnskap(orgnr) if include_regnskap else None
        results[orgnr] = {"enhet": enhet, "regnskap": regnskap}
        if progress_cb:
            try:
                progress_cb(i, total)
            except Exception:
                pass
    return results


def clear_cache() -> None:
    """Slett lokal cache (tvinger ny henting fra BRREG)."""
    p = _cache_path()
    if p.exists():
        p.unlink()

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
_ROLLER_URL   = "https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}/roller"
_REGNSKAP_URL = "https://data.brreg.no/regnskapsregisteret/regnskap/{orgnr}"
_CACHE_TTL    = 86_400   # 24 timer
_TIMEOUT      = 10       # sekunder per request
_REGNSKAP_SCHEMA_VERSION = "6"   # bump når felt-mappingen endres
_MAX_YEARS    = 5        # maks antall innleverte år å ta med fra BRREG-respons

# Kanoniske RL-nøkler som utgjør `linjer`-dictet (brukt av RL-mapping).
_LINJE_KEYS: frozenset[str] = frozenset({
    # Resultat — aggregat
    "driftsinntekter", "driftskostnader", "driftsresultat",
    "finansinntekter", "finanskostnader", "netto_finans",
    "resultat_for_skatt", "aarsresultat",
    "skattekostnad", "ekstraordinaere_poster", "totalresultat",
    # Resultat — detalj (innenfor driftsinntekter / driftskostnad)
    "salgsinntekt", "annen_driftsinntekt",
    "varekostnad", "loennskostnad",
    "avskrivning", "nedskrivning", "annen_driftskostnad",
    # Finanskostnad — detalj
    "rentekostnad_samme_konsern", "annen_rentekostnad",
    # Balanse — aggregat
    "sum_anleggsmidler", "sum_omloepsmidler", "sum_eiendeler",
    "sum_egenkapital", "sum_innskutt_egenkapital",
    "sum_opptjent_egenkapital",
    "langsiktig_gjeld", "kortsiktig_gjeld", "sum_gjeld",
    "sum_egenkapital_og_gjeld",
    # Balanse — detalj (optional fra oppstillingsplan)
    "goodwill", "sum_varer", "sum_fordringer",
    "sum_investeringer", "sum_bankinnskudd_og_kontanter",
})

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
# Roller (fra Enhetsregisteret)
# ---------------------------------------------------------------------------

# Rolletype-koder vi ønsker å hente ut
_ROLLE_MAP: dict[str, str] = {
    "DAGL": "Daglig leder",
    "LEDE": "Styreleder",
    "NEST": "Nestleder",
    "MEDL": "Styremedlem",
    "VARA": "Varamedlem",
    "REVI": "Revisor",
    "REGN": "Regnskapsfører",
    "KONT": "Kontaktperson",
    "KOMP": "Komplementar",
    "DTPR": "Deltaker med pro-rata ansvar",
    "DTSO": "Deltaker med solidarisk ansvar",
    "EIKM": "Eier/innehaver (enkeltpersonforetak)",
}


def fetch_roller(orgnr: str, *, use_cache: bool = True) -> list[dict[str, str]] | None:
    """Hent rolleinnehavere fra Enhetsregisteret.

    Returnerer liste av dicts med nøklene:
        rolle, rolle_kode, navn, fodselsdato (kan være tom)
    Sortert: Daglig leder → Styreleder → Nestleder → Styremedlem → Varamedlem → Revisor → andre.
    Returnerer None ved feil / ugyldig orgnr.
    """
    orgnr = orgnr.strip().replace(" ", "")
    if not _valid_orgnr(orgnr):
        return None

    cache = _load_cache() if use_cache else {}
    cache_key = f"roller:{orgnr}"
    entry = cache.get(cache_key)
    if entry and time.time() - entry.get("_ts", 0) < _CACHE_TTL:
        return entry.get("data")

    data = _get_json(_ROLLER_URL.format(orgnr=orgnr))
    if data is None:
        cache[cache_key] = {"_ts": time.time(), "data": None}
        _save_cache(cache)
        return None

    # Parse rollegrupper → flat liste
    result: list[dict[str, str]] = []
    for gruppe in data.get("rollegrupper", []):
        for rolle in gruppe.get("roller", []):
            if rolle.get("fratraadt"):
                continue
            rtype = rolle.get("type", {})
            kode = rtype.get("kode", "")
            beskrivelse = rtype.get("beskrivelse", _ROLLE_MAP.get(kode, kode))

            person = rolle.get("person")
            enhet = rolle.get("enhet")
            if person:
                # API returnerer navn som nestet objekt: person.navn.fornavn
                navn_obj = person.get("navn") or {}
                if isinstance(navn_obj, dict):
                    fornavn = navn_obj.get("fornavn", "")
                    mellomnavn = navn_obj.get("mellomnavn", "")
                    etternavn = navn_obj.get("etternavn", "")
                else:
                    # Fallback for evt. streng-format
                    fornavn, mellomnavn, etternavn = str(navn_obj), "", ""
                parts = [p for p in (fornavn, mellomnavn, etternavn) if p]
                navn = " ".join(parts)
                fdato = person.get("fodselsdato", "")
            elif enhet:
                raw_navn = enhet.get("navn", "")
                # API kan returnere navn som liste
                if isinstance(raw_navn, list):
                    navn = raw_navn[0] if raw_navn else ""
                else:
                    navn = str(raw_navn)
                fdato = ""
            else:
                continue

            result.append({
                "rolle": beskrivelse,
                "rolle_kode": kode,
                "navn": navn,
                "fodselsdato": fdato or "",
            })

    # Sortér etter prioritet
    _PRIO = {"DAGL": 0, "LEDE": 1, "NEST": 2, "MEDL": 3, "VARA": 4, "REVI": 5, "REGN": 6}
    result.sort(key=lambda r: (_PRIO.get(r["rolle_kode"], 99), r["navn"]))

    cache[cache_key] = {"_ts": time.time(), "data": result}
    _save_cache(cache)
    return result


# ---------------------------------------------------------------------------
# Regnskapsregisteret
# ---------------------------------------------------------------------------

def _extract_entry_fields(rec: dict) -> dict[str, Any]:
    """Parser én BRREG-regnskapspost til kanonisk struktur.

    Returnerer dict med toppnøkler (fra_dato, driftsinntekter, ...) og et
    `linjer`-subdict som inneholder RL-nøklene for mapping-formål.
    """
    rs       = rec.get("regnskapsperiode") or {}
    res      = rec.get("resultatregnskapResultat") or {}
    drift    = res.get("driftsresultat") or {}
    drifts_inn = drift.get("driftsinntekter") or {}
    drifts_kost = drift.get("driftskostnad") or {}
    finans   = res.get("finansresultat") or {}
    finans_kost = finans.get("finanskostnad") or {}
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

    ek = ek_gjeld.get("egenkapital") or {}
    innskutt = ek.get("innskuttEgenkapital") or {}
    opptjent = ek.get("opptjentEgenkapital") or {}

    # BRREG har inkonsistent stavemåte for "innskutt" — sumInnskuttEgenkaptial
    # observert i live data. Fall tilbake til korrekt staving hvis endret.
    _sum_innskutt = (
        innskutt.get("sumInnskuttEgenkaptial")
        or innskutt.get("sumInnskuttEgenkapital")
    )
    _sum_opptjent = opptjent.get("sumOpptjentEgenkapital")

    # Detaljposter innenfor driftsinntekter / driftskostnad — BRREG returnerer
    # disse når innleverende foretak har rapportert etter full regnskapsplikt.
    # For små foretak med forenklet oppstilling kan kun sum-nivået finnes.
    _avskrivning = (
        drifts_kost.get("avskrivningVarigeDriftsmidlerImmatrielleEiendeler")
        or drifts_kost.get("avskrivning")
    )
    _nedskrivning = (
        drifts_kost.get("nedskrivningVarigeDriftsmidlerImmatrielleEiendeler")
        or drifts_kost.get("nedskrivning")
    )

    fields: dict[str, Any] = {
        "fra_dato":           rs.get("fraDato", ""),
        "til_dato":           rs.get("tilDato", ""),
        "regnskapsaar":       (rs.get("fraDato") or "")[:4],
        # Resultatregnskap — aggregat
        "driftsinntekter":    _num(drifts_inn.get("sumDriftsinntekter")),
        "driftskostnader":    _num(drifts_kost.get("sumDriftskostnad")),
        "driftsresultat":     _num(drift.get("driftsresultat")),
        "finansinntekter":    _num((finans.get("finansinntekt") or {}).get("sumFinansinntekter")),
        "finanskostnader":    _num((finans.get("finanskostnad") or {}).get("sumFinanskostnad")),
        "netto_finans":       _num(finans.get("nettoFinans")),
        "resultat_for_skatt": _num(res.get("ordinaertResultatFoerSkattekostnad")),
        "aarsresultat":       _num(res.get("aarsresultat")),
        # Resultatregnskap — detaljposter
        "salgsinntekt":       _num(drifts_inn.get("salgsinntekt")),
        "annen_driftsinntekt": _num(drifts_inn.get("annenDriftsinntekt")),
        "varekostnad":        _num(drifts_kost.get("varekostnad")),
        "loennskostnad":      _num(drifts_kost.get("loennskostnad")),
        "avskrivning":        _num(_avskrivning),
        "nedskrivning":       _num(_nedskrivning),
        "annen_driftskostnad": _num(drifts_kost.get("annenDriftskostnad")),
        # Finanskostnad — detalj (optional fra oppstillingsplan)
        "rentekostnad_samme_konsern": _num(finans_kost.get("rentekostnadSammeKonsern")),
        "annen_rentekostnad":        _num(finans_kost.get("annenRentekostnad")),
        # Resultat — skatt / ekstraordinært / total (optional)
        "skattekostnad":             _num(res.get("ordinaertResultatSkattekostnad")),
        "ekstraordinaere_poster":    _num(res.get("ekstraordinaerePoster")),
        "totalresultat":             _num(res.get("totalresultat")),
        # Balanse — aggregat
        "sum_anleggsmidler":  _num((eiend.get("anleggsmidler") or {}).get("sumAnleggsmidler")),
        "sum_omloepsmidler":  _num((eiend.get("omloepsmidler") or {}).get("sumOmloepsmidler")),
        "sum_eiendeler":      _num(eiend.get("sumEiendeler")),
        "sum_egenkapital":    _num(ek.get("sumEgenkapital")),
        "sum_innskutt_egenkapital": _num(_sum_innskutt),
        "sum_opptjent_egenkapital": _num(_sum_opptjent),
        "langsiktig_gjeld":   _num((gjeld_ov.get("langsiktigGjeld") or {}).get("sumLangsiktigGjeld")),
        "kortsiktig_gjeld":   _num((gjeld_ov.get("kortsiktigGjeld") or {}).get("sumKortsiktigGjeld")),
        "sum_gjeld":          _num(gjeld_ov.get("sumGjeld")),
        "sum_egenkapital_og_gjeld": _num(ek_gjeld.get("sumEgenkapitalGjeld")),
        # Balanse — detalj (optional fra oppstillingsplan)
        "goodwill":                    _num(eiend.get("goodwill")),
        "sum_varer":                   _num(eiend.get("sumVarer")),
        "sum_fordringer":              _num(eiend.get("sumFordringer")),
        "sum_investeringer":           _num(eiend.get("sumInvesteringer")),
        "sum_bankinnskudd_og_kontanter": _num(eiend.get("sumBankinnskuddOgKontanter")),
        # Meta
        "valuta":             rec.get("valuta", "NOK"),
        "regnskapstype":      rec.get("regnskapstype", ""),
        "ikke_revidert":      ikke_rev,
        "fravalg_revisjon":   fravalg,
        "revisorberetning":   rev_txt,
    }
    fields["linjer"] = {
        k: v for k, v in fields.items()
        if k in _LINJE_KEYS and v is not None
    }
    return fields


def _normalize_years_keys(data: Any) -> Any:
    """Konverter years-dict-nøkler tilbake til int etter JSON-cache-load.

    JSON støtter kun string-nøkler, så int-nøkler i `years` serialiseres
    som strings og må konverteres tilbake ved load for konsistens.
    """
    if not isinstance(data, dict):
        return data
    years = data.get("years")
    if isinstance(years, dict):
        data["years"] = {
            (int(k) if isinstance(k, str) and k.isdigit() else k): v
            for k, v in years.items()
        }
    return data


def fetch_regnskap(orgnr: str, *, use_cache: bool = True) -> dict[str, Any] | None:
    """Hent innleverte årsregnskap fra Regnskapsregisteret.

    Returnerer dict for nyeste år med bakoverkompatible toppnøkler
    (regnskapsaar, linjer, driftsinntekter, ...) pluss flerårsfelter:
      - years: {år (int): {fra_dato, ..., linjer}, ...} opptil _MAX_YEARS
      - available_years: [år] sortert synkende

    Returnerer None hvis ingen regnskap er tilgjengelig.
    """
    orgnr = orgnr.strip().replace(" ", "")
    if not _valid_orgnr(orgnr):
        return None

    cache = _load_cache() if use_cache else {}
    cache_key = f"regnskap_v{_REGNSKAP_SCHEMA_VERSION}:{orgnr}"
    entry = cache.get(cache_key)
    if entry and time.time() - entry.get("_ts", 0) < _CACHE_TTL:
        return _normalize_years_keys(entry.get("data"))

    data = _get_json(_REGNSKAP_URL.format(orgnr=orgnr))
    result: dict[str, Any] | None = None

    if isinstance(data, list) and data:
        years: dict[int, dict[str, Any]] = {}
        for rec in data[:_MAX_YEARS]:
            fields = _extract_entry_fields(rec)
            aar_str = fields.get("regnskapsaar") or ""
            try:
                aar_int = int(aar_str)
            except (ValueError, TypeError):
                continue
            years[aar_int] = fields

        if years:
            available_years = sorted(years.keys(), reverse=True)
            newest = available_years[0]
            # Bakoverkompat: toppnivå = nyeste år (alle eksisterende nøkler)
            result = dict(years[newest])
            result["years"] = years
            result["available_years"] = available_years

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

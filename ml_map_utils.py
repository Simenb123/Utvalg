# -*- coding: utf-8 -*-
"""
ml_map_utils.py – R12f
Laster/lagrer .ml_map.json og hjelper til med å foreslå/oppdatere kolonnekart.

Denne filen er en tilpasset kopi av modulens innhold fra det opprinnelige
Utvalg‑prosjektet. I tillegg til original funksjonalitet har vi lagt til
flere aliaser for å gjenkjenne flere varianter av feltnavn som ofte
forekommer i regnskapsdata. Disse aliasene gjør at automatisk gjetting av
kolonnekarting (mapping) blir mer treffsikker. Ingen av funksjonene i
modulen sender data utenfor programmet; læring består kun i å lagre
tidligere mapping lokalt i `.ml_map.json`.

Endringer fra originalen:
 * Utvidet alias‑sets for flere felt (Beløp, MVA‑kode, MVA‑beløp,
   MVA‑prosent, Valuta, Valutabeløp) med nye synonymer slik at felt som
   «Bokført beløp», «ISO‑kode», «Belap i valuta», «avg kode» og
   «Mva‑sats» gjenkjennes.
 * Kommentert kode for klarhet.
"""

from __future__ import annotations
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import json
import os

import app_paths


DEFAULT_ML_MAP_FILENAME = ".ml_map.json"


def _default_ml_map_path() -> str:
    """Standard sti til .ml_map.json.

    - I utviklingsmodus (ikke frozen): bruker vi historisk fil i cwd
      (".ml_map.json") for å være bakoverkompatibel.
    - I PyInstaller/frozen: skriver vi til AppData (eller UTVALG_DATA_DIR)
      slik at filen ikke havner i en midlertidig utpakkingsmappe.
    """

    if app_paths.is_frozen():
        return str(app_paths.data_file(DEFAULT_ML_MAP_FILENAME))
    return DEFAULT_ML_MAP_FILENAME

# Liste over kanoniske felt. Rekkefølgen her brukes når DataFrame skal
# reorganiseres etter mapping.
CANON = [
    "Konto", "Kontonavn", "Bilag", "Beløp", "Dato", "Tekst",
    "Kundenr", "Kundenavn", "Leverandørnr", "Leverandørnavn",
    "MVA-kode", "MVA-beløp", "MVA-prosent", "Valuta", "Valutabeløp"
]

# Aliaslisten under hjelper til med å matche kolonnenavn i regneark mot
# kanoniske felt. Hver nøkkel er et kanonisk felt og peker på en mengde
# mulige header‑strenger. Alle strenger her bør skrives i små bokstaver,
# uten diakritiske tegn (akkurat slik _norm() produserer), slik at
# direkte membership‑sjekk i suggest_mapping() fungerer.
ALIASES: Dict[str, set[str]] = {
    # Konto: kontonummer og generelle GL‑kontoaliaser
    "Konto": {
        "konto", "kontonr", "kontonummer",
        "account", "account no", "account number", "gl account", "gl",
        "accountid", "account id", "accountid", "account number", "accountnumber"
    },
    # Kontonavn: navn eller beskrivelse for konto
    "Kontonavn": {
        "kontonavn", "konto navn", "kontobetegnelse",
        "account name", "gl name", "gl tekst",
        "accountdescription", "account description", "account desc"
    },
    # Bilag: dokumentnummer eller voucher
    "Bilag": {
        "bilag", "doknr", "dokumentnr", "dok nr",
        "document no", "document number", "documentno", "docno", "doc no",
        "voucher", "voucher no", "voucher number", "voucherno",
        "bilagsnr", "bilagsnummer"
    },
    # Beløp: beløp i lokal valuta. Vi har lagt til flere varianter som
    # bokført beløp for å fange opp kolonner som heter f.eks. "Bokført beløp".
    "Beløp": {
        "beløp", "belop", "beløp",
        "amount", "amount (nok)", "beløp (nok)", "beløp nok",
        "line amount", "amount local", "amount nok",
        # nye aliaser for bokførte beløp
        "bokfort belop", "bokfort beløp", "bokført belop", "bokført beløp"
    },
    # Dato: dato for bilag, postering eller transaksjon
    "Dato": {
        "dato", "bilagsdato", "posteringsdato", "transaksjonsdato",
        "date", "posting date", "document date"
    },
    # Tekst: posteringstekst eller beskrivelse
    "Tekst": {
        "tekst", "posteringstekst", "beskrivelse",
        "description", "text", "postingtext", "posting text"
    },
    # Kundenr: kundenummer
    "Kundenr": {
        "kundenr", "kundnr", "kund id",
        "customer id", "customerid", "customer no", "customer number"
    },
    # Kundenavn: kundenavn
    "Kundenavn": {
        "kundenavn", "customer name", "navn kunde", "customername", "customer description"
    },
    # Leverandørnr: leverandørnummer
    "Leverandørnr": {
        "leverandørnr", "leverandornr", "lev nr",
        "supplier id", "supplierid", "supplier no", "supplier number",
        "vendor id", "vendorid", "vendor no", "vendor number"
    },
    # Leverandørnavn: leverandørnavn
    "Leverandørnavn": {
        "leverandørnavn", "leverandornavn", "navn leverandør",
        "supplier name", "suppliername", "vendor name", "vendorname"
    },
    # MVA-kode: avgiftskode. Vi har utvidet med avg-kode-varianter.
    "MVA-kode": {
        "mva-kode", "mvakode", "mva kode",
        "vat code", "vatcode", "tax code", "taxcode",
        # nye aliaser
        "avg-kode", "avg kode", "avgkode", "avg.-kode"
    },
    # MVA-beløp: avgiftsbeløp. Vi har lagt til variasjoner uten diakritika.
    "MVA-beløp": {
        "mva-beløp", "mvabeløp", "mva beløp",
        "vat amount", "vatamount", "tax amount", "taxamount",
        # nye aliaser
        "mva-belop", "mvabelop", "mva belop"
    },
    # MVA-prosent: avgiftssats i prosent. Nye aliaser inkluderer mva-sats.
    "MVA-prosent": {
        "mva-prosent", "mvaprosent", "mva %",
        "vat %", "vat%", "tax %", "tax%",
        "vat percentage", "vatpercentage", "tax rate", "taxrate",
        # nye aliaser
        "mva-sats", "mvasats", "mva sats"
    },
    # Valuta: valutakode. Vi har lagt til ISO-varianter.
    "Valuta": {
        "valuta", "currency", "valutakode",
        "currency code", "currencycode",
        # nye aliaser for ISO-koder
        "iso", "iso-kode", "iso kode", "iso code", "isokode"
    },
    # Valutabeløp: beløp i utenlandsk valuta. Nye aliaser for beløp i valuta.
    "Valutabeløp": {
        "valutabeløp", "valuta beløp",
        "amount (cur)", "amount currency", "amountcurrency", "foreign amount", "foreignamount",
        # nye aliaser
        "belap i valuta", "beløp i valuta", "belop i valuta",
        "belap i utenlandsk valuta", "beløp i utenlandsk valuta", "belop i utenlandsk valuta",
        "beløp valuta", "belop valuta"
    },
}

def canonical_fields() -> List[str]:
    """Returner listen over kanoniske felter i fast rekkefølge."""
    return list(CANON)

def _norm(s: str) -> str:
    """
    Normaliser en header ved å fjerne diakritika, trimme og slå sammen
    whitespace. Denne funksjonen gjør at aliasene matcher uavhengig av
    store/små bokstaver, norske bokstaver og ekstra mellomrom.
    """
    import unicodedata
    s = (s or "").strip().lower()
    # Normaliser unicode (NFKD).
    s = unicodedata.normalize("NFKD", s)
    # Erstatt norske og nordiske bokstaver med enklere ekvivalenter før ascii
    replacements = {
        'ø': 'o', 'œ': 'oe', 'æ': 'ae', 'å': 'a', 'ä': 'a', 'ö': 'o',
        'é': 'e', 'á': 'a', 'à': 'a', 'è': 'e', 'ê': 'e', 'ë': 'e'
    }
    for ch, repl in replacements.items():
        s = s.replace(ch, repl)
    # Dropp eventuelle gjenværende diakritiske tegn
    s = s.encode("ascii", "ignore").decode("ascii")
    # Erstatt ikke‑brytende mellomrom med vanlige mellomrom og kollaps flere
    s = s.replace("\u00a0", " ")
    s = " ".join(s.split())
    return s

def _fingerprint(headers: List[str]) -> str:
    """Lag en fingeravtrykkstreng fra headerlisten for å sammenligne datasett."""
    return "|".join(sorted({_norm(h) for h in headers if h}))[:2000]

def load_ml_map(path: str | None = None) -> dict:
    """Les tidligere læring fra `.ml_map.json`.

    Hvis ``path`` ikke er angitt, brukes standard sti:
      - ikke frozen: cwd/.ml_map.json
      - frozen: AppData (eller UTVALG_DATA_DIR)/.ml_map.json

    I frozen-modus gjør vi også en *best effort* migrering fra eldre
    plasseringer (ved siden av exe / cwd) hvis standardfilen ikke finnes.
    """

    target = path or _default_ml_map_path()
    try:
        if os.path.exists(target):
            with open(target, "r", encoding="utf-8") as f:
                obj = json.load(f)
                if isinstance(obj, dict):
                    return obj

        # Best-effort migrering når vi ikke fant filen i target.
        if path is None and app_paths.is_frozen():
            legacy_candidates = app_paths.best_effort_legacy_paths(
                app_paths.executable_dir() / DEFAULT_ML_MAP_FILENAME,
                os.getcwd() and (Path(os.getcwd()) / DEFAULT_ML_MAP_FILENAME),
            )
            for lp in legacy_candidates:
                try:
                    with open(lp, "r", encoding="utf-8") as f:
                        obj = json.load(f)
                    if isinstance(obj, dict):
                        # migrer til target
                        save_ml_map(obj, target)
                        return obj
                except Exception:
                    continue
    except Exception:
        pass
    return {}

def save_ml_map(data: dict, path: str | None = None) -> None:
    """Skriv læringsobjektet til disk på en sikker måte."""
    target = path or _default_ml_map_path()
    try:
        # Sørg for mappe (spesielt viktig i frozen/AppData)
        try:
            Path(target).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    except Exception:
        pass

def _iter_signatures(ml: dict) -> List[Tuple[str, List[str], dict]]:
    """
    Iterate over signaturene i ml_map. Støtter både gammel (fp->mapping) og
    ny struktur (signatures-list).
    """
    out: List[Tuple[str, List[str], dict]] = []
    if not isinstance(ml, dict):
        return out
    # Style A: {fp: mapping}
    for k, v in ml.items():
        if isinstance(v, dict) and all(isinstance(kk, str) for kk in v.keys()):
            # Vi har ikke headers-liste, kun fingerprint. Vi kan ikke
            # beregne likhet, så vi lagrer en tom headerliste.
            out.append((str(k), [], v))
    # Style B: {"signatures":[{"headers":[...], "mapping":{...}}]}
    sigs = ml.get("signatures")
    if isinstance(sigs, list):
        for item in sigs:
            if not isinstance(item, dict):
                continue
            headers = item.get("headers", [])
            mapping = item.get("mapping", {})
            fp = item.get("fp") or _fingerprint(headers)
            if isinstance(mapping, dict):
                out.append((fp, list(headers) if isinstance(headers, list) else [], mapping))
    return out

def suggest_mapping(headers: List[str], ml: Optional[dict] = None) -> Optional[dict]:
    """
    Returner en foreslått mapping {Canon: SourceCol} for de kolonnene som
    kan matches enten via tidligere læring (ml_map) eller via aliaslisten.
    Dersom vi ikke finner noen gode treff, returneres None.
    """
    if not headers:
        return None
    headers_norm = {_norm(h) for h in headers if h}
    ml = ml or load_ml_map()
    # Først prøv å finne en match basert på historiske signaturer
    best: Optional[dict] = None
    best_score = 0.0
    for fp, sig_headers, mapping in _iter_signatures(ml):
        if sig_headers:
            sig_norm = {_norm(h) for h in sig_headers if h}
            inter = len(headers_norm & sig_norm)
            union = max(1, len(headers_norm | sig_norm))
            score = inter / union
        else:
            # bare fingerprint – sammenlign likhet mellom fingerprint
            score = 1.0 if fp == _fingerprint(list(headers_norm)) else 0.0
        if score > best_score:
            best_score = score
            best = mapping
    if best and best_score >= 0.55:
        # Filtrer til kolonner som faktisk eksisterer i input
        return {k: v for k, v in best.items() if v in headers}
    # Fallback via aliasmatch
    lowered = {_norm(h): h for h in headers}
    guess: Dict[str, str] = {}
    for canon, alias_set in ALIASES.items():
        for cand in alias_set:
            # Aliasene i ALIASES er i normalisert form; lowered har normaliserte
            # nøkler. Sjekk direkte membership.
            if cand in lowered:
                guess[canon] = lowered[cand]
                break
    return guess or None

def update_ml_map(headers: List[str], mapping: dict, ml: Optional[dict] = None, path: str | None = None) -> dict:
    """
    Flett inn en ny signatur i ml_map uten å overskrive eksisterende
    strukturer. Både gammel og ny struktur i .ml_map.json støttes.
    """
    ml = ml or load_ml_map(path)
    fp = _fingerprint(headers)
    # Style A: direkte fp->mapping
    if all(isinstance(k, str) and isinstance(v, dict) for k, v in ml.items() if k != "signatures"):
        cur = ml.get(fp, {})
        if isinstance(cur, dict):
            cur.update({k: v for k, v in mapping.items() if v in headers})
            ml[fp] = cur
    # Style B: signatures-liste
    sigs = ml.get("signatures")
    if not isinstance(sigs, list):
        sigs = []
    # finn samme fingerprint
    idx: Optional[int] = None
    for i, item in enumerate(sigs):
        if isinstance(item, dict) and (
            item.get("fp") == fp or _fingerprint(item.get("headers", [])) == fp
        ):
            idx = i
            break
    entry = {
        "fp": fp,
        "headers": list(headers),
        "mapping": {k: v for k, v in mapping.items() if v in headers},
    }
    if idx is None:
        sigs.append(entry)
    else:
        # merge
        old = sigs[idx].get("mapping", {}) if isinstance(sigs[idx], dict) else {}
        if not isinstance(old, dict):
            old = {}
        old.update(entry["mapping"])
        sigs[idx] = {"fp": fp, "headers": list(headers), "mapping": old}
    ml["signatures"] = sigs
    save_ml_map(ml, path)
    return ml

def apply_mapping(df, mapping: dict):
    """
    Returner en kopi av DataFrame der kolonner er mappet til kanoniske navn.
    Ikke-eksisterende felter i mapping ignoreres. Hvis df er None eller
    mapping er None, returneres df uendret.
    """
    if df is None or mapping is None:
        return df
    # Omvendt mapping: fra datakolonne til kanonisk felt
    rename = {src: canon for canon, src in mapping.items() if src in df.columns}
    out = df.rename(columns=rename)
    # plasser kanoniske felter først, deretter de som ikke er i listen
    cols = [c for c in CANON if c in out.columns] + [c for c in out.columns if c not in CANON]
    return out.loc[:, cols]

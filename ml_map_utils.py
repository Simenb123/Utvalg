# -*- coding: utf-8 -*-
"""
ml_map_utils.py – R12f
Laster/lagrer .ml_map.json og hjelper til med å foreslå/oppdatere kolonnekart.
Bevarer bakoverkompatibilitet:
- Støtter både struktur som {fp: mapping} og {"signatures":[{"headers":[...], "mapping":{...}}]}.
"""
from __future__ import annotations
from typing import Dict, List, Tuple, Optional
import json, os, re

CANON = [
    "Konto","Kontonavn","Bilag","Beløp","Dato","Tekst",
    "Kundenr","Kundenavn","Leverandørnr","Leverandørnavn",
    "MVA-kode","MVA-beløp","MVA-prosent","Valuta","Valutabeløp"
]

ALIASES = {
    # Ny aliasliste. Hver kanonisk felt peker på en mengde mulige kolonnenavn, inkludert engelske SAF‑T‑varianter.
    "Konto": {
        "konto","kontonr","kontonummer",
        "account","account no","account number","gl account","gl",
        "accountid","account id","accountid","account number","accountnumber"
    },
    "Kontonavn": {
        "kontonavn","konto navn","kontobetegnelse",
        "account name","gl name","gl tekst",
        "accountdescription","account description","account desc"
    },
    "Bilag": {
        "bilag","doknr","dokumentnr","dok nr",
        "document no","document number","documentno","docno","doc no",
        "voucher","voucher no","voucher number","voucherno",
        "bilagsnr","bilagsnummer"
    },
    "Beløp": {
        "beløp","belop","bel\u00f8p",
        "amount","amount (nok)","beløp (nok)","beløp nok",
        "line amount","amount local","amount nok"
    },
    "Dato": {
        "dato","bilagsdato","posteringsdato","transaksjonsdato",
        "date","posting date","document date"
    },
    "Tekst": {
        "tekst","posteringstekst","beskrivelse",
        "description","text","postingtext","posting text"
    },
    "Kundenr": {
        "kundenr","kundnr","kund id",
        "customer id","customerid","customer no","customer number"
    },
    "Kundenavn": {
        "kundenavn","customer name","navn kunde","customername","customer description"
    },
    "Leverandørnr": {
        "leverand\u00f8rnr","leverandornr","lev nr",
        "supplier id","supplierid","supplier no","supplier number",
        "vendor id","vendorid","vendor no","vendor number"
    },
    "Leverandørnavn": {
        "leverand\u00f8rnavn","leverandornavn","navn leverand\u00f8r",
        "supplier name","suppliername",
        "vendor name","vendorname"
    },
    "MVA-kode": {
        "mva-kode","mvakode","mva kode",
        "vat code","vatcode","tax code","taxcode"
    },
    "MVA-beløp": {
        "mva-beløp","mvabeløp","mva beløp",
        "vat amount","vatamount","tax amount","taxamount"
    },
    "MVA-prosent": {
        "mva-prosent","mvaprosent","mva %",
        "vat %","vat%","tax %","tax%",
        "vat percentage","vatpercentage","tax rate","taxrate"
    },
    "Valuta": {
        "valuta","currency","valutakode",
        "currency code","currencycode"
    },
    "Valutabeløp": {
        "valutabeløp","valuta beløp",
        "amount (cur)","amount currency","amountcurrency","foreign amount","foreignamount"
    },
}

def canonical_fields() -> List[str]:
    return list(CANON)

def _norm(s: str) -> str:
    """Normaliser en header ved å fjerne diakritika, trimme og slå sammen whitespace."""
    import unicodedata
    # Start med en strip-et streng i lower case
    s = (s or "").strip().lower()
    # Normaliser unicode (NFKD).
    s = unicodedata.normalize("NFKD", s)
    # Erstatt norske og nordiske bokstaver med enklere ekvivalenter før ascii-encoding.
    # Dette gjør at beløp, beloep, belop alle normaliseres til "belop".
    replacements = {
        'ø': 'o', 'œ': 'oe', 'æ': 'ae', 'å': 'a', 'ä': 'a', 'ö': 'o',
        'é': 'e', 'á': 'a', 'à': 'a', 'è': 'e', 'ê': 'e', 'ë': 'e'
    }
    for ch, repl in replacements.items():
        s = s.replace(ch, repl)
    # Konverter til ascii og dropp eventuelle gjenværende diakritiske tegn
    s = s.encode("ascii", "ignore").decode("ascii")
    # Erstatt ikke-brytende mellomrom med vanlige mellomrom
    s = s.replace("\u00a0", " ")
    # Kollaps flere mellomrom til ett
    s = " ".join(s.split())
    return s

def _fingerprint(headers: List[str]) -> str:
    return "|".join(sorted({_norm(h) for h in headers if h}))[:2000]

def load_ml_map(path: str = ".ml_map.json") -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                obj = json.load(f)
                if isinstance(obj, dict):
                    return obj
    except Exception:
        pass
    return {}

def save_ml_map(data: dict, path: str = ".ml_map.json") -> None:
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass

def _iter_signatures(ml: dict) -> List[Tuple[str, List[str], dict]]:
    out: List[Tuple[str, List[str], dict]] = []
    if not isinstance(ml, dict):
        return out
    # Style A: {fp: mapping}
    for k, v in ml.items():
        if isinstance(v, dict) and all(isinstance(kk,str) for kk in v.keys()):
            # we don't have headers list, only fp -> can't compute similarity properly; store empty headers
            out.append((str(k), [], v))
    # Style B: {"signatures":[{"headers":[...], "mapping":{...}}]}
    sigs = ml.get("signatures")
    if isinstance(sigs, list):
        for item in sigs:
            if not isinstance(item, dict): continue
            headers = item.get("headers", [])
            mapping = item.get("mapping", {})
            fp = item.get("fp") or _fingerprint(headers)
            if isinstance(mapping, dict):
                out.append((fp, list(headers) if isinstance(headers, list) else [], mapping))
    return out

def suggest_mapping(headers: List[str], ml: Optional[dict] = None) -> Optional[dict]:
    """Returner mapping {Canon: SourceCol} eller None om vi ikke finner noe godt.”"""
    if not headers: return None
    headers_norm = {_norm(h) for h in headers if h}
    ml = ml or load_ml_map()
    best = None; best_score = 0.0
    for fp, sig_headers, mapping in _iter_signatures(ml):
        if sig_headers:
            sig_norm = {_norm(h) for h in sig_headers if h}
            inter = len(headers_norm & sig_norm)
            union = max(1, len(headers_norm | sig_norm))
            score = inter / union
        else:
            # only fp – compare equality of fp as heuristic
            score = 1.0 if fp == _fingerprint(list(headers_norm)) else 0.0
        if score > best_score:
            best_score = score; best = mapping
    if best and best_score >= 0.55:
        # filter to columns that actually exist
        return {k:v for k,v in best.items() if v in headers}
    # fallback via aliases
    lowered = {_norm(h): h for h in headers}
    guess = {}
    for canon, alias_set in ALIASES.items():
        for cand in alias_set:
            if cand in lowered:
                guess[canon] = lowered[cand]; break
    return guess or None

def update_ml_map(headers: List[str], mapping: dict, ml: Optional[dict] = None, path: str = ".ml_map.json") -> dict:
    """Flett inn ny signatur uten å overskrive eksisterende på annen struktur.”"""
    ml = ml or load_ml_map(path)
    fp = _fingerprint(headers)
    # Style A: direkte fp->mapping
    if all(isinstance(k,str) and isinstance(v,dict) for k,v in ml.items() if k!="signatures"):
        cur = ml.get(fp, {})
        if isinstance(cur, dict):
            cur.update({k:v for k,v in mapping.items() if v in headers})
            ml[fp] = cur
    # Style B: signatures-liste
    sigs = ml.get("signatures")
    if not isinstance(sigs, list):
        sigs = []
    # find same fp
    idx = None
    for i, item in enumerate(sigs):
        if isinstance(item, dict) and (item.get("fp") == fp or _fingerprint(item.get("headers", [])) == fp):
            idx = i; break
    entry = {"fp": fp, "headers": list(headers), "mapping": {k:v for k,v in mapping.items() if v in headers}}
    if idx is None:
        sigs.append(entry)
    else:
        # merge
        old = sigs[idx].get("mapping", {}) if isinstance(sigs[idx], dict) else {}
        if not isinstance(old, dict): old = {}
        old.update(entry["mapping"])
        sigs[idx] = {"fp": fp, "headers": list(headers), "mapping": old}
    ml["signatures"] = sigs
    save_ml_map(ml, path)
    return ml

def apply_mapping(df, mapping: dict):
    """Returner DataFrame der kolonner er mappet til kanoniske navn. Ikke-eksisterende ignoreres.”"""
    if df is None or mapping is None:
        return df
    rename = {src: canon for canon, src in mapping.items() if src in df.columns}
    out = df.rename(columns=rename)
    # optional rekkefølge
    cols = [c for c in CANON if c in out.columns] + [c for c in out.columns if c not in CANON]
    return out.loc[:, cols]

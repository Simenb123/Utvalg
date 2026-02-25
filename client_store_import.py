# -*- coding: utf-8 -*-
"""client_store_import.py

Import av klientliste fra Excel/CSV (separert fra client_store.py for å holde
modulstørrelsen nede).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


ProgressCallback = Callable[[int, int, str], None]


def _col_match(cols: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    lower = {str(c).lower(): str(c) for c in cols}
    for cand in candidates:
        if str(cand).lower() in lower:
            return lower[str(cand).lower()]
    return None


def read_client_names_from_file(path: Path) -> List[str]:
    """Les klientnavn fra Excel/CSV.

    Forventer gjerne en kolonne som heter en av:
    Klient, Client, Kundenavn, Selskap, Navn.
    Hvis ikke: bruker første kolonne.
    """

    import pandas as pd

    path = Path(path)
    ext = path.suffix.lower()
    if ext in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        df = pd.read_excel(path, dtype=object, engine="openpyxl")
    else:
        # Norsk CSV er ofte semikolon-separert. Bruk enkel sniffing.
        sample = path.read_text(encoding="utf-8", errors="ignore")[:4096]
        if ";" in sample and sample.count(";") >= sample.count(","):
            sep = ";"
        elif "\t" in sample:
            sep = "\t"
        else:
            sep = ","
        df = pd.read_csv(path, dtype=object, sep=sep, engine="python")

    if df.empty:
        return []

    col = _col_match(df.columns, ["Klient", "Client", "Kundenavn", "Selskap", "Navn", "Kunde"])
    if col is None:
        col = str(df.columns[0])

    s = df[col].dropna().astype(str).map(lambda x: x.strip())
    s = s[s.map(lambda x: bool(x))]

    seen: set[str] = set()
    out: List[str] = []
    for v in s.tolist():
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def import_clients_from_file(path: Path, *, progress_cb: Optional[ProgressCallback] = None) -> Dict[str, Any]:
    """Importer klientliste fra fil til client_store. Returnerer statistikk.

    Viktig: Vi skal *ikke* kalle ``client_store.ensure_client`` for klienter som allerede
    finnes, fordi det kan bli tregt ved store klientlister.

    progress_cb (valgfri): callback som kalles som (i, total, navn) under opprettelse.
    """

    import client_store

    names = read_client_names_from_file(path)
    before = set(x.lower() for x in client_store.list_clients())

    to_create = [n for n in names if n.lower() not in before]
    total = len(to_create)

    if progress_cb is not None:
        try:
            progress_cb(0, total, "")
        except Exception:
            # Best effort: progress må aldri stoppe import
            pass

    created: List[str] = []
    for i, n in enumerate(to_create, start=1):
        client_store.ensure_client(n)
        created.append(n)
        before.add(n.lower())
        if progress_cb is not None:
            try:
                progress_cb(i, total, n)
            except Exception:
                pass

    return {
        "found": len(names),
        "created": len(created),
        "created_names": created,
        "skipped_existing": len(names) - len(to_create),
    }

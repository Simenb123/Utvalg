"""SQLite-basert cache for ferdigbygd datasett.

Mål:
 - Slippe å bygge datasett hver gang (lagre ferdigbygd DF i sqlite)
 - Sporbarhet: cache kobles til versjon (via sha256 + build-signature)

Dette er ment som en «trygg A»: minimal påvirkning på eksisterende flyt.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import pandas as pd


SCHEMA_VERSION = 1
DATA_TABLE = "transactions"
META_TABLE = "_utvalg_meta"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_signature(
    *,
    mapping: Dict[str, str],
    sheet_name: Optional[str],
    header_row: int,
) -> str:
    """Lager en stabil hash basert på bygg-parameterne.

    Hvis mapping/header_row/ark endrer seg, skal vi ikke treffe gammel cache.
    """

    payload = {
        "mapping": dict(sorted(mapping.items())),
        "sheet_name": sheet_name or "",
        "header_row": int(header_row),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def make_cache_filename(*, source_sha256: str, signature: str) -> str:
    """Kort filnavn (Windows-vennlig) men fortsatt kollisjonssikkert i praksis."""

    sha_part = (source_sha256 or "")[:32]
    sig_part = (signature or "")[:32]
    if not sha_part:
        sha_part = "unknown"
    if not sig_part:
        sig_part = "unknown"
    return f"{sha_part}__{sig_part}.sqlite"


@dataclass(frozen=True)
class CacheMeta:
    schema_version: int
    built_at: str
    source_sha256: str
    signature: str
    rows: int
    cols: int
    datetime_cols: Tuple[str, ...]

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CacheMeta":
        return CacheMeta(
            schema_version=int(d.get("schema_version", SCHEMA_VERSION)),
            built_at=str(d.get("built_at", "")),
            source_sha256=str(d.get("source_sha256", "")),
            signature=str(d.get("signature", "")),
            rows=int(d.get("rows", 0)),
            cols=int(d.get("cols", 0)),
            datetime_cols=tuple(d.get("datetime_cols", ())) or tuple(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "built_at": self.built_at,
            "source_sha256": self.source_sha256,
            "signature": self.signature,
            "rows": self.rows,
            "cols": self.cols,
            "datetime_cols": list(self.datetime_cols),
        }


def _detect_datetime_cols(df: pd.DataFrame) -> Tuple[str, ...]:
    cols: list[str] = []
    for c in df.columns:
        try:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                cols.append(str(c))
        except Exception:
            continue
    return tuple(cols)


def _prepare_df_for_sqlite(df: pd.DataFrame) -> Tuple[pd.DataFrame, Tuple[str, ...]]:
    """Konverterer datetyper som sqlite/pandas->sql har dårlig støtte for."""

    # SQLite er case-insensitiv på kolonnenavn. Derfor kan vi ikke ha både
    # "Konto" og "konto" som separate kolonner.
    # build_from_file lager ofte lowercase-aliaser; vi dropper duplikater her
    # (beholder første forekomst), og re-genererer aliaser ved load.
    seen_lower: set[str] = set()
    keep_cols: list[str] = []
    for c in df.columns:
        cl = str(c).lower()
        if cl in seen_lower:
            continue
        seen_lower.add(cl)
        keep_cols.append(c)

    out = df.loc[:, keep_cols].copy()
    datetime_cols = _detect_datetime_cols(out)
    for c in datetime_cols:
        # ISO dato/tid (UTC-naiv). Vi parser tilbake med pd.to_datetime.
        out[c] = pd.to_datetime(out[c], errors="coerce").dt.strftime("%Y-%m-%d")
    return out, datetime_cols


def fill_down_bilag_inplace(df: pd.DataFrame) -> int:
    """Fyll ned bilagsnummer (Bilag/bilag) der eksporten kun har verdi på første linje.

    Mange hovedbok-/SAF-T-eksporter lar bilagsnummer stå på første linje i en bilagsbunt og
    lar påfølgende linjer være tomme. Det gjør at analyser som grupperer per konto og bilag
    kan få 0 bilag på kontoer der bilagsnummeret aldri står på selve kontolinjen.

    Denne funksjonen forward-filler Bilag slik at alle linjer i bunten får samme bilagsnummer.

    Returnerer antall verdier som ble fylt (NA -> ikke-NA).
    """

    # Foretrekk canonical, men støtt også lowercase.
    col = None
    if "Bilag" in df.columns:
        col = "Bilag"
    elif "bilag" in df.columns:
        col = "bilag"
    else:
        return 0

    s = df[col]

    # Tom streng -> NA (vanlig ved CSV/XLSX). Gjør dette uten å tvinge dtype.
    if s.dtype == object or pd.api.types.is_string_dtype(s):
        try:
            s = s.replace("", pd.NA)
        except Exception:
            pass

    missing_before = int(s.isna().sum())
    if missing_before == 0:
        # Hold alias i sync selv om vi ikke fylte noe.
        if col == "Bilag" and "bilag" in df.columns:
            df["bilag"] = df["Bilag"]
        elif col == "bilag" and "Bilag" in df.columns:
            df["Bilag"] = df["bilag"]
        return 0

    if int(s.notna().sum()) == 0:
        return 0

    df[col] = s.ffill()

    # Sync canonical/lowercase alias
    if col == "Bilag" and "bilag" in df.columns:
        df["bilag"] = df["Bilag"]
    elif col == "bilag" and "Bilag" in df.columns:
        df["Bilag"] = df["bilag"]

    missing_after = int(df[col].isna().sum())
    filled = missing_before - missing_after
    return int(filled) if filled > 0 else 0


def _restore_df_from_sqlite(df: pd.DataFrame, meta: CacheMeta) -> pd.DataFrame:
    out = df
    for c in meta.datetime_cols:
        if c in out.columns:
            out[c] = pd.to_datetime(out[c], errors="coerce")

    # Re-generer lowercase aliaser (for kompatibilitet med eldre kode).
    # Dette gir f.eks både "Konto" og "konto".
    try:
        cols = list(out.columns)
        existing = set(cols)
        for c in cols:
            lc = str(c).lower()
            if lc not in existing:
                out[lc] = out[c]
                existing.add(lc)
    except Exception:
        pass

    # Fyll ned bilagsnummer hvis eksporten bare har bilag på første linje.
    fill_down_bilag_inplace(out)

    return out


def save_cache(df: pd.DataFrame, db_path: Path, *, source_sha256: str, signature: str) -> CacheMeta:
    """Skriver cache til sqlite (atomisk)."""

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = db_path.with_suffix(db_path.suffix + ".building")
    if tmp_path.exists():
        try:
            tmp_path.unlink()
        except Exception:
            # best effort
            pass

    df_to_write, datetime_cols = _prepare_df_for_sqlite(df)
    meta = CacheMeta(
        schema_version=SCHEMA_VERSION,
        built_at=_utc_now_iso(),
        source_sha256=source_sha256,
        signature=signature,
        rows=int(df.shape[0]),
        cols=int(df.shape[1]),
        datetime_cols=datetime_cols,
    )

    con = sqlite3.connect(tmp_path)
    try:
        cur = con.cursor()
        # Litt raskere innsetting for store DF-er.
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA temp_store=MEMORY;")

        df_to_write.to_sql(DATA_TABLE, con, if_exists="replace", index=False, chunksize=50_000)

        cur.execute(f"DROP TABLE IF EXISTS {META_TABLE};")
        cur.execute(
            f"CREATE TABLE {META_TABLE} (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        )
        for k, v in meta.to_dict().items():
            cur.execute(
                f"INSERT OR REPLACE INTO {META_TABLE} (key, value) VALUES (?, ?)",
                (str(k), json.dumps(v, ensure_ascii=False)),
            )
        con.commit()
    finally:
        con.close()

    # Atomisk replace
    tmp_path.replace(db_path)
    return meta


def load_cache(db_path: Path) -> Tuple[pd.DataFrame, CacheMeta]:
    """Laster DF + meta fra sqlite-cache."""

    db_path = Path(db_path)
    con = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(f"SELECT * FROM {DATA_TABLE}", con)
        cur = con.cursor()
        cur.execute(f"SELECT key, value FROM {META_TABLE}")
        meta_raw: Dict[str, Any] = {}
        for k, v in cur.fetchall():
            try:
                meta_raw[str(k)] = json.loads(v)
            except Exception:
                meta_raw[str(k)] = v
        meta = CacheMeta.from_dict(meta_raw)
    finally:
        con.close()

    df = _restore_df_from_sqlite(df, meta)
    return df, meta

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

import client_store
import saft_reader
from dataset_build_fast import build_from_file
from models import Columns

logger = logging.getLogger(__name__)


def is_saft_path(path: str | Path) -> bool:
    p = Path(path)
    return p.suffix.lower() in {".zip", ".xml"}


@dataclass(frozen=True)
class BuildRequest:
    path: Path
    mapping: Dict[str, str]
    sheet_name: Optional[str]
    header_row: int
    store_client: Optional[str] = None
    store_year: Optional[str] = None
    store_version_id: Optional[str] = None
    store_dtype: str = "hb"


@dataclass(frozen=True)
class BuildResult:
    df: pd.DataFrame
    cols: Columns
    stored_path: Optional[str] = None
    stored_version_id: Optional[str] = None
    stored_was_duplicate: bool = False
    loaded_from_cache: bool = False
    cache_path: Optional[str] = None


def _auto_detect_saft_system(client: str, saft_path: Path) -> None:
    """Auto-detect regnskapssystem og MVA-mapping fra SAF-T header.

    Kjøres bare for SAF-T-filer, og bare hvis klienten ikke allerede
    har et regnskapssystem satt.
    """
    try:
        import regnskap_client_overrides

        existing_system = regnskap_client_overrides.load_accounting_system(client)
        if existing_system:
            return

        header = saft_reader.read_saft_header(saft_path)
        detected = saft_reader.detect_accounting_system(header)
        if not detected:
            return

        regnskap_client_overrides.save_accounting_system(client, detected)
        logger.info("Auto-detected accounting system '%s' for client '%s'", detected, client)

        # Auto-sett MVA-mapping hvis klienten ikke har en fra før
        existing_mva = regnskap_client_overrides.load_mva_code_mapping(client)
        if not existing_mva:
            import mva_system_defaults

            default_mapping = mva_system_defaults.get_default_mapping(detected)
            if default_mapping:
                regnskap_client_overrides.save_mva_code_mapping(client, default_mapping)
                logger.info("Auto-applied MVA mapping for system '%s', client '%s'", detected, client)
    except Exception:
        logger.exception("Auto-detect accounting system failed")


def build_dataset(req: BuildRequest) -> BuildResult:
    """Bygger datasett (ren funksjon: ingen tkinter).

    Returnerer alltid en BuildResult med df + Columns.
    """

    stored_path = None
    stored_version_id = None
    stored_was_duplicate = False
    loaded_from_cache = False
    cache_path: Optional[str] = None

    build_path = req.path
    version_meta: Optional[Dict[str, Any]] = None
    cache_signature: Optional[str] = None

    if req.store_client and req.store_year:
        try:
            import client_store
            import dataset_cache_sqlite

            # For SAF-T-filer: inkluder saft_reader-versjon i signaturen
            # slik at nye felter i readeren invaliderer cachen automatisk.
            _extra_mapping = dict(req.mapping)
            if is_saft_path(req.path):
                try:
                    _extra_mapping["__saft_reader_version__"] = saft_reader.READER_VERSION
                except Exception:
                    pass
            cache_signature = dataset_cache_sqlite.build_signature(
                mapping=_extra_mapping,
                sheet_name=req.sheet_name,
                header_row=req.header_row,
            )

            # 1) Hvis UI allerede har valgt en lagret versjon, bruk den direkte —
            #    men bare hvis brukerens valgte filsti faktisk peker på samme versjon.
            #    Ellers har brukeren valgt en ny fil via «Velg fil…», og vi må
            #    behandle den som ny versjon (ikke gjenbruke gammel ID/cache).
            if req.store_version_id:
                v = client_store.get_version(
                    req.store_client,
                    year=req.store_year,
                    dtype=req.store_dtype,
                    version_id=req.store_version_id,
                )
                if v is not None and _paths_equal(v.path, req.path):
                    stored_version_id = v.id
                    stored_path = v.path
                    version_meta = v.meta
                    try:
                        if stored_path:
                            build_path = Path(stored_path)
                    except Exception:
                        pass

            # 2) Hvis vi ikke har versjon-id, forsøk å lagre filen som versjon (kopi, urørt).
            if not stored_version_id:
                stored_path, stored_version_id, stored_was_duplicate = _store_version_if_needed(
                    client=req.store_client,
                    year=req.store_year,
                    dtype=req.store_dtype,
                    src_path=req.path,
                )
                if stored_path:
                    build_path = Path(stored_path)
                if stored_version_id:
                    v2 = client_store.get_version(
                        req.store_client,
                        year=req.store_year,
                        dtype=req.store_dtype,
                        version_id=stored_version_id,
                    )
                    if v2 is not None:
                        version_meta = v2.meta

            # 2b) Auto-detect regnskapssystem fra SAF-T header (uavhengig av cache)
            if is_saft_path(build_path):
                _auto_detect_saft_system(req.store_client, build_path)

            # 3) Prøv å laste cached datasett fra sqlite (hvis finnes og signature matcher).
            if stored_version_id and cache_signature:
                dc = client_store.get_dataset_cache_meta(
                    req.store_client,
                    year=req.store_year,
                    dtype=req.store_dtype,
                    version_id=stored_version_id,
                )

                ds_dir = client_store.datasets_dir(req.store_client, year=req.store_year, dtype=req.store_dtype)
                db_path: Optional[Path] = None
                if isinstance(dc, dict) and dc.get("signature") == cache_signature and dc.get("file"):
                    db_path = ds_dir / str(dc.get("file"))
                else:
                    # Fallback: sjekk standard filnavn
                    src_sha = ""
                    if isinstance(version_meta, dict):
                        src_sha = str(version_meta.get("sha256") or "")
                    db_path = ds_dir / dataset_cache_sqlite.make_cache_filename(
                        source_sha256=src_sha,
                        signature=cache_signature,
                    )

                if db_path and db_path.exists():
                    df, cache_db_meta = dataset_cache_sqlite.load_cache(db_path)
                    cols = _columns_for_canonical_df(df)
                    loaded_from_cache = True
                    cache_path = str(db_path)
                    # Best effort: skriv pekeren tilbake hvis den manglet / var utdatert.
                    if (
                        not isinstance(dc, dict)
                        or dc.get("signature") != cache_signature
                        or dc.get("file") != db_path.name
                    ):
                        try:
                            client_store.set_dataset_cache_meta(
                                req.store_client,
                                year=req.store_year,
                                dtype=req.store_dtype,
                                version_id=stored_version_id,
                                dataset_cache={
                                    **cache_db_meta.to_dict(),
                                    "file": db_path.name,
                                    "build": {
                                        "sheet_name": req.sheet_name,
                                        "header_row": int(req.header_row),
                                        "mapping": dict(req.mapping),
                                    },
                                },
                            )
                        except Exception:
                            logger.exception("Updating dataset_cache meta failed")

                    return BuildResult(
                        df=df,
                        cols=cols,
                        stored_path=stored_path,
                        stored_version_id=stored_version_id,
                        stored_was_duplicate=stored_was_duplicate,
                        loaded_from_cache=True,
                        cache_path=cache_path,
                    )
        except Exception:
            # Ikke la lagring feile selve datasettbyggingen
            logger.exception("Auto-store version failed")

    # Cache miss / ingen store_client-year: bygg datasett på vanlig måte
    if is_saft_path(build_path):
        df = saft_reader.read_saft_ledger(build_path)

    else:
        df = build_from_file(
            build_path,
            mapping=req.mapping,
            sheet_name=req.sheet_name,
            header_row=req.header_row,
        )

    # Normaliser bilagsnummer: mange eksporter har bilag bare på første linje i en bilagsbunt.
    # Forward-fill gjør at alle linjer får bilagsnummer og at "Antall bilag" og motpost fungerer.
    try:
        import dataset_cache_sqlite

        dataset_cache_sqlite.fill_down_bilag_inplace(df)
    except Exception:
        logger.exception("Normalizing bilag failed")

    cols = _columns_for_canonical_df(df)

    # Etter bygg: lagre sqlite-cache hvis vi har versjon-id
    if req.store_client and req.store_year and stored_version_id:
        try:
            import client_store
            import dataset_cache_sqlite

            if not cache_signature:
                cache_signature = dataset_cache_sqlite.build_signature(
                    mapping=req.mapping,
                    sheet_name=req.sheet_name,
                    header_row=req.header_row,
                )

            if not isinstance(version_meta, dict):
                v3 = client_store.get_version(
                    req.store_client,
                    year=req.store_year,
                    dtype=req.store_dtype,
                    version_id=stored_version_id,
                )
                version_meta = v3.meta if v3 is not None else {}

            src_sha = ""
            if isinstance(version_meta, dict):
                src_sha = str(version_meta.get("sha256") or "")

            ds_dir = client_store.datasets_dir(req.store_client, year=req.store_year, dtype=req.store_dtype)
            ds_dir.mkdir(parents=True, exist_ok=True)
            filename = dataset_cache_sqlite.make_cache_filename(source_sha256=src_sha, signature=cache_signature)
            db_path = ds_dir / filename
            cache_meta = dataset_cache_sqlite.save_cache(df, db_path, source_sha256=src_sha, signature=cache_signature)

            client_store.set_dataset_cache_meta(
                req.store_client,
                year=req.store_year,
                dtype=req.store_dtype,
                version_id=stored_version_id,
                dataset_cache={
                    **cache_meta.to_dict(),
                    "file": filename,
                    "build": {
                        "sheet_name": req.sheet_name,
                        "header_row": int(req.header_row),
                        "mapping": dict(req.mapping),
                    },
                },
            )
            cache_path = str(db_path)
        except Exception:
            logger.exception("Saving dataset cache failed")

    return BuildResult(
        df=df,
        cols=cols,
        stored_path=stored_path,
        stored_version_id=stored_version_id,
        stored_was_duplicate=stored_was_duplicate,
        loaded_from_cache=loaded_from_cache,
        cache_path=cache_path,
    )


def _columns_for_canonical_df(df: pd.DataFrame) -> Columns:
    # Etter build_from_file/saft_reader skal data være kanonisk.
    return Columns(
        konto="Konto",
        kontonavn="Kontonavn" if "Kontonavn" in df.columns else None,
        bilag="Bilag",
        belop="Beløp",
        dato="Dato" if "Dato" in df.columns else None,
        tekst="Tekst" if "Tekst" in df.columns else None,
    )


def _store_version_if_needed(*, client: str, year: str, dtype: str, src_path: Path) -> Tuple[Optional[str], Optional[str], bool]:
    """Lagrer filen i klientlageret og gjør den aktiv.

    Returnerer (stored_path, version_id, was_duplicate).
    """

    clients_root = client_store.get_clients_root()
    if _is_inside_root(src_path, clients_root):
        return None, None, False

    try:
        v = client_store.create_version(client, year=year, dtype=dtype, src_path=src_path, make_active=True)
        return v.path, v.id, False
    except client_store.DuplicateContentError as e:
        client_store.set_active_version(client, year=year, dtype=dtype, version_id=e.existing_id)
        # Bygg path direkte (bruker interne helpers i repoet)
        versions_dir = client_store.versions_dir(client, year=year, dtype=dtype)
        stored_p = versions_dir / e.existing_filename
        return str(stored_p), e.existing_id, True


def _is_inside_root(p: Path, root: Path) -> bool:
    """Robust sjekk for nettverksstier / windows paths."""
    try:
        pr = p.resolve()
        rr = root.resolve()
        return str(pr).startswith(str(rr) + os.sep)
    except Exception:
        return str(p).startswith(str(root))


def _paths_equal(a: str | Path | None, b: str | Path | None) -> bool:
    """Sammenlign to filstier robust på tvers av case og separator.

    Ikke bruk resolve() på nettverksstier — det kan blokkere.
    """
    if not a or not b:
        return False
    try:
        na = os.path.normcase(os.path.normpath(str(a)))
        nb = os.path.normcase(os.path.normpath(str(b)))
        return na == nb
    except Exception:
        return str(a) == str(b)

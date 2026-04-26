"""consolidation.storage – Persistering av konsolideringsprosjekt.

Katalogstruktur under client_store:
    {clients_root}/{klient}/years/{YYYY}/consolidation/
        project.json
        companies/{company_id}.parquet
        exports/{run_id}_workbook.xlsx
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

import src.shared.client_store.store as client_store
from .models import (
    ConsolidationProject,
    project_from_dict,
    project_to_dict,
)

logger = logging.getLogger(__name__)

PROJECT_FILE = "project.json"
COMPANIES_DIR = "companies"
EXPORTS_DIR = "exports"
LINE_BASIS_SUFFIX = ".regnskapslinjer.csv"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def project_dir(client: str, year: str) -> Path:
    """Returnerer (og oppretter) konsolideringskatalogen for klient/aar."""
    base = client_store.years_dir(client, year=year)
    p = base / "consolidation"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _project_json_path(client: str, year: str) -> Path:
    return project_dir(client, year) / PROJECT_FILE


def _companies_dir(client: str, year: str) -> Path:
    d = project_dir(client, year) / COMPANIES_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _exports_dir(client: str, year: str) -> Path:
    d = project_dir(client, year) / EXPORTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Atomic JSON write (same pattern as client_store)
# ---------------------------------------------------------------------------

class _SafeEncoder(json.JSONEncoder):
    """Handle numpy types that dataclasses.asdict() does not convert."""

    def default(self, o: object) -> object:
        try:
            import numpy as np
            if isinstance(o, (np.bool_,)):
                return bool(o)
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                return float(o)
        except ImportError:
            pass
        return super().default(o)


def _write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, cls=_SafeEncoder),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Project save / load
# ---------------------------------------------------------------------------

def save_project(project: ConsolidationProject) -> Path:
    """Lagre prosjekt til project.json. Returnerer filstien."""
    project.touch()
    path = _project_json_path(project.client, project.year)
    _write_json_atomic(path, project_to_dict(project))
    logger.info("Saved consolidation project %s -> %s", project.project_id, path)
    return path


def load_project(client: str, year: str) -> Optional[ConsolidationProject]:
    """Last prosjekt fra project.json. Returnerer None hvis det ikke finnes."""
    path = _project_json_path(client, year)
    if not path.exists():
        return None
    d = _read_json(path)
    if not d:
        return None
    try:
        project = project_from_dict(d)
        if project.ensure_elimination_voucher_numbers():
            save_project(project)
        return project
    except Exception:
        logger.exception("Failed to load consolidation project from %s", path)
        return None


def delete_project(client: str, year: str) -> bool:
    """Slett hele konsolideringskatalogen for klient/aar."""
    pj = _project_json_path(client, year)
    if not pj.exists():
        return False
    import shutil
    shutil.rmtree(pj.parent, ignore_errors=True)
    return True


# ---------------------------------------------------------------------------
# Company TB (parquet)
# ---------------------------------------------------------------------------

def save_company_tb(client: str, year: str, company_id: str, df: pd.DataFrame) -> Path:
    """Lagre normalisert TB som CSV."""
    path = _companies_dir(client, year) / f"{company_id}.csv"
    df.to_csv(path, index=False, encoding="utf-8")
    logger.info("Saved company TB %s (%d rows) -> %s", company_id, len(df), path)
    return path


def load_company_tb(client: str, year: str, company_id: str) -> Optional[pd.DataFrame]:
    """Last TB-CSV for et selskap. Returnerer None hvis filen mangler."""
    path = _companies_dir(client, year) / f"{company_id}.csv"
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, encoding="utf-8", dtype={"konto": str})
    except Exception:
        logger.exception("Failed to load company TB from %s", path)
        return None


def delete_company_tb(client: str, year: str, company_id: str) -> bool:
    """Slett TB-fil for et selskap."""
    path = _companies_dir(client, year) / f"{company_id}.csv"
    if path.exists():
        path.unlink()
        return True
    return False


def _company_line_basis_path(client: str, year: str, company_id: str) -> Path:
    return _companies_dir(client, year) / f"{company_id}{LINE_BASIS_SUFFIX}"


def save_company_line_basis(client: str, year: str, company_id: str, df: pd.DataFrame) -> Path:
    """Lagre regnskapslinje-grunnlag som CSV."""
    path = _company_line_basis_path(client, year, company_id)
    df.to_csv(path, index=False, encoding="utf-8")
    logger.info("Saved company line basis %s (%d rows) -> %s", company_id, len(df), path)
    return path


def load_company_line_basis(client: str, year: str, company_id: str) -> Optional[pd.DataFrame]:
    """Last regnskapslinje-grunnlag for et selskap."""
    path = _company_line_basis_path(client, year, company_id)
    if not path.exists():
        return None
    try:
        return pd.read_csv(
            path,
            encoding="utf-8",
            dtype={
                "regnr": "Int64",
                "regnskapslinje": str,
                "source_regnskapslinje": str,
                "source_text": str,
                "review_status": str,
            },
        )
    except Exception:
        logger.exception("Failed to load company line basis from %s", path)
        return None


def delete_company_line_basis(client: str, year: str, company_id: str) -> bool:
    """Slett regnskapslinje-grunnlag for et selskap."""
    path = _company_line_basis_path(client, year, company_id)
    if path.exists():
        path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

def export_path(client: str, year: str, run_id: str) -> Path:
    """Returner sti for en eksport-arbeidsbok."""
    return _exports_dir(client, year) / f"{run_id}_workbook.xlsx"

from __future__ import annotations

"""Regnskap-konfigurasjon (regnskapslinjer + kontoplan-mapping).

Vi ønsker en enkel og robust måte å lagre felles oppsett i datamappen:

  <data_dir>/config/regnskap/
    - regnskapslinjer.xlsx
    - kontoplan_mapping.xlsx
    - regnskap_config.json

Dette gjør at oppsettet følger datamappen (som ofte er en felles share),
og ikke blandes inn i repo/onefile-exe katalogen.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import app_paths


log = logging.getLogger("app")


@dataclass(frozen=True)
class RegnskapConfigStatus:
    regnskapslinjer_path: Optional[Path]
    kontoplan_mapping_path: Optional[Path]
    regnskapslinjer_meta: Dict[str, Any]
    kontoplan_mapping_meta: Dict[str, Any]


def config_dir() -> Path:
    d = app_paths.data_dir() / "config" / "regnskap"
    d.mkdir(parents=True, exist_ok=True)
    return d


def regnskapslinjer_path() -> Path:
    return config_dir() / "regnskapslinjer.xlsx"


def kontoplan_mapping_path() -> Path:
    return config_dir() / "kontoplan_mapping.xlsx"


def meta_path() -> Path:
    return config_dir() / "regnskap_config.json"


def get_status() -> RegnskapConfigStatus:
    meta = _read_meta()
    rpath = regnskapslinjer_path()
    mpath = kontoplan_mapping_path()
    return RegnskapConfigStatus(
        regnskapslinjer_path=rpath if rpath.exists() else None,
        kontoplan_mapping_path=mpath if mpath.exists() else None,
        regnskapslinjer_meta=dict(meta.get("regnskapslinjer") or {}),
        kontoplan_mapping_meta=dict(meta.get("kontoplan_mapping") or {}),
    )


def import_regnskapslinjer(src_path: str | Path) -> Path:
    """Importer regnskapslinjer.xlsx inn i datamappen (kopi)."""

    return _import_file(
        kind="regnskapslinjer",
        src_path=Path(src_path),
        dst_path=regnskapslinjer_path(),
    )


def import_kontoplan_mapping(src_path: str | Path) -> Path:
    """Importer kontoplan_mapping.xlsx inn i datamappen (kopi)."""

    return _import_file(
        kind="kontoplan_mapping",
        src_path=Path(src_path),
        dst_path=kontoplan_mapping_path(),
    )


def load_regnskapslinjer(*, sheet_name: str = "Sheet1"):
    """Les regnskapslinjer fra importert fil.

    Returnerer en pandas DataFrame.
    """

    p = regnskapslinjer_path()
    if not p.exists():
        raise FileNotFoundError("Regnskapslinjer er ikke importert (mangler regnskapslinjer.xlsx i datamappen).")

    import pandas as pd

    df = pd.read_excel(p, sheet_name=sheet_name)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    # Standardiser kolonnenavn
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_kontoplan_mapping(*, sheet_name: str = "Intervall"):
    """Les konto→regnnr intervallmapping fra importert fil."""

    p = kontoplan_mapping_path()
    if not p.exists():
        raise FileNotFoundError("Kontoplan-mapping er ikke importert (mangler kontoplan_mapping.xlsx i datamappen).")

    import pandas as pd

    df = pd.read_excel(p, sheet_name=sheet_name)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _import_file(*, kind: str, src_path: Path, dst_path: Path) -> Path:
    if not src_path.exists():
        raise FileNotFoundError(str(src_path))

    dst_path.parent.mkdir(parents=True, exist_ok=True)

    # Kopier bytes (bevar original urørt)
    data = src_path.read_bytes()
    dst_path.write_bytes(data)

    sha = hashlib.sha256(data).hexdigest()
    meta = _read_meta()
    meta[kind] = {
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filename": src_path.name,
        "sha256": sha,
        "original_path": str(src_path),
    }
    _write_meta(meta)

    log.info("Importerte %s: %s → %s", kind, src_path, dst_path)
    return dst_path


def _read_meta() -> Dict[str, Any]:
    p = meta_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_meta(meta: Dict[str, Any]) -> None:
    p = meta_path()
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)

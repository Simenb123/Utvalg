from __future__ import annotations

"""Regnskap-konfigurasjon (regnskapslinjer + kontoplan-mapping).

Aktiv mapping for regnskapslinjer og kontoplan lagres i delt ``data_dir`` slik
at teamet bruker samme sannhet. Klientspesifikke profiler og andre
overstyringer bor fortsatt andre steder i den delte datamappen.

Denne modulen er JSON-only i runtime:

  <data_dir>/config/regnskap/
    - regnskapslinjer.json
    - kontoplan_mapping.json
    - regnskap_config.json

Excel brukes ikke som aktiv kilde eller fallback.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import app_paths


log = logging.getLogger("app")


ACTIVE_SOURCE_JSON = "json"
ACTIVE_SOURCE_MISSING = "missing"


@dataclass(frozen=True)
class RegnskapConfigStatus:
    regnskapslinjer_path: Optional[Path]
    kontoplan_mapping_path: Optional[Path]
    regnskapslinjer_meta: Dict[str, Any]
    kontoplan_mapping_meta: Dict[str, Any]
    regnskapslinjer_json_path: Optional[Path] = None
    kontoplan_mapping_json_path: Optional[Path] = None
    regnskapslinjer_active_source: str = ACTIVE_SOURCE_MISSING
    kontoplan_mapping_active_source: str = ACTIVE_SOURCE_MISSING


def config_dir() -> Path:
    d = Path(app_paths.data_dir()) / "config" / "regnskap"
    d.mkdir(parents=True, exist_ok=True)
    return d


def regnskapslinjer_path() -> Path:
    return config_dir() / "regnskapslinjer.json"


def kontoplan_mapping_path() -> Path:
    return config_dir() / "kontoplan_mapping.json"


def meta_path() -> Path:
    return config_dir() / "regnskap_config.json"


def regnskapslinjer_json_path() -> Path:
    return regnskapslinjer_path()


def kontoplan_mapping_json_path() -> Path:
    return kontoplan_mapping_path()


def legacy_shared_config_dir() -> Path:
    return config_dir()


def _effective_regnskapslinjer_json_path() -> Path | None:
    json_path = regnskapslinjer_json_path()
    if json_path.exists():
        return json_path
    return None


def _effective_kontoplan_mapping_json_path() -> Path | None:
    json_path = kontoplan_mapping_json_path()
    if json_path.exists():
        return json_path
    return None


def get_status() -> RegnskapConfigStatus:
    meta = _read_meta()
    rjson = _effective_regnskapslinjer_json_path()
    mjson = _effective_kontoplan_mapping_json_path()
    return RegnskapConfigStatus(
        regnskapslinjer_path=rjson,
        kontoplan_mapping_path=mjson,
        regnskapslinjer_meta=dict(meta.get("regnskapslinjer") or {}),
        kontoplan_mapping_meta=dict(meta.get("kontoplan_mapping") or {}),
        regnskapslinjer_json_path=rjson,
        kontoplan_mapping_json_path=mjson,
        regnskapslinjer_active_source=ACTIVE_SOURCE_JSON if rjson is not None else ACTIVE_SOURCE_MISSING,
        kontoplan_mapping_active_source=ACTIVE_SOURCE_JSON if mjson is not None else ACTIVE_SOURCE_MISSING,
    )


def _assert_local_admin_writable() -> None:
    """Beholdes for bakoverkompatibilitet; aktiv mapping lagres i delt data_dir."""
    return None


def import_regnskapslinjer(src_path: str | Path) -> Path:
    """Importer regnskapslinjer fra en JSON-fil til delt mapping-oppsett."""

    return _import_json_baseline(
        kind="regnskapslinjer",
        src_path=Path(src_path),
    )


def import_kontoplan_mapping(src_path: str | Path) -> Path:
    """Importer kontoplan-mapping fra en JSON-fil til delt mapping-oppsett."""

    return _import_json_baseline(
        kind="kontoplan_mapping",
        src_path=Path(src_path),
    )


_JSON_SCHEMA_VERSION = 1


def _df_to_rows(df) -> list[Dict[str, Any]]:
    import pandas as pd

    rows: list[Dict[str, Any]] = []
    for rec in df.to_dict(orient="records"):
        clean: Dict[str, Any] = {}
        for key, value in rec.items():
            if value is None:
                clean[str(key)] = None
                continue
            try:
                if pd.isna(value):
                    clean[str(key)] = None
                    continue
            except (TypeError, ValueError):
                pass
            if hasattr(value, "item"):
                try:
                    value = value.item()
                except Exception:
                    pass
            clean[str(key)] = value
        rows.append(clean)
    return rows


def _rows_to_df(rows):
    import pandas as pd

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(list(rows))
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _write_json_file(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": _JSON_SCHEMA_VERSION, "rows": list(rows)}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _normalize_rows_payload(data: Any, *, strict: bool) -> list[Dict[str, Any]]:
    rows = data.get("rows") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        if strict:
            raise ValueError("JSON-filen m? inneholde en liste under 'rows'.")
        return []
    out: list[Dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(dict(row))
        elif strict:
            raise ValueError("Alle rader i JSON-filen m? v?re objekter.")
    return out


def _read_json_rows(path: Path) -> list[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return _normalize_rows_payload(data, strict=False)


def _load_rows_from_json_file(path: Path) -> list[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Kunne ikke lese JSON-fil: {path}") from exc
    return _normalize_rows_payload(data, strict=True)


def load_regnskapslinjer_json():
    """Les regnskapslinjer fra JSON. Returnerer pandas DataFrame."""

    p = _effective_regnskapslinjer_json_path()
    if p is None:
        raise FileNotFoundError(str(regnskapslinjer_json_path()))
    return _rows_to_df(_read_json_rows(p))


def save_regnskapslinjer_json(rows) -> Path:
    """Lagre regnskapslinjer som JSON. Aksepterer DataFrame eller liste av dicts."""

    _assert_local_admin_writable()
    if hasattr(rows, "to_dict"):
        rows = _df_to_rows(rows)
    else:
        rows = [dict(r) for r in rows]
    p = regnskapslinjer_json_path()
    _write_json_file(p, rows)
    _update_meta_entry(
        "regnskapslinjer",
        filename=p.name,
        source="shared_json",
    )
    _invalidate_config_caches()
    return p


def load_kontoplan_mapping_json():
    """Les kontoplan-mapping fra JSON. Returnerer pandas DataFrame."""

    p = _effective_kontoplan_mapping_json_path()
    if p is None:
        raise FileNotFoundError(str(kontoplan_mapping_json_path()))
    return _rows_to_df(_read_json_rows(p))


def save_kontoplan_mapping_json(rows) -> Path:
    """Lagre kontoplan-mapping som JSON. Aksepterer DataFrame eller liste av dicts."""

    _assert_local_admin_writable()
    if hasattr(rows, "to_dict"):
        rows = _df_to_rows(rows)
    else:
        rows = [dict(r) for r in rows]
    p = kontoplan_mapping_json_path()
    _write_json_file(p, rows)
    _update_meta_entry(
        "kontoplan_mapping",
        filename=p.name,
        source="shared_json",
    )
    _invalidate_config_caches()
    return p


# ---------------------------------------------------------------------------
# Felles RL-baseline editor-kontrakt
# ---------------------------------------------------------------------------


@dataclass
class RLBaselineLine:
    """Én regnskapslinje i global baseline (lines-seksjonen)."""

    regnr: str
    regnskapslinje: str
    sumpost: bool
    formel: str = ""
    resultat_balanse: str = ""
    delsumnr: str = ""
    sumnr: str = ""
    sumnr2: str = ""
    sluttsumnr: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RLBaselineInterval:
    """Kontointervall som knytter fra-til konto til en regnr."""

    fra: int
    til: int
    regnr: str


@dataclass
class RLBaselineDocument:
    """Samlet felles RL-baseline (lines + intervals)."""

    lines: List[RLBaselineLine] = field(default_factory=list)
    intervals: List[RLBaselineInterval] = field(default_factory=list)


_KNOWN_LINE_FIELDS_LC = {
    "nr",
    "regnr",
    "regnnr",
    "regnskapslinje",
    "linje",
    "tekst",
    "sumpost",
    "formel",
    "resultat/balanse",
    "resultat_balanse",
    "rb",
    "delsumnr",
    "delsumlinje",
    "sumnr",
    "sumlinje",
    "sumnr2",
    "sumlinje2",
    "sluttsumnr",
    "sluttsumlinje",
}


def _lc_key_lookup(row: Dict[str, Any], *names: str) -> Any:
    lc = {str(k).strip().lower(): k for k in row}
    for n in names:
        key = lc.get(n.lower())
        if key is not None:
            return row[key]
    return None


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return ""
    except Exception:
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _int_or_none(value: Any) -> Optional[int]:
    text = _clean_cell(value)
    if not text:
        return None
    try:
        return int(float(text))
    except Exception:
        return None


def _normalize_regnr(value: Any) -> str:
    text = _clean_cell(value)
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except Exception:
        return text


def _is_truthy_sumpost(value: Any) -> bool:
    return _clean_cell(value).strip().lower() in {"ja", "yes", "true", "1"}


def _line_from_row(row: Dict[str, Any]) -> Optional[RLBaselineLine]:
    regnr = _normalize_regnr(_lc_key_lookup(row, "nr", "regnr", "regnnr"))
    if not regnr:
        return None
    line = RLBaselineLine(
        regnr=regnr,
        regnskapslinje=_clean_cell(_lc_key_lookup(row, "regnskapslinje", "linje", "tekst")),
        sumpost=_is_truthy_sumpost(_lc_key_lookup(row, "sumpost")),
        formel=_clean_cell(_lc_key_lookup(row, "formel")),
        resultat_balanse=_clean_cell(
            _lc_key_lookup(row, "resultat/balanse", "resultat_balanse", "rb")
        ),
        delsumnr=_normalize_regnr(_lc_key_lookup(row, "delsumnr")),
        sumnr=_normalize_regnr(_lc_key_lookup(row, "sumnr")),
        sumnr2=_normalize_regnr(_lc_key_lookup(row, "sumnr2")),
        sluttsumnr=_normalize_regnr(_lc_key_lookup(row, "sluttsumnr")),
    )
    extra: Dict[str, Any] = {}
    for key, value in row.items():
        lc = str(key).strip().lower()
        if lc in _KNOWN_LINE_FIELDS_LC:
            continue
        extra[str(key)] = value
    line.extra = extra
    return line


def _row_from_line(line: RLBaselineLine, lines_by_regnr: Dict[str, RLBaselineLine]) -> Dict[str, Any]:
    def _label_for(regnr: str) -> str:
        if not regnr:
            return ""
        ref = lines_by_regnr.get(regnr)
        return ref.regnskapslinje if ref else ""

    def _nr_or_none(regnr: str) -> Optional[int]:
        if not regnr:
            return None
        try:
            return int(regnr)
        except Exception:
            return None

    row: Dict[str, Any] = dict(line.extra or {})
    row["nr"] = _nr_or_none(line.regnr) or line.regnr
    row["regnskapslinje"] = line.regnskapslinje
    row["sumpost"] = "ja" if line.sumpost else "nei"
    row["Formel"] = line.formel if line.sumpost else ""
    row["resultat/balanse"] = line.resultat_balanse
    row["delsumnr"] = _nr_or_none(line.delsumnr)
    row["delsumlinje"] = _label_for(line.delsumnr)
    row["sumnr"] = _nr_or_none(line.sumnr)
    row["sumlinje"] = _label_for(line.sumnr)
    row["sumnr2"] = _nr_or_none(line.sumnr2)
    row["sumlinje2"] = _label_for(line.sumnr2)
    row["sluttsumnr"] = _nr_or_none(line.sluttsumnr)
    row["sluttsumlinje"] = _label_for(line.sluttsumnr)
    return row


def _interval_from_row(row: Dict[str, Any]) -> Optional[RLBaselineInterval]:
    fra = _int_or_none(_lc_key_lookup(row, "fra", "from"))
    til = _int_or_none(_lc_key_lookup(row, "til", "to"))
    regnr = _normalize_regnr(_lc_key_lookup(row, "regnr", "nr"))
    if fra is None or til is None or not regnr:
        return None
    return RLBaselineInterval(fra=int(fra), til=int(til), regnr=regnr)


def _row_from_interval(interval: RLBaselineInterval, lines_by_regnr: Dict[str, RLBaselineLine]) -> Dict[str, Any]:
    ref = lines_by_regnr.get(interval.regnr)
    label = ref.regnskapslinje if ref else ""
    try:
        regnr_out: Any = int(interval.regnr)
    except Exception:
        regnr_out = interval.regnr
    return {
        "fra": int(interval.fra),
        "til": int(interval.til),
        "regnr": regnr_out,
        "regnskapslinje": label,
    }


def load_rl_baseline_document() -> RLBaselineDocument:
    """Les felles RL-baseline fra delt JSON-sannhet."""

    lines: List[RLBaselineLine] = []
    intervals: List[RLBaselineInterval] = []

    rjson = _effective_regnskapslinjer_json_path()
    if rjson is not None:
        for row in _read_json_rows(rjson):
            line = _line_from_row(row)
            if line is not None:
                lines.append(line)

    mjson = _effective_kontoplan_mapping_json_path()
    if mjson is not None:
        for row in _read_json_rows(mjson):
            interval = _interval_from_row(row)
            if interval is not None:
                intervals.append(interval)

    try:
        lines.sort(key=lambda l: int(l.regnr))
    except Exception:
        lines.sort(key=lambda l: l.regnr)
    intervals.sort(key=lambda i: (i.regnr, i.fra))

    return RLBaselineDocument(lines=lines, intervals=intervals)


def save_rl_baseline_document(document: RLBaselineDocument) -> Tuple[Path, Path]:
    """Lagre felles RL-baseline til begge JSON-filene. Returnerer (lines_path, intervals_path)."""

    lines = list(document.lines)
    intervals = list(document.intervals)
    lines_by_regnr = {l.regnr: l for l in lines}

    line_rows = [_row_from_line(line, lines_by_regnr) for line in lines]
    interval_rows = [_row_from_interval(iv, lines_by_regnr) for iv in intervals]

    r_path = save_regnskapslinjer_json(line_rows)
    m_path = save_kontoplan_mapping_json(interval_rows)
    return r_path, m_path


# Module-level cache for de hyppigst-leste konfig-filene. Disse leses
# fra disk hver gang en RL-pivot bygges uten cache gir det ~250-300 ms
# overhead pr aggregering, som dominerer Analyse-refresh-tid.
_REGNSKAPSLINJER_CACHE: tuple[float, object] | None = None
_KONTOPLAN_CACHE: tuple[float, object] | None = None


def _path_mtime(path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def load_regnskapslinjer(*, sheet_name: str = "Sheet1"):
    """Les regnskapslinjer fra delt JSON-baseline."""
    _ = sheet_name
    global _REGNSKAPSLINJER_CACHE

    json_path = _effective_regnskapslinjer_json_path()
    if json_path is not None:
        mtime = _path_mtime(json_path)
        cached = _REGNSKAPSLINJER_CACHE
        if cached is not None and cached[0] == mtime:
            return cached[1].copy() if hasattr(cached[1], "copy") else cached[1]
        df = load_regnskapslinjer_json()
        _REGNSKAPSLINJER_CACHE = (mtime, df)
        return df.copy() if hasattr(df, "copy") else df

    raise FileNotFoundError(str(regnskapslinjer_json_path()))


def load_kontoplan_mapping(*, sheet_name: str = "Intervall"):
    """Les konto til regnnr-intervallmapping fra delt JSON-baseline."""
    _ = sheet_name
    global _KONTOPLAN_CACHE

    json_path = _effective_kontoplan_mapping_json_path()
    if json_path is not None:
        mtime = _path_mtime(json_path)
        cached = _KONTOPLAN_CACHE
        if cached is not None and cached[0] == mtime:
            return cached[1].copy() if hasattr(cached[1], "copy") else cached[1]
        df = load_kontoplan_mapping_json()
        _KONTOPLAN_CACHE = (mtime, df)
        return df.copy() if hasattr(df, "copy") else df

    raise FileNotFoundError(str(kontoplan_mapping_json_path()))


def _invalidate_config_caches() -> None:
    """Tving re-lesing fra disk neste gang."""
    global _REGNSKAPSLINJER_CACHE, _KONTOPLAN_CACHE
    _REGNSKAPSLINJER_CACHE = None
    _KONTOPLAN_CACHE = None


def bootstrap_local_json_from_shared(*, overwrite: bool = False) -> dict[str, Path]:
    """Beholdt for bakoverkompatibilitet; aktiv mapping er allerede delt."""

    source_dir = legacy_shared_config_dir()
    imported: dict[str, Path] = {}
    targets = {
        "regnskapslinjer": (source_dir / "regnskapslinjer.json", regnskapslinjer_json_path()),
        "kontoplan_mapping": (source_dir / "kontoplan_mapping.json", kontoplan_mapping_json_path()),
    }
    for kind, (src, dst) in targets.items():
        try:
            same_path = src.resolve() == dst.resolve()
        except Exception:
            same_path = False
        if same_path:
            continue
        if not src.exists():
            continue
        if dst.exists() and not overwrite:
            continue
        imported[kind] = _import_json_baseline(kind=kind, src_path=src)
    return imported


def _import_json_baseline(*, kind: str, src_path: Path) -> Path:
    if not src_path.exists():
        raise FileNotFoundError(str(src_path))

    if kind == "regnskapslinjer":
        dst_path = regnskapslinjer_json_path()
        writer = save_regnskapslinjer_json
    elif kind == "kontoplan_mapping":
        dst_path = kontoplan_mapping_json_path()
        writer = save_kontoplan_mapping_json
    else:
        raise ValueError(f"Ukjent kind: {kind}")

    prior_bytes = dst_path.read_bytes() if dst_path.exists() else None
    prior_meta = _read_meta()
    rows = _load_rows_from_json_file(src_path)

    try:
        result = writer(rows)
        _update_meta_entry(
            kind,
            filename=src_path.name,
            source="json_import",
            original_path=str(src_path),
            sha256=hashlib.sha256(src_path.read_bytes()).hexdigest(),
            imported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        return result
    except Exception:
        if prior_bytes is None:
            try:
                dst_path.unlink()
            except FileNotFoundError:
                pass
        else:
            dst_path.write_bytes(prior_bytes)
        _write_meta(prior_meta)
        _invalidate_config_caches()
        raise


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


def _update_meta_entry(kind: str, **updates: Any) -> None:
    meta = _read_meta()
    entry = dict(meta.get(kind) or {})
    entry.update({k: v for k, v in updates.items() if v not in (None, "")})
    entry.setdefault("updated_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    meta[kind] = entry
    _write_meta(meta)

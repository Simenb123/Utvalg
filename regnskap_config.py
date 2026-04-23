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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import app_paths


log = logging.getLogger("app")


ACTIVE_SOURCE_JSON = "json"
ACTIVE_SOURCE_EXCEL = "excel"
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
    d = app_paths.data_dir() / "config" / "regnskap"
    d.mkdir(parents=True, exist_ok=True)
    return d


def regnskapslinjer_path() -> Path:
    return config_dir() / "regnskapslinjer.xlsx"


def kontoplan_mapping_path() -> Path:
    return config_dir() / "kontoplan_mapping.xlsx"


def meta_path() -> Path:
    return config_dir() / "regnskap_config.json"


def regnskapslinjer_json_path() -> Path:
    return config_dir() / "regnskapslinjer.json"


def kontoplan_mapping_json_path() -> Path:
    return config_dir() / "kontoplan_mapping.json"


def _active_source(json_path: Path, excel_path: Path) -> str:
    if json_path.exists():
        return ACTIVE_SOURCE_JSON
    if excel_path.exists():
        return ACTIVE_SOURCE_EXCEL
    return ACTIVE_SOURCE_MISSING


def get_status() -> RegnskapConfigStatus:
    meta = _read_meta()
    rpath = regnskapslinjer_path()
    mpath = kontoplan_mapping_path()
    rjson = regnskapslinjer_json_path()
    mjson = kontoplan_mapping_json_path()
    return RegnskapConfigStatus(
        regnskapslinjer_path=rpath if rpath.exists() else None,
        kontoplan_mapping_path=mpath if mpath.exists() else None,
        regnskapslinjer_meta=dict(meta.get("regnskapslinjer") or {}),
        kontoplan_mapping_meta=dict(meta.get("kontoplan_mapping") or {}),
        regnskapslinjer_json_path=rjson if rjson.exists() else None,
        kontoplan_mapping_json_path=mjson if mjson.exists() else None,
        regnskapslinjer_active_source=_active_source(rjson, rpath),
        kontoplan_mapping_active_source=_active_source(mjson, mpath),
    )


def import_regnskapslinjer(src_path: str | Path) -> Path:
    """Importer regnskapslinjer.xlsx inn i datamappen + regenerer JSON.

    Importen er atomisk: hvis JSON-refresh feiler rulles Excel-bytes og meta
    tilbake, slik at vi ikke ender med ny Excel og gammel JSON.
    """

    return _import_with_json_refresh(
        kind="regnskapslinjer",
        src_path=Path(src_path),
    )


def import_kontoplan_mapping(src_path: str | Path) -> Path:
    """Importer kontoplan_mapping.xlsx inn i datamappen + regenerer JSON."""

    return _import_with_json_refresh(
        kind="kontoplan_mapping",
        src_path=Path(src_path),
    )


_JSON_SCHEMA_VERSION = 1


def _read_excel_regnskapslinjer(*, sheet_name: str = "Sheet1"):
    p = regnskapslinjer_path()
    if not p.exists():
        raise FileNotFoundError("Regnskapslinjer er ikke importert (mangler regnskapslinjer.xlsx i datamappen).")

    import pandas as pd

    df = pd.read_excel(p, sheet_name=sheet_name)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _read_excel_kontoplan_mapping(*, sheet_name: str = "Intervall"):
    p = kontoplan_mapping_path()
    if not p.exists():
        raise FileNotFoundError("Kontoplan-mapping er ikke importert (mangler kontoplan_mapping.xlsx i datamappen).")

    import pandas as pd

    df = pd.read_excel(p, sheet_name=sheet_name)
    df = df.dropna(axis=0, how="all").dropna(axis=1, how="all")
    df.columns = [str(c).strip() for c in df.columns]
    return df


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


def _read_json_rows(path: Path) -> list[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    return [dict(r) for r in rows if isinstance(r, dict)]


def load_regnskapslinjer_json():
    """Les regnskapslinjer fra JSON. Returnerer pandas DataFrame."""

    p = regnskapslinjer_json_path()
    if not p.exists():
        raise FileNotFoundError(str(p))
    return _rows_to_df(_read_json_rows(p))


def save_regnskapslinjer_json(rows) -> Path:
    """Lagre regnskapslinjer som JSON. Aksepterer DataFrame eller liste av dicts."""

    if hasattr(rows, "to_dict"):
        rows = _df_to_rows(rows)
    else:
        rows = [dict(r) for r in rows]
    p = regnskapslinjer_json_path()
    _write_json_file(p, rows)
    return p


def load_kontoplan_mapping_json():
    """Les kontoplan-mapping fra JSON. Returnerer pandas DataFrame."""

    p = kontoplan_mapping_json_path()
    if not p.exists():
        raise FileNotFoundError(str(p))
    return _rows_to_df(_read_json_rows(p))


def save_kontoplan_mapping_json(rows) -> Path:
    """Lagre kontoplan-mapping som JSON. Aksepterer DataFrame eller liste av dicts."""

    if hasattr(rows, "to_dict"):
        rows = _df_to_rows(rows)
    else:
        rows = [dict(r) for r in rows]
    p = kontoplan_mapping_json_path()
    _write_json_file(p, rows)
    return p


# ---------------------------------------------------------------------------
# Global RL-baseline editor-kontrakt
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
    """Samlet global RL-baseline (lines + intervals)."""

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
    """Les global RL-baseline fra JSON (bootstrap fra Excel ved behov)."""

    ensure_json_baseline_from_excel()

    lines: List[RLBaselineLine] = []
    intervals: List[RLBaselineInterval] = []

    rjson = regnskapslinjer_json_path()
    if rjson.exists():
        for row in _read_json_rows(rjson):
            line = _line_from_row(row)
            if line is not None:
                lines.append(line)

    mjson = kontoplan_mapping_json_path()
    if mjson.exists():
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
    """Lagre global RL-baseline til begge JSON-filene. Returnerer (lines_path, intervals_path)."""

    lines = list(document.lines)
    intervals = list(document.intervals)
    lines_by_regnr = {l.regnr: l for l in lines}

    line_rows = [_row_from_line(line, lines_by_regnr) for line in lines]
    interval_rows = [_row_from_interval(iv, lines_by_regnr) for iv in intervals]

    r_path = save_regnskapslinjer_json(line_rows)
    m_path = save_kontoplan_mapping_json(interval_rows)
    return r_path, m_path


def refresh_regnskapslinjer_json_from_excel() -> Path:
    """Regenerer regnskapslinjer.json fra Excel. Kaster hvis Excel mangler/ikke kan leses."""

    df = _read_excel_regnskapslinjer()
    return save_regnskapslinjer_json(_df_to_rows(df))


def refresh_kontoplan_mapping_json_from_excel() -> Path:
    """Regenerer kontoplan_mapping.json fra Excel. Kaster hvis Excel mangler/ikke kan leses."""

    df = _read_excel_kontoplan_mapping()
    return save_kontoplan_mapping_json(_df_to_rows(df))


def refresh_json_baseline_from_excel(*, kind: str) -> Path:
    """Regenerer JSON-baseline for gitt kind fra nyimportert Excel."""

    if kind == "regnskapslinjer":
        return refresh_regnskapslinjer_json_from_excel()
    if kind == "kontoplan_mapping":
        return refresh_kontoplan_mapping_json_from_excel()
    raise ValueError(f"Ukjent kind: {kind}")


def ensure_json_baseline_from_excel() -> Tuple[bool, bool]:
    """Bootstrap JSON-baseline fra Excel hvis JSON mangler.

    Returnerer (regnskapslinjer_bootstrapet, kontoplan_bootstrapet).
    Overskriver aldri eksisterende JSON-filer.
    """

    created_r = False
    created_k = False

    rjson = regnskapslinjer_json_path()
    if not rjson.exists() and regnskapslinjer_path().exists():
        try:
            df = _read_excel_regnskapslinjer()
            save_regnskapslinjer_json(_df_to_rows(df))
            created_r = True
            log.info("Bootstrappet regnskapslinjer.json fra Excel: %s", rjson)
        except Exception:
            log.exception("Klarte ikke å bootstrappe regnskapslinjer.json fra Excel")

    kjson = kontoplan_mapping_json_path()
    if not kjson.exists() and kontoplan_mapping_path().exists():
        try:
            df = _read_excel_kontoplan_mapping()
            save_kontoplan_mapping_json(_df_to_rows(df))
            created_k = True
            log.info("Bootstrappet kontoplan_mapping.json fra Excel: %s", kjson)
        except Exception:
            log.exception("Klarte ikke å bootstrappe kontoplan_mapping.json fra Excel")

    return created_r, created_k


# Module-level cache for de hyppigst-leste konfig-filene. Disse leses
# fra disk hver gang en RL-pivot bygges — uten cache gir det ~250-300 ms
# overhead pr aggregering, som dominerer Analyse-refresh-tid (jf. bench).
# Cache invalideres når filen på disk endres (mtime sjekk).
_REGNSKAPSLINJER_CACHE: tuple[float, object] | None = None
_KONTOPLAN_CACHE: tuple[float, object] | None = None


def _path_mtime(path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def load_regnskapslinjer(*, sheet_name: str = "Sheet1"):
    """Les regnskapslinjer (JSON-first; Excel er bootstrap-kilde).

    Returnerer en pandas DataFrame. Caches i minne — invalideres når
    JSON-filen på disk endres (mtime).
    """
    global _REGNSKAPSLINJER_CACHE

    ensure_json_baseline_from_excel()

    json_path = regnskapslinjer_json_path()
    if json_path.exists():
        mtime = _path_mtime(json_path)
        cached = _REGNSKAPSLINJER_CACHE
        if cached is not None and cached[0] == mtime:
            return cached[1].copy() if hasattr(cached[1], "copy") else cached[1]
        df = load_regnskapslinjer_json()
        _REGNSKAPSLINJER_CACHE = (mtime, df)
        return df.copy() if hasattr(df, "copy") else df

    return _read_excel_regnskapslinjer(sheet_name=sheet_name)


def load_kontoplan_mapping(*, sheet_name: str = "Intervall"):
    """Les konto→regnnr intervallmapping (JSON-first; Excel er bootstrap-kilde).

    Caches i minne — invalideres når JSON-filen på disk endres (mtime).
    """
    global _KONTOPLAN_CACHE

    ensure_json_baseline_from_excel()

    json_path = kontoplan_mapping_json_path()
    if json_path.exists():
        mtime = _path_mtime(json_path)
        cached = _KONTOPLAN_CACHE
        if cached is not None and cached[0] == mtime:
            return cached[1].copy() if hasattr(cached[1], "copy") else cached[1]
        df = load_kontoplan_mapping_json()
        _KONTOPLAN_CACHE = (mtime, df)
        return df.copy() if hasattr(df, "copy") else df

    return _read_excel_kontoplan_mapping(sheet_name=sheet_name)


def _invalidate_config_caches() -> None:
    """Tving re-lesing fra disk neste gang. Brukes av tester eller etter
    eksplisitt config-import."""
    global _REGNSKAPSLINJER_CACHE, _KONTOPLAN_CACHE
    _REGNSKAPSLINJER_CACHE = None
    _KONTOPLAN_CACHE = None


def _import_with_json_refresh(*, kind: str, src_path: Path) -> Path:
    if kind == "regnskapslinjer":
        dst_path = regnskapslinjer_path()
        json_path = regnskapslinjer_json_path()
        refresh = refresh_regnskapslinjer_json_from_excel
    elif kind == "kontoplan_mapping":
        dst_path = kontoplan_mapping_path()
        json_path = kontoplan_mapping_json_path()
        refresh = refresh_kontoplan_mapping_json_from_excel
    else:
        raise ValueError(f"Ukjent kind: {kind}")

    prior_excel_bytes = dst_path.read_bytes() if dst_path.exists() else None
    prior_json_bytes = json_path.read_bytes() if json_path.exists() else None
    prior_meta = _read_meta()

    result = _import_file(kind=kind, src_path=src_path, dst_path=dst_path)

    try:
        refresh()
    except Exception as exc:
        if prior_excel_bytes is None:
            try:
                dst_path.unlink()
            except FileNotFoundError:
                pass
        else:
            dst_path.write_bytes(prior_excel_bytes)
        if prior_json_bytes is None:
            try:
                json_path.unlink()
            except FileNotFoundError:
                pass
        else:
            json_path.write_bytes(prior_json_bytes)
        _write_meta(prior_meta)
        log.exception("JSON-refresh feilet for %s — rullet tilbake import", kind)
        raise RuntimeError(
            f"Excel-import lyktes, men JSON-regenerering for {kind} feilet: {exc}. "
            "Importen ble rullet tilbake."
        ) from exc

    return result


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

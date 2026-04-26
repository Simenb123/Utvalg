"""Import og validering av regnskapslinje-grunnlag for konsolidering."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


LINE_BASIS_REQUIRED_COLS = ("regnr", "regnskapslinje", "ub")
LINE_BASIS_OPTIONAL_COLS = (
    "source_regnskapslinje",
    "source_page",
    "source_text",
    "confidence",
    "review_status",
)
LINE_BASIS_COLS = list(LINE_BASIS_REQUIRED_COLS + LINE_BASIS_OPTIONAL_COLS)


def _pick_column(df: pd.DataFrame, *names: str, optional: bool = False) -> str | None:
    cols = {str(c).strip().lower(): c for c in df.columns}
    for name in names:
        if name.lower() in cols:
            return cols[name.lower()]
    if optional:
        return None
    raise ValueError(f"Mangler kolonne {names}. Kolonner: {list(df.columns)}")


def _to_int(value: object) -> int | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        text = str(value).strip().replace(" ", "")
        if not text:
            return None
        return int(float(text))
    except Exception:
        return None


def _to_float(value: object) -> float | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, str):
            text = value.strip().replace(" ", "").replace("\u00a0", "")
            if not text:
                return None
            if "," in text and "." in text:
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", ".")
            return float(text)
        return float(value)
    except Exception:
        return None


def normalize_company_line_basis(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliser rå line-import til kanoniske kolonner."""
    if df is None or df.empty:
        raise ValueError("Regnskapslinje-importen er tom.")

    c_regnr = _pick_column(df, "regnr", "regnnr", "nr")
    c_name = _pick_column(df, "regnskapslinje", "linje", "tekst", "name")
    c_ub = _pick_column(df, "ub", "belop", "beløp", "amount", "closing_balance")
    c_source_name = _pick_column(df, "source_regnskapslinje", "kildelinje", optional=True)
    c_source_page = _pick_column(df, "source_page", "page", "side", optional=True)
    c_source_text = _pick_column(df, "source_text", "kildetekst", optional=True)
    c_confidence = _pick_column(df, "confidence", "score", optional=True)
    c_review = _pick_column(df, "review_status", "status", optional=True)

    out = pd.DataFrame()
    out["regnr"] = df[c_regnr].map(_to_int)
    out["regnskapslinje"] = (
        df[c_name].fillna("").astype(str).map(lambda v: v.strip())
    )
    out["ub"] = df[c_ub].map(_to_float)

    out["source_regnskapslinje"] = (
        df[c_source_name].fillna("").astype(str).map(lambda v: v.strip())
        if c_source_name
        else ""
    )
    out["source_page"] = df[c_source_page].map(_to_int) if c_source_page else pd.Series([pd.NA] * len(df), dtype="Int64")
    out["source_text"] = (
        df[c_source_text].fillna("").astype(str).map(lambda v: v.strip())
        if c_source_text
        else ""
    )
    out["confidence"] = df[c_confidence].map(_to_float) if c_confidence else pd.Series([pd.NA] * len(df), dtype="Float64")
    out["review_status"] = (
        df[c_review].fillna("").astype(str).map(lambda v: v.strip())
        if c_review
        else ""
    )

    out = out.dropna(axis=0, how="all").copy()
    out = out.loc[
        out["regnr"].notna() | out["regnskapslinje"].astype(str).str.strip().ne("") | out["ub"].notna()
    ].copy()
    out["regnr"] = out["regnr"].astype("Int64")
    out["source_page"] = out["source_page"].astype("Int64")
    out["confidence"] = out["confidence"].astype("Float64")
    return out.reset_index(drop=True)


def _preview_list(values: Iterable[object], *, limit: int = 5) -> str:
    items = [str(v) for v in values if str(v).strip()]
    if not items:
        return ""
    preview = ", ".join(items[:limit])
    if len(items) > limit:
        preview += f" +{len(items) - limit} til"
    return preview


def validate_company_line_basis(
    df: pd.DataFrame,
    *,
    regnskapslinjer: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Valider og kanoniser regnskapslinje-grunnlag."""
    from src.shared.regnskap.mapping import normalize_regnskapslinjer

    work = normalize_company_line_basis(df)
    if work.empty:
        raise ValueError("Regnskapslinje-importen inneholder ingen data.")
    if not work["ub"].notna().any():
        raise ValueError("Regnskapslinje-importen mangler UB-verdier.")

    regn = normalize_regnskapslinjer(regnskapslinjer)
    leaf = regn.loc[~regn["sumpost"], ["regnr", "regnskapslinje"]].copy()
    leaf["regnr"] = leaf["regnr"].astype(int)
    regnr_to_name = {int(row["regnr"]): str(row["regnskapslinje"] or "") for _, row in leaf.iterrows()}
    known_leaf_regnrs = set(regnr_to_name)
    all_regnrs = set(int(v) for v in regn["regnr"].dropna().astype(int).tolist())
    sum_regnrs = all_regnrs - known_leaf_regnrs

    missing_regnr_rows = work.loc[work["regnr"].isna()]
    if not missing_regnr_rows.empty:
        raise ValueError("Alle rader må ha gyldig regnr.")

    regnrs = work["regnr"].astype(int)
    unknown = sorted({int(v) for v in regnrs.tolist() if int(v) not in all_regnrs})
    if unknown:
        raise ValueError(f"Ukjente regnr i importen: {_preview_list(unknown)}")

    sumpost = sorted({int(v) for v in regnrs.tolist() if int(v) in sum_regnrs})
    if sumpost:
        raise ValueError(f"Sumlinjer kan ikke importeres som grunnlag: {_preview_list(sumpost)}")

    dupes = work.loc[regnrs.duplicated(keep=False), "regnr"].astype(int).tolist()
    if dupes:
        raise ValueError(f"Dupliserte regnr i importen: {_preview_list(sorted(set(dupes)))}")

    warnings: list[str] = []
    mismatches: list[str] = []
    canonical_names: list[str] = []
    source_names: list[str] = []
    for _, row in work.iterrows():
        regnr = int(row["regnr"])
        canonical = regnr_to_name.get(regnr, "")
        provided = str(row.get("regnskapslinje", "") or "").strip()
        canonical_names.append(canonical)
        if provided and provided != canonical:
            mismatches.append(f"{regnr}: {provided}")
            source_names.append(provided)
        else:
            source_names.append(str(row.get("source_regnskapslinje", "") or "").strip())
    if mismatches:
        warnings.append(
            "Regnskapslinjenavn avvek fra konsernoppsettet og ble normalisert: "
            + _preview_list(mismatches)
        )

    work["source_regnskapslinje"] = source_names
    work["regnskapslinje"] = canonical_names
    return work[LINE_BASIS_COLS].copy(), warnings


def import_company_line_basis(
    path: str | Path,
    *,
    regnskapslinjer: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Importer regnskapslinje-grunnlag fra Excel eller CSV."""
    src = Path(path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(str(src))

    suffix = src.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        raw = pd.read_excel(src)
    elif suffix == ".csv":
        raw = pd.read_csv(src, encoding="utf-8")
    else:
        raise ValueError("Regnskapslinje-import støtter bare Excel og CSV.")

    raw = raw.dropna(axis=0, how="all").dropna(axis=1, how="all")
    raw.columns = [str(c).strip() for c in raw.columns]
    return validate_company_line_basis(raw, regnskapslinjer=regnskapslinjer)


def export_line_basis_template(
    path: str | Path,
    *,
    regnskapslinjer: pd.DataFrame,
) -> str:
    """Eksporter standardmal for regnskapslinje-grunnlag."""
    from src.shared.regnskap.mapping import normalize_regnskapslinjer

    target = Path(path)
    if target.suffix.lower() != ".xlsx":
        target = target.with_suffix(".xlsx")

    regn = normalize_regnskapslinjer(regnskapslinjer)
    leaf = regn.loc[~regn["sumpost"], ["regnr", "regnskapslinje"]].copy()
    leaf["ub"] = pd.Series([pd.NA] * len(leaf), dtype="Float64")

    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        leaf.to_excel(writer, index=False, sheet_name="Regnskapslinjer")

    return str(target)

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Mapping

import pandas as pd

from .control.basis import control_gl_basis_column_for_account
from .utils import dec_round, nb_to_decimal


DEFAULT_EXCLUDED_CODES: set[str] = {"aga", "forskuddstrekk"}


def _norm_code(code: Any) -> str:
    return str(code or "").strip().lower()


def _make_exclude_set(exclude_codes: Iterable[str] | None) -> set[str]:
    if exclude_codes is None:
        return set(DEFAULT_EXCLUDED_CODES)
    return {_norm_code(c) for c in exclude_codes if _norm_code(c)}


def _basis_value(row: pd.Series, basis_col: str) -> Decimal:
    basis = str(basis_col or "").strip().upper()
    ib = nb_to_decimal(row.get("IB"))
    ub = nb_to_decimal(row.get("UB"))

    if basis in ("IB-UB", "IB_MINUS_UB"):
        return ib - ub
    if basis in ("UB-IB", "UB_MINUS_IB"):
        return ub - ib
    basis_name = _basis_column_for_account(row, fallback=basis_col)
    if basis_name == "IB":
        return ib
    if basis_name == "UB":
        return ub
    if basis_name == "Endring":
        return nb_to_decimal(row.get("Endring"))
    return nb_to_decimal(row.get(basis_col))


def _basis_column_for_account(row: pd.Series, *, fallback: object = "Endring") -> str:
    return control_gl_basis_column_for_account(
        row.get("Konto"),
        row.get("Navn"),
        requested_basis=fallback,
    )


def mapping_to_assigned_df(
    mapping: Mapping[str, str],
    gl_df: pd.DataFrame,
    basis_col: str = "UB",
    include_empty: bool = True,
    exclude_codes: Iterable[str] | None = None,
) -> pd.DataFrame:
    _ = basis_col
    exclude_set = _make_exclude_set(exclude_codes)

    rows: list[dict[str, str]] = []
    if "Konto" not in gl_df.columns:
        for konto, kode in mapping.items():
            kode_norm = _norm_code(kode)
            kode_str = "" if (not kode_norm or kode_norm in exclude_set) else str(kode).strip()
            if include_empty or kode_str:
                rows.append({"Konto": str(konto), "Navn": "", "Kode": kode_str})
        return pd.DataFrame(rows, columns=["Konto", "Navn", "Kode"])

    gl_lookup = gl_df.copy()
    gl_lookup["Konto"] = gl_lookup["Konto"].astype(str)
    gl_lookup = gl_lookup.drop_duplicates(subset=["Konto"]).set_index("Konto", drop=False)

    for konto, kode in mapping.items():
        konto_str = str(konto)
        kode_norm = _norm_code(kode)
        kode_str = "" if (not kode_norm or kode_norm in exclude_set) else str(kode).strip()
        if not include_empty and not kode_str:
            continue
        navn = ""
        if konto_str in gl_lookup.index:
            try:
                navn = str(gl_lookup.loc[konto_str].get("Navn") or "")
            except Exception:
                navn = ""
        rows.append({"Konto": konto_str, "Navn": navn, "Kode": kode_str})

    return pd.DataFrame(rows, columns=["Konto", "Navn", "Kode"])


def unmapped_accounts_df(
    gl_df: pd.DataFrame,
    mapping: Mapping[str, str],
    basis_col: str = "UB",
    exclude_codes: Iterable[str] | None = None,
) -> pd.DataFrame:
    exclude_set = _make_exclude_set(exclude_codes)
    mapped: set[str] = set()
    for konto, kode in mapping.items():
        kode_norm = _norm_code(kode)
        if not kode_norm or kode_norm in exclude_set:
            continue
        mapped.add(str(konto))

    out = gl_df.copy()
    if "Konto" not in out.columns:
        return pd.DataFrame(columns=["Konto", "Navn", "GL_Belop", "Kode"])

    out["Konto"] = out["Konto"].astype(str)
    out = out[~out["Konto"].isin(mapped)].copy()
    out["GL_Belop"] = out.apply(lambda r: dec_round(_basis_value(r, basis_col)), axis=1)
    out["Kode"] = ""
    if "Navn" not in out.columns:
        out["Navn"] = ""
    return out[["Konto", "Navn", "GL_Belop", "Kode"]]


def reconcile_a07_vs_gl(
    a07_df: pd.DataFrame,
    gl_df: pd.DataFrame,
    mapping: Mapping[str, str],
    basis_col: str = "UB",
    a07_monthly_df: pd.DataFrame | None = None,
    *,
    exclude_codes: Iterable[str] | None = None,
    tolerance_rel: float = 0.02,
    tolerance_abs: float = 100.0,
) -> pd.DataFrame:
    _ = a07_monthly_df
    exclude_set = _make_exclude_set(exclude_codes)

    a07_sums: dict[str, Decimal] = {}
    a07_names: dict[str, str] = {}
    if a07_df is not None and len(a07_df) > 0:
        for _, r in a07_df.iterrows():
            kode = str(r.get("Kode") or "").strip()
            if not kode:
                continue
            kode_norm = _norm_code(kode)
            if kode_norm in exclude_set:
                continue
            navn = str(r.get("Navn") or "").strip() or kode
            a07_names.setdefault(kode, navn)
            bel = nb_to_decimal(r.get("Belop"))
            a07_sums[kode] = a07_sums.get(kode, Decimal("0")) + bel

    if gl_df is None or "Konto" not in gl_df.columns:
        gl_lookup = pd.DataFrame()
    else:
        gl_lookup = gl_df.copy()
        gl_lookup["Konto"] = gl_lookup["Konto"].astype(str)
        gl_lookup = gl_lookup.drop_duplicates(subset=["Konto"]).set_index("Konto", drop=False)

    assigned = mapping_to_assigned_df(
        mapping=mapping,
        gl_df=gl_df,
        basis_col=basis_col,
        include_empty=False,
        exclude_codes=exclude_set,
    )

    gl_sums: dict[str, Decimal] = {}
    kontoer: dict[str, list[str]] = {}
    if assigned is not None and len(assigned) > 0:
        for _, r in assigned.iterrows():
            konto = str(r.get("Konto") or "").strip()
            kode = str(r.get("Kode") or "").strip()
            if not konto or not kode:
                continue
            kode_norm = _norm_code(kode)
            if kode_norm in exclude_set or konto not in gl_lookup.index:
                continue
            gl_row = gl_lookup.loc[konto]
            bel = dec_round(_basis_value(gl_row, basis_col))
            gl_sums[kode] = gl_sums.get(kode, Decimal("0.00")) + bel
            kontoer.setdefault(kode, []).append(konto)

    codes = sorted(
        {
            *[k for k in a07_sums.keys() if _norm_code(k) not in exclude_set],
            *[k for k in gl_sums.keys() if _norm_code(k) not in exclude_set],
        }
    )

    tol_rel_dec = Decimal(str(tolerance_rel))
    tol_abs_dec = Decimal(str(tolerance_abs))
    rows: list[dict[str, Any]] = []

    for kode in codes:
        a = dec_round(a07_sums.get(kode, Decimal("0.00")))
        g = dec_round(gl_sums.get(kode, Decimal("0.00")))
        diff = dec_round(a - g)
        kontoliste = kontoer.get(kode, [])
        limit = tol_abs_dec
        try:
            rel_limit = (abs(a) * tol_rel_dec).quantize(Decimal("0.0001"))
            if rel_limit > limit:
                limit = rel_limit
        except Exception:
            pass
        within = abs(diff) <= limit
        rows.append(
            {
                "Kode": kode,
                "Navn": a07_names.get(kode, kode),
                "A07_Belop": a,
                "GL_Belop": g,
                "Diff": diff,
                "AntallKontoer": int(len(kontoliste)),
                "Kontoer": ", ".join(kontoliste),
                "WithinTolerance": bool(within),
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "Kode",
            "Navn",
            "A07_Belop",
            "GL_Belop",
            "Diff",
            "AntallKontoer",
            "Kontoer",
            "WithinTolerance",
        ],
    )

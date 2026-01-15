from __future__ import annotations

import re
from typing import Any, Optional, Sequence, Set, Tuple

import pandas as pd

import formatting

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore


_TRAILING_DOT_ZERO_RE = re.compile(r"\.0$")


def normalize_bilag_value(value: Any) -> str:
    """Normaliser bilag til en sammenlignbar streng (fjerner bl.a. trailing .0)."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return ""
    s = _TRAILING_DOT_ZERO_RE.sub("", s)
    return s


def konto_set_from_df(df_base: Optional[pd.DataFrame], konto_col: str = "Konto") -> Set[str]:
    if df_base is None or df_base.empty or konto_col not in df_base.columns:
        return set()
    s = df_base[konto_col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    s = s.replace({"nan": "", "None": ""})
    return {x for x in s.unique().tolist() if x}


def extract_bilag_rows(df: pd.DataFrame, bilag_value: Any, bilag_col: str = "Bilag") -> pd.DataFrame:
    """Finn alle rader i df for et gitt bilag. Robust for int/float/str og leading zeros."""
    if df is None or df.empty or bilag_col not in df.columns:
        return pd.DataFrame()

    target = normalize_bilag_value(bilag_value)
    if not target:
        return pd.DataFrame()

    raw = df[bilag_col]

    # Numerisk match (håndterer bl.a. '00101' vs 101)
    target_num = pd.to_numeric(pd.Series([target]), errors="coerce").iloc[0]
    if pd.notna(target_num):
        raw_num = pd.to_numeric(raw, errors="coerce")
        mask_num = raw_num == target_num
    else:
        mask_num = pd.Series(False, index=df.index)

    # Strengmatch
    raw_str = raw.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    mask_str = raw_str == target

    mask = mask_num | mask_str
    return df.loc[mask].copy()


def annotate_scope(df_rows: pd.DataFrame, konto_set: Set[str], konto_col: str = "Konto") -> pd.DataFrame:
    """Legg på bool-kolonne 'I kontoutvalg' for å skille valgte kontoer og motposter."""
    if df_rows is None or df_rows.empty:
        return pd.DataFrame()

    out = df_rows.copy()
    if konto_col not in out.columns:
        out["I kontoutvalg"] = False
        return out

    konto_norm = out[konto_col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    out["I kontoutvalg"] = konto_norm.isin(konto_set)
    return out


def _first_existing_column(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _resolve_drilldown_inputs(
    master: Any,
    df_base: Optional[pd.DataFrame],
    df_all: Optional[pd.DataFrame],
    bilag_value: Any,
    *,
    preset_bilag: Any = None,
    bilag: Any = None,
    bilag_id: Any = None,
    selected_bilag: Any = None,
    bilag_col: str = "Bilag",
) -> Tuple[pd.DataFrame, Optional[pd.DataFrame], Any, str]:
    """Normaliser argumenter til open_bilag_drill_dialog.

    Hvorfor finnes denne?
    ---------------------
    UI-kode og eldre kallesteder har historisk sendt litt ulike signaturer.
    Dette helper-laget gjør at vi kan være robuste uten å måtte refaktorere
    alle kall samtidig.

    Støtter spesielt:
    - preset_bilag / bilag / bilag_id / selected_bilag som alias for bilag_value
    - df_base kan mangle: vi forsøker å hente fra master._df_base / master._df_filtered
    """

    # 1) Bilag-verdi: prioriter eksplisitt bilag_value, ellers alias.
    resolved_bilag = bilag_value
    if resolved_bilag is None or str(resolved_bilag).strip() == "":
        for candidate in (preset_bilag, bilag, bilag_id, selected_bilag):
            if candidate is None:
                continue
            if str(candidate).strip() == "":
                continue
            resolved_bilag = candidate
            break

    # 2) df_base: bruk eksplisitt hvis gitt, ellers prøv å hente fra master.
    resolved_base = df_base
    if not isinstance(resolved_base, pd.DataFrame):
        resolved_base = None

    if resolved_base is None:
        # SelectionStudio (GUI) har vanligvis _df_base og/eller _df_filtered.
        for attr in ("_df_base", "_df_filtered"):
            try:
                v = getattr(master, attr, None)
                if isinstance(v, pd.DataFrame):
                    resolved_base = v
                    break
            except Exception:
                continue

    if resolved_base is None:
        resolved_base = pd.DataFrame()

    # 3) df_all: hvis ikke gitt, bruk df_base.
    resolved_all = df_all if isinstance(df_all, pd.DataFrame) else None
    if resolved_all is None:
        resolved_all = resolved_base

    # 4) bilag_col: robust str.
    resolved_col = str(bilag_col or "Bilag")

    return resolved_base, resolved_all, resolved_bilag, resolved_col


def open_bilag_drill_dialog(
    master: Any,
    df_base: Optional[pd.DataFrame] = None,
    df_all: Optional[pd.DataFrame] = None,
    bilag_value: Any = None,
    # --- Backwards compatible aliases (UI / legacy call sites)
    preset_bilag: Any = None,
    bilag: Any = None,
    bilag_id: Any = None,
    selected_bilag: Any = None,
    bilag_col: str = "Bilag",
    **_ignored_kwargs: Any,
) -> None:
    """
    Åpner et enkelt drilldown-vindu for valgt bilag.
    - Bruker df_all hvis tilgjengelig (for å få med motposter)
    - Markerer rader som er i kontoutvalg (df_base)
    """
    # Normaliser input (robusthet mot ulike signaturer / UI-kall)
    df_base_res, df_all_res, bilag_res, bilag_col_res = _resolve_drilldown_inputs(
        master,
        df_base,
        df_all,
        bilag_value,
        preset_bilag=preset_bilag,
        bilag=bilag,
        bilag_id=bilag_id,
        selected_bilag=selected_bilag,
        bilag_col=bilag_col,
    )

    if tk is None or ttk is None:  # pragma: no cover
        raise RuntimeError("Tkinter er ikke tilgjengelig i dette miljøet.")

    source_df = df_all_res if isinstance(df_all_res, pd.DataFrame) and not df_all_res.empty else df_base_res
    bilag_norm = normalize_bilag_value(bilag_res)

    rows = extract_bilag_rows(source_df, bilag_norm, bilag_col=bilag_col_res)
    if rows.empty:
        messagebox.showinfo("Bilagsdrill", f"Fant ingen rader for bilag: {bilag_norm}")
        return

    konto_set = konto_set_from_df(df_base_res, konto_col="Konto")
    rows = annotate_scope(rows, konto_set, konto_col="Konto")

    # Forsøk å lage en "Motpart"-kolonne hvis vi finner en relevant kilde
    motpart_col = _first_existing_column(
        rows,
        ["Kunder", "Kunde", "Kundenavn", "Leverandør", "Leverandørnavn", "Motpart", "Navn"],
    )
    rows["Motpart"] = rows[motpart_col] if motpart_col else ""

    # Sortering (Dato hvis mulig)
    if "Dato" in rows.columns:
        try:
            _d = pd.to_datetime(rows["Dato"], errors="coerce", dayfirst=True)
            rows = (
                rows.assign(_sort_dato=_d)
                .sort_values(by=["_sort_dato"], kind="mergesort")
                .drop(columns=["_sort_dato"])
            )
        except Exception:
            pass

    # Summer
    bel = pd.to_numeric(rows.get("Beløp", 0), errors="coerce").fillna(0.0)
    sum_all = float(bel.sum())
    sum_sel = float(bel[rows["I kontoutvalg"]].sum()) if "I kontoutvalg" in rows.columns else 0.0
    sum_mot = float(bel[~rows["I kontoutvalg"]].sum()) if "I kontoutvalg" in rows.columns else 0.0

    top = tk.Toplevel(master)
    top.title(f"Bilag {bilag_norm}")
    try:
        top.geometry("1100x500")
    except Exception:
        pass

    frm = ttk.Frame(top, padding=10)
    frm.pack(fill="both", expand=True)

    hdr = ttk.Label(
        frm,
        text=(
            f"Bilag: {bilag_norm} | Rader: {formatting.format_int_no(len(rows))} | "
            f"Sum: {formatting.fmt_amount(sum_all)} | "
            f"I kontoutvalg: {formatting.fmt_amount(sum_sel)} | Motposter: {formatting.fmt_amount(sum_mot)}"
        ),
    )
    hdr.pack(anchor="w", pady=(0, 8))

    desired_cols = ["I kontoutvalg", "Dato", "Konto", "Kontonavn", "Beløp", "Tekst", "Motpart"]
    cols = [c for c in desired_cols if c in rows.columns]

    tree = ttk.Treeview(frm, columns=cols, show="headings", height=16)
    vsb = ttk.Scrollbar(frm, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)

    tree.pack(side="left", fill="both", expand=True)
    vsb.pack(side="left", fill="y")

    def col_width(c: str) -> int:
        return {
            "I kontoutvalg": 110,
            "Dato": 90,
            "Konto": 80,
            "Kontonavn": 220,
            "Beløp": 100,
            "Tekst": 350,
            "Motpart": 220,
        }.get(c, 120)

    for c in cols:
        tree.heading(c, text=c)
        anchor = "e" if c in ("Beløp",) else "w"
        tree.column(c, width=col_width(c), anchor=anchor, stretch=True)

    # Styling tags
    try:
        tree.tag_configure("scope_yes", foreground="black")
        tree.tag_configure("scope_no", foreground="#666666")
        tree.tag_configure("neg", foreground="red")
    except Exception:
        pass

    def fmt(c: str, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, float) and pd.isna(v):
            return ""
        if isinstance(v, str) and v.lower() == "nan":
            return ""
        if c == "Beløp":
            return formatting.fmt_amount(v)
        if c == "Dato":
            return formatting.fmt_date(v)
        if c == "I kontoutvalg":
            return "Ja" if bool(v) else "Nei"
        return str(v)

    for _, r in rows.iterrows():
        values = [fmt(c, r.get(c)) for c in cols]
        tags = ["scope_yes" if bool(r.get("I kontoutvalg", False)) else "scope_no"]
        try:
            b = float(pd.to_numeric(r.get("Beløp", 0), errors="coerce"))
            if b < 0:
                tags.append("neg")
        except Exception:
            pass
        tree.insert("", "end", values=values, tags=tags)

    ttk.Button(frm, text="Lukk", command=top.destroy).pack(anchor="e", pady=(8, 0))


__all__ = [
    "normalize_bilag_value",
    "konto_set_from_df",
    "extract_bilag_rows",
    "annotate_scope",
    "open_bilag_drill_dialog",
]

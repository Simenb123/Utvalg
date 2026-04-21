"""page_statistikk_compute.py — Data-beregning for Statistikk-fanen.

Utskilt fra page_statistikk.py. Inneholder rene DataFrame-funksjoner for:
- RL-range/konto-set-filter (override-bevisst via ``resolve_accounts_to_rl``)
- Konto-, månedspivot-, bilag-, MVA- og motpost-aggregering
- Små formatterings-helpere (``_fmt_amount``, ``_fmt_pct``)

Ingen tkinter-avhengighet — kan kalles fra batch-jobber, tester eller
Excel-eksport. UI-laget ([page_statistikk.py](page_statistikk.py)) og
Excel-laget ([page_statistikk_excel.py](page_statistikk_excel.py)) re-eksporterer
disse symbolene for bakoverkompatibilitet.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

_AMT_FMT = "#,##0.00;[Red]-#,##0.00"

# MVA-koder → normalsats (brukes i avstemming)
_MVA_SATS_MAP: dict[str, float] = {
    "1": 0.25, "11": 0.15, "12": 0.12, "13": 0.0,
    "3": 0.25, "31": 0.15, "32": 0.12, "33": 0.0,
}
# Kontoer for utgående MVA
_MVA_KONTO_FRA = 2700
_MVA_KONTO_TIL = 2799


# ---------------------------------------------------------------------------
# Små helpere
# ---------------------------------------------------------------------------

def _safe_float(v: object) -> float:
    try:
        f = float(v)  # type: ignore[arg-type]
        return f if f == f else 0.0
    except Exception:
        return 0.0


def _safe_int(v: object) -> int:
    try:
        return int(float(v))  # type: ignore[arg-type]
    except Exception:
        return 0


def _fmt_amount(v: object) -> str:
    try:
        f = float(v)  # type: ignore[arg-type]
        if f != f:
            return "\u2013"
        return f"{f:,.0f}".replace(",", "\u202f")
    except Exception:
        return "\u2013"


def _fmt_pct(v: object) -> str:
    try:
        f = float(v)  # type: ignore[arg-type]
        if f != f:
            return "\u2013"
        return f"{f:.1f} %"
    except Exception:
        return "\u2013"


# ---------------------------------------------------------------------------
# RL-range / konto-set
# ---------------------------------------------------------------------------

def _get_konto_ranges(page: object, regnr: int) -> list[tuple[int, int]]:
    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    if intervals is None or (hasattr(intervals, "empty") and intervals.empty):
        return []
    leaf_set: set[int] = {regnr}
    if regnskapslinjer is not None and not (hasattr(regnskapslinjer, "empty") and regnskapslinjer.empty):
        try:
            from regnskap_mapping import expand_regnskapslinje_selection, normalize_regnskapslinjer
            regn = normalize_regnskapslinjer(regnskapslinjer)
            if bool(regn.loc[regn["regnr"].astype(int) == regnr, "sumpost"].any()):
                expanded = expand_regnskapslinje_selection(
                    regnskapslinjer=regnskapslinjer, selected_regnr=[regnr]
                )
                if expanded:
                    leaf_set = set(expanded)
        except Exception as exc:
            log.warning("_get_konto_ranges: %s", exc)
    ranges: list[tuple[int, int]] = []
    try:
        for _, row in intervals.iterrows():
            if int(row["regnr"]) in leaf_set:
                ranges.append((int(row["fra"]), int(row["til"])))
    except Exception as exc:
        log.warning("_get_konto_ranges loop: %s", exc)
    return ranges


def _filter_df(df: pd.DataFrame, ranges: list[tuple[int, int]]) -> pd.DataFrame:
    if not ranges or df is None or df.empty or "Konto" not in df.columns:
        return pd.DataFrame(columns=(df.columns if df is not None else []))
    try:
        num = pd.to_numeric(df["Konto"], errors="coerce")
        mask = pd.Series(False, index=df.index)
        for fra, til in ranges:
            mask |= (num >= fra) & (num <= til)
        return df.loc[mask].copy()
    except Exception as exc:
        log.warning("_filter_df: %s", exc)
        return pd.DataFrame(columns=df.columns)


def _get_konto_set_for_regnr(
    page: object,
    regnr: int,
    ranges: list[tuple[int, int]],
    df_all: pd.DataFrame | None,
    sb_df: pd.DataFrame | None,
    sb_prev_df: pd.DataFrame | None,
) -> set[str] | None:
    """Returner konto-set som faktisk mapper til ``regnr`` etter override-bevisst mapping.

    Bruker samme tjeneste som RL-pivoten (``resolve_accounts_to_rl``), slik at
    Statistikk-fanen får samme konto-utvalg som pivot-raden for regnr. Returnerer
    ``None`` hvis mapping-context ikke er tilgjengelig (brukeren skal da falle
    tilbake til rent intervall-filter).
    """
    if not ranges:
        return set()
    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    if intervals is None or regnskapslinjer is None:
        return None

    leaf_set: set[int] = {int(regnr)}
    try:
        from regnskap_mapping import expand_regnskapslinje_selection, normalize_regnskapslinjer
        regn = normalize_regnskapslinjer(regnskapslinjer)
        if bool(regn.loc[regn["regnr"].astype(int) == int(regnr), "sumpost"].any()):
            expanded = expand_regnskapslinje_selection(
                regnskapslinjer=regnskapslinjer, selected_regnr=[int(regnr)]
            )
            if expanded:
                leaf_set = {int(x) for x in expanded}
    except Exception as exc:
        log.warning("_get_konto_set_for_regnr (leaf expand): %s", exc)

    candidates: set[str] = set()
    try:
        # Konti med bevegelser innenfor ranges
        if isinstance(df_all, pd.DataFrame) and not df_all.empty and "Konto" in df_all.columns:
            num = pd.to_numeric(df_all["Konto"], errors="coerce")
            mask = pd.Series(False, index=df_all.index)
            for fra, til in ranges:
                mask |= (num >= fra) & (num <= til)
            candidates.update(df_all.loc[mask, "Konto"].astype(str).unique())
        # SB-konti i ranges (også konti uten bevegelse)
        for sb in (sb_df, sb_prev_df):
            if isinstance(sb, pd.DataFrame) and not sb.empty and "konto" in sb.columns:
                num = pd.to_numeric(sb["konto"], errors="coerce")
                mask = pd.Series(False, index=sb.index)
                for fra, til in ranges:
                    mask |= (num >= fra) & (num <= til)
                candidates.update(sb.loc[mask, "konto"].astype(str).unique())
    except Exception as exc:
        log.warning("_get_konto_set_for_regnr (candidates): %s", exc)
        return None

    if not candidates:
        return set()

    try:
        from regnskapslinje_mapping_service import context_from_page, resolve_accounts_to_rl
        ctx = context_from_page(page)
        mapping = resolve_accounts_to_rl(sorted(candidates), context=ctx)
    except Exception as exc:
        log.warning("_get_konto_set_for_regnr (resolve): %s", exc)
        return None

    if mapping is None or mapping.empty:
        return set()

    kept = mapping[mapping["regnr"].isin(leaf_set)]
    return set(kept["konto"].astype(str).tolist())


def _sb_kontoer_in_ranges(
    sb: pd.DataFrame | None,
    ranges: list[tuple[int, int]],
) -> list[tuple[str, str, float, float]]:
    """Returnerer [(konto, kontonavn, ib, ub)] for SB-rader innenfor RL-ranges.

    Filtrerer bort rader med både IB=0 og UB=0 (helt tomme konti er ikke relevante).
    """
    if sb is None or sb.empty or "konto" not in sb.columns or not ranges:
        return []
    try:
        num = pd.to_numeric(sb["konto"], errors="coerce")
        mask = pd.Series(False, index=sb.index)
        for fra, til in ranges:
            mask |= (num >= fra) & (num <= til)
        sub = sb.loc[mask]
    except Exception:
        return []

    out: list[tuple[str, str, float, float]] = []
    for _, r in sub.iterrows():
        ib = _safe_float(r.get("ib"))
        ub = _safe_float(r.get("ub"))
        if ib == 0.0 and ub == 0.0:
            continue
        konto = str(r.get("konto") or "").strip()
        if not konto:
            continue
        kontonavn = str(r.get("kontonavn") or "").strip() if "kontonavn" in sub.columns else ""
        out.append((konto, kontonavn, ib, ub))
    return out


# ---------------------------------------------------------------------------
# Compute-funksjoner
# ---------------------------------------------------------------------------

def _compute_kontoer(
    df_rl: pd.DataFrame,
    page: object,
    *,
    ranges: list[tuple[int, int]] | None = None,
    konto_set: set[str] | None = None,
) -> tuple[pd.DataFrame, str]:
    """Returnerer (grp_df, ib_col_label) der label er 'UB fjor' eller 'IB'.

    Kontoer vises selv om de ikke har bilag i perioden, så lenge de finnes i
    saldobalansen innenfor RL-intervallet med IB≠0 eller UB≠0. Dette gir
    revisor et komplett bilde av regnskapslinjen — også konti som er urørte
    i år men hadde UB fra fjor.
    """
    empty_cols = ["Konto", "Kontonavn", "IB", "Bevegelse", "UB", "Antall"]

    # --- Tx-gruppering (eksisterende logikk) ---
    if df_rl is not None and not df_rl.empty and "Beløp" in df_rl.columns:
        df = df_rl.copy()
        df["_b"] = pd.to_numeric(df["Beløp"], errors="coerce").fillna(0)
        grp_tx = (
            df.groupby("Konto", sort=False)
            .agg(Kontonavn=("Kontonavn", "first"), Bevegelse=("_b", "sum"), Antall=("_b", "count"))
            .reset_index()
        )
        grp_tx["Konto"] = grp_tx["Konto"].astype(str)
    else:
        grp_tx = pd.DataFrame(columns=["Konto", "Kontonavn", "Bevegelse", "Antall"])

    # --- SB-maps ---
    ib_map: dict[str, float] = {}
    ub_map: dict[str, float] = {}
    sb_navn: dict[str, str] = {}
    ib_label = "IB"

    sb_prev = getattr(page, "_rl_sb_prev_df", None)
    if sb_prev is not None and not sb_prev.empty and "konto" in sb_prev.columns:
        for _, r in sb_prev.iterrows():
            k = str(r["konto"])
            ib_map[k] = _safe_float(r.get("ub"))   # fjorår UB = årets IB
        ib_label = "UB fjor"

    try:
        sb = page._get_effective_sb_df()  # type: ignore[union-attr]
    except Exception:
        sb = getattr(page, "_rl_sb_df", None)
    if sb is not None and not sb.empty and "konto" in sb.columns:
        fallback_ib = not bool(ib_map)  # sb_prev manglet — bruk sb.ib som IB
        for _, r in sb.iterrows():
            k = str(r["konto"])
            if fallback_ib:
                ib_map[k] = _safe_float(r.get("ib"))
            ub_map[k] = _safe_float(r.get("ub"))
            if "kontonavn" in sb.columns:
                nav = str(r.get("kontonavn") or "").strip()
                if nav:
                    sb_navn[k] = nav
        if fallback_ib:
            ib_label = "IB"

    # --- Supplér med SB-kontoer i RL-range som mangler transaksjoner ---
    if ranges:
        tx_set = set(grp_tx["Konto"].astype(str)) if not grp_tx.empty else set()
        extra_rows: list[dict] = []

        def _allowed(k: str) -> bool:
            return True if konto_set is None else (k in konto_set)

        for konto, kontonavn, _ib, _ub in _sb_kontoer_in_ranges(sb, ranges):
            if konto in tx_set or not _allowed(konto):
                continue
            extra_rows.append({
                "Konto": konto,
                "Kontonavn": kontonavn,
                "Bevegelse": 0.0,
                "Antall": 0,
            })
        # Inkluder også konti fra fjor-SB (sb_prev) som kan ha UB_fjor men ikke finnes i år
        for konto, kontonavn, _ib, _ub in _sb_kontoer_in_ranges(sb_prev, ranges):
            if konto in tx_set or not _allowed(konto) or any(r["Konto"] == konto for r in extra_rows):
                continue
            extra_rows.append({
                "Konto": konto,
                "Kontonavn": kontonavn,
                "Bevegelse": 0.0,
                "Antall": 0,
            })
        if extra_rows:
            grp_tx = pd.concat([grp_tx, pd.DataFrame(extra_rows)], ignore_index=True)

    if grp_tx.empty:
        return pd.DataFrame(columns=empty_cols), ib_label

    grp_tx["Kontonavn"] = grp_tx["Kontonavn"].fillna("").astype(str)
    # Fyll manglende Kontonavn fra SB
    missing_navn = grp_tx["Kontonavn"].str.strip() == ""
    if missing_navn.any():
        grp_tx.loc[missing_navn, "Kontonavn"] = grp_tx.loc[missing_navn, "Konto"].map(sb_navn).fillna("")

    grp_tx["IB"] = grp_tx["Konto"].astype(str).map(ib_map)
    grp_tx["UB"] = grp_tx["Konto"].astype(str).map(ub_map)
    grp_tx["Antall"] = pd.to_numeric(grp_tx["Antall"], errors="coerce").fillna(0).astype(int)
    grp_tx = grp_tx.sort_values("Konto").reset_index(drop=True)
    return grp_tx[empty_cols], ib_label


def _compute_extra_stats(df_rl: pd.DataFrame) -> dict:
    """Beregner ekstra analytiske nøkkeltall for visning under nøkkeltall-bandet."""
    out: dict = {}
    if df_rl.empty or "Beløp" not in df_rl.columns:
        return out

    beløp = pd.to_numeric(df_rl["Beløp"], errors="coerce").fillna(0)
    total_abs = beløp.abs().sum()

    # Konsentrasjon: topp 10 bilag som % av total
    if "Bilag" in df_rl.columns and total_abs > 0:
        bilag_abs = (
            df_rl.assign(_b=beløp).groupby("Bilag")["_b"].sum().abs().nlargest(10)
        )
        out["top10_pct"] = bilag_abs.sum() / total_abs * 100
        out["n_bilag"] = df_rl["Bilag"].nunique()

    # Unike kunder
    if "Kunder" in df_rl.columns:
        out["n_kunder"] = int(df_rl["Kunder"].dropna().nunique())

    # Månedlig spredning
    if "Dato" in df_rl.columns:
        try:
            dato = pd.to_datetime(df_rl["Dato"], dayfirst=True, errors="coerce")
            mnd_sum = (
                df_rl.assign(_b=beløp, _mnd=dato.dt.to_period("M"))
                .groupby("_mnd")["_b"].sum()
            )
            if len(mnd_sum) > 1:
                out["mnd_snitt"] = float(mnd_sum.mean())
                out["mnd_std"] = float(mnd_sum.std())
                out["mnd_max_name"] = str(mnd_sum.abs().idxmax())
                out["mnd_max_val"] = float(mnd_sum[mnd_sum.abs().idxmax()])
                # Anomali: måneder der abs(avvik fra snitt) > 1.5 × std
                if out["mnd_std"] > 0:
                    avvik = (mnd_sum - out["mnd_snitt"]).abs()
                    out["n_anomali_mnd"] = int((avvik > 1.5 * out["mnd_std"]).sum())
        except Exception:
            pass

    # Runde beløp-andel (beløp delbart med 1000)
    runde = (beløp.abs() % 1000 == 0) & (beløp.abs() >= 1000)
    out["runde_pct"] = float(runde.sum() / len(beløp) * 100) if len(beløp) > 0 else 0.0

    return out


def _compute_maned_pivot(df_rl: pd.DataFrame) -> tuple[list[str], pd.DataFrame]:
    if df_rl.empty or "Beløp" not in df_rl.columns:
        return [], pd.DataFrame()
    df = df_rl.copy()
    df["_b"] = pd.to_numeric(df["Beløp"], errors="coerce").fillna(0)
    if "Dato" in df.columns:
        try:
            df["_mnd"] = pd.to_datetime(df["Dato"], dayfirst=True, errors="coerce").dt.to_period("M").astype(str)
        except Exception:
            df["_mnd"] = "Ukjent"
    elif "Periode" in df.columns:
        df["_mnd"] = df["Periode"].astype(str)
    else:
        df["_mnd"] = "Ukjent"
    months = sorted(df["_mnd"].dropna().unique().tolist())
    konto_navn = df.groupby("Konto")["Kontonavn"].first()
    pivot = df.pivot_table(index="Konto", columns="_mnd", values="_b", aggfunc="sum", fill_value=0.0)
    pivot = pivot.reindex(columns=months, fill_value=0.0)
    pivot["Sum"] = pivot[months].sum(axis=1)
    pivot = pivot.reset_index()
    pivot.insert(1, "Kontonavn", pivot["Konto"].astype(str).map(konto_navn).fillna(""))
    return months, pivot.sort_values("Konto")


def _compute_bilag(df_rl: pd.DataFrame) -> pd.DataFrame:
    empty = pd.DataFrame(columns=["Bilag", "Dato", "Tekst", "Sum beløp", "Antall poster", "Kontoer"])
    if df_rl.empty or "Bilag" not in df_rl.columns or "Beløp" not in df_rl.columns:
        return empty
    df = df_rl.copy()
    df["_b"] = pd.to_numeric(df["Beløp"], errors="coerce").fillna(0)
    if "Dato" in df.columns:
        try:
            df["_dato"] = pd.to_datetime(df["Dato"], dayfirst=True, errors="coerce").dt.strftime("%d.%m.%Y")
        except Exception:
            df["_dato"] = df["Dato"].astype(str)
    else:
        df["_dato"] = ""
    tekst_col = "Tekst" if "Tekst" in df.columns else "_dato"

    def _ktoer(s: pd.Series) -> str:
        u = sorted(s.dropna().astype(str).unique())
        return ", ".join(u[:5]) + (" …" if len(u) > 5 else "")

    grp = df.groupby("Bilag", sort=False).agg(
        Dato=("_dato", "first"),
        Tekst=(tekst_col, "first"),
        SumBeløp=("_b", "sum"),
        Antall=("_b", "count"),
        Kontoer=("Konto", _ktoer),
    ).reset_index()
    grp["_abs"] = grp["SumBeløp"].abs()
    grp = grp.sort_values("_abs", ascending=False).drop(columns=["_abs"])
    return grp.rename(columns={"SumBeløp": "Sum beløp", "Antall": "Antall poster"})


def _compute_mva(df_rl: pd.DataFrame, df_all: Optional[pd.DataFrame] = None) -> dict:
    """
    MVA-analyse med to strategier for å finne faktisk MVA-beløp:
    1. Direkte: MVA-beløp-feltet på transaksjonslinjen
    2. Motpost: konto 2700-2799 med samme bilagsnummer

    Inkluderer rader uten MVA-kode som egen gruppe.
    Returnerer dict med 'rows' (DataFrame) og avstemmingstall.
    """
    _EMPTY_ROWS = pd.DataFrame(
        columns=["MVA-kode", "Antall", "Grunnlag", "MVA-beløp", "Sats %", "Effektiv %", "Status"]
    )
    _empty = {
        "rows": _EMPTY_ROWS, "total_bevegelse": 0.0,
        "total_med_kode": 0.0, "total_uten_kode": 0.0,
        "total_mva": 0.0, "total_forventet_mva": 0.0,
    }

    if df_rl.empty or "Beløp" not in df_rl.columns:
        return _empty

    df = df_rl.copy()
    df["_b"] = pd.to_numeric(df["Beløp"], errors="coerce").fillna(0)
    df["_mva_direkt"] = (
        pd.to_numeric(df["MVA-beløp"], errors="coerce").fillna(0)
        if "MVA-beløp" in df.columns else pd.Series(0.0, index=df.index)
    )

    total_bevegelse = float(df["_b"].sum())

    if "MVA-kode" not in df.columns:
        return {**_empty, "total_bevegelse": total_bevegelse, "total_uten_kode": total_bevegelse}

    # Splitt i med/uten kode
    has_kode = df["MVA-kode"].notna() & (df["MVA-kode"].astype(str).str.strip() != "")
    df_med = df[has_kode]
    df_uten = df[~has_kode]

    total_med_kode = float(df_med["_b"].sum())
    total_uten_kode = float(df_uten["_b"].sum())

    # Motpost-oppslag for MVA-kontoer (2700-2799)
    motpost_mva: dict[str, float] = {}
    if (
        df_all is not None and not df_all.empty
        and "Bilag" in df.columns and "Bilag" in df_all.columns
        and "Konto" in df_all.columns
    ):
        try:
            konto_num_all = pd.to_numeric(df_all["Konto"], errors="coerce")
            df_mva_k = df_all.loc[
                (konto_num_all >= _MVA_KONTO_FRA) & (konto_num_all <= _MVA_KONTO_TIL)
            ].copy()
            if not df_mva_k.empty:
                df_mva_k["_b"] = pd.to_numeric(df_mva_k["Beløp"], errors="coerce").fillna(0)
                for kode in df_med["MVA-kode"].unique():
                    ks = str(kode).strip()
                    bilag_k = set(
                        df_med[df_med["MVA-kode"].astype(str).str.strip() == ks]["Bilag"]
                        .dropna().astype(str).unique()
                    )
                    if bilag_k:
                        motpost_mva[ks] = float(
                            df_mva_k.loc[df_mva_k["Bilag"].astype(str).isin(bilag_k), "_b"].sum()
                        )
        except Exception as exc:
            log.warning("_compute_mva motpost-oppslag: %s", exc)

    rows: list[dict] = []
    total_faktisk_mva = 0.0
    total_forventet_mva = 0.0

    # --- Rader med MVA-kode ---
    if not df_med.empty:
        grp = df_med.groupby("MVA-kode", sort=False).agg(
            Antall=("_b", "count"),
            Grunnlag=("_b", "sum"),
            MVADirekt=("_mva_direkt", "sum"),
        ).reset_index()

        for _, row in grp.iterrows():
            kode = str(row["MVA-kode"]).strip()
            grunnlag = float(row["Grunnlag"])
            direkt = float(row["MVADirekt"])
            motpost = motpost_mva.get(kode, 0.0)

            actual_mva = direkt if abs(direkt) > 1 else (motpost if abs(motpost) > 1 else 0.0)
            eff_sats = abs(actual_mva / grunnlag) * 100 if abs(grunnlag) > 1 else 0.0
            forventet_sats = _MVA_SATS_MAP.get(kode)
            forventet_mva_kode = abs(grunnlag) * (forventet_sats or 0.0)

            total_faktisk_mva += actual_mva
            total_forventet_mva += forventet_mva_kode

            status = ""
            if forventet_sats is not None and abs(grunnlag) > 100:
                if abs(actual_mva) < 1:
                    if forventet_mva_kode > 100:
                        status = f"\u26a0 Ingen MVA funnet (forventet {_fmt_amount(forventet_mva_kode)})"
                else:
                    avvik = (
                        abs(forventet_mva_kode - abs(actual_mva)) / forventet_mva_kode * 100
                        if forventet_mva_kode > 0 else 0.0
                    )
                    status = "\u2713 OK" if avvik < 2.0 else f"\u26a0 Avvik {avvik:.1f}%"

            rows.append({
                "MVA-kode": kode,
                "Antall": _safe_int(row["Antall"]),
                "Grunnlag": grunnlag,
                "MVA-beløp": actual_mva,
                "Sats %": (forventet_sats or 0.0) * 100,
                "Effektiv %": eff_sats,
                "Status": status,
            })

    # --- Rader uten MVA-kode ---
    if not df_uten.empty:
        rows.append({
            "MVA-kode": "\u2013 Ingen kode",
            "Antall": len(df_uten),
            "Grunnlag": float(df_uten["_b"].sum()),
            "MVA-beløp": 0.0,
            "Sats %": 0.0,
            "Effektiv %": 0.0,
            "Status": "",
        })

    result_df = pd.DataFrame(rows)
    if not result_df.empty:
        # Sorter: rader med kode øverst (etter grunnlag), "Ingen kode" sist
        med_kode_df = result_df[~result_df["MVA-kode"].str.startswith("\u2013")].sort_values("Grunnlag")
        ingen_df = result_df[result_df["MVA-kode"].str.startswith("\u2013")]
        result_df = pd.concat([med_kode_df, ingen_df], ignore_index=True)

    return {
        "rows": result_df,
        "total_bevegelse": total_bevegelse,
        "total_med_kode": total_med_kode,
        "total_uten_kode": total_uten_kode,
        "total_mva": total_faktisk_mva,
        "total_forventet_mva": total_forventet_mva,
    }


def _compute_motpost(df_all: pd.DataFrame, df_rl: pd.DataFrame) -> pd.DataFrame:
    empty = pd.DataFrame(columns=["Konto", "Kontonavn", "Beløp", "Andel", "AntallBilag"])
    if df_rl.empty or df_all is None or df_all.empty:
        return empty
    if "Bilag" not in df_rl.columns or "Bilag" not in df_all.columns:
        return empty
    rl_bilag = set(df_rl["Bilag"].dropna().astype(str).unique())
    rl_kontoer = set(df_rl["Konto"].dropna().astype(str).unique()) if "Konto" in df_rl.columns else set()
    mask = df_all["Bilag"].astype(str).isin(rl_bilag)
    df_mp = df_all.loc[mask].copy()
    if "Konto" in df_mp.columns:
        df_mp = df_mp.loc[~df_mp["Konto"].astype(str).isin(rl_kontoer)]
    if df_mp.empty:
        return empty
    df_mp = df_mp.copy()
    df_mp["_b"] = pd.to_numeric(df_mp["Beløp"], errors="coerce").fillna(0)
    grp = (
        df_mp.groupby("Konto", sort=False)
        .agg(Kontonavn=("Kontonavn", "first"), Beløp=("_b", "sum"), AntallBilag=("Bilag", "nunique"))
        .reset_index()
    )
    grp["_abs"] = grp["Beløp"].abs()
    grp = grp.sort_values("_abs", ascending=False)
    total = grp["_abs"].sum()
    grp["Andel"] = (grp["_abs"] / total * 100).round(1) if total > 0 else 0.0
    return grp[["Konto", "Kontonavn", "Beløp", "Andel", "AntallBilag"]]

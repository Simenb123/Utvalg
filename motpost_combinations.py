"""Motpost: beregning av motkonto-kombinasjoner.

Denne er skilt ut fra views_motpost_konto.py for å holde UI-fila mer oversiktlig.
Funksjonene her er "pure" (ingen Tkinter/OpenPyXL).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd

from motpost_utils import _bilag_str, _clean_name, _konto_str, _safe_float


def _first_non_empty(values: Iterable[Any]) -> str:
    """Returnerer første ikke-tomme verdi som str, ellers tom streng."""
    for v in values:
        if v is None:
            continue
        try:
            if pd.isna(v):
                continue
        except Exception:
            pass
        s = str(v).strip()
        if not s:
            continue

        # Unngå å fylle kontonavn-mapper med tekst som i praksis betyr "mangler"
        # (typisk når kildedata inneholder tekstlige "nan" i stedet for NaN).
        if s.lower() in {"nan", "none", "<na>", "nat"}:
            continue

        return s
    return ""


def build_konto_navn_map(
    df_scope: pd.DataFrame,
    *,
    konto_col: str = "Konto",
    navn_col: str = "Kontonavn",
) -> Dict[str, str]:
    """Bygg mapping {konto_str: kontonavn} fra et scope-dataframe."""
    if df_scope is None or df_scope.empty:
        return {}
    if konto_col not in df_scope.columns or navn_col not in df_scope.columns:
        return {}
    tmp = df_scope[[konto_col, navn_col]].copy()
    tmp["_konto"] = tmp[konto_col].map(_konto_str)
    # NB: behold også mapping for tom konto? vi filtrerer bort tom nøkkel
    grp = tmp.groupby("_konto")[navn_col].apply(_first_non_empty)
    m = {k: v for k, v in grp.to_dict().items() if k}
    return m


def build_motkonto_combinations(
    df_scope: pd.DataFrame,
    selected_accounts: Set[str],
    *,
    outlier_motkonto: Optional[Set[str]] = None,
    konto_navn_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """Bygg en oversikt over *motkonto*-kombinasjoner per bilag.

    Vi tar utgangspunkt i df_scope (alle linjer i bilag som inneholder valgte kontoer).
    For hvert bilag:
      - Motkonto-kombinasjon = sett av kontoer i bilaget som *ikke* er i selected_accounts
      - Sum valgte kontoer = sum(Beløp) for linjer som er i selected_accounts

    Returnerer et dataframe med:
      - Kombinasjon #
      - Kombinasjon
      - (valgfritt) Kombinasjon (navn)
      - Antall bilag
      - Sum valgte kontoer
      - % andel bilag
      - Outlier
    """

    if df_scope is None or df_scope.empty:
        return pd.DataFrame(columns=["Kombinasjon #", "Kombinasjon", "Antall bilag", "Sum valgte kontoer", "% andel bilag", "Outlier"])

    if "Bilag" not in df_scope.columns or "Konto" not in df_scope.columns or "Beløp" not in df_scope.columns:
        # Defensive: returner tomt DF med forventede kolonner
        return pd.DataFrame(columns=["Kombinasjon #", "Kombinasjon", "Antall bilag", "Sum valgte kontoer", "% andel bilag", "Outlier"])

    df = df_scope.copy()

    # normaliser nøkler
    df["_bilag"] = df["Bilag"].map(_bilag_str)
    df["_konto"] = df["Konto"].map(_konto_str)

    # beløp valgte kontoer (vektorisert)
    sel = {str(k) for k in (selected_accounts or set())}
    belop = df["Beløp"].map(_safe_float)
    df["_belop_valgt"] = belop.where(df["_konto"].isin(sel), 0.0)

    # total bilag i grunnlaget
    bilag_total = int(df["_bilag"].nunique())

    # bygg per-bilag summary
    bilag_rows: List[Tuple[str, str, float]] = []
    for bilag, g in df.groupby("_bilag", dropna=False):
        # motkontoer = alle kontoer som ikke er valgt
        motkonto_set = {k for k in g["_konto"].tolist() if k and k not in sel}
        combo = ", ".join(sorted(motkonto_set))
        sum_valgt = float(g["_belop_valgt"].sum())
        bilag_rows.append((str(bilag), combo, sum_valgt))

    if not bilag_rows:
        return pd.DataFrame(columns=["Kombinasjon #", "Kombinasjon", "Antall bilag", "Sum valgte kontoer", "% andel bilag", "Outlier"])

    df_b = pd.DataFrame(bilag_rows, columns=["_bilag", "_combo", "_sum_valgt"])

    # grupper på kombinasjon
    rows: List[Dict[str, Any]] = []
    out_set = {str(k) for k in (outlier_motkonto or set())}

    grouped = df_b.groupby("_combo", dropna=False)
    for combo, g in grouped:
        combo = str(combo or "").strip()
        cnt = int(g["_bilag"].nunique())
        sum_valgt = float(g["_sum_valgt"].sum())
        pct = round((cnt / bilag_total) * 100.0, 1) if bilag_total else 0.0

        # outlier flag hvis kombinasjonen inneholder outlier-motkonto
        outlier_flag = ""
        if out_set and combo:
            accounts = {c.strip() for c in combo.split(",") if c.strip()}
            if accounts & out_set:
                outlier_flag = "Ja"

        rows.append(
            {
                "Kombinasjon": combo or "(ingen motkonto)",
                "Antall bilag": cnt,
                "Sum valgte kontoer": sum_valgt,
                "% andel bilag": pct,
                "Outlier": outlier_flag,
            }
        )

    df_combo = pd.DataFrame(rows)

    # sortér: flest bilag først, deretter største beløp (absolutt) (det er ofte nyttig)
    if not df_combo.empty:
        df_combo["_abs_sum"] = df_combo["Sum valgte kontoer"].abs()
        df_combo = df_combo.sort_values(by=["Antall bilag", "_abs_sum"], ascending=[False, False]).drop(columns=["_abs_sum"])

    # legg til navn-kolonne hvis vi har mapping (enten sendt inn eller kan bygges fra df_scope)
    if konto_navn_map is None:
        konto_navn_map = build_konto_navn_map(df_scope)

    if konto_navn_map:
        combo_names: List[str] = []
        for combo in df_combo["Kombinasjon"].tolist():
            if not combo or combo == "(ingen motkonto)":
                combo_names.append("")
                continue
            parts = [p.strip() for p in str(combo).split(",") if p.strip()]
            pretty: List[str] = []
            for k in parts:
                name = _clean_name(konto_navn_map.get(k))
                pretty.append(f"{k} - {name}" if name else k)
            combo_names.append(", ".join(pretty))
        # Sett inn rett etter Kombinasjon
        insert_at = list(df_combo.columns).index("Kombinasjon") + 1
        df_combo.insert(insert_at, "Kombinasjon (navn)", combo_names)

    # legg på løpenummer først
    df_combo.insert(0, "Kombinasjon #", range(1, len(df_combo) + 1))

    return df_combo


def build_motkonto_combinations_per_selected_account(
    df_scope: pd.DataFrame,
    selected_accounts: Set[str],
    *,
    outlier_motkonto: Optional[Set[str]] = None,
    konto_navn_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """Bygg kombinasjoner, men fordelt per *valgt konto*.

    Dette kan være nyttig når man har valgt flere kontoer og ønsker å se hvilke
    motkonto-kombinasjoner som typisk forekommer sammen med hver enkelt valgt konto.

    Returnerer en DataFrame egnet for visning i Excel/GUI.
    """

    required = {"Bilag", "Konto", "Beløp"}
    missing = required - set(df_scope.columns)
    if missing:
        raise KeyError(f"df_scope mangler kolonner: {sorted(missing)}")

    if df_scope.empty:
        # Stabilt skjema selv om ingen rader
        cols = [
            "Valgt konto",
            "Valgt kontonavn",
            "Kombinasjon #",
            "Kombinasjon",
            "Kombinasjon (navn)",
            "Antall bilag",
            "Sum valgt konto",
            "% andel bilag",
            "Outlier",
        ]
        return pd.DataFrame(columns=cols)

    sel = {_konto_str(k) for k in selected_accounts if _konto_str(k)}
    out_set = {_konto_str(k) for k in (outlier_motkonto or set()) if _konto_str(k)}

    # Bygg konto->navn map hvis ikke gitt
    if konto_navn_map is None:
        konto_navn_map = build_konto_navn_map(df_scope)

    # Normaliser til en liten mellomtabell per (bilag, konto)
    df = df_scope.copy()
    df["_bilag"] = df["Bilag"].map(_bilag_str)
    df["_konto"] = df["Konto"].map(_konto_str)
    df["_belop"] = df["Beløp"].map(_safe_float)

    df_sums = (
        df.groupby(["_bilag", "_konto"], dropna=False)["_belop"]
        .sum()
        .reset_index()
    )

    # Motkonto-kombinasjon per bilag (alle kontoer som IKKE er i selected_accounts)
    df_mot = df_sums[(df_sums["_konto"] != "") & (~df_sums["_konto"].isin(sel))]

    def _combo_str(values: pd.Series) -> str:
        parts = sorted({str(v).strip() for v in values if str(v).strip()})
        return ", ".join(parts)

    df_combo_by_bilag = (
        df_mot.groupby("_bilag")["_konto"].apply(_combo_str).reset_index()
    )

    # Sørg for at alle bilag finnes (også de uten motkonto)
    df_all_bilag = df_sums[["_bilag"]].drop_duplicates()
    df_combo_by_bilag = df_all_bilag.merge(df_combo_by_bilag, on="_bilag", how="left")
    df_combo_by_bilag["_konto"] = df_combo_by_bilag["_konto"].fillna("")
    df_combo_by_bilag["Kombinasjon"] = df_combo_by_bilag["_konto"].replace(
        {"": "(ingen motkonto)"}
    )
    df_combo_by_bilag = df_combo_by_bilag[["_bilag", "Kombinasjon"]]

    # Filtrer til rader for valgte kontoer (per bilag)
    df_sel = df_sums[(df_sums["_konto"] != "") & (df_sums["_konto"].isin(sel))].copy()
    df_sel.rename(columns={"_konto": "Valgt konto", "_belop": "Sum valgt konto"}, inplace=True)

    # Koble på kombinasjon per bilag
    df_sel = df_sel.merge(df_combo_by_bilag, on="_bilag", how="left")
    df_sel["Kombinasjon"] = df_sel["Kombinasjon"].fillna("(ingen motkonto)")

    # Aggreger per valgt konto + kombinasjon
    grouped = (
        df_sel.groupby(["Valgt konto", "Kombinasjon"], dropna=False)
        .agg(
            **{
                "Antall bilag": ("_bilag", "nunique"),
                "Sum valgt konto": ("Sum valgt konto", "sum"),
            }
        )
        .reset_index()
    )

    # Andel bilag per valgt konto
    total_bilag_per_konto = (
        df_sel.groupby("Valgt konto")["_bilag"].nunique().to_dict()
    )

    def _pct(row) -> float:
        denom = int(total_bilag_per_konto.get(row["Valgt konto"], 0) or 0)
        if denom <= 0:
            return 0.0
        return round((float(row["Antall bilag"]) / denom) * 100.0, 1)

    grouped["% andel bilag"] = grouped.apply(_pct, axis=1)

    # Outlier-flag basert på kombinasjonen
    if out_set:
        def _is_outlier(combo: str) -> str:
            if not combo or combo == "(ingen motkonto)":
                return ""
            parts = {p.strip() for p in str(combo).split(",") if p.strip()}
            return "Ja" if (parts & out_set) else ""

        grouped["Outlier"] = grouped["Kombinasjon"].map(_is_outlier)
    else:
        grouped["Outlier"] = ""

    # Kontonavn for valgt konto
    grouped.insert(
        1,
        "Valgt kontonavn",
        grouped["Valgt konto"].map(lambda k: _clean_name(konto_navn_map.get(k))),
    )

    # Kontonavn for kombinasjon
    if konto_navn_map:
        def _combo_pretty(combo: str) -> str:
            if combo == "(ingen motkonto)":
                return ""
            parts = [p.strip() for p in str(combo).split(",") if p.strip()]
            pretty = []
            for k in parts:
                name = _clean_name(konto_navn_map.get(k))
                pretty.append(f"{k} - {name}" if name else k)
            return ", ".join(pretty)

        insert_at = list(grouped.columns).index("Kombinasjon") + 1
        grouped.insert(insert_at, "Kombinasjon (navn)", grouped["Kombinasjon"].map(_combo_pretty))
    else:
        insert_at = list(grouped.columns).index("Kombinasjon") + 1
        grouped.insert(insert_at, "Kombinasjon (navn)", "")

    # Sortering: per valgt konto, mest vanlige først
    grouped["_abs_sum"] = grouped["Sum valgt konto"].abs()
    grouped = grouped.sort_values(
        by=["Valgt konto", "Antall bilag", "_abs_sum"],
        ascending=[True, False, False],
        kind="mergesort",
    ).drop(columns=["_abs_sum"])

    # Kombinasjon # per valgt konto (1..n)
    grouped.insert(2, "Kombinasjon #", grouped.groupby("Valgt konto").cumcount() + 1)

    # Rydd kolonnerekkefølge
    cols = [
        "Valgt konto",
        "Valgt kontonavn",
        "Kombinasjon #",
        "Kombinasjon",
        "Kombinasjon (navn)",
        "Antall bilag",
        "Sum valgt konto",
        "% andel bilag",
        "Outlier",
    ]
    grouped = grouped[[c for c in cols if c in grouped.columns]]
    return grouped


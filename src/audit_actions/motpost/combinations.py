"""Motpost: beregning av motkonto-kombinasjoner.

Denne er skilt ut fra views_motpost_konto.py for å holde UI-fila mer oversiktlig.
Funksjonene her er "pure" (ingen Tkinter/OpenPyXL).

Ytelse:
- Disse funksjonene brukes både i kombinasjonsvisningen (popup) og i Excel-eksport.
- For store datasett (millioner av rader) er det kritisk å unngå Python-løkker
  per bilag/gruppe. Derfor er implementasjonene i hovedsak vektoriserte.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import pandas as pd

from .utils import _bilag_str, _clean_name, _konto_str, _safe_float


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


def build_bilag_to_motkonto_combo(
    df_scope: pd.DataFrame,
    selected_accounts: Sequence[str],
    *,
    empty_label: str = "(ingen motkonto)",
) -> dict[str, str]:
    """Returnerer mapping {bilag_str -> kombinasjon}.

    Kombinasjon = sett av *motkontoer* i bilaget (kontoer i bilaget minus
    valgte kontoer), sortert og joinet med ", ".

    Viktig: implementasjonen må være stabil/deterministisk fordi kombinasjons-
    streng brukes som nøkkel i UI/eksport.

    Parametre
    ---------
    df_scope:
        DataFrame med *alle transaksjonslinjer* for bilagene i scope.
        Forventet å inneholde kolonnene: Bilag og Konto (evt Bilag_str/Konto_str).
    selected_accounts:
        Kontoer valgt i analysen (som vi ser på motpost for).
    empty_label:
        Label brukt når bilaget ikke har noen motkontoer utover valgte kontoer.
    """

    if df_scope is None or df_scope.empty:
        return {}

    df = df_scope
    need_copy = False
    if "Bilag_str" not in df.columns:
        need_copy = True
    if "Konto_str" not in df.columns:
        need_copy = True
    if need_copy:
        df = df.copy()
        if "Bilag_str" not in df.columns:
            if "Bilag" not in df.columns:
                return {}
            df["Bilag_str"] = df["Bilag"].map(_bilag_str)
        if "Konto_str" not in df.columns:
            if "Konto" not in df.columns:
                return {}
            df["Konto_str"] = df["Konto"].map(_konto_str)

    bilag_s = df["Bilag_str"].astype(str)
    konto_s = df["Konto_str"].astype(str).str.strip()

    selected_set = {str(_konto_str(a)).strip() for a in selected_accounts if str(_konto_str(a)).strip()}

    # Bilag-orden (bevar rekkefølge fra input; blank bilagsid kan forekomme)
    bilag_order = bilag_s.drop_duplicates(keep="first")

    # Motkonto-rader: kontoer som IKKE er i selected_set
    mot = pd.DataFrame({"Bilag_str": bilag_s, "Konto_str": konto_s})
    mot = mot[(mot["Konto_str"] != "") & (~mot["Konto_str"].isin(selected_set))]

    if mot.empty:
        return {str(b): empty_label for b in bilag_order.tolist()}

    # Unike kontoer per bilag + sortert join
    mot = mot.drop_duplicates(["Bilag_str", "Konto_str"])
    mot = mot.sort_values(by=["Bilag_str", "Konto_str"], kind="mergesort")
    combo_series = mot.groupby("Bilag_str", sort=False)["Konto_str"].agg(", ".join)

    # Sørg for at alle bilag finnes i mappingen
    combo_series = combo_series.reindex(bilag_order).fillna("")
    combo_series = combo_series.astype(str)
    combo_series = combo_series.where(combo_series.str.strip() != "", other=empty_label)

    return dict(zip(bilag_order.tolist(), combo_series.tolist()))


def build_motkonto_combinations(
    df_scope: pd.DataFrame,
    selected_accounts: Set[str],
    *,
    selected_direction: str = "Alle",
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

    cols = ["Kombinasjon #", "Kombinasjon", "Antall bilag", "Sum valgte kontoer", "% andel bilag", "Outlier"]
    if df_scope is None or df_scope.empty:
        return pd.DataFrame(columns=cols)

    required = {"Bilag", "Konto", "Beløp"}
    if required - set(df_scope.columns):
        return pd.DataFrame(columns=cols)

    # Normaliser nøkler (bruk eksisterende *_str hvis de finnes)
    bilag_s = df_scope["Bilag_str"].astype(str) if "Bilag_str" in df_scope.columns else df_scope["Bilag"].map(_bilag_str)
    konto_s = df_scope["Konto_str"].astype(str) if "Konto_str" in df_scope.columns else df_scope["Konto"].map(_konto_str)

    # Beløp: prøv numerisk først (Beløp_num brukes i MotpostData)
    if "Beløp_num" in df_scope.columns and pd.api.types.is_numeric_dtype(df_scope["Beløp_num"]):
        belop = df_scope["Beløp_num"].astype(float)
    else:
        belop = df_scope["Beløp"]
        if not pd.api.types.is_numeric_dtype(belop):
            belop = belop.map(_safe_float)
        belop = belop.astype(float)

    sel = {str(_konto_str(k)) for k in (selected_accounts or set()) if str(_konto_str(k))}
    bilag_order = bilag_s.drop_duplicates(keep="first")
    bilag_total = int(len(bilag_order))

    # Direction filter brukes kun på "valgt side"
    dir_norm = (selected_direction or "Alle").strip().lower()
    if dir_norm.startswith("deb"):
        dir_mask = belop > 0
    elif dir_norm.startswith("kre") or dir_norm.startswith("cri"):
        dir_mask = belop < 0
    else:
        dir_mask = pd.Series(True, index=df_scope.index)

    sel_mask = konto_s.isin(sel) & dir_mask
    sum_valgt_by_bilag = belop.where(sel_mask, 0.0).groupby(bilag_s).sum()

    # Motkonto-kombinasjon per bilag (gjenbruk vektoriserte builder)
    bilag_to_combo = build_bilag_to_motkonto_combo(df_scope, list(sel))
    combo_for_bilag = pd.Series([bilag_to_combo.get(b, "(ingen motkonto)") for b in bilag_order.tolist()], index=bilag_order)

    df_bilag = pd.DataFrame(
        {
            "_bilag": bilag_order.tolist(),
            "Kombinasjon": combo_for_bilag.values.tolist(),
            "_sum_valgt": sum_valgt_by_bilag.reindex(bilag_order).fillna(0.0).astype(float).values,
        }
    )

    # Aggreger per kombinasjon
    df_combo = (
        df_bilag.groupby("Kombinasjon", dropna=False, sort=False)
        .agg(
            **{
                "Antall bilag": ("_bilag", "count"),
                "Sum valgte kontoer": ("_sum_valgt", "sum"),
            }
        )
        .reset_index()
    )

    df_combo["% andel bilag"] = (
        (df_combo["Antall bilag"].astype(float) / float(bilag_total) * 100.0).round(1) if bilag_total else 0.0
    )

    # Outlier-flag hvis kombinasjonen inneholder outlier-motkonto
    out_set = {str(_konto_str(k)) for k in (outlier_motkonto or set()) if str(_konto_str(k))}
    if out_set:
        def _is_outlier(combo: str) -> str:
            combo = str(combo or "").strip()
            if not combo or combo == "(ingen motkonto)":
                return ""
            parts = {c.strip() for c in combo.split(",") if c.strip()}
            return "Ja" if (parts & out_set) else ""

        df_combo["Outlier"] = df_combo["Kombinasjon"].map(_is_outlier)
    else:
        df_combo["Outlier"] = ""

    # Sortér: flest bilag først, deretter største beløp (absolutt)
    if not df_combo.empty:
        df_combo["_abs_sum"] = df_combo["Sum valgte kontoer"].abs()
        df_combo = df_combo.sort_values(by=["Antall bilag", "_abs_sum"], ascending=[False, False]).drop(columns=["_abs_sum"]).reset_index(drop=True)

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
        insert_at = list(df_combo.columns).index("Kombinasjon") + 1
        df_combo.insert(insert_at, "Kombinasjon (navn)", combo_names)

    # legg på løpenummer først
    df_combo.insert(0, "Kombinasjon #", range(1, len(df_combo) + 1))

    return df_combo


def build_motkonto_combinations_per_selected_account(
    df_scope: pd.DataFrame,
    selected_accounts: Set[str],
    *,
    selected_direction: str = "Alle",
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

    if df_scope is None or df_scope.empty:
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

    bilag_s = df_scope["Bilag_str"].astype(str) if "Bilag_str" in df_scope.columns else df_scope["Bilag"].map(_bilag_str)
    konto_s = df_scope["Konto_str"].astype(str) if "Konto_str" in df_scope.columns else df_scope["Konto"].map(_konto_str)

    if "Beløp_num" in df_scope.columns and pd.api.types.is_numeric_dtype(df_scope["Beløp_num"]):
        belop = df_scope["Beløp_num"].astype(float)
    else:
        belop = df_scope["Beløp"]
        if not pd.api.types.is_numeric_dtype(belop):
            belop = belop.map(_safe_float)
        belop = belop.astype(float)

    df = pd.DataFrame({"_bilag": bilag_s, "_konto": konto_s, "_belop": belop})

    # Retning filter for valgte kontoer (typisk: "Kredit" for 3xxx)
    dir_norm = (selected_direction or "Alle").strip().lower()
    if dir_norm.startswith("deb"):
        # Hvis vi analyserer Debet: nullstill kreditlinjer på valgte kontoer
        mask = df["_konto"].isin(sel) & (df["_belop"] <= 0)
        df.loc[mask, "_belop"] = 0.0
    elif dir_norm.startswith("kre") or dir_norm.startswith("cri"):
        # Hvis vi analyserer Kredit: nullstill debetlinjer på valgte kontoer
        mask = df["_konto"].isin(sel) & (df["_belop"] >= 0)
        df.loc[mask, "_belop"] = 0.0

    # Summer per (bilag, konto)
    df_sums = df.groupby(["_bilag", "_konto"], dropna=False)["_belop"].sum().reset_index()

    # Motkonto-kombinasjon per bilag (alle kontoer som IKKE er i selected_accounts)
    df_mot = df_sums[(df_sums["_konto"] != "") & (~df_sums["_konto"].isin(sel))].copy()

    if df_mot.empty:
        # Alle bilag har kun valgte kontoer => "(ingen motkonto)"
        df_combo_by_bilag = df_sums[["_bilag"]].drop_duplicates().assign(Kombinasjon="(ingen motkonto)")
        df_combo_by_bilag = df_combo_by_bilag[["_bilag", "Kombinasjon"]]
    else:
        # Sortér slik at join blir deterministisk (kontoer sortert)
        df_mot = df_mot.sort_values(by=["_bilag", "_konto"], kind="mergesort")
        df_mot = df_mot.drop_duplicates(["_bilag", "_konto"])

        df_combo_by_bilag = df_mot.groupby("_bilag", sort=False)["_konto"].agg(", ".join).reset_index()
        df_combo_by_bilag.rename(columns={"_konto": "Kombinasjon"}, inplace=True)

        # Sørg for at alle bilag finnes (også de uten motkonto)
        df_all_bilag = df_sums[["_bilag"]].drop_duplicates()
        df_combo_by_bilag = df_all_bilag.merge(df_combo_by_bilag, on="_bilag", how="left")
        df_combo_by_bilag["Kombinasjon"] = df_combo_by_bilag["Kombinasjon"].fillna("").replace({"": "(ingen motkonto)"})

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

    # Andel bilag per valgt konto (vektorisert)
    total_bilag_per_konto = df_sel.groupby("Valgt konto")["_bilag"].nunique()
    denom = grouped["Valgt konto"].map(total_bilag_per_konto).astype(float)
    grouped["% andel bilag"] = (grouped["Antall bilag"].astype(float) / denom * 100.0).round(1).fillna(0.0)

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
    ).drop(columns=["_abs_sum"]).reset_index(drop=True)

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

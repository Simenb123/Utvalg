from __future__ import annotations

"""Motpost: kombinasjons-workflow (status + rapportgrunnlag).

Dette modul har to formål:
1) Status per kombinasjon (forventet / outlier / umerket) – lagres i UI-state.
2) Rene pandas-funksjoner som bygger rapportgrunnlag for Excel og tester.

Design:
- "Retning" (Alle/Debet/Kredit) filtrerer kun *valgte kontoer* (analysegrunnlaget).
- "Motposter" defineres som alle øvrige linjer i de samme bilagene (komplement),
  slik at sum(valgt) + sum(mot) = bilagets totalsum (typisk 0).

Dette gjør at bilag med f.eks. MVA-kredit på andre kontoer fortsatt avstemmes.
"""

from typing import Any, Mapping, Sequence

import logging
import pandas as pd

from .combinations import build_bilag_to_motkonto_combo
from .utils import _bilag_str, _konto_str, _safe_float

logger = logging.getLogger(__name__)

STATUS_EXPECTED = "expected"
STATUS_OUTLIER = "outlier"
STATUS_NEUTRAL = ""


def apply_combo_status(status_map: dict[str, str], combo_keys: Sequence[str], status: str | None) -> None:
    """Oppdaterer status_map for én eller flere kombinasjoner.

    Brukes av UI (multiselect + hurtigtaster).

    - status_map muteres in-place (bevarer referanse)
    - status normaliseres med :func:`normalize_combo_status`
    - tom/blank kombinasjonsnøkkel ignoreres
    """
    if status_map is None:
        raise ValueError("status_map kan ikke være None")

    status_code = normalize_combo_status(status)

    for key in combo_keys:
        ck = str(key).strip()
        if not ck:
            continue
        if status_code == STATUS_NEUTRAL:
            status_map.pop(ck, None)
        else:
            status_map[ck] = status_code


def infer_konto_navn_map(df_scope: pd.DataFrame) -> dict[str, str]:
    """Best-effort bygging av konto->kontonavn-map fra df_scope.

    SAF-T/grunnlag kan ha tomme eller NaN-verdier i Kontonavn.
    Vi plukker første ikke-tomme kontonavn pr konto.
    """
    if df_scope is None or df_scope.empty:
        return {}
    if "Konto" not in df_scope.columns or "Kontonavn" not in df_scope.columns:
        return {}

    tmp = df_scope[["Konto", "Kontonavn"]].copy()
    tmp["Konto_str"] = tmp["Konto"].map(_konto_str)

    # Rens kontonavn
    tmp["_name"] = tmp["Kontonavn"].astype(object).map(lambda x: str(x).strip() if x is not None else "")
    tmp = tmp[tmp["_name"].astype(str).str.len() > 0]
    tmp = tmp[tmp["_name"].astype(str).str.lower() != "nan"]

    if tmp.empty:
        return {}

    # Første per konto
    out = tmp.groupby("Konto_str", dropna=False)["_name"].first().to_dict()
    # Normaliser keys/values
    return {str(_konto_str(k)): str(v).strip() for k, v in out.items() if str(_konto_str(k)).strip() and str(v).strip()}


def combo_display_name(
    combo: str,
    konto_navn_map: Mapping[str, str] | None,
    *,
    sep: str = "; ",
    include_numbers: bool = True,
) -> str:
    """Bygger en lesbar tekst for en kombinasjon, inkl. kontonavn.

    Eksempel: "2400, 2710" -> "2400 Leverandørgjeld; 2710 Inngående merverdiavgift"
    """
    s = str(combo or "").strip()
    if not s:
        return ""

    konto_navn_map = konto_navn_map or {}
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out_parts: list[str] = []
    for p in parts:
        key = str(_konto_str(p))
        name = str(konto_navn_map.get(key, "") or "").strip()
        if name and include_numbers:
            out_parts.append(f"{key} {name}")
        elif name:
            out_parts.append(name)
        else:
            out_parts.append(key)
    return sep.join(out_parts)


def combo_display_name_for_mode(
    combo: str,
    *,
    display_mode: str = "konto",
    konto_navn_map: Mapping[str, str] | None = None,
    konto_regnskapslinje_map: Mapping[str, str] | None = None,
) -> str:
    mode = (display_mode or "konto").strip().lower()
    if mode.startswith("regn") and konto_regnskapslinje_map:
        return combo_display_name(combo, konto_regnskapslinje_map, include_numbers=False)
    return combo_display_name(combo, konto_navn_map)


def account_display_name_for_mode(
    konto: str,
    *,
    display_mode: str = "konto",
    konto_navn_map: Mapping[str, str] | None = None,
    konto_regnskapslinje_map: Mapping[str, str] | None = None,
) -> str:
    key = _konto_str(konto)
    mode = (display_mode or "konto").strip().lower()
    if mode.startswith("regn") and konto_regnskapslinje_map:
        return str(konto_regnskapslinje_map.get(key, key) or key)
    if konto_navn_map:
        name = str(konto_navn_map.get(key, "") or "").strip()
        if name:
            return f"{key} {name}"
    return key


def combo_regnskapslinje_labels(
    combo: str,
    *,
    konto_regnskapslinje_map: Mapping[str, str] | None = None,
) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    label_map = konto_regnskapslinje_map or {}
    for raw in str(combo or "").split(","):
        key = _konto_str(raw)
        if not key:
            continue
        label = str(label_map.get(key, "") or "").strip()
        if not label or label in seen:
            continue
        labels.append(label)
        seen.add(label)
    return labels


def find_expected_combos_by_regnskapslinjer(
    combos: Sequence[str],
    *,
    expected_regnskapslinjer: Sequence[str],
    konto_regnskapslinje_map: Mapping[str, str] | None = None,
) -> list[str]:
    expected = {str(v).strip() for v in expected_regnskapslinjer if str(v).strip()}
    if not expected or not konto_regnskapslinje_map:
        return []

    matched: list[str] = []
    for combo in combos:
        combo_key = str(combo or "").strip()
        if not combo_key:
            continue
        labels = combo_regnskapslinje_labels(
            combo_key,
            konto_regnskapslinje_map=konto_regnskapslinje_map,
        )
        if labels and set(labels).issubset(expected):
            matched.append(combo_key)
    return matched


def _legacy_find_expected_combos_by_netting_regnskapslinjer(
    combos: Sequence[str],
    *,
    df_scope: pd.DataFrame,
    selected_accounts: Sequence[str],
    selected_regnskapslinjer: Sequence[str] | None = None,
    expected_regnskapslinjer: Sequence[str],
    konto_regnskapslinje_map: Mapping[str, str] | None = None,
    selected_direction: str | None = None,
    tolerance: float = 1.0,
    empty_label: str = "(ingen motkonto)",
) -> list[str]:
    expected = {str(v).strip() for v in expected_regnskapslinjer if str(v).strip()}
    if not expected or not konto_regnskapslinje_map:
        return []
    if df_scope is None or df_scope.empty:
        return []
    selected_source = None
    if selected_regnskapslinjer is not None:
        selected_source = {str(v).strip() for v in selected_regnskapslinjer if str(v).strip()}
        if not selected_source:
            return []

    df = _ensure_scope_columns(df_scope)
    sel_set = {str(_konto_str(k)) for k in selected_accounts if str(_konto_str(k))}
    if not sel_set:
        return []
    belop_col = "Beløp"
    if belop_col not in df.columns:
        for col in df.columns:
            cleaned = str(col).strip().lower()
            if cleaned in {"belop", "beløp", "belã¸p"}:
                belop_col = str(col)
                break

    try:
        tolerance_value = max(float(tolerance or 0.0), 0.0)
    except Exception:
        tolerance_value = 1.0

    bilag_to_combo = build_bilag_to_motkonto_combo(df, list(sel_set), empty_label=empty_label)

    sel_mask = df["Konto_str"].isin(sel_set)
    selected_by_bilag = df.loc[sel_mask].groupby("Bilag_str")["Beløp"].sum()

    dir_norm = normalize_direction(selected_direction)
    if dir_norm == "kredit":
        selected_by_bilag = selected_by_bilag.where(selected_by_bilag < 0, 0.0)
    elif dir_norm == "debet":
        selected_by_bilag = selected_by_bilag.where(selected_by_bilag > 0, 0.0)

    regnskapslinje_labels = df["Konto_str"].map(lambda k: str((konto_regnskapslinje_map or {}).get(str(k), "") or "").strip())
    expected_mask = (~sel_mask) & regnskapslinje_labels.isin(expected)
    other_mask = (~sel_mask) & ~regnskapslinje_labels.isin(expected)

    expected_by_bilag = df.loc[expected_mask].groupby("Bilag_str")["Beløp"].sum()
    other_by_bilag = df.loc[other_mask].groupby("Bilag_str")["Beløp"].apply(lambda s: s.abs().sum())
    expected_presence = df.loc[expected_mask].groupby("Bilag_str").size()

    bilag_values = sorted({str(v) for v in df["Bilag_str"].dropna().astype(str).tolist() if str(v).strip()})
    if not bilag_values:
        return []

    bilag_eval = pd.DataFrame(index=pd.Index(bilag_values, name="Bilag_str"))
    bilag_eval["Kombinasjon"] = [str(bilag_to_combo.get(_bilag_str(v), empty_label) or "").strip() for v in bilag_values]
    bilag_eval["SelectedNet"] = selected_by_bilag.reindex(bilag_values).fillna(0.0).astype(float).values
    bilag_eval["ExpectedSum"] = expected_by_bilag.reindex(bilag_values).fillna(0.0).astype(float).values
    bilag_eval["OtherAbs"] = other_by_bilag.reindex(bilag_values).fillna(0.0).astype(float).values
    bilag_eval["HasExpected"] = expected_presence.reindex(bilag_values).fillna(0).astype(int).values > 0
    bilag_eval["Residual"] = bilag_eval["SelectedNet"] + bilag_eval["ExpectedSum"]
    bilag_eval["Matches"] = (
        bilag_eval["HasExpected"]
        & bilag_eval["Residual"].abs().le(tolerance_value)
        & bilag_eval["OtherAbs"].le(tolerance_value)
    )

    matched_set: set[str] = set()
    for combo_key, group in bilag_eval.groupby("Kombinasjon", dropna=False):
        combo_text = str(combo_key or "").strip()
        if not combo_text:
            continue
        if bool(group["HasExpected"].any()) and bool(group["Matches"].all()):
            matched_set.add(combo_text)

    matched: list[str] = []
    for combo in combos:
        combo_key = str(combo or "").strip()
        if combo_key and combo_key in matched_set:
            matched.append(combo_key)
    return matched


def find_expected_combos_by_netting_regnskapslinjer(
    combos: Sequence[str],
    *,
    df_scope: pd.DataFrame,
    selected_accounts: Sequence[str],
    selected_regnskapslinjer: Sequence[str] | None = None,
    expected_regnskapslinjer: Sequence[str],
    konto_regnskapslinje_map: Mapping[str, str] | None = None,
    selected_direction: str | None = None,
    tolerance: float = 1.0,
    empty_label: str = "(ingen motkonto)",
) -> list[str]:
    expected = {str(v).strip() for v in expected_regnskapslinjer if str(v).strip()}
    if not expected or not konto_regnskapslinje_map:
        return []
    if df_scope is None or df_scope.empty:
        return []

    selected_source = None
    if selected_regnskapslinjer is not None:
        selected_source = {str(v).strip() for v in selected_regnskapslinjer if str(v).strip()}
        if not selected_source:
            return []

    df = _ensure_scope_columns(df_scope)
    sel_set = {str(_konto_str(k)) for k in selected_accounts if str(_konto_str(k))}
    if not sel_set:
        return []
    belop_col = "Beløp"
    if belop_col not in df.columns:
        for col in df.columns:
            cleaned = str(col).strip().lower()
            if cleaned in {"belop", "beløp", "belã¸p"}:
                belop_col = str(col)
                break

    try:
        tolerance_value = max(float(tolerance or 0.0), 0.0)
    except Exception:
        tolerance_value = 1.0

    bilag_to_combo = build_bilag_to_motkonto_combo(df, list(sel_set), empty_label=empty_label)

    regnskapslinje_labels = df["Konto_str"].map(
        lambda k: str((konto_regnskapslinje_map or {}).get(str(k), "") or "").strip()
    )
    sel_mask = df["Konto_str"].isin(sel_set)
    if selected_source is None:
        selected_focus_mask = sel_mask
    else:
        selected_focus_mask = sel_mask & regnskapslinje_labels.isin(selected_source)

    selected_by_bilag = df.loc[selected_focus_mask].groupby("Bilag_str")[belop_col].sum()

    dir_norm = normalize_direction(selected_direction)
    if dir_norm == "kredit":
        selected_by_bilag = selected_by_bilag.where(selected_by_bilag < 0, 0.0)
    elif dir_norm == "debet":
        selected_by_bilag = selected_by_bilag.where(selected_by_bilag > 0, 0.0)

    expected_mask = (~sel_mask) & regnskapslinje_labels.isin(expected)
    other_mask = ~(selected_focus_mask | expected_mask)

    expected_by_bilag = df.loc[expected_mask].groupby("Bilag_str")[belop_col].sum()
    # Netto av "andre" linjer — tillater intern balansering (f.eks. MVA + leverandoergjeld)
    other_net_by_bilag = df.loc[other_mask].groupby("Bilag_str")[belop_col].sum()
    expected_presence = df.loc[expected_mask].groupby("Bilag_str").size()
    selected_presence = df.loc[selected_focus_mask].groupby("Bilag_str").size()

    bilag_values = sorted({str(v) for v in df["Bilag_str"].dropna().astype(str).tolist() if str(v).strip()})
    if not bilag_values:
        return []

    bilag_eval = pd.DataFrame(index=pd.Index(bilag_values, name="Bilag_str"))
    bilag_eval["Kombinasjon"] = [str(bilag_to_combo.get(_bilag_str(v), empty_label) or "").strip() for v in bilag_values]
    bilag_eval["SelectedNet"] = selected_by_bilag.reindex(bilag_values).fillna(0.0).astype(float).values
    bilag_eval["ExpectedSum"] = expected_by_bilag.reindex(bilag_values).fillna(0.0).astype(float).values
    bilag_eval["OtherNetAbs"] = other_net_by_bilag.reindex(bilag_values).fillna(0.0).astype(float).abs().values
    bilag_eval["HasExpected"] = expected_presence.reindex(bilag_values).fillna(0).astype(int).values > 0
    bilag_eval["HasSelected"] = selected_presence.reindex(bilag_values).fillna(0).astype(int).values > 0
    bilag_eval["Residual"] = bilag_eval["SelectedNet"] + bilag_eval["ExpectedSum"]
    bilag_eval["Relevant"] = bilag_eval["HasSelected"] | bilag_eval["HasExpected"]
    bilag_eval["Matches"] = (
        bilag_eval["Relevant"]
        & bilag_eval["HasSelected"]
        & bilag_eval["HasExpected"]
        & bilag_eval["Residual"].abs().le(tolerance_value)
        & bilag_eval["OtherNetAbs"].le(tolerance_value)
    )

    matched_set: set[str] = set()
    for combo_key, group in bilag_eval.groupby("Kombinasjon", dropna=False):
        combo_text = str(combo_key or "").strip()
        if not combo_text:
            continue
        relevant_group = group[group["Relevant"]]
        if not relevant_group.empty and bool(relevant_group["Matches"].all()):
            matched_set.add(combo_text)

    matched: list[str] = []
    for combo in combos:
        combo_key = str(combo or "").strip()
        if combo_key and combo_key in matched_set:
            matched.append(combo_key)
    return matched


def normalize_direction(selected_direction: str | None) -> str:
    """Normaliser retning til en av: 'alle', 'debet', 'kredit'."""
    s = (selected_direction or "").strip().lower()
    if not s:
        return "alle"
    if s.startswith("deb"):
        return "debet"
    if s.startswith("kre") or s.startswith("cri") or s.startswith("cre"):
        return "kredit"
    if s in {"alle", "all"}:
        return "alle"
    if s in {"debet", "debit"}:
        return "debet"
    if s in {"kredit", "credit"}:
        return "kredit"
    return "alle"


def normalize_combo_status(value: str | None) -> str:
    """Normaliser status til intern kode: '', 'expected' eller 'outlier'."""
    s = (value or "").strip().lower()
    if not s:
        return STATUS_NEUTRAL
    if s in {STATUS_EXPECTED, "forventet"}:
        return STATUS_EXPECTED
    if s in {STATUS_OUTLIER, "outlier", "avvik"}:
        return STATUS_OUTLIER
    return STATUS_NEUTRAL


def status_label(value: str | None, *, neutral_label: str = "") -> str:
    """Visningslabel for status i UI/Excel."""
    s = normalize_combo_status(value)
    if s == STATUS_EXPECTED:
        return "Forventet"
    if s == STATUS_OUTLIER:
        return "Outlier"
    return neutral_label


def status_sort_key(value: str | None) -> int:
    """Gir stabil sortering i rapporter: Outlier først, så forventet, så umerket."""
    s = normalize_combo_status(value)
    if s == STATUS_OUTLIER:
        return 0
    if s == STATUS_EXPECTED:
        return 1
    return 2


def _ensure_scope_columns(df_scope: pd.DataFrame) -> pd.DataFrame:
    """Sikrer at vi har Bilag_str, Konto_str og numerisk Beløp.

    NB: For store datasett er `.copy()` dyrt. Vi kopierer bare når vi faktisk
    må legge til/konvertere kolonner.
    """
    if df_scope is None or df_scope.empty:
        return pd.DataFrame()

    if "Beløp" not in df_scope.columns:
        raise KeyError("df_scope mangler kolonne 'Beløp'")

    need_copy = False
    if "Bilag_str" not in df_scope.columns:
        need_copy = True
    if "Konto_str" not in df_scope.columns:
        need_copy = True
    if not pd.api.types.is_numeric_dtype(df_scope["Beløp"]):
        need_copy = True

    df = df_scope.copy() if need_copy else df_scope

    if "Bilag_str" not in df.columns:
        if "Bilag" not in df.columns:
            raise KeyError("df_scope mangler kolonne 'Bilag'")
        df["Bilag_str"] = df["Bilag"].map(_bilag_str)

    if "Konto_str" not in df.columns:
        if "Konto" not in df.columns:
            raise KeyError("df_scope mangler kolonne 'Konto'")
        df["Konto_str"] = df["Konto"].map(_konto_str)

    if not pd.api.types.is_numeric_dtype(df["Beløp"]):
        df["Beløp"] = df["Beløp"].map(_safe_float)

    return df


def build_combo_totals_df(
    df_scope: pd.DataFrame,
    selected_accounts: Sequence[str],
    *,
    selected_direction: str = "Alle",
    empty_label: str = "(ingen motkonto)",
) -> pd.DataFrame:
    """Bygg kombinasjonsoversikt med summer for valgt side + motposter.

    Returnerer DF med kolonner:
      - Kombinasjon #
      - Kombinasjon
      - Antall bilag
      - Sum valgte kontoer
      - Sum motposter
      - Differanse  (valgt + mot) = totalsum i bilag (skal normalt være 0)
      - % andel bilag  (0-1, egnet for Excel %-format)
    """
    if df_scope is None or df_scope.empty:
        return pd.DataFrame(
            columns=[
                "Kombinasjon #",
                "Kombinasjon",
                "Antall bilag",
                "Sum valgte kontoer",
                "Sum motposter",
                "Differanse",
                "% andel bilag",
            ]
        )

    df = _ensure_scope_columns(df_scope)

    sel_set = {str(_konto_str(k)) for k in selected_accounts if str(_konto_str(k))}
    if not sel_set:
        raise ValueError("selected_accounts er tomt")

    dir_norm = normalize_direction(selected_direction)

    belop = df["Beløp"].astype(float)

    if dir_norm == "debet":
        dir_mask = belop > 0
    elif dir_norm == "kredit":
        dir_mask = belop < 0
    else:
        dir_mask = pd.Series(True, index=df.index)

    sel_mask = df["Konto_str"].isin(sel_set) & dir_mask

    # Sum valgte kontoer per bilag (med retning-filter)
    sel_sum = belop.where(sel_mask, 0.0).groupby(df["Bilag_str"]).sum()

    # Totalsum per bilag (alle linjer)
    total_sum = belop.groupby(df["Bilag_str"]).sum()

    # Motposter = komplementet (alle øvrige linjer i bilaget)
    mot_sum = (total_sum - sel_sum).rename("Sum motposter")

    bilag_level = pd.DataFrame(
        {
            "Bilag_str": sel_sum.index.astype(str),
            "Sum valgte kontoer": sel_sum.values.astype(float),
            "Sum motposter": mot_sum.reindex(sel_sum.index).values.astype(float),
            "Differanse": total_sum.reindex(sel_sum.index).values.astype(float),
        }
    )

    # Kombinasjon per bilag (sett av motkontoer = alle kontoer minus valgte kontoer)
    bilag_to_combo = build_bilag_to_motkonto_combo(df, list(sel_set), empty_label=empty_label)
    bilag_level["Kombinasjon"] = bilag_level["Bilag_str"].map(lambda b: bilag_to_combo.get(_bilag_str(b), empty_label))

    # Aggreger per kombinasjon
    bilag_total = int(bilag_level["Bilag_str"].nunique())
    combo_agg = (
        bilag_level.groupby("Kombinasjon", dropna=False)
        .agg(
            **{
                "Antall bilag": ("Bilag_str", pd.Series.nunique),
                "Sum valgte kontoer": ("Sum valgte kontoer", "sum"),
                "Sum motposter": ("Sum motposter", "sum"),
                "Differanse": ("Differanse", "sum"),
            }
        )
        .reset_index()
    )
    combo_agg["% andel bilag"] = (
        combo_agg["Antall bilag"].astype(float) / float(bilag_total) if bilag_total else 0.0
    )

    # Sorter: flest bilag først, deretter største beløp (abs)
    if not combo_agg.empty:
        combo_agg["_abs_sum"] = combo_agg["Sum valgte kontoer"].abs()
        combo_agg = combo_agg.sort_values(
            by=["Antall bilag", "_abs_sum", "Kombinasjon"], ascending=[False, False, True]
        ).drop(columns=["_abs_sum"])

    # Nummerering av kombinasjoner: bruk partall (2, 4, 6, ...) for å matche
    # arbeidspapir-malen og gi rom for manuelle innslag hvis ønskelig.
    combo_agg.insert(0, "Kombinasjon #", range(2, 2 * len(combo_agg) + 1, 2))
    return combo_agg


def summarize_status_df(
    df_combos: pd.DataFrame,
    status_map: Mapping[str, str] | None,
    *,
    combo_key_col: str = "Kombinasjon",
    sum_col: str = "Sum valgte kontoer",
    bilag_count_col: str = "Antall bilag",
) -> pd.DataFrame:
    """Bygg oppsummering per status.

    Bruker abs(sum) som basis for %-andeler (robust ved Kredit=negative beløp).
    """
    if df_combos is None or df_combos.empty:
        return pd.DataFrame(
            columns=[
                "Status",
                "Sum valgte kontoer",
                "Andel av total",
                "Antall kombinasjoner",
                "Antall bilag",
            ]
        )

    status_map = status_map or {}
    tmp = df_combos.copy()
    tmp["_status"] = tmp[combo_key_col].map(lambda k: normalize_combo_status(status_map.get(str(k), "")))

    def _status_label(s: Any) -> str:
        if s == STATUS_OUTLIER:
            return "Outlier"
        if s == STATUS_EXPECTED:
            return "Forventet"
        return "Umerket"

    tmp["Status"] = tmp["_status"].map(_status_label)

    # Totalbasis (abs) for %-andeler
    total_abs = float(tmp[sum_col].abs().sum()) if sum_col in tmp.columns else 0.0

    grp = (
        tmp.groupby("Status", dropna=False)
        .agg(
            **{
                "Sum valgte kontoer": (sum_col, "sum"),
                "Antall kombinasjoner": (combo_key_col, "count"),
                "Antall bilag": (bilag_count_col, "sum"),
            }
        )
        .reset_index()
    )
    if total_abs > 1e-12:
        grp["Andel av total"] = grp["Sum valgte kontoer"].abs().astype(float) / total_abs
    else:
        grp["Andel av total"] = 0.0

    # Stabil rekkefølge
    order = {"Outlier": 0, "Forventet": 1, "Umerket": 2}
    grp["_order"] = grp["Status"].map(lambda s: order.get(str(s), 99))
    grp = grp.sort_values(["_order", "Status"]).drop(columns=["_order"]).reset_index(drop=True)

    return grp


def extract_full_bilag_for_outlier_combos(
    df_scope: pd.DataFrame,
    selected_accounts: Sequence[str],
    outlier_combos: Sequence[str],
    *,
    empty_label: str = "(ingen motkonto)",
    include_blank_bilag: bool = False,
) -> tuple[pd.DataFrame, dict[str, str], set[str], int]:
    """Returner full bilagsutskrift for outlier-kombinasjoner.

    Returnerer:
      (df_out, bilag_to_combo, out_bilag_set, excluded_blank_bilag_count)

    - df_out: alle linjer i bilagene som tilhører outlier-kombinasjoner
    - bilag_to_combo: mapping bilag_str -> kombinasjon (for hele scope)
    - out_bilag_set: bilag_str som faktisk er med (etter blank-filter)
    - excluded_blank_bilag_count: antall bilag-grupper som ble ekskludert pga tom bilagsid
    """
    if df_scope is None or df_scope.empty:
        return pd.DataFrame(), {}, set(), 0

    df = _ensure_scope_columns(df_scope)

    sel_set = {str(_konto_str(k)) for k in selected_accounts if str(_konto_str(k))}
    bilag_to_combo = build_bilag_to_motkonto_combo(df, list(sel_set), empty_label=empty_label)

    out_combo_set = {str(c).strip() for c in outlier_combos if str(c).strip()}
    out_bilag = {b for b, combo in bilag_to_combo.items() if combo in out_combo_set}

    excluded_blank = 0
    if not include_blank_bilag:
        blank = {b for b in out_bilag if not str(b).strip()}
        excluded_blank = len(blank)
        out_bilag = {b for b in out_bilag if str(b).strip()}

    df_out = df[df["Bilag_str"].isin(out_bilag)].copy()
    return df_out, bilag_to_combo, out_bilag, excluded_blank

def compute_selected_net_sum_by_combo(
    df_scope: pd.DataFrame,
    selected_accounts: Sequence[str],
    *,
    bilag_to_combo: Mapping[str, str] | None = None,
    selected_direction: str | None = None,
    empty_label: str = "(ingen motkonto)",
) -> dict[str, float]:
    """Beregner netto (kredit+debet) på valgte kontoer per kombinasjon.

    Dette er ment som et *supplerende* tall i UI/rapportering når
    `selected_direction='Kredit'` (typisk 3xxx). Da kan noen bilag inneholde
    debetlinjer på samme valgte kontoer (korrigeringer), og netto viser hvor mye
    disse reduserer kredit-summen.

    Viktig:
    - Standard (selected_direction=None/"Alle"): netto på valgte kontoer (kredit+debet).
    - selected_direction="Kredit": kun bilag der netto på valgte kontoer er kredit (netto < 0) bidrar.
      Bilag med netto debet bidrar 0.
    - selected_direction="Debet": kun bilag der netto på valgte kontoer er debet (netto > 0) bidrar.
      Bilag med netto kredit bidrar 0.
    - Bilag/kombinasjon er definert av motkonto-settet (kontoer i bilaget minus valgte kontoer),
      på samme måte som i øvrig motpostanalyse.

    Parametre
    ---------
    df_scope:
        DataFrame med alle linjer i scope (alle kontoer, alle bilag).
    selected_accounts:
        Kontoer valgt i analysen (f.eks. 3xxx).
    bilag_to_combo:
        (Valgfri) mapping {Bilag_str -> Kombinasjon}. Dersom ikke oppgitt, bygges
        den fra df_scope.
    selected_direction:
        (Valgfri) retning. Brukes til å ta kun "netto i valgt retning" (overvekt):
        - Kredit: bilag med netto < 0 bidrar, øvrige blir 0
        - Debet: bilag med netto > 0 bidrar, øvrige blir 0
    empty_label:
        Label for bilag som ikke har motkontoer utenfor valgte kontoer.

    Returnerer
    ---------
    dict[str, float]:
        mapping {kombinasjon -> netto sum på valgte kontoer}.
    """
    if df_scope is None or df_scope.empty:
        return {}

    df = _ensure_scope_columns(df_scope)

    sel_set = {str(_konto_str(k)) for k in selected_accounts if str(_konto_str(k))}
    if not sel_set:
        raise ValueError("selected_accounts er tomt")

    if bilag_to_combo is None:
        bilag_to_combo = build_bilag_to_motkonto_combo(df, list(sel_set), empty_label=empty_label)

    mask = df["Konto_str"].isin(sel_set)
    if not bool(mask.any()):
        return {}

    # Netto per bilag (kun valgte kontoer, alle retninger)
    by_bilag = df.loc[mask].groupby("Bilag_str")["Beløp"].sum()

    # Når retning er angitt ønsker vi ofte "netto i valgt retning" (overvekt).
    # Dette er spesielt nyttig for 3xxx med retning=Kredit der vi vil summere
    # kun bilag som ender i netto kredit på valgte kontoer.
    dir_norm = normalize_direction(selected_direction)
    if dir_norm == "kredit":
        by_bilag = by_bilag.where(by_bilag < 0, 0.0)
    elif dir_norm == "debet":
        by_bilag = by_bilag.where(by_bilag > 0, 0.0)

    # Map bilag -> kombinasjon (vectorized reindex)
    combo_for_bilag = pd.Series(bilag_to_combo).reindex(by_bilag.index).fillna(empty_label)

    tmp = pd.DataFrame(
        {
            "Kombinasjon": combo_for_bilag.values.astype(str),
            "Netto valgte kontoer": by_bilag.values.astype(float),
        }
    )

    by_combo = tmp.groupby("Kombinasjon", dropna=False)["Netto valgte kontoer"].sum()
    return {str(k): float(v) for k, v in by_combo.items()}

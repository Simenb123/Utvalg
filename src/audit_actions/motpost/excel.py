"""Excel-eksport for motpostanalyse.

Denne eksporten er tilpasset en arbeidspapir-mal:
- Oversikt (kort + lenker)
- #<n> (én fane per outlier-kombinasjon)
- Outlier - alle transaksjoner (full bilagsutskrift)
- Data (tabeller for valgte kontoer / kombinasjoner / status)

Eksporten støtter to kilder til status/kommentar:
- Legacy: outlier_combinations=set[str]
- Ny: combo_status_map=dict[combo->status], combo_comment_map=dict[combo->kommentar]

Status normaliseres til: "outlier", "expected" eller "neutral".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd
from openpyxl import Workbook

from .combo_workflow import (
    build_combo_totals_df,
    combo_display_name,
    compute_selected_net_sum_by_combo,
    infer_konto_navn_map,
)
from .excel_sheets.sheet_data import write_data_sheet
from .excel_sheets.sheet_outlier_full_bilag import (
    build_outlier_frames,
    write_outlier_detail_sheets,
    write_outlier_transactions_sheet,
)
from .excel_sheets.sheet_oversikt import write_oversikt_sheet
from .utils import _konto_str


DEFAULT_OUTLIER_SHEET_NAME = "Outlier - alle transaksjoner"


def normalize_combo_status_map(status_map: Optional[dict[str, str]]) -> dict[str, str]:
    """Normaliserer statusverdier fra GUI til {combo: outlier/expected/neutral}."""

    if not status_map:
        return {}

    out: dict[str, str] = {}
    for combo, raw in status_map.items():
        s = str(raw or "").strip().lower()
        if s in {"outlier", "ikke forventet", "not_expected", "not expected"}:
            out[str(combo)] = "outlier"
        elif s in {"expected", "forventet"}:
            out[str(combo)] = "expected"
        elif s in {"", "neutral", "umerket", "unmarked"}:
            out[str(combo)] = "neutral"
        else:
            # Ukjent -> behold som neutral
            out[str(combo)] = "neutral"
    return out


def normalize_comment_map(comment_map: Optional[dict[str, str]]) -> dict[str, str]:
    if not comment_map:
        return {}
    return {str(k): ("" if v is None else str(v)) for k, v in comment_map.items()}


def _direction_norm(direction: str) -> str:
    d = str(direction or "").strip().lower()
    if d.startswith("k"):
        return "kredit"
    if d.startswith("d"):
        return "debet"
    return "alle"


def sum_label(direction: str) -> str:
    d = _direction_norm(direction)
    if d == "kredit":
        return "Sum valgte kontoer (Kredit)"
    if d == "debet":
        return "Sum valgte kontoer (Debet)"
    return "Sum valgte kontoer"


def population_label(direction: str) -> str:
    """Display label for population on *Oversikt*.

    The population is defined as postings on the selected accounts in the chosen direction
    (i.e. the same basis as *Sum valgte kontoer (Kredit/Debet)*).
    """

    d = direction.lower()
    if d.startswith("kred"):
        return "Populasjon (valgte kontoer - Kredit)"
    if d.startswith("deb"):
        return "Populasjon (valgte kontoer - Debet)"
    return "Populasjon (valgte kontoer)"


def net_key_label(direction: str) -> str:
    d = _direction_norm(direction)
    if d == "kredit":
        return "Netto kredit (valgte kontoer)"
    if d == "debet":
        return "Netto debet (valgte kontoer)"
    return "Netto valgte kontoer"


def net_status_header(direction: str) -> str:
    d = _direction_norm(direction)
    if d == "kredit":
        return "Netto kredit"
    if d == "debet":
        return "Netto debet"
    return "Netto"


def _build_valgte_kontoer_df(
    df_scope: pd.DataFrame,
    *,
    selected_accounts: list[str],
    direction: str,
) -> pd.DataFrame:
    """Valgte kontoer (populasjon)"""

    s_label = sum_label(direction)
    net_label = net_key_label(direction)

    sel_set = {str(_konto_str(x)) for x in selected_accounts}

    if df_scope is None or df_scope.empty:
        return pd.DataFrame(
            columns=[
                "Konto",
                "Kontonavn",
                s_label,
                net_label,
                "Kredit",
                "Debet",
                "Netto",
                "Andel %",
                "Antall bilag",
            ]
        )

    df_sel = df_scope[df_scope["Konto_str"].astype(str).isin(sel_set)].copy()
    if df_sel.empty:
        return pd.DataFrame(
            columns=[
                "Konto",
                "Kontonavn",
                s_label,
                net_label,
                "Kredit",
                "Debet",
                "Netto",
                "Andel %",
                "Antall bilag",
            ]
        )

    amount = pd.to_numeric(df_sel["Beløp"], errors="coerce").fillna(0.0)

    credit = amount.where(amount < 0, 0.0).groupby(df_sel["Konto_str"]).sum()
    debet = amount.where(amount > 0, 0.0).groupby(df_sel["Konto_str"]).sum()
    netto = amount.groupby(df_sel["Konto_str"]).sum()

    dn = _direction_norm(direction)
    if dn == "kredit":
        sum_dir = credit
        df_dir = df_sel.loc[amount < 0]
    elif dn == "debet":
        sum_dir = debet
        df_dir = df_sel.loc[amount > 0]
    else:
        sum_dir = netto
        df_dir = df_sel

    ant_bilag = df_dir.groupby("Konto_str")["Bilag_str"].nunique()

    kontonavn = df_sel.groupby("Konto_str")["Kontonavn"].first()

    # Netto per konto: summer konto-beløp kun for bilag i "netto-retning".
    bilag_net = amount.groupby(df_sel["Bilag_str"]).sum()
    if dn == "kredit":
        pop_bilag = set(bilag_net[bilag_net < 0].index.astype(str))
    elif dn == "debet":
        pop_bilag = set(bilag_net[bilag_net > 0].index.astype(str))
    else:
        pop_bilag = set(bilag_net.index.astype(str))

    pop_net = amount[df_sel["Bilag_str"].astype(str).isin(pop_bilag)].groupby(df_sel["Konto_str"]).sum()

    idx = pd.Index(sorted(sel_set), name="Konto")

    df_out = pd.DataFrame(
        {
            "Konto": idx.astype(str),
            "Kontonavn": kontonavn.reindex(idx).fillna(""),
            s_label: sum_dir.reindex(idx).fillna(0.0),
            net_label: pop_net.reindex(idx).fillna(0.0),
            "Kredit": credit.reindex(idx).fillna(0.0),
            "Debet": debet.reindex(idx).fillna(0.0),
            "Netto": netto.reindex(idx).fillna(0.0),
            "Antall bilag": ant_bilag.reindex(idx).fillna(0).astype(int),
        }
    )

    total_abs = float(df_out[s_label].abs().sum())
    if total_abs:
        df_out["Andel %"] = df_out[s_label].abs() / total_abs
    else:
        df_out["Andel %"] = 0.0

    # Sortér som i malen: størst andel først
    df_out = df_out.sort_values(by=[s_label], key=lambda s: s.abs(), ascending=False).reset_index(drop=True)

    # Reorder
    df_out = df_out[
        [
            "Konto",
            "Kontonavn",
            s_label,
            net_label,
            "Kredit",
            "Debet",
            "Netto",
            "Andel %",
            "Antall bilag",
        ]
    ]

    return df_out


def _build_kombinasjoner_df(
    df_scope: pd.DataFrame,
    *,
    selected_accounts: list[str],
    direction: str,
    status_map_norm: dict[str, str],
    comment_map_norm: dict[str, str],
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Bygger tabellen "Kombinasjoner" og returnerer også combo_name_map."""

    s_label = sum_label(direction)
    net_label = net_key_label(direction)

    konto_navn_map = infer_konto_navn_map(df_scope)

    # Base: totals pr kombinasjon
    df_combo = build_combo_totals_df(df_scope, selected_accounts, selected_direction=direction)

    # Netto per kombinasjon ("populasjon")
    net_map = compute_selected_net_sum_by_combo(df_scope, selected_accounts, selected_direction=direction)

    # Legg inn navn
    df_combo["Kombinasjon (navn)"] = df_combo["Kombinasjon"].map(lambda c: combo_display_name(str(c), konto_navn_map))

    combo_name_map = {
        str(c): str(n)
        for c, n in zip(df_combo["Kombinasjon"].astype(str).tolist(), df_combo["Kombinasjon (navn)"].astype(str).tolist())
    }

    # Rename/drop
    df_combo = df_combo.rename(
        columns={
            "Kombinasjon #": "#",
            "Sum valgte kontoer": s_label,
            "% andel bilag": "% andel bilag",
        }
    )

    # Populasjon-kolonne
    df_combo[net_label] = df_combo["Kombinasjon"].map(lambda c: float(net_map.get(str(c), 0.0)))

    # % andel beløp (basert på populasjon)
    total_pop = float(df_combo[net_label].sum())
    if total_pop:
        df_combo["% andel beløp"] = df_combo[net_label].abs() / abs(total_pop)
    else:
        df_combo["% andel beløp"] = 0.0

    # Status + kommentar
    def _status_label(combo: str) -> str:
        s = status_map_norm.get(combo, "neutral")
        if s == "outlier":
            return "Ikke forventet"
        if s == "expected":
            return "Forventet"
        return "Umerket"

    df_combo["Status"] = df_combo["Kombinasjon"].astype(str).map(_status_label)
    df_combo["Kommentar"] = df_combo["Kombinasjon"].astype(str).map(lambda c: comment_map_norm.get(str(c), ""))

    # Behold kun kolonner fra malen
    df_combo = df_combo[
        [
            "#",
            "Kombinasjon",
            "Kombinasjon (navn)",
            s_label,
            net_label,
            "Antall bilag",
            "% andel bilag",
            "% andel beløp",
            "Status",
            "Kommentar",
        ]
    ]

    # Sortér: outlier -> forventet -> umerket, deretter #
    sort_key = df_combo["Status"].map({"Ikke forventet": 0, "Forventet": 1, "Umerket": 2}).fillna(9)
    df_combo = df_combo.assign(_status_sort=sort_key).sort_values(by=["_status_sort", "#"], kind="mergesort")
    df_combo = df_combo.drop(columns=["_status_sort"]).reset_index(drop=True)

    return df_combo, combo_name_map


def _build_status_summary_df(
    df_kombinasjoner: pd.DataFrame,
    *,
    direction: str,
) -> pd.DataFrame:
    """Bygger "Oversikt forventet / ikke forventet"."""

    s_label = sum_label(direction)
    net_label = net_key_label(direction)

    net_header = net_status_header(direction)

    if df_kombinasjoner is None or df_kombinasjoner.empty:
        return pd.DataFrame(
            columns=[
                "Status",
                "Sum valgte kontoer",
                net_header,
                "Antall kombinasjoner",
                "Antall bilag",
                "Andel av total",
                "Kommentar",
            ]
        )

    total_sum = float(df_kombinasjoner[s_label].sum())

    def group_label(status: str) -> str:
        s = str(status or "").strip().lower()
        if s == "ikke forventet":
            return "Outlier - ikke forventet"
        if s == "forventet":
            return "Forventet"
        return "ikke vesentlig (ikke markert)"

    grp = df_kombinasjoner.copy()
    grp["_grp"] = grp["Status"].map(group_label)

    agg = grp.groupby("_grp", dropna=False).agg(
        sum_selected=(s_label, "sum"),
        net=(net_label, "sum"),
        antall_komb=("Kombinasjon", "count"),
        antall_bilag=("Antall bilag", "sum"),
    )

    def _andel(x: float) -> float:
        if not total_sum:
            return 0.0
        return abs(float(x)) / abs(total_sum)

    rows: list[dict[str, Any]] = []
    order = ["Outlier - ikke forventet", "Forventet", "ikke vesentlig (ikke markert)"]
    comments = {
        "Outlier - ikke forventet": "ikke forventede kombinasjoner forklart/revidert - se egne faner per kombinasjon",
        "Forventet": "Forventet",
        "ikke vesentlig (ikke markert)": "Sum ikke forklart - samlet sett ikke vesentlig",
    }

    for key in order:
        if key not in agg.index:
            rows.append(
                {
                    "Status": key,
                    "Sum valgte kontoer": 0.0,
                    net_header: 0.0,
                    "Antall kombinasjoner": 0,
                    "Antall bilag": 0,
                    "Andel av total": 0.0,
                    "Kommentar": comments.get(key, ""),
                }
            )
            continue
        rows.append(
            {
                "Status": key,
                "Sum valgte kontoer": float(agg.loc[key, "sum_selected"]),
                net_header: float(agg.loc[key, "net"]),
                "Antall kombinasjoner": int(agg.loc[key, "antall_komb"]),
                "Antall bilag": int(agg.loc[key, "antall_bilag"]),
                "Andel av total": _andel(float(agg.loc[key, "sum_selected"])),
                "Kommentar": comments.get(key, ""),
            }
        )

    return pd.DataFrame(rows)


def _build_outlier_index_df(
    df_kombinasjoner: pd.DataFrame,
    *,
    direction: str,
) -> pd.DataFrame:
    """Kort outlier-oversikt for Oversikt-arket."""

    s_label = sum_label(direction)

    if df_kombinasjoner is None or df_kombinasjoner.empty:
        # Kun en kompakt indeks for outliers (lenker til egne faner).
        return pd.DataFrame(columns=["#", "Kombinasjon", "Kombinasjon (navn)", s_label, "Antall bilag", "Fane"])

    df_out = df_kombinasjoner[df_kombinasjoner["Status"].astype(str).str.lower().eq("ikke forventet")].copy()
    if df_out.empty:
        return pd.DataFrame(columns=["#", "Kombinasjon", "Kombinasjon (navn)", s_label, "Antall bilag", "Fane"])

    # Hyperlink til fane
    def _fane_link(num: Any) -> str:
        try:
            n = int(num)
        except Exception:
            n = str(num)
        sheet = f"#{n}"
        return f'=HYPERLINK("#\'{sheet}\'!A1","{sheet}")'

    df_out["Fane"] = df_out["#"].map(_fane_link)

    # Hold indeksen kort: ikke ta med "Kommentar" her, siden kommentarer/handling/resultat
    # fylles ut i egne outlier-faner.
    return df_out[["#", "Kombinasjon", "Kombinasjon (navn)", s_label, "Antall bilag", "Fane"]].reset_index(drop=True)


def build_motpost_excel_workbook(
    data: Any,
    *,
    outlier_motkonto: Optional[set[str]] = None,
    selected_motkonto: Optional[str] = None,
    outlier_combinations: Optional[set[str]] = None,
    combo_status_map: Optional[dict[str, str]] = None,
    combo_comment_map: Optional[dict[str, str]] = None,
    include_outlier_transactions: bool = True,
    materiality_amount: Optional[float] = None,
) -> Workbook:
    """Bygg en Excel-workbook for motpostanalyse."""

    df_scope: pd.DataFrame = getattr(data, "df_scope")
    selected_accounts: list[str] = list(getattr(data, "selected_accounts"))
    direction: str = str(getattr(data, "selected_direction", "Alle") or "Alle")

    # Normaliser status/kommentar
    status_norm = normalize_combo_status_map(combo_status_map)
    comment_norm = normalize_comment_map(combo_comment_map)

    # Legacy: outlier_combinations
    if outlier_combinations and not status_norm:
        status_norm = {str(c): "outlier" for c in outlier_combinations}

    # Tabellgrunnlag
    df_valgte_kontoer = _build_valgte_kontoer_df(df_scope, selected_accounts=selected_accounts, direction=direction)
    df_kombinasjoner, combo_name_map = _build_kombinasjoner_df(
        df_scope,
        selected_accounts=selected_accounts,
        direction=direction,
        status_map_norm=status_norm,
        comment_map_norm=comment_norm,
    )
    df_status = _build_status_summary_df(df_kombinasjoner, direction=direction)
    df_outlier_index = _build_outlier_index_df(df_kombinasjoner, direction=direction)

    # Summer for oversikt
    s_label = sum_label(direction)
    pop_label = population_label(direction)
    net_label = net_key_label(direction)

    selected_sum = float(getattr(data, "selected_sum", df_kombinasjoner[s_label].sum() if not df_kombinasjoner.empty else 0.0) or 0.0)
    population_net = float(df_kombinasjoner[net_label].sum() if not df_kombinasjoner.empty else 0.0)

    # Outlier combos
    outlier_combos = df_kombinasjoner[df_kombinasjoner["Status"].astype(str).str.lower().eq("ikke forventet")]["Kombinasjon"].astype(str).tolist()

    frames = build_outlier_frames(
        df_scope,
        selected_accounts=selected_accounts,
        outlier_combos=outlier_combos,
        combo_name_map=combo_name_map,
        include_transactions=include_outlier_transactions,
    )

    # Workbook og ark-rekkefølge:
    # Oversikt -> #n -> Outlier - alle transaksjoner -> Data
    wb = Workbook()

    ws_over = wb.active
    ws_over.title = "Oversikt"

    # Detaljfaner for outliers
    write_outlier_detail_sheets(
        wb,
        df_kombinasjoner=df_kombinasjoner,
        frames=frames,
        df_scope=df_scope,
        selected_accounts=selected_accounts,
        direction=direction,
        sum_label=s_label,
        net_label=net_label,
        outlier_sheet_name=DEFAULT_OUTLIER_SHEET_NAME,
        include_outlier_transactions=include_outlier_transactions,
    )

    # Outlier - alle transaksjoner (alltid)
    write_outlier_transactions_sheet(
        wb,
        frames=frames,
        sheet_name=DEFAULT_OUTLIER_SHEET_NAME,
    )

    # Data (sist)
    ws_data = wb.create_sheet("Data")
    write_data_sheet(ws_data, df_valgte_kontoer=df_valgte_kontoer, df_kombinasjoner=df_kombinasjoner, df_status=df_status)

    # Oversikt (til slutt, slik at vi kan bruke ferdige DF'er)
    write_oversikt_sheet(
        ws_over,
        data=data,
        direction=direction,
        selected_accounts=selected_accounts,
        selected_sum=selected_sum,
        population_net=population_net,
        df_status=df_status,
        df_outlier_index=df_outlier_index,
        outlier_sheet_name=DEFAULT_OUTLIER_SHEET_NAME,
        sum_label=s_label,
        population_label=pop_label,
        net_label=net_label,
        materiality_amount=materiality_amount,
    )

    return wb

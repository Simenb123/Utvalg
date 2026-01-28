"""Filtrering for Utvalg (Selection Studio).

Denne modulen brukes både av GUI og av tester.

Beløpsfilter ("Beløp fra/til"):
- Retning kan være "Alle", "Debet" eller "Kredit".
- Dersom ``use_abs`` er True, brukes absoluttverdi for beløpsfilteret.
- Ved kun ``min_value`` (og tom ``max_value``) i absolutt-modus tolkes det
  funksjonelt som et terskelfilter som *fjerner* transaksjoner i intervallet
  (-min, +min) ved at vi beholder rader med ``abs(Beløp) >= min``.

Datofilter:
- ``date_from`` / ``date_to`` kan oppgis som dd.mm.yyyy (anbefalt), men vi
  aksepterer også ISO-dato (yyyy-mm-dd).

Kompatibilitet:
- Eldre tester/kode kan kalle funksjonen med ``df_base=...`` i stedet for å
  sende DataFrame som første argument. Begge støttes.
- Eldre tester forventer nøklene ``summary['N']`` og ``summary['S']``.

Funksjonen returnerer både filtrert DataFrame og en ``summary``-dict med nøkkeltall.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import pandas as pd


def _parse_float(value: Any) -> Optional[float]:
    """Parse tall fra GUI/tekst.

    Tillater både 1 234,56 og 1234.56.
    Returnerer None hvis tom/ugyldig.
    """

    if value is None:
        return None

    s = str(value).strip()
    if not s:
        return None

    # Fjern vanlige tusenskilletegn (mellomrom og NBSP) og normaliser desimal.
    s = s.replace("\u00a0", " ").replace(" ", "").replace(",", ".")

    try:
        return float(s)
    except Exception:
        return None


def _parse_date(value: Any) -> Optional[pd.Timestamp]:
    """Parse dato fra dd.mm.yyyy eller ISO.

    Returnerer normalisert Timestamp (kl 00:00) eller None.
    """

    if value is None:
        return None

    s = str(value).strip()
    if not s:
        return None

    ts = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.isna(ts):
        return None
    return ts.normalize()


def filter_selectionstudio_dataframe(
    df: Optional[pd.DataFrame] = None,
    *,
    df_base: Optional[pd.DataFrame] = None,
    direction: str = "Alle",
    min_value: str = "",
    max_value: str = "",
    use_abs: bool = False,
    date_from: str = "",
    date_to: str = "",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Filtrer transaksjonsdata for Utvalg.

    Args:
        df: DataFrame med minst kolonnene "Beløp" og (valgfritt) "Dato".
        df_base: Alias for df (bakoverkompatibilitet).
        direction: "Alle", "Debet" eller "Kredit".
        min_value: Nedre grense/terskel (tekst fra GUI).
        max_value: Øvre grense (tekst fra GUI).
        use_abs: Hvis True brukes absoluttverdi ved beløpsfilter.
        date_from: Startdato (dd.mm.yyyy).
        date_to: Sluttdato (dd.mm.yyyy).

    Returns:
        (df_filtered, summary)
    """

    df_in = (df if df is not None else df_base)
    if df_in is None:
        raise ValueError("filter_selectionstudio_dataframe: df (eller df_base) må angis")

    df_in = df_in.copy()

    # Hvis beløpskolonne mangler, returner "tom" summary som er kompatibel.
    if "Beløp" not in df_in.columns:
        summary = {
            "direction_in": direction,
            "use_abs": bool(use_abs),
            "min_value": min_value,
            "max_value": max_value,
            "date_from": date_from,
            "date_to": date_to,
            "base_n": int(len(df_in)),
            "base_s": 0.0,
            "base_abs": 0.0,
            "filtered_n": int(len(df_in)),
            "filtered_s": 0.0,
            "filtered_abs": 0.0,
            "removed_n": 0,
            "removed_s": 0.0,
            "removed_abs": 0.0,
            "amount_filter_active": False,
            "removed_by_amount_net": 0.0,
            "removed_by_amount_abs": 0.0,
            "removed_by_amount_count": 0,
            "removed_interval_s": 0.0,
            "removed_interval_abs": 0.0,
            "date_filter_active": False,
            "removed_by_date_net": 0.0,
            "removed_by_date_abs": 0.0,
            "removed_by_date_count": 0,
        }
        # Alias-nøkler for tester
        summary["N"] = summary["filtered_n"]
        summary["S"] = summary["filtered_s"]
        summary["amount_filter_removed_count"] = summary["removed_by_amount_count"]
        summary["amount_filter_removed_net_sum"] = summary["removed_by_amount_net"]
        summary["amount_filter_removed_abs_sum"] = summary["removed_by_amount_abs"]
        summary["date_filter_removed_count"] = summary["removed_by_date_count"]
        summary["date_filter_removed_net_sum"] = summary["removed_by_date_net"]
        summary["date_filter_removed_abs_sum"] = summary["removed_by_date_abs"]
        return df_in, summary

    # --- Beløp (robust numerisk) -------------------------------------------------
    bel = pd.to_numeric(df_in["Beløp"], errors="coerce")

    base_n = int(len(df_in))
    base_s = float(bel.sum(skipna=True))
    base_abs = float(bel.abs().sum(skipna=True))

    # --- Retning -----------------------------------------------------------------
    direction_norm = str(direction or "Alle").strip().lower()
    if direction_norm == "debet":
        mask_dir = bel > 0
    elif direction_norm == "kredit":
        mask_dir = bel < 0
    else:
        mask_dir = pd.Series([True] * len(df_in), index=df_in.index)

    df_dir = df_in.loc[mask_dir].copy()
    bel_dir = bel.loc[mask_dir]

    # --- Beløpsfilter ------------------------------------------------------------
    min_amount = _parse_float(min_value)
    max_amount = _parse_float(max_value)
    amount_filter_active = bool(min_amount is not None or max_amount is not None)

    bel_base = bel_dir.abs() if use_abs else bel_dir

    mask_keep_amount = pd.Series([True] * len(df_dir), index=df_dir.index)
    if min_amount is not None:
        mask_keep_amount &= bel_base >= min_amount
    if max_amount is not None:
        mask_keep_amount &= bel_base <= max_amount

    removed_by_amount_mask = ~mask_keep_amount
    removed_by_amount_net = float(bel_dir.loc[removed_by_amount_mask].sum(skipna=True))
    removed_by_amount_abs = float(bel_dir.loc[removed_by_amount_mask].abs().sum(skipna=True))
    removed_by_amount_count = int(removed_by_amount_mask.sum())

    # For GUI: hvor mye som ligger i "filtrert bort"-intervallet
    removed_interval_s = removed_by_amount_net
    removed_interval_abs = removed_by_amount_abs

    df_amount = df_dir.loc[mask_keep_amount].copy()
    bel_amount = bel_dir.loc[mask_keep_amount]

    # --- Datofilter --------------------------------------------------------------
    date_from_ts = _parse_date(date_from)
    date_to_ts = _parse_date(date_to)
    date_filter_active = bool(date_from_ts is not None or date_to_ts is not None)

    removed_by_date_net = 0.0
    removed_by_date_abs = 0.0
    removed_by_date_count = 0

    df_final = df_amount
    bel_final = bel_amount

    if date_filter_active and "Dato" in df_amount.columns:
        # "Dato" kan komme i flere formater (f.eks. YYYY-MM-DD eller DD.MM.YYYY).
        # Vi parser først uten dayfirst for å unngå advarsel på ISO-datoer, og
        # prøver dayfirst kun der det trengs.
        raw_dates = df_amount["Dato"]
        dts = pd.to_datetime(raw_dates, errors="coerce")
        mask_nat = dts.isna() & raw_dates.astype(str).str.strip().ne("")
        if mask_nat.any():
            dts.loc[mask_nat] = pd.to_datetime(raw_dates.loc[mask_nat], errors="coerce", dayfirst=True)
        dts = dts.dt.normalize()

        mask_keep_date = pd.Series([True] * len(df_amount), index=df_amount.index)
        if date_from_ts is not None:
            mask_keep_date &= dts >= date_from_ts
        if date_to_ts is not None:
            mask_keep_date &= dts <= date_to_ts

        removed_by_date_mask = ~mask_keep_date
        removed_by_date_net = float(bel_amount.loc[removed_by_date_mask].sum(skipna=True))
        removed_by_date_abs = float(bel_amount.loc[removed_by_date_mask].abs().sum(skipna=True))
        removed_by_date_count = int(removed_by_date_mask.sum())

        df_final = df_amount.loc[mask_keep_date].copy()
        bel_final = bel_amount.loc[mask_keep_date]

    # --- Summary -----------------------------------------------------------------
    filtered_n = int(len(df_final))
    filtered_s = float(bel_final.sum(skipna=True))
    filtered_abs = float(bel_final.abs().sum(skipna=True))

    removed_n = base_n - filtered_n
    removed_s = base_s - filtered_s
    removed_abs = base_abs - filtered_abs

    summary: Dict[str, Any] = {
        # input
        "direction_in": direction,
        "use_abs": bool(use_abs),
        "min_value": min_value,
        "max_value": max_value,
        "date_from": date_from,
        "date_to": date_to,
        # base
        "base_n": base_n,
        "base_s": base_s,
        "base_abs": base_abs,
        # filtered
        "filtered_n": filtered_n,
        "filtered_s": filtered_s,
        "filtered_abs": filtered_abs,
        # total removed
        "removed_n": int(removed_n),
        "removed_s": float(removed_s),
        "removed_abs": float(removed_abs),
        # amount filter removal
        "amount_filter_active": amount_filter_active,
        "removed_by_amount_net": removed_by_amount_net,
        "removed_by_amount_abs": removed_by_amount_abs,
        "removed_by_amount_count": removed_by_amount_count,
        "removed_interval_s": removed_interval_s,
        "removed_interval_abs": removed_interval_abs,
        # date filter removal
        "date_filter_active": date_filter_active,
        "removed_by_date_net": removed_by_date_net,
        "removed_by_date_abs": removed_by_date_abs,
        "removed_by_date_count": removed_by_date_count,
    }

    # Kompatibilitetsnøkler
    summary["N"] = filtered_n
    summary["S"] = filtered_s

    summary["amount_filter_removed_count"] = removed_by_amount_count
    summary["amount_filter_removed_net_sum"] = removed_by_amount_net
    summary["amount_filter_removed_abs_sum"] = removed_by_amount_abs

    # Nøkler brukt i enkelte tester/GUI-tekster ("rows" i stedet for "count")
    summary["removed_by_amount_rows"] = removed_by_amount_count
    summary["removed_by_amount_net_sum"] = removed_by_amount_net
    summary["removed_by_amount_abs_sum"] = removed_by_amount_abs
    # Alternative nøkkelnavn (noen tester bruker "sum_net/sum_abs")
    summary["removed_by_amount_sum_net"] = removed_by_amount_net
    summary["removed_by_amount_sum_abs"] = removed_by_amount_abs

    summary["date_filter_removed_count"] = removed_by_date_count
    summary["date_filter_removed_net_sum"] = removed_by_date_net
    summary["date_filter_removed_abs_sum"] = removed_by_date_abs

    summary["removed_by_date_rows"] = removed_by_date_count
    summary["removed_by_date_net_sum"] = removed_by_date_net
    summary["removed_by_date_abs_sum"] = removed_by_date_abs
    summary["removed_by_date_sum_net"] = removed_by_date_net
    summary["removed_by_date_sum_abs"] = removed_by_date_abs

    return df_final, summary

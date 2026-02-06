from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Set

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .combo_workflow import (
    STATUS_OUTLIER,
    build_combo_totals_df,
    combo_display_name,
    extract_full_bilag_for_outlier_combos,
    infer_konto_navn_map,
    normalize_combo_status,
    status_label,
    status_sort_key,
    summarize_status_df,
)
from .utils import _bilag_str, _konto_str

THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)


def _norm(s: str) -> str:
    """Normaliser streng til alfanumerisk (Excel/Tabell-safe)."""
    out = []
    for ch in str(s):
        if ch.isalnum():
            out.append(ch)
    return "".join(out) or "Sheet"


def _safe_table_name(sheet_title: str) -> str:
    """Excel Table displayName: må være alfanumerisk + starte med bokstav/underscore.

    Vi prefikser med 'T' og normaliserer til [A-Za-z0-9].
    """
    base = _norm(sheet_title)
    return f"T{base}"


def _set_cell(ws, row: int, col: int, value, bold: bool = False, num_format: Optional[str] = None):
    cell = ws.cell(row=row, column=col, value=value)
    cell.border = THIN_BORDER
    if bold:
        cell.font = Font(bold=True)
    if num_format:
        cell.number_format = num_format
    return cell


def _apply_table_style(ws, start_row: int, start_col: int, end_row: int, end_col: int):
    """Opprett Excel Table med stil (båndrader) og num-format på relevante kolonner."""
    if end_row <= start_row:
        return

    ref = f"{get_column_letter(start_col)}{start_row}:{get_column_letter(end_col)}{end_row}"
    table = Table(displayName=_safe_table_name(ws.title), ref=ref)
    style = TableStyleInfo(
        name="TableStyleMedium9",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    table.tableStyleInfo = style
    ws.add_table(table)

    header_row = start_row
    headers = [ws.cell(row=header_row, column=c).value for c in range(start_col, end_col + 1)]

    # Heuristikk for beløp og prosent-kolonner.
    money_headers = {
        "Sum",
        "Beløp",
        "Sum valgte kontoer",
        "Sum motposter",
        "Motbeløp",
        "Differanse",
        "Debet",
        "Kredit",
    }
    percent_headers = {
        "% andel",
        "% andel bilag",
        "Andel av total",
        "Andel av valgt",
    }

    for idx, h in enumerate(headers, start=start_col):
        h_str = str(h or "").strip()
        if h_str in money_headers:
            for r in range(start_row + 1, end_row + 1):
                ws.cell(row=r, column=idx).number_format = "#,##0.00"
        if h_str in percent_headers:
            for r in range(start_row + 1, end_row + 1):
                ws.cell(row=r, column=idx).number_format = "0.00%"

    # Freeze header
    ws.freeze_panes = ws.cell(row=start_row + 1, column=start_col)


def _write_df_table(ws, df: pd.DataFrame, title: str, start_row: int = 1) -> int:
    """Skriv en DF som en tabell med tittel."""
    cur = start_row
    _set_cell(ws, cur, 1, title, bold=True)
    ws.cell(row=cur, column=1).font = Font(bold=True, size=14)
    cur += 2

    if df is None or df.empty:
        _set_cell(ws, cur, 1, "(ingen rader)")
        return cur + 2

    # Headers
    for j, col in enumerate(df.columns, start=1):
        _set_cell(ws, cur, j, col, bold=True)
    header_row = cur
    cur += 1

    # Rows
    for _, row in df.iterrows():
        for j, col in enumerate(df.columns, start=1):
            val = row[col]
            _set_cell(ws, cur, j, val)
        cur += 1

    end_row = cur - 1
    _apply_table_style(ws, header_row, 1, end_row, len(df.columns))

    # Auto width (best effort)
    for j, col in enumerate(df.columns, start=1):
        try:
            max_len = max(len(str(col)), *(len(str(x)) for x in df[col].head(200).astype(str).tolist()))
            ws.column_dimensions[get_column_letter(j)].width = min(max(10, max_len + 2), 60)
        except Exception:
            pass

    return cur + 1


def _write_kv_sheet(ws, title: str, kv: list[tuple[str, object]], start_row: int = 1) -> int:
    cur = start_row
    _set_cell(ws, cur, 1, title, bold=True)
    ws.cell(row=cur, column=1).font = Font(bold=True, size=14)
    cur += 2

    for k, v in kv:
        _set_cell(ws, cur, 1, k, bold=True)
        c = _set_cell(ws, cur, 2, v)
        c.alignment = Alignment(horizontal="left")
        cur += 1

    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 60
    return cur + 1


def _normalize_status_map(
    combo_status_map: Optional[Mapping[str, str]],
    outlier_combinations: Optional[Set[str]],
) -> dict[str, str]:
    """Kombiner ny status_map + legacy outlier-sett til en samlet mapping."""
    merged: dict[str, str] = {}
    if combo_status_map:
        for k, v in combo_status_map.items():
            ck = str(k).strip()
            if not ck:
                continue
            merged[ck] = normalize_combo_status(v)
    if outlier_combinations:
        for c in outlier_combinations:
            ck = str(c).strip()
            if not ck:
                continue
            # Ikke overskriv forventet
            if merged.get(ck) != "expected":
                merged[ck] = STATUS_OUTLIER
    return merged


def build_motpost_excel_workbook(
    data,
    *,
    outlier_motkonto: Optional[Set[str]] = None,
    selected_motkonto: Optional[str] = None,
    df_details_view: Optional[pd.DataFrame] = None,
    outlier_accounts: Optional[Set[str]] = None,
    outlier_combinations: Optional[Set[str]] = None,
    combo_status_map: Optional[Mapping[str, str]] = None,
) -> Workbook:
    """Bygg Excel-rapport for motpostanalyse (kompakt).

    Ny workflow (2026-02):
    - Kombinasjoner kan merkes som Forventet / Outlier / Umerket.
    - Full bilagsutskrift tas kun for outlier-kombinasjoner for å holde rapporten liten.

    Parametre som ikke brukes lenger (outlier_motkonto, selected_motkonto, df_details_view, outlier_accounts)
    beholdes for bakoverkompatibilitet, men rapporten fokuserer på kombinasjonsworkflow.
    """
    wb = Workbook()
    # Fjern default-arket
    if wb.sheetnames:
        wb.remove(wb[wb.sheetnames[0]])

    status_map = _normalize_status_map(combo_status_map, outlier_combinations)

    # --- Oversikt ---
    ws_over = wb.create_sheet("Oversikt")
    selected_accounts_txt = ", ".join(getattr(data, "selected_accounts", []) or [])
    df_scope = getattr(data, "df_scope", pd.DataFrame())
    konto_navn_map = infer_konto_navn_map(df_scope)

    # Kontroll/avstemming
    selected_sum = float(getattr(data, "selected_sum", 0.0) or 0.0)
    control_sum = float(getattr(data, "control_sum", 0.0) or 0.0)
    bilag_count = int(getattr(data, "bilag_count", 0) or 0)
    row_count = int(len(df_scope)) if df_scope is not None else 0
    direction = str(getattr(data, "selected_direction", "Alle") or "Alle")

    kv = [
        ("Retning (valgte kontoer)", direction),
        ("Valgte kontoer", selected_accounts_txt),
        ("Antall bilag i scope", bilag_count),
        ("Antall rader i scope", row_count),
        ("Sum valgte kontoer (retning)", selected_sum),
        ("Kontrollsum (sum alle linjer i scope)", control_sum),
        ("Merknad", "Motposter beregnes som komplementet til valgte linjer i samme bilag."),
    ]
    _write_kv_sheet(ws_over, "Oversikt", kv)
    # Number formats
    for r in range(1, ws_over.max_row + 1):
        k = ws_over.cell(row=r, column=1).value
        if k in ("Sum valgte kontoer (retning)", "Kontrollsum (sum alle linjer i scope)"):
            ws_over.cell(row=r, column=2).number_format = "#,##0.00"

    # --- Valgte kontoer (oversikt) ---
    ws_sel = wb.create_sheet("Valgte kontoer")
    df_selected = getattr(data, "df_selected", pd.DataFrame())
    if df_selected is None:
        df_selected = pd.DataFrame()

    df_sel_print = pd.DataFrame()
    if not df_selected.empty:
        df_sel_print = df_selected.copy()
        # Standardiser kolonnenavn
        if "Sum" in df_sel_print.columns:
            df_sel_print = df_sel_print.rename(columns={"Sum": "Sum valgte kontoer"})
        if "Kontonavn" not in df_sel_print.columns:
            df_sel_print["Kontonavn"] = df_sel_print.get("Konto", "").map(lambda k: konto_navn_map.get(str(k), ""))

        # Andel (0-1) basert på absolutt beløp
        try:
            total_abs = float(df_sel_print["Sum valgte kontoer"].astype(float).abs().sum())
        except Exception:
            total_abs = 0.0
        if total_abs:
            try:
                df_sel_print["Andel av valgt"] = df_sel_print["Sum valgte kontoer"].astype(float).abs() / total_abs
            except Exception:
                df_sel_print["Andel av valgt"] = 0.0
        else:
            df_sel_print["Andel av valgt"] = 0.0

        # Kolonneordre
        keep = [c for c in ["Konto", "Kontonavn", "Sum valgte kontoer", "Andel av valgt", "Antall bilag"] if c in df_sel_print.columns]
        df_sel_print = df_sel_print[keep]

        # Sorter etter absolutt beløp
        if "Sum valgte kontoer" in df_sel_print.columns:
            df_sel_print = df_sel_print.sort_values(by="Sum valgte kontoer", key=lambda s: s.astype(float).abs(), ascending=False)

    _write_df_table(ws_sel, df_sel_print, f"Valgte kontoer ({direction})")

    # --- Kombinasjoner (med summer) ---
    ws_combo = wb.create_sheet("Kombinasjoner")
    df_combos = build_combo_totals_df(
        df_scope,
        list(getattr(data, "selected_accounts", []) or []),
        selected_direction=direction,
    )

    if not df_combos.empty:
        df_combos = df_combos.copy()

        # Legg til kontonavn for kombinasjonen (lesbarhet i revisjonsdokumentasjon)
        try:
            uniq = df_combos["Kombinasjon"].astype(str).fillna("").unique().tolist()
            combo_name_map = {c: combo_display_name(c, konto_navn_map) for c in uniq if str(c).strip()}
            df_combos.insert(
                list(df_combos.columns).index("Kombinasjon") + 1,
                "Kombinasjon (navn)",
                df_combos["Kombinasjon"].astype(str).map(lambda c: combo_name_map.get(str(c).strip(), "")),
            )
        except Exception:
            pass

        df_combos["Status"] = df_combos["Kombinasjon"].map(lambda c: status_label(status_map.get(str(c), ""), neutral_label="Umerket"))

        # Sorter så Outlier kommer først (stabil)
        df_combos["_status_order"] = df_combos["Kombinasjon"].map(lambda c: status_sort_key(status_map.get(str(c), "")))
        df_combos = df_combos.sort_values(
            by=["_status_order", "Antall bilag", "Kombinasjon #"],
            ascending=[True, False, True],
        ).drop(columns=["_status_order"])

    _write_df_table(ws_combo, df_combos, "Kombinasjoner")

    # Fargekoding av rader i kombinasjonstabellen (best effort)
    try:
        if df_combos is not None and not df_combos.empty and "Status" in df_combos.columns:
            status_col = list(df_combos.columns).index("Status") + 1
            start_row = 4  # data starter etter tittel(1) + blank(2) + header(3)
            end_row = start_row + len(df_combos) - 1
            fill_expected = PatternFill("solid", fgColor="C6EFCE")
            fill_outlier = PatternFill("solid", fgColor="FFF2CC")
            for r in range(start_row, end_row + 1):
                v = ws_combo.cell(row=r, column=status_col).value
                if v == "Forventet":
                    fill = fill_expected
                elif v == "Outlier":
                    fill = fill_outlier
                else:
                    continue
                for c in range(1, len(df_combos.columns) + 1):
                    ws_combo.cell(row=r, column=c).fill = fill
    except Exception:
        pass

    # --- Oppsummering status ---
    ws_stat = wb.create_sheet("Oppsummering status")
    df_status = summarize_status_df(df_combos, status_map)
    _write_df_table(ws_stat, df_status, "Oppsummering status")

    # --- Outlier – Full bilagsutskrift ---
    ws_out = wb.create_sheet("Outlier – Full bilagsutskrift")
    outlier_combos_list = [c for c, v in status_map.items() if normalize_combo_status(v) == STATUS_OUTLIER]

    df_out, bilag_to_combo, out_bilag, excluded_blank = extract_full_bilag_for_outlier_combos(
        df_scope,
        list(getattr(data, "selected_accounts", []) or []),
        outlier_combos_list,
        include_blank_bilag=False,
    )

    if df_out is None or df_out.empty:
        _write_df_table(ws_out, pd.DataFrame(), "Outlier – Full bilagsutskrift")
        note = "Ingen outlier-kombinasjoner er markert, eller ingen bilag kunne hentes."
        _set_cell(ws_out, 4, 1, note)
        if excluded_blank:
            _set_cell(
                ws_out,
                6,
                1,
                f"NB: {excluded_blank} bilag-grupper uten bilagsnummer er ekskludert fra full bilagsutskrift.",
            )
    else:
        df_out = df_out.copy()
        if "Bilag_str" not in df_out.columns and "Bilag" in df_out.columns:
            df_out["Bilag_str"] = df_out["Bilag"].map(_bilag_str)
        if "Konto_str" not in df_out.columns and "Konto" in df_out.columns:
            df_out["Konto_str"] = df_out["Konto"].map(_konto_str)

        df_out["Kombinasjon"] = df_out["Bilag_str"].map(lambda b: bilag_to_combo.get(str(b), ""))
        # Kontonavn pr kombinasjon (best effort – kan være tomt dersom navn ikke finnes)
        try:
            uniq2 = df_out["Kombinasjon"].astype(str).fillna("").unique().tolist()
            combo_name_map2 = {c: combo_display_name(c, konto_navn_map) for c in uniq2 if str(c).strip()}
            df_out["Kombinasjon (navn)"] = df_out["Kombinasjon"].astype(str).map(lambda c: combo_name_map2.get(str(c).strip(), ""))
        except Exception:
            df_out["Kombinasjon (navn)"] = ""
        df_out["Status"] = "Outlier"

        belop = df_out["Beløp"].astype(float) if "Beløp" in df_out.columns else 0.0
        if "Beløp" not in df_out.columns:
            df_out["Beløp"] = belop

        df_out["Debet"] = belop.where(belop > 0, 0.0)
        df_out["Kredit"] = (-belop).where(belop < 0, 0.0)

        # Velg kolonner (bruk det vi har)
        cols = [
            "Status",
            "Kombinasjon",
            "Kombinasjon (navn)",
            "Bilag_str",
        ]
        if "Dato" in df_out.columns:
            cols.append("Dato")
        if "Tekst" in df_out.columns:
            cols.append("Tekst")
        cols += [
            "Konto_str",
        ]
        if "Kontonavn" in df_out.columns:
            cols.append("Kontonavn")
        cols += ["Debet", "Kredit", "Beløp"]

        df_print = df_out[cols].rename(
            columns={
                "Bilag_str": "Bilag",
                "Konto_str": "Konto",
            }
        )

        # Sortering
        sort_cols = ["Bilag"]
        if "Dato" in df_print.columns:
            sort_cols.append("Dato")
        sort_cols.append("Konto")
        df_print = df_print.sort_values(sort_cols, ascending=True, kind="mergesort")

        _write_df_table(ws_out, df_print, "Outlier – Full bilagsutskrift")

        # Merknad om blank bilag (hvis ekskludert)
        if excluded_blank:
            # Find next empty row after table
            r = ws_out.max_row + 2
            _set_cell(
                ws_out,
                r,
                1,
                f"NB: {excluded_blank} bilag-grupper uten bilagsnummer er ekskludert fra full bilagsutskrift.",
            )

        # Date format
        if "Dato" in df_print.columns:
            # Find column index
            col_idx = list(df_print.columns).index("Dato") + 1
            for r in range(4, ws_out.max_row + 1):
                ws_out.cell(row=r, column=col_idx).number_format = "dd.mm.yyyy"

    return wb

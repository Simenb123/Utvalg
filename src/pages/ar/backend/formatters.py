"""page_ar_formatters.py — formattere og hjelpere for AR-fanen.

Utskilt fra page_ar.py. Rene funksjoner uten klassestate. page_ar
re-eksporterer navnene for bakoverkompatibilitet (tester importerer
_build_owned_help_text fra page_ar).
"""

from __future__ import annotations

from typing import Any


def _fmt_pct(value: object) -> str:
    try:
        pct = float(value or 0.0)
    except Exception:
        pct = 0.0
    return f"{pct:.2f}".replace(".", ",")


def _fmt_optional_pct(value: object) -> str:
    if value in (None, ""):
        return "-"
    return _fmt_pct(value)


def _parse_float(value: object) -> float:
    text = str(value or "").strip().replace(" ", "").replace("\u00a0", "")
    if not text:
        return 0.0
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    return float(text)


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _relation_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "datter":
        return "Datter"
    if text == "tilknyttet":
        return "Tilknyttet"
    if text == "investering":
        return "Investering"
    if text == "vurder":
        return "Vurder"
    return text or "-"


def _source_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "register":
        return "Register"
    if text == "accepted_register":
        return "Godkjent register"
    if text == "carry_forward":
        return "Videreført"
    if text == "manual":
        return "Manuell"
    if text == "manual_override":
        return "Register + manuell"
    return text or "-"


def _fmt_thousand(n: object) -> str:
    try:
        value = int(n or 0)
    except Exception:
        return str(n or "")
    return f"{value:,}".replace(",", "\u00a0")


def _fmt_signed_thousand(n: object) -> str:
    try:
        value = int(n or 0)
    except Exception:
        return str(n or "")
    if value > 0:
        return f"+{_fmt_thousand(value)}"
    if value < 0:
        return f"\u2212{_fmt_thousand(-value)}"
    return "0"


def _fmt_currency(v: object) -> str:
    try:
        value = float(v or 0.0)
    except Exception:
        return str(v or "")
    if value == 0:
        return ""
    sign = "-" if value < 0 else ""
    abs_val = abs(value)
    whole, frac = divmod(round(abs_val * 100), 100)
    whole_str = f"{int(whole):,}".replace(",", "\u00a0")
    return f"{sign}{whole_str},{int(frac):02d}"


def _compare_change_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "new":
        return "Ny"
    if text == "removed":
        return "Borte"
    if text == "changed":
        return "Endret"
    if text == "unchanged":
        return "Uendret"
    return text or "-"


def _change_type_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "added":
        return "Ny i register"
    if text == "removed":
        return "Mangler i register"
    if text == "changed":
        return "Endret"
    if text == "owner_overwrite":
        return "Eier: register vs manuell"
    if text == "owner_restored":
        return "Eier: gjenopprettet i register"
    return text or "-"


def _relation_fill(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "datter":
        return "#DBF5E8"
    if text == "tilknyttet":
        return "#FFF2D6"
    if text == "investering":
        return "#E7EEFF"
    if text == "vurder":
        return "#F2F4F7"
    return "#F8FAFC"


def _relation_accent(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "datter":
        return "#1F7A4D"
    if text == "tilknyttet":
        return "#B26B00"
    if text == "investering":
        return "#2952A3"
    if text == "vurder":
        return "#667085"
    return "#98A2B3"


def _build_owned_help_text(row: dict[str, Any] | None, *, year: str, accepted_meta: dict[str, Any] | None) -> str:
    if not row:
        return (
            "Velg en rad for Ã¥ se hva eierskapet betyr, hvilken kilde som brukes, "
            "og om raden kan sendes videre til konsolidering."
        )

    company_name = _safe_text(row.get("company_name")) or "ukjent selskap"
    pct_text = _fmt_pct(row.get("ownership_pct"))
    relation = _relation_label(row.get("relation_type"))
    source = _safe_text(row.get("source"))
    accepted_meta = accepted_meta or {}

    parts = [f"Klienten eier {pct_text} % av {company_name}. Klassifisering: {relation}."]

    if source == "carry_forward":
        source_year = _safe_text(accepted_meta.get("source_year"))
        if source_year:
            parts.append(f"Raden er viderefÃ¸rt fra akseptert eierstatus {source_year}.")
        else:
            parts.append("Raden er viderefÃ¸rt fra tidligere akseptert eierstatus.")
    elif source == "accepted_register":
        source_year = _safe_text(accepted_meta.get("register_year")) or year
        parts.append(f"Raden bygger pÃ¥ godkjent aksjonÃ¦rregister {source_year}.")
    elif source == "manual_override":
        parts.append("Raden er manuelt overstyrt og brukes foran registeret til nye endringer eventuelt godkjennes.")
    elif source == "manual":
        parts.append("Raden er lagt inn manuelt fordi eierskapet ikke finnes i registergrunnlaget ennÃ¥.")

    matched_client = _safe_text(row.get("matched_client"))
    if matched_client:
        if row.get("has_active_sb"):
            parts.append(f"Klientmatch funnet: {matched_client}, og aktiv SB finnes for {year}.")
        else:
            parts.append(f"Klientmatch funnet: {matched_client}, men aktiv SB mangler for {year}.")
    else:
        parts.append("Ingen klientmatch pÃ¥ org.nr ennÃ¥.")

    return " ".join(parts)


def _ar_sheet_respecting_displaycolumns(_xls, tree, *, title: str, heading: str) -> dict:
    """Build sheet dict from a Treeview, filtering to its current displaycolumns."""
    sheet = _xls.treeview_to_sheet(tree, title=title, heading=heading)
    try:
        all_cols = list(tree["columns"])
        dc = tree.cget("displaycolumns")
        if isinstance(dc, str):
            dc_list = [dc]
        else:
            dc_list = list(dc or [])
        if not dc_list or dc_list == ["#all"]:
            return sheet
        keep_idx = [all_cols.index(c) for c in dc_list if c in all_cols]
        if not keep_idx:
            return sheet
        cols = sheet.get("columns") or []
        sheet["columns"] = [cols[i] for i in keep_idx if i < len(cols)]
        new_rows = []
        for row in sheet.get("rows") or []:
            vals = row.get("values") or []
            row = dict(row)
            row["values"] = [vals[i] for i in keep_idx if i < len(vals)]
            new_rows.append(row)
        sheet["rows"] = new_rows
    except Exception:
        pass
    return sheet


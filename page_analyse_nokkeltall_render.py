"""page_analyse_nokkeltall_render.py — inline Nøkkeltall-rendering.

Utskilt fra page_analyse.py. Rendrer NokkeltallResult til en Text-widget
med temafarger og BRREG-sammenligning. page_analyse re-eksporterer navnene
for bakoverkompatibilitet (f.eks. analyse_drilldown.py importerer _nk_write
og _nk_render fra page_analyse).
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Nøkkeltall inline rendering helpers
# ---------------------------------------------------------------------------

def _nk_write(widget, msg: str) -> None:
    """Skriv enkel tekstmelding til nk_text-widgeten."""
    try:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", msg)
        widget.configure(state="disabled")
    except Exception:
        pass


def _nk_render(widget, result, *, brreg_data: dict | None = None) -> None:  # noqa: ANN001
    """Rendrer NokkeltallResult til nk_text-widgeten med formattering."""
    try:
        widget.configure(state="normal")
        widget.delete("1.0", "end")

        # Tema-farger (synkronisert med theme.py)
        _FG      = "#1F2430"
        _ACCENT  = "#2F6D62"
        _MUTED   = "#667085"
        _BORDER  = "#D7D1C7"
        _VAL_FG  = "#1A4D44"
        _PREV_FG = "#8B8680"
        _POS     = "#2E7D32"
        _NEG     = "#C62828"
        _NA      = "#B0A99A"
        _KPI_BG  = "#F0FAF7"
        _BRREG_FG = "#6B4C8A"  # lilla for BRREG-tall

        # Sett opp tags
        widget.tag_configure("title",
            font=("Segoe UI Semibold", 13), foreground=_FG, spacing3=1)
        widget.tag_configure("subtitle",
            font=("Segoe UI", 9), foreground=_MUTED, spacing3=6)
        widget.tag_configure("section",
            font=("Segoe UI Semibold", 10), foreground=_ACCENT,
            spacing1=10, spacing3=2)
        widget.tag_configure("sep", foreground=_BORDER)
        widget.tag_configure("col_header",
            font=("Segoe UI Semibold", 9), foreground=_MUTED)
        widget.tag_configure("label",
            font=("Segoe UI", 10), foreground=_FG)
        widget.tag_configure("val",
            font=("Consolas", 10), foreground=_VAL_FG)
        widget.tag_configure("val_prev",
            font=("Consolas", 10), foreground=_PREV_FG)
        widget.tag_configure("val_brreg",
            font=("Consolas", 10), foreground=_BRREG_FG)
        widget.tag_configure("bold_label",
            font=("Segoe UI Semibold", 10), foreground=_FG)
        widget.tag_configure("bold_val",
            font=("Consolas", 10, "bold"), foreground=_VAL_FG)
        widget.tag_configure("pos_chg",
            font=("Consolas", 9), foreground=_POS)
        widget.tag_configure("neg_chg",
            font=("Consolas", 9), foreground=_NEG)
        widget.tag_configure("na",
            font=("Segoe UI", 10), foreground=_NA)
        widget.tag_configure("kpi_label",
            font=("Segoe UI", 10), foreground=_MUTED)
        widget.tag_configure("kpi_val",
            font=("Segoe UI Semibold", 12), foreground=_VAL_FG,
            spacing1=1, spacing3=0)
        widget.tag_configure("kpi_chg",
            font=("Segoe UI", 9), spacing3=4)
        widget.tag_configure("brreg_label",
            font=("Segoe UI", 8), foreground=_BRREG_FG)

        # Tittel
        title = "Nøkkeltall"
        widget.insert("end", title + "\n", "title")
        sub_parts = []
        if result.client:
            sub_parts.append(result.client)
        if result.year:
            sub_parts.append(f"Regnskapsår {result.year}")
        if sub_parts:
            widget.insert("end", "  ".join(sub_parts) + "\n", "subtitle")
        widget.insert("end", "─" * 70 + "\n", "sep")

        # --- KPI-kort (visuelt fremhevede) ---
        widget.insert("end", "Sentrale nøkkeltall\n", "section")
        has_kpi = False
        for card in result.kpi_cards:
            has_kpi = True
            label = str(card.get("label", ""))
            formatted = str(card.get("formatted", "–"))
            chg = card.get("change_pct")
            widget.insert("end", f"  {label}\n", "kpi_label")
            widget.insert("end", f"  {formatted}", "kpi_val")
            if chg is not None:
                arrow = "▲" if chg >= 0 else "▼"
                chg_str = f"  {arrow} {abs(chg):.1f} %"
                tag = "pos_chg" if chg >= 0 else "neg_chg"
                widget.insert("end", chg_str, tag)
            widget.insert("end", "\n", "kpi_chg")
        if not has_kpi:
            widget.insert("end", "  Ingen data tilgjengelig\n", "na")
        widget.insert("end", "\n")

        # --- Nøkkeltall-tabell (Lønnsomhet, Likviditet, Soliditet, Effektivitet) ---
        categories = {}
        for m in result.metrics:
            categories.setdefault(m.category, []).append(m)

        for cat, items in categories.items():
            any_data = any(m.value is not None for m in items)
            if not any_data:
                continue
            widget.insert("end", f"{cat}\n", "section")
            widget.insert("end", "─" * 50 + "\n", "sep")
            for m in items:
                if m.value is None:
                    continue
                widget.insert("end", f"  {m.label:<38}", "label")
                widget.insert("end", f"{m.formatted:>12}", "val")
                if result.has_prev_year and m.prev_value is not None:
                    widget.insert("end", f"  {m.formatted_prev:>10}", "val_prev")
                    chg = m.change_pct
                    if chg is not None:
                        arrow = "▲" if chg >= 0 else "▼"
                        tag = "pos_chg" if chg >= 0 else "neg_chg"
                        widget.insert("end", f"  {arrow}{abs(chg):.1f}%", tag)
                widget.insert("end", "\n")
            widget.insert("end", "\n")

        # --- Resultatregnskap ---
        has_brreg = brreg_data is not None
        if result.pl_summary:
            widget.insert("end", "Resultatregnskap\n", "section")
            widget.insert("end", "─" * 70 + "\n", "sep")
            header = f"  {'':38}{'I år':>14}"
            if result.has_prev_year:
                header += f"{'Fjor':>14}{'Endring':>12}"
            elif has_brreg:
                header += f"{'BRREG':>14}{'Endring':>12}"
            widget.insert("end", header + "\n", "col_header")
            for row in result.pl_summary:
                is_sum = row.get("is_sum", False)
                label_tag = "bold_label" if is_sum else "label"
                val_tag = "bold_val" if is_sum else "val"
                name = str(row.get("name", ""))
                formatted = str(row.get("formatted", "–"))
                widget.insert("end", f"  {name:<38}", label_tag)
                widget.insert("end", f"{formatted:>14}", val_tag)
                if result.has_prev_year:
                    prev_fmt = row.get("prev_formatted") or "–"
                    widget.insert("end", f"{prev_fmt:>14}", "val_prev")
                    chg_amt = row.get("change_amount_formatted")
                    if chg_amt:
                        chg = row.get("change_amount", 0) or 0
                        tag = "pos_chg" if chg >= 0 else "neg_chg"
                        widget.insert("end", f"{chg_amt:>12}", tag)
                elif has_brreg:
                    _nk_insert_brreg_pl_comparison(widget, row, brreg_data)
                widget.insert("end", "\n")

        # --- Balanse ---
        if result.bs_summary:
            widget.insert("end", "\nBalanse\n", "section")
            widget.insert("end", "─" * 70 + "\n", "sep")
            header = f"  {'':38}{'I år':>14}"
            if result.has_prev_year:
                header += f"{'Fjor':>14}{'Endring':>12}"
            elif has_brreg:
                header += f"{'BRREG':>14}{'Endring':>12}"
            widget.insert("end", header + "\n", "col_header")
            for row in result.bs_summary:
                is_sum = row.get("is_sum", False)
                label_tag = "bold_label" if is_sum else "label"
                val_tag = "bold_val" if is_sum else "val"
                name = str(row.get("name", ""))
                formatted = str(row.get("formatted", "–"))
                widget.insert("end", f"  {name:<38}", label_tag)
                widget.insert("end", f"{formatted:>14}", val_tag)
                if result.has_prev_year:
                    prev_fmt = row.get("prev_formatted") or "–"
                    widget.insert("end", f"{prev_fmt:>14}", "val_prev")
                    chg_amt = row.get("change_amount_formatted")
                    if chg_amt:
                        chg = row.get("change_amount", 0) or 0
                        tag = "pos_chg" if chg >= 0 else "neg_chg"
                        widget.insert("end", f"{chg_amt:>12}", tag)
                elif has_brreg:
                    _nk_insert_brreg_bs_comparison(widget, row, brreg_data)
                widget.insert("end", "\n")

        # BRREG-merknad
        if has_brreg:
            brreg_year = brreg_data.get("regnskapsaar", "")
            widget.insert("end", f"\n  BRREG-tall fra regnskapsåret {brreg_year}\n", "brreg_label")

        widget.configure(state="disabled")
    except Exception as exc:
        try:
            widget.configure(state="disabled")
        except Exception:
            pass
        log.warning("_nk_render error: %s", exc)


# Mapping fra pl_summary-radnavn → BRREG-nøkkel
_PL_BRREG_MAP: dict[str, str] = {
    "Driftsinntekter": "driftsinntekter",
    "Sum driftsinntekter": "driftsinntekter",
    "Driftskostnader": "driftskostnader",
    "Sum driftskostnader": "driftskostnader",
    "Driftsresultat": "driftsresultat",
    "Finansinntekter": "finansinntekter",
    "Finanskostnader": "finanskostnader",
    "Netto finans": "netto_finans",
    "Resultat før skatt": "resultat_for_skatt",
    "Årsresultat": "aarsresultat",
}

_BS_BRREG_MAP: dict[str, str] = {
    "Sum anleggsmidler": "sum_anleggsmidler",
    "Anleggsmidler": "sum_anleggsmidler",
    "Sum omløpsmidler": "sum_omloepsmidler",
    "Omløpsmidler": "sum_omloepsmidler",
    "Sum eiendeler": "sum_eiendeler",
    "Eiendeler": "sum_eiendeler",
    "Sum egenkapital": "sum_egenkapital",
    "Egenkapital": "sum_egenkapital",
    "Langsiktig gjeld": "langsiktig_gjeld",
    "Kortsiktig gjeld": "kortsiktig_gjeld",
    "Sum gjeld": "sum_gjeld",
}


def _fmt_amount(v: float | None) -> str:
    if v is None:
        return "–"
    if abs(v) >= 1e6:
        return f"{v / 1e6:,.1f} M".replace(",", " ")
    if abs(v) >= 1e3:
        return f"{v / 1e3:,.0f} k".replace(",", " ")
    return f"{v:,.0f}".replace(",", " ")


def _nk_insert_brreg_pl_comparison(widget, row: dict, brreg: dict) -> None:
    name = str(row.get("name", ""))
    brreg_key = _PL_BRREG_MAP.get(name)
    if not brreg_key:
        return
    brreg_val = brreg.get(brreg_key)
    if brreg_val is None:
        return
    widget.insert("end", f"{_fmt_amount(brreg_val):>14}", "val_brreg")
    current = row.get("value")
    if current is not None and abs(brreg_val) > 1e-9:
        chg_pct = ((current - brreg_val) / abs(brreg_val)) * 100
        arrow = "▲" if chg_pct >= 0 else "▼"
        tag = "pos_chg" if chg_pct >= 0 else "neg_chg"
        widget.insert("end", f"  {arrow}{abs(chg_pct):.1f}%", tag)


def _nk_insert_brreg_bs_comparison(widget, row: dict, brreg: dict) -> None:
    name = str(row.get("name", ""))
    brreg_key = _BS_BRREG_MAP.get(name)
    if not brreg_key:
        return
    brreg_val = brreg.get(brreg_key)
    if brreg_val is None:
        return
    widget.insert("end", f"{_fmt_amount(brreg_val):>14}", "val_brreg")
    current = row.get("value")
    if current is not None and abs(brreg_val) > 1e-9:
        chg_pct = ((current - brreg_val) / abs(brreg_val)) * 100
        arrow = "▲" if chg_pct >= 0 else "▼"
        tag = "pos_chg" if chg_pct >= 0 else "neg_chg"
        widget.insert("end", f"  {arrow}{abs(chg_pct):.1f}%", tag)


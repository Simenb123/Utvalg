"""nokkeltall_report.py — Generer HTML-rapport med nøkkeltall og SVG-charts.

Bruker string.Template (stdlib) — ingen jinja2/weasyprint dependency.
Rapporten kan åpnes i browser eller skrives ut som PDF.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path
from string import Template

import pandas as pd

from .engine import (
    NokkeltallObservation,
    NokkeltallResult,
    ReskontroRow,
    compute_nokkeltall,
)
from .svg import (
    svg_donut,
    svg_hbar,
    svg_kpi_card,
    svg_vbar,
)


# Fargepaletter brukt i både vannfall-diagram og resultatsammensetning.
# Samme kategori → samme farge i begge visninger så brukeren lett kan koble
# dem sammen. Annen driftskostnad bruker brun for ikke å forveksles med
# driftsresultat (grønn).
_CATEGORY_COLORS = {
    "inntekt":      "#4472C4",  # blå — driftsinntekter
    "varekost":     "#ED7D31",  # oransje — RL 20
    "lonn":         "#8FAADC",  # lyseblå — RL 40
    "avskriv":      "#FFC000",  # gul — RL 50
    "annen_drift":  "#A66B2B",  # brun — RL 70
    "driftsres":    "#70AD47",  # grønn — driftsresultat (positivt)
    "driftstap":    "#E74C3C",  # rød — driftstap (negativt)
    "finans_pos":   "#2E8B57",  # sjøgrønn — netto finans positiv
    "finans_neg":   "#B94A48",  # rust — netto finans negativ
    "skatt":        "#7F7F7F",  # grå — skattekostnad
    "arsres":       "#1F4E79",  # mørk blå — årsresultat
}


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
@page { size: A4 landscape; margin: 5mm 8mm; }
body {
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    color: #2c3e50;
    background: #f8f9fa;
    line-height: 1.4;
    font-size: 12px;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}
.page {
    background: white;
    max-width: 1100px;
    margin: 20px auto;
    padding: 36px 44px;
    border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    page-break-before: always;
}
.page:first-child { page-break-before: auto; }
@media print {
    body { background: white; margin: 0; padding: 0; font-size: 9px; }
    .page { box-shadow: none; margin: 0; padding: 6mm 8mm; border-radius: 0; max-width: none; overflow: hidden; }
    .no-print { display: none !important; }
    .report-header { border-bottom-color: #4472C4; padding-bottom: 4px; margin-bottom: 6px; }
    .report-title { font-size: 14px; }
    .report-subtitle { font-size: 9px; }
    .section-title { margin: 4px 0 2px 0; font-size: 10px; padding-bottom: 1px; }
    .data-table { font-size: 8px; margin-bottom: 2px; page-break-inside: avoid; break-inside: avoid; }
    .data-table td { padding: 1px 5px; }
    .data-table th { padding: 2px 5px; font-size: 7px; }
    .data-table .cat-header { padding-top: 3px; }
    .kpi-grid { gap: 6px; margin-bottom: 6px; }
    .kpi-card { padding: 4px 6px; }
    .kpi-value { font-size: 12px; }
    .kpi-label { font-size: 7px; }
    .chart-row { gap: 10px; margin: 2px 0; page-break-inside: avoid; break-inside: avoid; }
    .chart-label { font-size: 8px; margin-bottom: 1px; }
    .chart-box svg { max-height: 150px; }
    .activity-grid { page-break-inside: avoid; break-inside: avoid; gap: 6px; margin-top: 2px; }
    .activity-card { padding: 6px 8px; }
    .activity-card .ac-title { font-size: 9px; }
    .activity-card .ac-value { font-size: 11px; }
    .activity-card .ac-detail { font-size: 8px; }
    .report-footer { margin-top: 4px; }
}

/* Header */
.report-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 3px solid #4472C4;
    padding-bottom: 6px;
    margin-bottom: 12px;
}
.report-header .title-wrap {
    display: flex; align-items: baseline; gap: 12px;
    flex-wrap: wrap;
}
.report-title { font-size: 20px; font-weight: 700; color: #1a1a2e; }
.report-subtitle { font-size: 12px; color: #7f8c8d; }
.report-header .title-wrap .report-subtitle::before {
    content: "— "; color: #bfc6cc;
}

/* Section */
.section-title {
    font-size: 14px;
    font-weight: 700;
    color: #4472C4;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 22px 0 10px 0;
    padding-bottom: 3px;
    border-bottom: 1px solid #e8ecf1;
}
.section-title:first-child { margin-top: 0; }

/* KPI cards */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
}
.kpi-card {
    background: #f0f4f8;
    border-radius: 8px;
    padding: 12px 14px;
    text-align: center;
    border-left: 4px solid #4472C4;
}
.kpi-label { font-size: 10px; color: #7f8c8d; text-transform: uppercase; letter-spacing: 0.3px; margin-bottom: 3px; }
.kpi-value { font-size: 18px; font-weight: 700; color: #1a1a2e; margin-bottom: 2px; }

/* Tables */
.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
    margin-bottom: 12px;
}
.data-table th {
    background: #f0f4f8;
    color: #4472C4;
    font-weight: 600;
    text-align: left;
    padding: 6px 10px;
    border-bottom: 2px solid #d5dde5;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}
.data-table td {
    padding: 4px 10px;
    border-bottom: 1px solid #eef1f5;
}
.data-table tr:hover { background: #fafbfc; }
.data-table .num { text-align: right; font-variant-numeric: tabular-nums;
                    white-space: nowrap; }
.data-table .sum-row { font-weight: 700; background: #f6f8fb; }
.data-table .cat-header {
    font-weight: 600;
    color: #4472C4;
    background: #f8fafc;
    padding-top: 8px;
}
.change-pos { color: #27AE60; font-weight: 600; }
.change-neg { color: #E74C3C; font-weight: 600; }

/* Chart containers */
.chart-row {
    display: flex;
    gap: 28px;
    align-items: flex-start;
    flex-wrap: wrap;
    margin: 12px 0;
}
.chart-box {
    flex: 1;
    min-width: 240px;
}
.chart-label {
    font-size: 11px;
    font-weight: 600;
    color: #555;
    margin-bottom: 6px;
}

/* Activity cards */
.activity-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 12px;
    margin-top: 8px;
}
.activity-card {
    background: #fafbfc;
    border: 1px solid #e8ecf1;
    border-radius: 8px;
    padding: 12px 16px;
}
.activity-card .ac-title { font-weight: 600; font-size: 12px; color: #1a1a2e; }
.activity-card .ac-detail { font-size: 11px; color: #7f8c8d; margin-top: 3px; }
.activity-card .ac-value { font-size: 16px; font-weight: 700; color: #4472C4; margin-top: 2px; }

/* Footer */
.report-footer {
    font-size: 9px;
    color: #aaa;
    text-align: right;
    margin-top: 12px;
    padding-top: 6px;
    border-top: 1px solid #eef1f5;
}

/* Standardvurderinger (observasjonskort) */
.obs-note { font-size: 10px; color: #667085;
            margin: 2px 0 8px; font-style: italic; }
.obs-category { font-size: 10.5px; font-weight: 600; color: #475467;
                text-transform: uppercase; letter-spacing: 0.04em;
                margin: 10px 0 6px; }
.obs-category:first-child { margin-top: 0; }
.obs-grid { display: grid; grid-template-columns: repeat(3, 1fr);
            gap: 8px; margin-bottom: 4px; }
.obs-card { border: 1px solid #e5e7eb; border-left: 4px solid #98a2b3;
            border-radius: 6px; padding: 6px 10px; background: #fff;
            page-break-inside: avoid; }
.obs-critical { border-left-color: #dc2626; background: #fef2f2; }
.obs-watch    { border-left-color: #f59e0b; background: #fffbeb; }
.obs-ok       { border-left-color: #16a34a; background: #f0fdf4; }
.obs-label    { font-size: 9.5px; color: #475467;
                text-transform: uppercase; letter-spacing: 0.02em; }
.obs-row      { display: flex; justify-content: space-between;
                align-items: baseline; gap: 8px; margin-top: 1px; }
.obs-value    { font-size: 15px; font-weight: 700; color: #101828;
                font-variant-numeric: tabular-nums; white-space: nowrap; }
.obs-bench    { font-size: 9.5px; color: #667085; white-space: nowrap; }

/* Side 4 — Aktivitet & endringer */
.activity-table { width: 100%; border-collapse: collapse;
                  font-size: 11px; margin-top: 4px; }
.activity-table th { text-align: left; font-weight: 600;
                     font-size: 9.5px; color: #667085;
                     text-transform: uppercase; letter-spacing: 0.04em;
                     border-bottom: 1px solid #e5e7eb;
                     padding: 6px 8px; }
.activity-table th.num { text-align: right; }
.activity-table td { padding: 6px 8px;
                     border-bottom: 1px solid #f2f4f7; }
.activity-table td.num { text-align: right;
                         font-variant-numeric: tabular-nums; }
.activity-table .bar-cell { width: 140px; padding-right: 10px; }
.activity-table .bar-wrap { height: 10px; background: #f2f4f7;
                            border-radius: 3px; overflow: hidden; }
.activity-table .bar-fill { height: 100%; background: #4472C4; }
.changes-row { display: grid; grid-template-columns: 1fr 1fr;
               gap: 16px; margin-top: 8px; }
.change-panel { border: 1px solid #e5e7eb; border-radius: 8px;
                padding: 10px 12px; background: #fff; }
.change-panel h4 { margin: 0 0 8px; font-size: 11px;
                   text-transform: uppercase; letter-spacing: 0.04em;
                   color: #475467; }
.change-row { display: grid;
              grid-template-columns: 1fr 110px 50px;
              align-items: center; gap: 8px;
              padding: 4px 0;
              border-bottom: 1px solid #f2f4f7; font-size: 10.5px; }
.change-row:last-child { border-bottom: none; }
.change-row .cr-name { color: #101828; overflow: hidden;
                       text-overflow: ellipsis; white-space: nowrap; }
.change-row .cr-amount { text-align: right;
                         font-variant-numeric: tabular-nums;
                         font-weight: 600; white-space: nowrap; }
.change-row .cr-bar { height: 8px; background: #f2f4f7;
                      border-radius: 2px; overflow: hidden; }
.change-row .cr-bar span { display: block; height: 100%; }
.change-inc .cr-amount { color: #16a34a; }
.change-inc .cr-bar span { background: #16a34a; }
.change-dec .cr-amount { color: #dc2626; }
.change-dec .cr-bar span { background: #dc2626; }
.conc-grid { display: grid; grid-template-columns: repeat(3, 1fr);
             gap: 10px; margin-top: 10px; }
.conc-card { border: 1px solid #e5e7eb; border-radius: 8px;
             padding: 12px 14px; background: #fff;
             page-break-inside: avoid; }
.conc-label { font-size: 10px; text-transform: uppercase;
              letter-spacing: 0.04em; color: #475467; }
.conc-value { font-size: 22px; font-weight: 700; color: #101828;
              margin-top: 4px; font-variant-numeric: tabular-nums; }
.conc-detail { font-size: 10px; color: #667085; margin-top: 2px; }

/* Reskontro — kunder og leverandører */
.resk-grid { display: grid; grid-template-columns: 1fr 1fr;
             gap: 16px 14px; margin-top: 6px; }
.resk-section { position: relative;
                page-break-inside: avoid;
                background: #fff;
                border: 1px solid #eef1f5;
                border-radius: 8px;
                padding: 14px 10px 12px;
                overflow: hidden; }
.resk-accent { position: absolute; top: 0; left: 0; right: 0;
               height: 3px; }
.resk-kunder .resk-accent { background: #2e5eaa; }
.resk-lev    .resk-accent { background: #c4691a; }
.resk-section h4 { margin: 0 0 10px; font-size: 11px;
                   font-weight: 700;
                   text-transform: uppercase; letter-spacing: 0.06em;
                   color: #344054; }
.resk-kunder h4 { color: #2e5eaa; }
.resk-lev    h4 { color: #c4691a; }
.resk-table { width: 100%; border-collapse: collapse;
              font-size: 11px; }
.resk-table th { text-align: left; font-weight: 600;
                 font-size: 9px; color: #98a2b3;
                 text-transform: uppercase; letter-spacing: 0.06em;
                 border-bottom: 1px solid #e5e7eb;
                 padding: 4px 4px 6px; white-space: nowrap; }
.resk-table th.num { text-align: right; }
.resk-table th.rank-col { width: 20px; padding-left: 0; padding-right: 3px; }
.resk-table tbody tr:nth-child(even) { background: #fafbfc; }
.resk-table td { padding: 7px 4px;
                 border-bottom: 1px solid #f2f4f7;
                 vertical-align: middle; }
.resk-table tbody tr:last-child td { border-bottom: none; }
.resk-table td.num { text-align: right;
                     font-variant-numeric: tabular-nums;
                     white-space: nowrap;
                     font-size: 10px; }
.resk-table td.num-sec { color: #667085; font-size: 9.5px; }
.resk-table td.num-main { color: #101828;
                          position: relative;
                          padding-left: 8px; padding-right: 4px;
                          min-width: 70px; }
.resk-table th.num-main { color: #344054; padding-right: 4px; }
.resk-table td.num-main .num-main-txt { position: relative;
                                         font-weight: 700;
                                         font-size: 10.5px;
                                         display: inline-block; }
.resk-table td.num-main .bar-bg { position: absolute;
                                   left: 6px; right: 3px;
                                   bottom: 2px; height: 3px;
                                   background: #f2f4f7;
                                   border-radius: 2px;
                                   overflow: hidden; }
.resk-table td.num-main .bar-fill { display: block; height: 100%;
                                     border-radius: 2px;
                                     float: right; }
.resk-kunder td.num-main .bar-fill { background: #4a7dc6; }
.resk-lev    td.num-main .bar-fill { background: #e08a3c; }
.resk-table td.rank-col { padding-left: 0; padding-right: 3px;
                          width: 20px; }
.rank-pill { display: inline-block; width: 18px; height: 18px;
             line-height: 18px; border-radius: 50%;
             font-size: 9.5px; font-weight: 700; text-align: center;
             color: #fff; font-variant-numeric: tabular-nums; }
.resk-kunder .rank-pill { background: #4a7dc6; }
.resk-lev    .rank-pill { background: #e08a3c; }
.resk-table td.navn { overflow: hidden; text-overflow: ellipsis;
                      white-space: nowrap; max-width: 130px;
                      color: #101828; font-weight: 500;
                      font-size: 10.5px; padding-right: 4px; }
.resk-table .navn-missing { color: #98a2b3; font-style: italic;
                            font-weight: 400; }
.resk-empty { font-size: 10.5px; color: #98a2b3; font-style: italic;
              padding: 12px 0; text-align: center; }
.resk-table tr.resk-sum td { background: #f8fafc; font-weight: 600;
                             border-top: 1px solid #d0d5dd; }
.resk-table tr.resk-sum-total td { background: #eef2f6;
                                   border-top: 2px solid #667085; }
.resk-table tr.resk-sum td.num-main { padding-left: 10px; }
.resk-table tr.resk-sum td.navn { color: #344054; font-weight: 700; }
"""

_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nøkkeltall — $client $year</title>
<style>
$css
</style>
</head>
<body>

<!-- ============ Side 1: Resultatregnskap ============ -->
<div class="page">
  <div class="report-header">
    <div class="title-wrap">
      <div class="report-title">$client</div>
      <div class="report-subtitle">Resultatregnskap $year</div>
    </div>
  </div>

  <div style="display:flex; gap:36px; align-items:flex-start;">
    <div style="flex:1; max-width:560px;">
      <div class="section-title" style="margin-top:0">Resultatregnskap</div>
      $pl_table_html
    </div>
    <div style="flex:0 0 440px; padding-top:28px;">
      <div class="chart-label">Fra inntekt til årsresultat</div>
      $pl_waterfall_svg
    </div>
  </div>

  <div style="margin-top:16px;">
    <div class="chart-label">Resultatsammensetning</div>
    $pl_composition_svg
  </div>
</div>

<!-- ============ Side 2: Balanse ============ -->
<div class="page">
  <div class="report-header">
    <div class="title-wrap">
      <div class="report-title">$client</div>
      <div class="report-subtitle">Balanse $year</div>
    </div>
  </div>

  <div style="display:flex; gap:28px;">
    <div style="flex:1">
      <div class="section-title" style="margin-top:0">Eiendeler</div>
      $bs_eiendeler_html
    </div>
    <div style="flex:1">
      <div class="section-title" style="margin-top:0">Egenkapital og gjeld</div>
      $bs_ek_gjeld_html
    </div>
  </div>

  <div style="margin-top:16px;">
    <div class="chart-label">Balansesammensetning</div>
    $bs_composition_svg
  </div>
</div>

<!-- ============ Side 3: N&#248;kkeltall ============ -->
<div class="page">
  <div class="report-header">
    <div class="title-wrap">
      <div class="report-title">$client</div>
      <div class="report-subtitle">N&#248;kkeltall $year</div>
    </div>
  </div>

  <div style="display:flex; gap:28px;">
    <div style="flex:1">
      <div class="section-title" style="margin-top:0">L&#248;nnsomhet</div>
      $key_metrics_pl_html
    </div>
    <div style="flex:1">
      <div class="section-title" style="margin-top:0">Likviditet, soliditet og effektivitet</div>
      $key_metrics_bs_html
    </div>
  </div>

  $observations_html
</div>

<!-- ============ Side 4: Aktivitet og endringer ============ -->
<div class="page">
  <div class="report-header">
    <div class="title-wrap">
      <div class="report-title">$client</div>
      <div class="report-subtitle">Aktivitet og endringer $year</div>
    </div>
  </div>

  $top_rl_table_html
  $top_changes_html
</div>

$reskontro_page_html
<!-- ============ Side 5: Beregningsgrunnlag ============ -->
<div class="page">
  <div class="report-header">
    <div class="title-wrap">
      <div class="report-title">Beregningsgrunnlag</div>
      <div class="report-subtitle">Formler og regnskapslinjer brukt i n&#248;kkeltallsberegning</div>
    </div>
  </div>

  $formula_ref_html
</div>

</body>
</html>
""")


# ---------------------------------------------------------------------------
# Builder functions
# ---------------------------------------------------------------------------

def _change_cell(change_pct: float | None) -> str:
    if change_pct is None:
        return '<td class="num">–</td>'
    css = "change-pos" if change_pct >= 0 else "change-neg"
    sign = "+" if change_pct >= 0 else ""
    return f'<td class="num {css}">{sign}{change_pct:.1f}%</td>'


def _change_cell_abs(m) -> str:
    """Vis endring som prosentpoeng (for %), absolutt differanse (for beløp/desimal)."""
    if m.value is None or m.prev_value is None:
        return '<td class="num">\u2013</td>'
    diff = m.value - m.prev_value
    css = "change-pos" if diff >= 0 else "change-neg"
    sign = "+" if diff >= 0 else ""
    if m.fmt == "pct":
        txt = f"{sign}{diff:.1f} pp"
    elif m.fmt == "decimal":
        txt = f"{sign}{diff:.2f}"
    elif m.fmt == "amount":
        from .engine import _format_value
        txt = f"{sign}{_format_value(diff, 'amount')}"
    else:
        txt = f"{sign}{diff:.1f}"
    return f'<td class="num {css}">{txt}</td>'


def _build_kpi_cards_html(cards: list[dict]) -> str:
    if not cards:
        return ""
    parts = ['<div class="kpi-grid">']
    for c in cards:
        parts.append(svg_kpi_card(
            c["label"], c["formatted"], c.get("change_pct"),
        ))
    parts.append("</div>")
    return "\n".join(parts)


def _build_summary_table(lines: list[dict], has_prev: bool) -> str:
    if not lines:
        return '<p style="color:#aaa">Ingen data</p>'

    # Skjul detaljrader hvor både i år og fjor er null — reduserer visuell
    # støy i balansetabellen. Sumrader beholdes alltid (0-sum er meningsfylt).
    def _is_zero(v: object) -> bool:
        try:
            return v is None or abs(float(v)) < 0.5
        except (TypeError, ValueError):
            return True

    visible = [
        line for line in lines
        if line.get("is_sum")
        or not (_is_zero(line.get("value")) and _is_zero(line.get("prev")))
    ]
    if not visible:
        return '<p style="color:#aaa">Ingen data</p>'

    prev_cols = ""
    if has_prev:
        prev_cols = ('<th class="num">I fjor</th>'
                     '<th class="num">Endring</th>'
                     '<th class="num" style="width:1%;white-space:nowrap">%</th>')

    rows: list[str] = []
    for line in visible:
        cls = ' class="sum-row"' if line.get("is_sum") else ""
        prev_cells = ""
        if has_prev:
            prev_fmt = line.get("prev_formatted") or "–"
            change_amt = line.get("change_amount_formatted") or "–"
            prev_cells = (
                f'<td class="num">{prev_fmt}</td>'
                f'<td class="num">{change_amt}</td>'
                + _change_cell(line.get("change_pct"))
            )

        rows.append(
            f'<tr{cls}>'
            f'<td>{_esc(line["name"])}</td>'
            f'<td class="num">{_esc(line["formatted"])}</td>'
            f'{prev_cells}'
            f'</tr>'
        )

    col_header = "I år" if has_prev else "Beløp"
    return (
        f'<table class="data-table">'
        f'<thead><tr><th>Post</th><th class="num">{col_header}</th>{prev_cols}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table>'
    )


def _build_metrics_table(metrics: list, has_prev: bool, *,
                         exclude_ids: set[str] | None = None) -> str:
    if not metrics:
        return ""

    filtered = [m for m in metrics
                if m.value is not None and (not exclude_ids or m.id not in exclude_ids)]
    if not filtered:
        return ""

    prev_cols = ""
    if has_prev:
        prev_cols = '<th class="num">Forrige år</th><th class="num">Endring</th>'

    rows: list[str] = []
    current_cat = ""
    for m in filtered:
        if m.category != current_cat:
            current_cat = m.category
            colspan = 4 if has_prev else 2
            rows.append(
                f'<tr><td class="cat-header" colspan="{colspan}">{_esc(current_cat)}</td></tr>'
            )

        prev_cells = ""
        if has_prev:
            prev_cells = f'<td class="num">{_esc(m.formatted_prev)}</td>'
            prev_cells += _change_cell(m.change_pct)

        rows.append(
            f'<tr>'
            f'<td>{_esc(m.label)}</td>'
            f'<td class="num">{_esc(m.formatted)}</td>'
            f'{prev_cells}'
            f'</tr>'
        )

    return (
        f'<table class="data-table">'
        f'<thead><tr><th>Nøkkeltall</th><th class="num">Verdi</th>{prev_cols}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table>'
    )


def _build_activity_html(top_activity: list[dict]) -> str:
    """Topp regnskapslinjer etter bilagsvolum som tabell med inline bar."""
    if not top_activity:
        return ""

    label = top_activity[0].get("count_label", "bilag")
    has_dk = any(it.get("formatted_debet") for it in top_activity)

    rows: list[str] = []
    for item in top_activity:
        bar_pct = float(item.get("bar_pct") or 0.0)
        count = int(item.get("count") or 0)
        dk_cells = ""
        if has_dk:
            dk_cells = (
                f'<td class="num">{_esc(item.get("formatted_debet") or "")}</td>'
                f'<td class="num">{_esc(item.get("formatted_kredit") or "")}</td>'
                f'<td class="num">{_esc(item.get("formatted_netto") or "")}</td>'
            )
        rows.append(
            f'<tr>'
            f'<td>{_esc(item["name"])}</td>'
            f'{dk_cells}'
            f'<td class="num">{count:,}</td>'
            f'<td class="bar-cell">'
            f'<div class="bar-wrap"><div class="bar-fill" '
            f'style="width:{bar_pct:.1f}%"></div></div>'
            f'</td>'
            f'</tr>'.replace(",", " ")
        )

    dk_headers = ""
    if has_dk:
        dk_headers = (
            '<th class="num">Debet</th>'
            '<th class="num">Kredit</th>'
            '<th class="num">Netto</th>'
        )

    return (
        f'<div class="section-title" style="margin-top:0">'
        f'Topp regnskapslinjer etter {_esc(label)}svolum</div>'
        f'<table class="activity-table">'
        f'<thead><tr>'
        f'<th>Regnskapslinje</th>'
        f'{dk_headers}'
        f'<th class="num">Antall {_esc(label)}</th>'
        f'<th class="num">Fordeling</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table>'
    )


def _build_top_changes_html(top_changes: dict) -> str:
    """To paneler side om side: største økninger (grønn) og reduksjoner (rød)."""
    increases = top_changes.get("increases") or []
    decreases = top_changes.get("decreases") or []
    if not increases and not decreases:
        return ""

    def _panel(title: str, items: list[dict], css_class: str, sign: str) -> str:
        if not items:
            return (
                f'<div class="change-panel">'
                f'<h4>{_esc(title)}</h4>'
                f'<div style="font-size:10.5px;color:#667085">'
                f'Ingen endringer \u00e5 rapportere.</div>'
                f'</div>'
            )
        rows = []
        for r in items:
            amount = r.get("formatted_diff", "")
            if not amount.startswith(("+", "-")):
                amount = f'{sign}{amount}'
            bar_pct = float(r.get("bar_pct") or 0.0)
            pct_html = ""
            if r.get("change_pct") is not None:
                pct_html = f' <span style="color:#98a2b3;font-weight:400">' \
                          f'({r["change_pct"]:+.0f}%)</span>'
            rows.append(
                f'<div class="change-row {css_class}">'
                f'<div class="cr-name" title="{_esc(r["name"])}">{_esc(r["name"])}</div>'
                f'<div class="cr-amount">{_esc(amount)}{pct_html}</div>'
                f'<div class="cr-bar"><span style="width:{bar_pct:.1f}%"></span></div>'
                f'</div>'
            )
        return (
            f'<div class="change-panel">'
            f'<h4>{_esc(title)}</h4>'
            f'{"".join(rows)}'
            f'</div>'
        )

    return (
        f'<div class="section-title">St\u00f8rste endringer mot fjor\u00e5r</div>'
        f'<div class="changes-row">'
        f'{_panel("Topp 5 \u00f8kninger", increases, "change-inc", "+")}'
        f'{_panel("Topp 5 reduksjoner", decreases, "change-dec", "")}'
        f'</div>'
    )


def _build_concentration_html(concentration: list[dict]) -> str:
    """Tre konsentrasjonsfliser."""
    if not concentration:
        return ""
    cards = []
    for c in concentration:
        pct = float(c.get("value_pct") or 0.0)
        cards.append(
            f'<div class="conc-card">'
            f'<div class="conc-label">{_esc(c["label"])}</div>'
            f'<div class="conc-value">{pct:.0f}\u00a0%</div>'
            f'<div class="conc-detail">{_esc(c["detail"])}</div>'
            f'</div>'
        )
    return (
        f'<div class="section-title">Konsentrasjon</div>'
        f'<div class="conc-grid">{"".join(cards)}</div>'
    )


def _build_pl_bar_items(pl_summary: list[dict]) -> list[dict]:
    """Velg hovedposter for bar chart."""
    show_regnr = {10, 20, 40, 50, 70, 80, 280}
    return [line for line in pl_summary if line.get("regnr") in show_regnr]


_FORMULA_REF = [
    ("Lønnsomhet", [
        ("Bruttofortjeneste", "(Salgsinntekt \u2212 Varekostnad) / Salgsinntekt \u00d7 100", "RL 10, 20"),
        ("Driftsmargin", "Driftsresultat / Sum driftsinntekter \u00d7 100", "RL 80, 19"),
        ("Nettoresultatmargin", "\u00c5rsresultat / Sum driftsinntekter \u00d7 100", "RL 280, 19"),
        ("EBITDA-margin", "(Driftsinntekter \u2212 (Driftskostnader \u2212 Avskrivning)) / Driftsinntekter \u00d7 100", "RL 19, 79, 50"),
        ("Resultat f\u00f8r skatt i % av inntekter", "Resultat f\u00f8r skattekostnad / Sum driftsinntekter \u00d7 100", "RL 160, 19"),
    ]),
    ("Likviditet", [
        ("Likviditetsgrad 1", "Sum oml\u00f8psmidler / Sum kortsiktig gjeld", "RL 660, 810"),
        ("Likviditetsgrad 2", "(Sum oml\u00f8psmidler \u2212 Varelager) / Sum kortsiktig gjeld", "RL 660, 605, 810"),
        ("Arbeidskapital", "Sum oml\u00f8psmidler \u2212 Sum kortsiktig gjeld", "RL 660, 810"),
    ]),
    ("Soliditet", [
        ("Egenkapitalandel", "Sum egenkapital / Sum eiendeler \u00d7 100", "RL 715, 665"),
        ("Gjeldsgrad", "Sum gjeld / Sum egenkapital", "RL 820, 715"),
    ]),
    ("Effektivitet", [
        ("Kundefordringer i % av salg", "Kundefordringer / Salgsinntekt \u00d7 100", "RL 610, 10"),
        ("Varelager i % av varekostnad", "Varelager / Varekostnad \u00d7 100", "RL 605, 20"),
        ("Leverandørgjeld i % av driftskostnader", "Leverandørgjeld / (Varekostnad + Annen driftskostnad) \u00d7 100", "RL 780, 20, 70"),
        ("Lønnskostnad i % av driftsinntekter", "Lønnskostnad / Sum driftsinntekter \u00d7 100", "RL 40, 19"),
        ("Annen driftskostnad i % av driftsinntekter", "Annen driftskostnad / Sum driftsinntekter \u00d7 100", "RL 70, 19"),
    ]),
]


def _build_formula_ref_html() -> str:
    """Bygg formelreferanse-tabell som viser beregningsgrunnlag for alle nøkkeltall."""
    rows: list[str] = []
    for cat, items in _FORMULA_REF:
        rows.append(
            f'<tr><td class="cat-header" colspan="3">{_esc(cat)}</td></tr>'
        )
        for label, formula, rl in items:
            rows.append(
                f'<tr>'
                f'<td>{_esc(label)}</td>'
                f'<td style="font-family:monospace;font-size:0.95em">{_esc(formula)}</td>'
                f'<td class="num" style="white-space:nowrap">{_esc(rl)}</td>'
                f'</tr>'
            )
    return (
        f'<table class="data-table">'
        f'<thead><tr>'
        f'<th style="width:28%">N\u00f8kkeltall</th>'
        f'<th style="width:52%">Formel</th>'
        f'<th class="num" style="width:20%">Regnskapslinjer</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table>'
        f'<p style="font-size:10px;color:#999;margin-top:10px">'
        f'RL = regnskapslinjenummer i standard norsk kontoplan. '
        f'Alle beløp er hentet fra UB-kolonnen (utgående balanse / akkumulert).'
        f'</p>'
    )


_KEY_PL_IDS = [
    "bruttofort_kr", "bruttofort_pct",
    "driftsmargin", "nettoresmargin", "ebitda_pct",
    "res_for_skatt_pct", "lonn_pct", "annen_drift_pct",
]
_KEY_BS_IDS = [
    "likv1", "likv2", "arb_kap",
    "ek_andel", "gjeldsgrad",
    "kundefordr_pct", "varelager_pct", "levgjeld_pct",
]
_PAGE1_IDS = set(_KEY_PL_IDS) | set(_KEY_BS_IDS)


def _build_key_metrics_mini(metrics: list, ids: list[str], has_prev: bool) -> str:
    """Bygg kompakt nøkkeltall-tabell for et utvalg."""
    order = {id: i for i, id in enumerate(ids)}
    selected = [m for m in metrics if m.id in order and m.value is not None]
    if not selected:
        return ""
    selected.sort(key=lambda m: order.get(m.id, 99))

    prev_cols = ""
    prev_colgroup = ""
    if has_prev:
        prev_cols = '<th class="num">I fjor</th><th class="num">Endr.</th>'
        prev_colgroup = '<col style="width:70px"><col style="width:70px">'

    rows: list[str] = []
    for m in selected:
        prev_cells = ""
        if has_prev:
            prev_cells = f'<td class="num">{_esc(m.formatted_prev)}</td>'
            prev_cells += _change_cell_abs(m)
        rows.append(
            f'<tr>'
            f'<td>{_esc(m.label)}</td>'
            f'<td class="num">{_esc(m.formatted)}</td>'
            f'{prev_cells}'
            f'</tr>'
        )

    return (
        f'<table class="data-table" style="margin-top:0;table-layout:fixed">'
        f'<colgroup><col><col style="width:70px">{prev_colgroup}</colgroup>'
        f'<thead><tr><th>N\u00f8kkeltall</th><th class="num">I \u00e5r</th>{prev_cols}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        f'</table>'
    )


def _build_observations_html(obs: list[NokkeltallObservation]) -> str:
    """Bygg 'Standardvurderinger'-seksjonen for side 3, gruppert per kategori."""
    if not obs:
        return ""
    groups: dict[str, list[NokkeltallObservation]] = {}
    for o in obs:
        groups.setdefault(o.category, []).append(o)

    parts: list[str] = [
        '<div class="section-title">Standardvurderinger</div>',
        '<div class="obs-note">Fargen angir status mot generiske '
        'tommelfingerregler (r\u00f8d = svak, gul = moderat, '
        'gr\u00f8nn = sunn). Ikke bransjespesifikke fasiter.</div>',
    ]
    for category, items in groups.items():
        parts.append(
            f'<div class="obs-category">{_esc(category)}</div>'
        )
        cards = [
            f'<div class="obs-card obs-{_esc(o.severity)}">'
            f'<div class="obs-label">{_esc(o.label)}</div>'
            f'<div class="obs-row">'
            f'<span class="obs-value">{_esc(o.actual_text)}</span>'
            f'<span class="obs-bench">{_esc(o.benchmark_text)}</span>'
            f'</div>'
            f'</div>'
            for o in items
        ]
        parts.append(f'<div class="obs-grid">{"".join(cards)}</div>')
    return "".join(parts)


def _build_reskontro_table(
    rows: list[ReskontroRow],
    *,
    title: str,
    navn_header: str,
    theme: str,            # "kunder" | "lev"
    main_col: str,         # "ub" | "debet" | "kredit"
    empty_msg: str = "Ingen data.",
    all_rows: list[ReskontroRow] | None = None,
) -> str:
    """Bygg én seksjon med aksent, rangering-pill og data-bar bak hovedverdi.

    Når ``all_rows`` er gitt legges det på to sumrader under topp-radene:
    ``Sum andre`` (resten) og ``Sum totalt`` (alle).
    """
    from .engine import _format_value

    col_label = {"ub": "UB", "debet": "Debet", "kredit": "Kredit"}

    def _head_cell(col: str) -> str:
        cls = "num num-main" if col == main_col else "num"
        return f'<th class="{cls}">{col_label[col]}</th>'

    header = (
        '<thead><tr>'
        '<th class="rank-col"></th>'
        f'<th>{_esc(navn_header)}</th>'
        '<th class="num">IB</th>'
        f'{_head_cell("debet")}'
        f'{_head_cell("kredit")}'
        f'{_head_cell("ub")}'
        '</tr></thead>'
    )

    if not rows:
        body = (
            '<tbody><tr>'
            '<td colspan="6" class="resk-empty">'
            f'{_esc(empty_msg)}</td></tr></tbody>'
        )
    else:
        max_main = max((abs(getattr(r, main_col)) for r in rows), default=0.0)
        trs: list[str] = []

        def _cell(val: float, col: str, *, is_sum: bool = False) -> str:
            fmt = _format_value(val, "amount")
            if col != main_col:
                return f'<td class="num num-sec">{fmt}</td>'
            if is_sum:
                return f'<td class="num num-main">{fmt}</td>'
            pct = 0.0
            if max_main > 1e-9:
                pct = max(0.0, min(100.0, abs(val) / max_main * 100.0))
            return (
                '<td class="num num-main">'
                f'<span class="bar-bg"><span class="bar-fill" '
                f'style="width:{pct:.1f}%"></span></span>'
                f'<span class="num-main-txt">{fmt}</span>'
                '</td>'
            )

        for idx, r in enumerate(rows, start=1):
            navn_html = (_esc(r.navn)
                         or '<span class="navn-missing">(uten navn)</span>')
            trs.append(
                '<tr>'
                f'<td class="rank-col"><span class="rank-pill">{idx}</span></td>'
                f'<td class="navn" title="{_esc(r.navn)}">{navn_html}</td>'
                f'<td class="num num-sec">{_format_value(r.ib, "amount")}</td>'
                f'{_cell(r.debet, "debet")}'
                f'{_cell(r.kredit, "kredit")}'
                f'{_cell(r.ub, "ub")}'
                '</tr>'
            )

        if all_rows:
            top_nrs = {r.nr for r in rows}
            total_ib = sum(r.ib for r in all_rows)
            total_debet = sum(r.debet for r in all_rows)
            total_kredit = sum(r.kredit for r in all_rows)
            total_ub = sum(r.ub for r in all_rows)
            other = [r for r in all_rows if r.nr not in top_nrs]
            if other:
                o_ib = sum(r.ib for r in other)
                o_debet = sum(r.debet for r in other)
                o_kredit = sum(r.kredit for r in other)
                o_ub = sum(r.ub for r in other)
                trs.append(
                    '<tr class="resk-sum resk-sum-other">'
                    '<td class="rank-col"></td>'
                    f'<td class="navn">Sum andre ({len(other)})</td>'
                    f'<td class="num num-sec">{_format_value(o_ib, "amount")}</td>'
                    f'{_cell(o_debet, "debet", is_sum=True)}'
                    f'{_cell(o_kredit, "kredit", is_sum=True)}'
                    f'{_cell(o_ub, "ub", is_sum=True)}'
                    '</tr>'
                )
            trs.append(
                '<tr class="resk-sum resk-sum-total">'
                '<td class="rank-col"></td>'
                f'<td class="navn">Sum totalt ({len(all_rows)})</td>'
                f'<td class="num num-sec">{_format_value(total_ib, "amount")}</td>'
                f'{_cell(total_debet, "debet", is_sum=True)}'
                f'{_cell(total_kredit, "kredit", is_sum=True)}'
                f'{_cell(total_ub, "ub", is_sum=True)}'
                '</tr>'
            )
        body = f'<tbody>{"".join(trs)}</tbody>'

    return (
        f'<div class="resk-section resk-{_esc(theme)}">'
        f'<div class="resk-accent"></div>'
        f'<h4>{_esc(title)}</h4>'
        f'<table class="resk-table">{header}{body}</table>'
        '</div>'
    )


def _build_reskontro_html(result: NokkeltallResult) -> str:
    """Bygg hele reskontro-siden.

    Returnerer tom streng hvis ingen reskontrodata finnes — da hopper
    templaten over sidewrapperen via $reskontro_page.
    """
    has_kunder = bool(result.reskontro_kunder_top_ub
                      or result.reskontro_kunder_top_debet)
    has_lev = bool(result.reskontro_lev_top_ub
                   or result.reskontro_lev_top_kredit)
    if not (has_kunder or has_lev):
        return ""

    sections: list[str] = []
    if has_kunder:
        sections.append(_build_reskontro_table(
            result.reskontro_kunder_top_ub,
            title="Topp 5 kunder — st\u00f8rste UB-saldo",
            navn_header="Kunde",
            theme="kunder", main_col="ub",
            all_rows=result.reskontro_kunder_all,
        ))
        sections.append(_build_reskontro_table(
            result.reskontro_kunder_top_debet,
            title="Topp 5 kunder — st\u00f8rste debet-bevegelse",
            navn_header="Kunde",
            theme="kunder", main_col="debet",
            all_rows=result.reskontro_kunder_all,
        ))
    if has_lev:
        sections.append(_build_reskontro_table(
            result.reskontro_lev_top_ub,
            title="Topp 5 leverand\u00f8rer — st\u00f8rste UB-saldo",
            navn_header="Leverand\u00f8r",
            theme="lev", main_col="ub",
            all_rows=result.reskontro_lev_all,
        ))
        sections.append(_build_reskontro_table(
            result.reskontro_lev_top_kredit,
            title="Topp 5 leverand\u00f8rer — st\u00f8rste kredit-bevegelse",
            navn_header="Leverand\u00f8r",
            theme="lev", main_col="kredit",
            all_rows=result.reskontro_lev_all,
        ))
    return f'<div class="resk-grid">{"".join(sections)}</div>'


def _build_stacked_composition_svg(
    groups: list[tuple[str, list[dict]]],
    *,
    width: int = 900,
    palette: list[str] | None = None,
) -> str:
    """Generisk stablet vannrett bar — én rad per gruppe, segmentert internt.

    Hver gruppe skaleres til 100 % av bar-bredden. Brukes for balansesammen­
    setning (Eiendeler / EK og gjeld) og resultatsammensetning (Inntekter /
    Fordeling).
    """
    groups = [(lbl, items) for lbl, items in groups if items]
    if not groups:
        return ""

    palette = palette or ["#4472C4", "#5B9BD5", "#A5A5A5", "#ED7D31", "#FFC000", "#70AD47", "#E74C3C"]

    bar_h = 28
    gap = 12
    label_w = 120
    bar_w = width - label_w - 20
    n_rows = len(groups)
    height = n_rows * (bar_h + gap) + 30

    parts: list[str] = []
    legend_items: list[tuple[str, str, float]] = []

    for row_idx, (label, items) in enumerate(groups):
        total = sum(d.get("value", 0) for d in items)
        if total < 1e-9:
            continue
        y = row_idx * (bar_h + gap) + 5

        parts.append(
            f'<text x="{label_w - 8}" y="{y + bar_h / 2 + 5:.0f}" '
            f'font-size="11" fill="#333" text-anchor="end" font-weight="600">{label}</text>'
        )

        x = label_w
        for seg_idx, d in enumerate(items):
            val = d.get("value", 0)
            seg_w = (val / total) * bar_w if total > 1e-9 else 0
            # Allow caller to override color via "color" key (e.g. driftstap = red)
            color = d.get("color") or palette[(row_idx * 3 + seg_idx) % len(palette)]

            parts.append(
                f'<rect x="{x:.1f}" y="{y}" width="{seg_w:.1f}" height="{bar_h}" '
                f'fill="{color}" opacity="0.85"/>'
            )

            pct = val / total * 100
            seg_label = d.get("label", "")
            if seg_w > 100:
                parts.append(
                    f'<text x="{x + seg_w / 2:.0f}" y="{y + bar_h / 2 + 4:.0f}" '
                    f'font-size="10" fill="white" text-anchor="middle" font-weight="600">'
                    f'{seg_label} ({pct:.0f}%)</text>'
                )

            legend_items.append((seg_label, color, pct))
            x += seg_w

    ly = n_rows * (bar_h + gap) + 10
    lx = label_w
    for seg_label, color, pct in legend_items:
        parts.append(
            f'<rect x="{lx:.0f}" y="{ly}" width="10" height="10" rx="2" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{lx + 14:.0f}" y="{ly + 9}" font-size="10" fill="#555">'
            f'{seg_label} ({pct:.0f}%)</text>'
        )
        lx += 160

    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        + "".join(parts)
        + "</svg>"
    )


def _build_bs_composition_svg(bs_breakdown: list[dict], *, width: int = 900) -> str:
    """Stacked bar — balansesammensetning (eiendeler vs finansiering)."""
    if not bs_breakdown:
        return ""
    eiendeler = [d for d in bs_breakdown if d.get("side") == "eiendeler"]
    finans = [d for d in bs_breakdown if d.get("side") == "finansiering"]
    return _build_stacked_composition_svg(
        [("Eiendeler", eiendeler), ("EK og gjeld", finans)],
        width=width,
    )


def _build_pl_composition_svg(pl_summary: list[dict], *, width: int = 900) -> str:
    """Stacked bar — resultatsammensetning.

    Rad 1 (Inntekter): driftsinntektene fordelt på sine enkeltposter.
    Rad 2 (Fordeling): samme totalbeløp fordelt på kostnadstyper +
    driftsresultat + netto finans. Fargene er låst per kategori slik at
    vannfall-diagrammet og fordelingsbaren kan kobles visuelt.
    """
    if not pl_summary:
        return ""

    by_regnr = {line.get("regnr"): line for line in pl_summary}

    def _val(regnr: int) -> float:
        line = by_regnr.get(regnr)
        return float(line.get("value") or 0) if line else 0.0

    # --- Inntekter: alle ikke-sum PL-linjer med regnr < 19. Fallback: RL 19. ---
    inntekter_items: list[dict] = []
    income_regnrs = sorted(
        r for r, line in by_regnr.items()
        if isinstance(r, int) and r < 19 and not line.get("is_sum")
    )
    for r in income_regnrs:
        v = _val(r)
        if abs(v) > 1e-9:
            inntekter_items.append({
                "label": by_regnr[r]["name"],
                "value": abs(v),
                "color": _CATEGORY_COLORS["inntekt"],
            })
    if not inntekter_items:
        v = _val(19)
        if abs(v) > 1e-9:
            inntekter_items.append({
                "label": "Driftsinntekter",
                "value": abs(v),
                "color": _CATEGORY_COLORS["inntekt"],
            })

    # --- Fordeling: kostnader + driftsresultat + netto finans ---
    # PL-linjer er lagret med regnskapsmessig fortegn (inntekt=negativ,
    # kostnad=positiv). Driftsresultat utledes fra inntekter minus
    # kostnader i display-fortegn, ikke fra RL 80 direkte, for å være
    # robust mot ulike lagringskonvensjoner.
    fordeling_items: list[dict] = []
    kostnader_total = 0.0
    cost_cats = [
        (20, "Varekostnad",        "varekost"),
        (40, "Lønnskostnad",       "lonn"),
        (50, "Avskrivning",        "avskriv"),
        (70, "Annen driftskostnad", "annen_drift"),
    ]
    for regnr, label, cat in cost_cats:
        v = _val(regnr)
        if abs(v) > 1e-9:
            fordeling_items.append({
                "label": label,
                "value": abs(v),
                "color": _CATEGORY_COLORS[cat],
            })
            kostnader_total += abs(v)

    inntekter_total = sum(d["value"] for d in inntekter_items)

    # Netto finans (inntekter lagres negativt → flip med minus)
    fin_net = sum(
        -_val(r) for r, line in by_regnr.items()
        if isinstance(r, int) and 90 <= r < 160 and not line.get("is_sum")
    )
    if abs(fin_net) > 1e-9:
        is_pos = fin_net >= 0
        fordeling_items.append({
            "label": "Netto finans" if is_pos else "Netto finanskost",
            "value": abs(fin_net),
            "color": _CATEGORY_COLORS["finans_pos" if is_pos else "finans_neg"],
        })

    # Årsresultat (sluttmål) — grønn ved overskudd, rød ved tap.
    skatt = sum(
        _val(r) for r, line in by_regnr.items()
        if isinstance(r, int) and 160 < r < 280 and not line.get("is_sum")
    )
    driftsres_display = inntekter_total - kostnader_total
    arsres_display = driftsres_display + fin_net - abs(skatt)
    if abs(arsres_display) > 1e-9:
        is_pos = arsres_display >= 0
        fordeling_items.append({
            "label": "Årsresultat" if is_pos else "Årstap",
            "value": abs(arsres_display),
            "color": _CATEGORY_COLORS["driftsres" if is_pos else "driftstap"],
        })

    return _build_stacked_composition_svg(
        [("Inntekter", inntekter_items), ("Fordeling", fordeling_items)],
        width=width,
    )


def _build_waterfall_svg(pl_summary: list[dict], *, width: int = 420, height: int = 320) -> str:
    """Vannfall-diagram — viser hvordan driftsinntekter blir til årsresultat.

    Steg: Driftsinntekter → -Varekost → -Lønn → -Avskriv → -Annen
          → Driftsresultat → ±Finans → Resultat før skatt → -Skatt → Årsresultat

    Bare poster som faktisk finnes tas med.
    """
    if not pl_summary:
        return ""

    by_regnr = {line.get("regnr"): line for line in pl_summary}

    def _val(regnr: int) -> float:
        line = by_regnr.get(regnr)
        return float(line.get("value") or 0) if line else 0.0

    # Driftsinntekter i display-fortegn (positiv). PL-linjer lagres med
    # regnskapsfortegn (inntekt=negativ), så vi bruker abs() her.
    raw_driftsinnt = _val(19) if 19 in by_regnr else sum(
        _val(r) for r, line in by_regnr.items()
        if isinstance(r, int) and r < 19 and not line.get("is_sum")
    )
    driftsinnt = abs(raw_driftsinnt)
    if driftsinnt < 1e-9:
        return ""

    # Bygg steg-sekvens. `delta` er endringen på running-totalen.
    # For "subtotal"/"total" settes delta til None og den faktiske verdien
    # utledes fra running når vi beregner søylene nedenfor.
    # Hver tuple: (label, delta, kind, category). Category styrer fargen og
    # matcher resultatsammensetningen slik at bruker kan koble dem visuelt.
    steps: list[tuple[str, float | None, str, str]] = []
    steps.append(("Driftsinnt.", driftsinnt, "start", "inntekt"))
    for regnr, short, cat in [(20, "Varekost", "varekost"),
                               (40, "Lønn", "lonn"),
                               (50, "Avskriv.", "avskriv"),
                               (70, "Annen drift", "annen_drift")]:
        v = _val(regnr)
        if abs(v) > 1e-9:
            steps.append((short, -abs(v), "subtract", cat))

    # Netto finans i display-fortegn (finansinntekter - finanskostnader).
    # Rå finansinntekter lagres som negative, rå finanskostnader som positive.
    fin_net_display = sum(
        -_val(r) for r, line in by_regnr.items()
        if isinstance(r, int) and 90 <= r < 160 and not line.get("is_sum")
    )
    if abs(fin_net_display) > 1e-9:
        is_pos = fin_net_display >= 0
        steps.append((
            "Finans",
            fin_net_display if is_pos else -abs(fin_net_display),
            "add" if is_pos else "subtract",
            "finans_pos" if is_pos else "finans_neg",
        ))

    # Skatt (positiv raw = kostnad)
    skatt = sum(
        _val(r) for r, line in by_regnr.items()
        if isinstance(r, int) and 160 < r < 280 and not line.get("is_sum")
    )
    if abs(skatt) > 1e-9:
        steps.append(("Skatt", -abs(skatt), "subtract", "skatt"))

    if 280 in by_regnr:
        steps.append(("Årsres.", None, "total", "arsres"))

    if len(steps) < 3:
        return ""

    # Beregn baseline + top for hver søyle. Subtotal/total utledes fra running.
    running = 0.0
    bars: list[dict] = []
    for lbl, delta, kind, cat in steps:
        if kind == "start":
            running = delta or 0.0
            top, bottom = running, 0.0
            shown_delta = running
        elif kind in ("subtotal", "total"):
            top, bottom = running, 0.0
            shown_delta = running
        elif kind == "subtract":
            top = running
            running = running + (delta or 0.0)  # delta er negativ
            bottom = running
            shown_delta = delta or 0.0
        else:  # add
            bottom = running
            running = running + (delta or 0.0)
            top = running
            shown_delta = delta or 0.0
        bars.append({
            "label": lbl, "top": top, "bottom": bottom,
            "kind": kind, "delta": shown_delta, "cat": cat,
        })

    # Y-skala
    all_y = [b["top"] for b in bars] + [b["bottom"] for b in bars] + [0.0]
    y_min = min(all_y)
    y_max = max(all_y)
    if y_max - y_min < 1e-9:
        return ""
    # Litt padding
    pad = (y_max - y_min) * 0.08
    y_min -= pad
    y_max += pad

    # Layout
    margin_l, margin_r, margin_t, margin_b = 10, 10, 16, 50
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    n = len(bars)
    bar_gap = 4
    bar_w = (plot_w - (n - 1) * bar_gap) / n

    def _y(val: float) -> float:
        return margin_t + (y_max - val) / (y_max - y_min) * plot_h

    parts: list[str] = []

    # Null-linje
    y0 = _y(0)
    parts.append(
        f'<line x1="{margin_l}" y1="{y0:.1f}" x2="{margin_l + plot_w}" y2="{y0:.1f}" '
        f'stroke="#ccc" stroke-dasharray="2,2"/>'
    )

    # Bars + connector-linjer
    from .engine import _format_value
    for i, b in enumerate(bars):
        x = margin_l + i * (bar_w + bar_gap)
        yt = _y(b["top"])
        yb = _y(b["bottom"])
        h = abs(yb - yt)
        y = min(yt, yb)
        cat = b.get("cat") or ""
        # Årsres og andre result-totaler farges dynamisk: grønn ved positivt
        # resultat, rød ved tap. Koblet visuelt til resultatsammensetningen.
        if cat == "arsres":
            result_val = b.get("top", 0.0) or 0.0
            color = _CATEGORY_COLORS["driftsres" if result_val >= 0 else "driftstap"]
        else:
            color = _CATEGORY_COLORS.get(cat, "#888")

        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(h, 1):.1f}" '
            f'fill="{color}" opacity="0.88"/>'
        )

        # Verdi-label over/under søylen
        fmt = _format_value(b["delta"], "amount")
        lbl_y = y - 3 if b["delta"] >= 0 else y + h + 11
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{lbl_y:.1f}" font-size="9" '
            f'fill="#333" text-anchor="middle" font-weight="600">{fmt}</text>'
        )

        # Kategori-label under x-aksen
        parts.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{height - 30:.1f}" font-size="9" '
            f'fill="#555" text-anchor="middle" transform="rotate(-20 {x + bar_w / 2:.1f} {height - 30:.1f})">'
            f'{_esc(b["label"])}</text>'
        )

        # Connector til neste søyle
        if i < n - 1 and b["kind"] not in ("total",):
            nxt = bars[i + 1]
            # Connector-linjen går fra toppen av nåværende running-nivå til neste søyles baseline
            connect_y = _y(b["top"] if b["kind"] in ("start", "subtotal", "add") else b["bottom"])
            parts.append(
                f'<line x1="{x + bar_w:.1f}" y1="{connect_y:.1f}" '
                f'x2="{x + bar_w + bar_gap:.1f}" y2="{connect_y:.1f}" '
                f'stroke="#aaa" stroke-dasharray="2,2"/>'
            )

    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        + "".join(parts)
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_report_html(result: NokkeltallResult) -> str:
    """Bygg komplett HTML-rapport fra NokkeltallResult."""

    # Skjul detaljerte finansposter i PL-tabellen — kun sumposten
    # "Resultat av finansposter" (regnr 155) vises. Detaljene brukes fortsatt
    # i waterfall og resultatsammensetning.
    def _is_finans_detail(line: dict) -> bool:
        if line.get("is_sum"):
            return False
        try:
            regnr = int(line.get("regnr") or 0)
        except (TypeError, ValueError):
            return False
        return 90 <= regnr <= 154
    pl_lines_collapsed = [ln for ln in result.pl_summary if not _is_finans_detail(ln)]
    pl_table = _build_summary_table(pl_lines_collapsed, result.has_prev_year)
    bs_eien = _build_summary_table(result.bs_eiendeler, result.has_prev_year)
    bs_ekg = _build_summary_table(result.bs_ek_gjeld, result.has_prev_year)
    key_pl = _build_key_metrics_mini(result.metrics, _KEY_PL_IDS, result.has_prev_year)
    key_bs = _build_key_metrics_mini(result.metrics, _KEY_BS_IDS, result.has_prev_year)
    observations_html = _build_observations_html(result.observations)
    top_rl_table_html = _build_activity_html(result.top_activity)
    top_changes_html = _build_top_changes_html(result.top_changes)
    reskontro_body = _build_reskontro_html(result)
    if reskontro_body:
        reskontro_page_html = (
            '<!-- ============ Side: Reskontro ============ -->\n'
            '<div class="page">\n'
            '  <div class="report-header">\n'
            f'    <div class="title-wrap">\n'
            f'      <div class="report-title">{_esc(result.client)}</div>\n'
            f'      <div class="report-subtitle">Reskontro \u2014 '
            f'kunder og leverand\u00f8rer {_esc(result.year)}</div>\n'
            f'    </div>\n'
            '  </div>\n'
            f'  {reskontro_body}\n'
            '</div>\n'
        )
    else:
        reskontro_page_html = ""
    formula_ref = _build_formula_ref_html()

    bs_composition = _build_bs_composition_svg(result.bs_breakdown, width=900)
    pl_composition = _build_pl_composition_svg(result.pl_summary, width=900)
    pl_waterfall = _build_waterfall_svg(result.pl_summary, width=440, height=320)

    return _TEMPLATE.substitute(
        css=_CSS,
        client=_esc(result.client),
        year=_esc(result.year),
        pl_table_html=pl_table,
        bs_eiendeler_html=bs_eien,
        bs_ek_gjeld_html=bs_ekg,
        key_metrics_pl_html=key_pl,
        key_metrics_bs_html=key_bs,
        observations_html=observations_html,
        pl_waterfall_svg=pl_waterfall,
        pl_composition_svg=pl_composition,
        bs_composition_svg=bs_composition,
        top_rl_table_html=top_rl_table_html,
        top_changes_html=top_changes_html,
        reskontro_page_html=reskontro_page_html,
        formula_ref_html=formula_ref,
    )


def save_report_html(
    path: str | Path,
    *,
    rl_df: pd.DataFrame,
    transactions_df: pd.DataFrame | None = None,
    reskontro_df: pd.DataFrame | None = None,
    client: str = "",
    year: str | int = "",
) -> str:
    """Beregn nøkkeltall og lagre HTML-rapport.

    Returns path to saved file.
    """
    result = compute_nokkeltall(
        rl_df,
        transactions_df=transactions_df,
        reskontro_df=reskontro_df,
        client=client,
        year=year,
    )
    html = build_report_html(result)

    out = Path(path)
    if out.suffix.lower() not in (".html", ".htm"):
        out = out.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out)


def save_report_pdf(
    path: str | Path,
    *,
    rl_df: pd.DataFrame,
    transactions_df: pd.DataFrame | None = None,
    reskontro_df: pd.DataFrame | None = None,
    client: str = "",
    year: str | int = "",
) -> str:
    """Beregn nøkkeltall og lagre PDF-rapport via playwright (headless Chromium).

    Returns path to saved file.
    Raises ImportError if playwright is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ImportError(
            "playwright er ikke installert. Installer med:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        )

    result = compute_nokkeltall(
        rl_df,
        transactions_df=transactions_df,
        reskontro_df=reskontro_df,
        client=client,
        year=year,
    )
    html = build_report_html(result)

    out = Path(path)
    if out.suffix.lower() != ".pdf":
        out = out.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    # Skriv HTML til temp-fil for Chromium
    import tempfile
    tmp_html = Path(tempfile.gettempdir()) / "utvalg_nokkeltall_tmp.html"
    tmp_html.write_text(html, encoding="utf-8")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(tmp_html.as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(out),
                landscape=True,
                print_background=True,
                format="A4",
                margin={"top": "5mm", "bottom": "5mm",
                        "left": "8mm", "right": "8mm"},
            )
            browser.close()
    finally:
        try:
            tmp_html.unlink(missing_ok=True)
        except Exception:
            pass

    return str(out)


def open_report_in_browser(
    *,
    rl_df: pd.DataFrame,
    transactions_df: pd.DataFrame | None = None,
    client: str = "",
    year: str | int = "",
    path: str | Path | None = None,
) -> str:
    """Generer rapport og åpne i standard browser.

    Hvis path ikke er gitt, lagres til temp-mappe.
    """
    if path is None:
        import tempfile
        tmp = Path(tempfile.gettempdir()) / "utvalg_nokkeltall.html"
        path = tmp

    saved = save_report_html(
        path,
        rl_df=rl_df,
        transactions_df=transactions_df,
        client=client,
        year=year,
    )
    try:
        webbrowser.open(Path(saved).as_uri())
    except Exception:
        pass
    return saved


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

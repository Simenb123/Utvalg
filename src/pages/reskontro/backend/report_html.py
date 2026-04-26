"""reskontro_report_html.py — HTML/PDF-rendering for reskontrorapporten.

Bruker samme CSS-basis og struktur som nokkeltall_report, slik at kunde- og
leverandørrapporter får identisk design (med fargeaksent som skiller dem).

Én renderer (`build_report_html`) fungerer for begge modi. PDF genereres via
Playwright, samme mønster som nokkeltall.
"""
from __future__ import annotations

import webbrowser
from html import escape as _esc
from pathlib import Path
from string import Template
from typing import Sequence

from .report_engine import (
    AgingBucket,
    HbAccountRow,
    MotpostRow,
    PartyRow,
    ReskontroReport,
    TransactionRow,
    compute_reskontro_report,
)


# ---------------------------------------------------------------------------
# Formattering
# ---------------------------------------------------------------------------

def _fmt_amount(v: float | None, *, decimals: int = 0) -> str:
    if v is None:
        return "–"
    try:
        vv = float(v)
    except (TypeError, ValueError):
        return "–"
    if vv != vv:  # NaN
        return "–"
    s = f"{vv:,.{decimals}f}"
    return s.replace(",", " ").replace(".", ",") if decimals else s.replace(",", " ")


def _fmt_int(v: int | float | None) -> str:
    if v is None:
        return "–"
    try:
        return f"{int(round(float(v))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "–"


def _fmt_pct(v: float | None, *, decimals: int = 1) -> str:
    if v is None:
        return "–"
    try:
        return f"{float(v):.{decimals}f} %".replace(".", ",")
    except (TypeError, ValueError):
        return "–"


def _fmt_days(v: int | None) -> str:
    if v is None:
        return "–"
    return f"{v} d"


def _amount_class(v: float, *, good_positive: bool = True) -> str:
    if abs(v) < 0.5:
        return ""
    if good_positive:
        return "change-pos" if v > 0 else "change-neg"
    return "change-neg" if v > 0 else "change-pos"


# ---------------------------------------------------------------------------
# CSS (felles med nokkeltall + reskontro-spesifikt)
# ---------------------------------------------------------------------------

_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
@page {
    size: A4 landscape;
    margin: 8mm 10mm 12mm 10mm;
    @bottom-right {
        content: "Generert av Utvalg \u2014 side " counter(page) " av " counter(pages);
        font-size: 8px;
        color: #aaa;
        padding-right: 2mm;
    }
}
body {
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    color: #2c3e50;
    background: #f8f9fa;
    line-height: 1.35;
    font-size: 11px;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
}
.page {
    background: white;
    max-width: 1100px;
    margin: 20px auto;
    padding: 28px 36px;
    border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    page-break-before: always;
    page-break-after: always;
    break-inside: avoid;
}
.page:first-child { page-break-before: auto; }
.page:last-child { page-break-after: auto; }
@media print {
    body { background: white; margin: 0; padding: 0; font-size: 9px; }
    .page { box-shadow: none; margin: 0; padding: 4mm 6mm;
            border-radius: 0; max-width: none; }
    .data-table { font-size: 8px; }
    .data-table td { padding: 1.5px 5px; }
    .data-table th { padding: 2.5px 5px; font-size: 7.5px; }
    .kpi-grid { gap: 6px; margin-bottom: 6px; }
    .kpi-card { padding: 4px 6px; }
    .kpi-value { font-size: 13px; }
    .kpi-label { font-size: 7.5px; }
    .kpi-detail { font-size: 7.5px; }
    .section-title { margin: 6px 0 3px 0; font-size: 10px; padding-bottom: 2px; }
    .report-header { margin-bottom: 8px; padding-bottom: 5px; }
    .report-title { font-size: 15px; }
    .report-subtitle { font-size: 9px; }
    .subhead { font-size: 8px; margin-top: -2px; margin-bottom: 4px; }
    .recon-card { margin: 4px 0 6px; gap: 10px; }
    .recon-box { padding: 6px 10px; }
    .recon-value { font-size: 13px; }
    .recon-label, .recon-detail { font-size: 7.5px; }
    .aging-bars { font-size: 9px; }
    .conc-card { padding: 8px 10px; }
    .conc-value { font-size: 16px; }
    .conc-label, .conc-detail { font-size: 7.5px; }
}

.report-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 3px solid var(--accent);
    padding-bottom: 10px;
    margin-bottom: 18px;
}
.report-title { font-size: 20px; font-weight: 700; color: #1a1a2e; }
.report-subtitle { font-size: 12px; color: #7f8c8d; }

.section-title {
    font-size: 14px; font-weight: 700;
    color: var(--accent);
    text-transform: uppercase; letter-spacing: 0.5px;
    margin: 22px 0 10px 0;
    padding-bottom: 3px;
    border-bottom: 1px solid #e8ecf1;
}
.section-title:first-child { margin-top: 0; }

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
    border-left: 4px solid var(--accent);
}
.kpi-label { font-size: 10px; color: #7f8c8d;
             text-transform: uppercase; letter-spacing: 0.3px;
             margin-bottom: 3px; }
.kpi-value { font-size: 18px; font-weight: 700; color: #1a1a2e;
             margin-bottom: 2px; }
.kpi-detail { font-size: 10px; color: #98a2b3; }

.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
    margin-bottom: 12px;
}
.data-table th {
    background: #f0f4f8;
    color: var(--accent);
    font-weight: 600;
    text-align: left;
    padding: 6px 10px;
    border-bottom: 2px solid #d5dde5;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}
.data-table th.num { text-align: right; }
.data-table td {
    padding: 4px 10px;
    border-bottom: 1px solid #eef1f5;
}
.data-table tr:nth-child(even) { background: #fafbfc; }
.data-table tr:hover { background: #f6f8fb; }
.data-table .num { text-align: right;
                    font-variant-numeric: tabular-nums;
                    white-space: nowrap; }
.data-table .sum-row { font-weight: 700; background: #f0f4f8; }
.data-table .cat-header { font-weight: 600; color: var(--accent);
                          background: #f8fafc; }
.data-table .navn {
    max-width: 280px; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
}
.data-table .rank-pill {
    display: inline-block; width: 20px; height: 20px;
    line-height: 20px; border-radius: 50%;
    font-size: 10px; font-weight: 700; text-align: center;
    color: #fff; background: var(--accent);
    font-variant-numeric: tabular-nums;
}
.data-table .orgnr { font-size: 10px; color: #98a2b3;
                     font-variant-numeric: tabular-nums;
                     white-space: nowrap; }

.change-pos { color: #27AE60; font-weight: 600; }
.change-neg { color: #E74C3C; font-weight: 600; }
.muted { color: #98a2b3; font-style: italic; }

.recon-card {
    display: grid; grid-template-columns: 1fr 1fr 1fr;
    gap: 14px;
    margin: 10px 0 14px;
}
.recon-box {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 10px 14px;
    background: #fff;
}
.recon-box.ok { border-left: 4px solid #27AE60; }
.recon-box.warn { border-left: 4px solid #E74C3C; }
.recon-label { font-size: 10px; text-transform: uppercase;
               letter-spacing: 0.4px; color: #667085; }
.recon-value { font-size: 18px; font-weight: 700;
               font-variant-numeric: tabular-nums;
               color: #101828; margin-top: 4px; }
.recon-detail { font-size: 10px; color: #98a2b3; margin-top: 2px; }

.aging-bars {
    display: grid; grid-template-columns: 110px 1fr 80px 60px;
    gap: 6px 14px;
    align-items: center;
    font-size: 11px;
    margin-top: 8px;
}
.aging-label { color: #475467; }
.aging-bar-wrap { height: 14px; background: #f2f4f7;
                   border-radius: 3px; overflow: hidden; }
.aging-bar-fill { height: 100%; background: var(--accent); }
.aging-amount { text-align: right;
                font-variant-numeric: tabular-nums;
                font-weight: 600; }
.aging-count { text-align: right;
               font-size: 10px; color: #667085; }

.conc-grid { display: grid; grid-template-columns: repeat(3, 1fr);
             gap: 10px; margin-top: 10px; }
.conc-card { border: 1px solid #e5e7eb; border-radius: 8px;
             padding: 12px 14px; background: #fff; }
.conc-label { font-size: 10px; text-transform: uppercase;
              letter-spacing: 0.04em; color: #475467; }
.conc-value { font-size: 22px; font-weight: 700; color: #101828;
              margin-top: 4px; font-variant-numeric: tabular-nums; }
.conc-detail { font-size: 10px; color: #667085; margin-top: 2px; }

.empty-note { font-size: 11px; color: #98a2b3;
              font-style: italic; padding: 8px 0 12px; }

.subhead { font-size: 11px; color: #667085; margin-top: -4px;
           margin-bottom: 10px; }

/* Theme accent */
body.theme-kunder { --accent: #2e5eaa; }
body.theme-lev    { --accent: #c4691a; }
"""


# ---------------------------------------------------------------------------
# Tabell-byggere
# ---------------------------------------------------------------------------

def _kpi_card(label: str, value: str, detail: str = "") -> str:
    det = f'<div class="kpi-detail">{_esc(detail)}</div>' if detail else ""
    return (
        '<div class="kpi-card">'
        f'<div class="kpi-label">{_esc(label)}</div>'
        f'<div class="kpi-value">{_esc(value)}</div>'
        f'{det}'
        '</div>'
    )


def _build_kpi_grid(report: ReskontroReport) -> str:
    k = report.kpi or {}
    if not k:
        return ""
    cards = [
        _kpi_card(
            f"Antall {k.get('label_party', '')}",
            _fmt_int(k.get("antall_total", 0)),
            f"{_fmt_int(k.get('antall_aktive', 0))} aktive",
        ),
        _kpi_card(
            "Total UB",
            _fmt_amount(k.get("total_ub", 0.0)),
            f"Snitt pr. aktiv: {_fmt_amount(k.get('snitt_ub_aktive', 0.0))}",
        ),
        _kpi_card(
            "Debet (år)",
            _fmt_amount(k.get("total_debet", 0.0)),
        ),
        _kpi_card(
            "Kredit (år)",
            _fmt_amount(k.get("total_kredit", 0.0)),
        ),
        _kpi_card(
            "Transaksjoner",
            _fmt_int(k.get("total_transaksjoner", 0)),
            f"{_fmt_int(k.get('antall_bilag', 0))} bilag",
        ),
        _kpi_card(
            "Med MVA-beløp",
            _fmt_int(k.get("mva_tx", 0)),
            f"Sum MVA: {_fmt_amount(k.get('mva_belop', 0.0))}",
        ),
    ]
    return '<div class="kpi-grid">' + "".join(cards) + "</div>"


def _build_hb_accounts_table(rows: Sequence[HbAccountRow]) -> str:
    if not rows:
        return '<div class="empty-note">Ingen reskontrokontoer funnet.</div>'
    head = (
        "<tr>"
        "<th>Konto</th><th>Kontonavn</th>"
        "<th class='num'>Antall poster</th>"
        "<th class='num'>IB</th>"
        "<th class='num'>Bevegelse</th>"
        "<th class='num'>UB</th>"
        "</tr>"
    )
    body_rows: list[str] = []
    tot_ib = tot_bev = tot_ub = tot_ant = 0
    for r in rows:
        body_rows.append(
            "<tr>"
            f"<td>{_esc(r.konto)}</td>"
            f"<td class='navn'>{_esc(r.kontonavn) if r.kontonavn else '<span class=\"muted\">—</span>'}</td>"
            f"<td class='num'>{_fmt_int(r.antall)}</td>"
            f"<td class='num'>{_fmt_amount(r.ib)}</td>"
            f"<td class='num'>{_fmt_amount(r.bevegelse)}</td>"
            f"<td class='num'>{_fmt_amount(r.ub)}</td>"
            "</tr>"
        )
        tot_ib += r.ib
        tot_bev += r.bevegelse
        tot_ub += r.ub
        tot_ant += r.antall
    body_rows.append(
        "<tr class='sum-row'>"
        "<td colspan='2'>Sum</td>"
        f"<td class='num'>{_fmt_int(tot_ant)}</td>"
        f"<td class='num'>{_fmt_amount(tot_ib)}</td>"
        f"<td class='num'>{_fmt_amount(tot_bev)}</td>"
        f"<td class='num'>{_fmt_amount(tot_ub)}</td>"
        "</tr>"
    )
    return (
        "<table class='data-table'>"
        "<thead>" + head + "</thead>"
        "<tbody>" + "".join(body_rows) + "</tbody>"
        "</table>"
    )


def _build_reconciliation(recon: dict) -> str:
    if not recon or not recon.get("has_sb"):
        return (
            '<div class="empty-note">'
            'Ingen saldobalanse er lastet inn — kan ikke avstemme mot HB-kontoer.'
            '</div>'
        )
    diff = float(recon.get("diff", 0.0))
    diff_cls = "ok" if abs(diff) < 0.5 else "warn"
    missing_note = ""
    if recon.get("missing_accounts"):
        missing = ", ".join(recon["missing_accounts"])
        missing_note = (
            f'<div class="empty-note">Kontoer uten treff i SB: {_esc(missing)}</div>'
        )
    return (
        '<div class="recon-card">'
        '<div class="recon-box">'
        '<div class="recon-label">Reskontro UB</div>'
        f'<div class="recon-value">{_fmt_amount(recon.get("reskontro_ub", 0.0))}</div>'
        '</div>'
        '<div class="recon-box">'
        '<div class="recon-label">SB UB (samme kontoer)</div>'
        f'<div class="recon-value">{_fmt_amount(recon.get("sb_ub", 0.0))}</div>'
        '</div>'
        f'<div class="recon-box {diff_cls}">'
        '<div class="recon-label">Avvik</div>'
        f'<div class="recon-value">{_fmt_amount(diff)}</div>'
        '<div class="recon-detail">'
        + ("Avstemt." if abs(diff) < 0.5 else "⚠ Følges opp")
        + '</div>'
        '</div>'
        '</div>'
        + missing_note
    )


def _build_party_table(
    rows: Sequence[PartyRow],
    *,
    navn_hdr: str,
    highlight_col: str = "ub",
    include_dager: bool = True,
) -> str:
    """Generisk topp-N tabell over PartyRow."""
    if not rows:
        return '<div class="empty-note">Ingen poster å vise.</div>'

    total_highlight = sum(abs(getattr(r, highlight_col)) for r in rows) or 1.0

    head_cells = [
        "<th style='width:28px'>#</th>",
        f"<th>{_esc(navn_hdr)}</th>",
        "<th>Konto</th>",
        "<th class='num'>Antall</th>",
        "<th class='num'>IB</th>",
        "<th class='num'>Debet</th>",
        "<th class='num'>Kredit</th>",
        "<th class='num'>UB</th>",
        "<th class='num'>Snitt bilag</th>",
    ]
    if include_dager:
        head_cells.append("<th class='num'>Siste</th>")
    head_cells.append("<th class='num'>Andel</th>")

    body_rows: list[str] = []
    for i, r in enumerate(rows, 1):
        navn_html = (
            _esc(r.navn) if r.navn
            else f'<span class="muted">({r.nr})</span>'
        )
        orgnr_html = (
            f'<div class="orgnr">{_esc(r.orgnr)}</div>'
            if r.orgnr and r.orgnr.strip() and r.orgnr != "nan" else ""
        )
        dager_html = (
            f"<td class='num'>{_fmt_days(r.dager_siden_siste)}</td>"
            if include_dager else ""
        )
        andel = abs(getattr(r, highlight_col)) / total_highlight * 100.0
        cls_ub = _amount_class(r.ub) if highlight_col == "ub" else ""
        body_rows.append(
            "<tr>"
            f"<td><span class='rank-pill'>{i}</span></td>"
            f"<td class='navn'><strong>{navn_html}</strong>"
            f"<div class='orgnr'>{_esc(r.nr)}"
            + (f" · {_esc(r.orgnr)}" if r.orgnr and r.orgnr != 'nan' else "")
            + "</div>"
            "</td>"
            f"<td>{_esc(r.hb_konto)}</td>"
            f"<td class='num'>{_fmt_int(r.antall)}</td>"
            f"<td class='num'>{_fmt_amount(r.ib)}</td>"
            f"<td class='num'>{_fmt_amount(r.debet)}</td>"
            f"<td class='num'>{_fmt_amount(r.kredit)}</td>"
            f"<td class='num {cls_ub}'>{_fmt_amount(r.ub)}</td>"
            f"<td class='num'>{_fmt_amount(r.snitt_bilag)}</td>"
            + dager_html +
            f"<td class='num'>{_fmt_pct(andel)}</td>"
            "</tr>"
        )
        _ = orgnr_html  # orgnr vises allerede i navn-kolonnen

    return (
        "<table class='data-table'>"
        "<thead><tr>" + "".join(head_cells) + "</tr></thead>"
        "<tbody>" + "".join(body_rows) + "</tbody>"
        "</table>"
    )


def _build_transactions_table(rows: Sequence[TransactionRow]) -> str:
    if not rows:
        return '<div class="empty-note">Ingen transaksjoner å vise.</div>'
    head = (
        "<tr>"
        "<th style='width:28px'>#</th>"
        "<th>Dato</th>"
        "<th>Bilag</th>"
        "<th>Konto</th>"
        "<th>Motpart</th>"
        "<th>Tekst</th>"
        "<th class='num'>Beløp</th>"
        "</tr>"
    )
    body: list[str] = []
    for i, r in enumerate(rows, 1):
        party = (
            f"{_esc(r.navn)} <span class='muted'>({_esc(r.nr)})</span>"
            if r.navn else _esc(r.nr)
        )
        cls = "change-pos" if r.belop > 0 else "change-neg"
        body.append(
            "<tr>"
            f"<td><span class='rank-pill'>{i}</span></td>"
            f"<td>{_esc(r.dato)}</td>"
            f"<td>{_esc(r.bilag)}</td>"
            f"<td>{_esc(r.konto)}</td>"
            f"<td class='navn'>{party}</td>"
            f"<td class='navn'>{_esc(r.tekst)}</td>"
            f"<td class='num {cls}'>{_fmt_amount(r.belop)}</td>"
            "</tr>"
        )
    return (
        "<table class='data-table'>"
        "<thead>" + head + "</thead>"
        "<tbody>" + "".join(body) + "</tbody>"
        "</table>"
    )


def _build_motpost_table(rows: Sequence[MotpostRow]) -> str:
    if not rows:
        return '<div class="empty-note">Ingen motposter funnet.</div>'
    head = (
        "<tr>"
        "<th>Konto</th>"
        "<th>Kontonavn</th>"
        "<th class='num'>Antall</th>"
        "<th class='num'>Sum beløp</th>"
        "<th class='num'>Andel</th>"
        "</tr>"
    )
    body = []
    for r in rows:
        body.append(
            "<tr>"
            f"<td>{_esc(r.konto)}</td>"
            f"<td class='navn'>{_esc(r.kontonavn)}</td>"
            f"<td class='num'>{_fmt_int(r.antall)}</td>"
            f"<td class='num'>{_fmt_amount(r.sum_belop)}</td>"
            f"<td class='num'>{_fmt_pct(r.andel_pct)}</td>"
            "</tr>"
        )
    return (
        "<table class='data-table'>"
        "<thead>" + head + "</thead>"
        "<tbody>" + "".join(body) + "</tbody>"
        "</table>"
    )


def _build_aging(buckets: Sequence[AgingBucket]) -> str:
    if not buckets:
        return '<div class="empty-note">Aldersanalyse ikke tilgjengelig (balansedato mangler).</div>'
    tot_abs = sum(abs(b.sum_gjenstar) for b in buckets) or 1.0
    rows: list[str] = []
    for b in buckets:
        pct = abs(b.sum_gjenstar) / tot_abs * 100.0
        rows.append(
            f'<div class="aging-label">{_esc(b.label)}</div>'
            f'<div class="aging-bar-wrap"><div class="aging-bar-fill" '
            f'style="width:{pct:.1f}%"></div></div>'
            f'<div class="aging-amount">{_fmt_amount(b.sum_gjenstar)}</div>'
            f'<div class="aging-count">{_fmt_int(b.antall)}</div>'
        )
    return '<div class="aging-bars">' + "".join(rows) + "</div>"


def _build_concentration(c: dict) -> str:
    if not c or c.get("count", 0) == 0:
        return '<div class="empty-note">Ingen data for konsentrasjonsanalyse.</div>'
    return (
        '<div class="conc-grid">'
        '<div class="conc-card">'
        '<div class="conc-label">Topp 5 andel</div>'
        f'<div class="conc-value">{_fmt_pct(c.get("top5_pct", 0))}</div>'
        '<div class="conc-detail">av total UB</div>'
        '</div>'
        '<div class="conc-card">'
        '<div class="conc-label">Topp 10 andel</div>'
        f'<div class="conc-value">{_fmt_pct(c.get("top10_pct", 0))}</div>'
        '<div class="conc-detail">av total UB</div>'
        '</div>'
        '<div class="conc-card">'
        '<div class="conc-label">HHI</div>'
        f'<div class="conc-value">{_fmt_int(c.get("hhi", 0))}</div>'
        '<div class="conc-detail">0 = fullt diversifisert, 10 000 = monopol</div>'
        '</div>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# HTML-template
# ---------------------------------------------------------------------------

_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="utf-8">
<title>Reskontro $party_label — $client $year</title>
<style>
$css
</style>
</head>
<body class="theme-$theme">

<!-- ============ Side 1 — Sammendrag ============ -->
<div class="page">
  <div class="report-header">
    <div>
      <div class="report-title">$client</div>
      <div class="report-subtitle">Reskontro — $party_label_cap $year</div>
    </div>
    <div class="report-subtitle">$reference_date</div>
  </div>

  <div class="section-title" style="margin-top:0">Sammendrag</div>
  $kpi_grid_html

  <div class="section-title">HB-kontoer som inngår</div>
  $hb_accounts_html

  <div class="section-title">Avstemming mot saldobalanse</div>
  $reconciliation_html
</div>

<!-- ============ Side 2 — Topp UB-saldo ============ -->
<div class="page">
  <div class="report-header">
    <div>
      <div class="report-title">$client</div>
      <div class="report-subtitle">Topp $top_n — Største UB-saldo — $party_label_cap $year</div>
    </div>
  </div>

  <div class="section-title" style="margin-top:0">Topp $top_n — Største UB-saldo</div>
  <div class="subhead">Ranket etter absolutt UB pr. $reference_date.</div>
  $top_ub_html
</div>

<!-- ============ Side 3 — Topp signed-bevegelse ============ -->
<div class="page">
  <div class="report-header">
    <div>
      <div class="report-title">$client</div>
      <div class="report-subtitle">Topp $top_n — Største $signed_label_cap-bevegelse — $party_label_cap $year</div>
    </div>
  </div>

  <div class="section-title" style="margin-top:0">Topp $top_n — Største $signed_label_cap-bevegelse</div>
  <div class="subhead">$signed_helpertext</div>
  $top_signed_html
</div>

<!-- ============ Side 4 — Brutto aktivitet ============ -->
<div class="page">
  <div class="report-header">
    <div>
      <div class="report-title">$client</div>
      <div class="report-subtitle">Topp $top_n — Brutto aktivitet — $party_label_cap $year</div>
    </div>
  </div>

  <div class="section-title" style="margin-top:0">Topp $top_n — Høyeste brutto aktivitet</div>
  <div class="subhead">Sum av debet + |kredit| — viser mest aktive $party_label uavhengig av saldo.</div>
  $top_activity_html
</div>

<!-- ============ Side 5 — Enkelttransaksjoner + counter_balance ============ -->
<div class="page">
  <div class="report-header">
    <div>
      <div class="report-title">$client</div>
      <div class="report-subtitle">Topp $top_n — Enkelttransaksjoner — $party_label_cap $year</div>
    </div>
  </div>

  <div class="section-title" style="margin-top:0">Topp $top_n — Største enkelttransaksjoner</div>
  <div class="subhead">Enkeltposter med høyest |beløp|.</div>
  $top_transactions_html

  $counter_balance_section
</div>

<!-- ============ Side 6 — Motposter debet ============ -->
<div class="page">
  <div class="report-header">
    <div>
      <div class="report-title">$client</div>
      <div class="report-subtitle">Motposter — debetside — $party_label_cap $year</div>
    </div>
  </div>

  <div class="section-title" style="margin-top:0">Motposter — debetside</div>
  <div class="subhead">Kontoer som debiteres i bilag med $party_label-transaksjoner.</div>
  $motpost_debet_html
</div>

<!-- ============ Side 7 — Motposter kredit ============ -->
<div class="page">
  <div class="report-header">
    <div>
      <div class="report-title">$client</div>
      <div class="report-subtitle">Motposter — kreditside — $party_label_cap $year</div>
    </div>
  </div>

  <div class="section-title" style="margin-top:0">Motposter — kreditside</div>
  <div class="subhead">Kontoer som krediteres i bilag med $party_label-transaksjoner.</div>
  $motpost_kredit_html
</div>

<!-- ============ Side 8 — Alder + Konsentrasjon ============ -->
<div class="page">
  <div class="report-header">
    <div>
      <div class="report-title">$client</div>
      <div class="report-subtitle">Aldersanalyse og konsentrasjon — $party_label_cap $year</div>
    </div>
  </div>

  <div class="section-title" style="margin-top:0">Aldersanalyse — åpne poster</div>
  $aging_html

  <div class="section-title">Konsentrasjon</div>
  $concentration_html
</div>

</body>
</html>
""")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_report_html(report: ReskontroReport, *, top_n: int = 10) -> str:
    """Bygg komplett HTML-rapport for kunde- eller leverandør-reskontro."""

    is_kunder = report.mode == "kunder"
    theme = "kunder" if is_kunder else "lev"
    party_label = "kunder" if is_kunder else "leverandører"
    party_label_cap = "Kunder" if is_kunder else "Leverandører"
    navn_hdr = "Kunde" if is_kunder else "Leverandør"

    if is_kunder:
        signed_label_cap = "kredit"
        signed_helpertext = (
            "For kunder: størst sum på kreditsiden (innbetalinger og kreditnotaer)."
        )
        signed_col = "kredit"
    else:
        signed_label_cap = "debet"
        signed_helpertext = (
            "For leverandører: størst sum på debetsiden (utbetalinger og returkreditnotaer)."
        )
        signed_col = "debet"

    # Motsatt-fortegn-seksjon — vis kun hvis det finnes rader
    cb_rows = report.counter_balance_rows
    if cb_rows:
        cb_title = (
            "Kunder med negativ UB (forskudd/kreditnota)"
            if is_kunder else
            "Leverandører med negativ gjeld (tilgode hos lev.)"
        )
        counter_balance_section = (
            f'<div class="section-title">{_esc(cb_title)}</div>'
            + _build_party_table(cb_rows, navn_hdr=navn_hdr, highlight_col="ub",
                                 include_dager=True)
        )
    else:
        counter_balance_section = ""

    subs = {
        "css": _CSS,
        "client": _esc(report.client or "(uten klient)"),
        "year": _esc(report.year or ""),
        "theme": theme,
        "party_label": party_label,
        "party_label_cap": party_label_cap,
        "top_n": str(top_n),
        "reference_date": _esc(report.reference_date or ""),
        "signed_label_cap": signed_label_cap,
        "signed_helpertext": _esc(signed_helpertext),
        "kpi_grid_html": _build_kpi_grid(report),
        "hb_accounts_html": _build_hb_accounts_table(report.hb_accounts),
        "reconciliation_html": _build_reconciliation(report.hb_reconciliation),
        "top_ub_html": _build_party_table(
            report.top_ub, navn_hdr=navn_hdr, highlight_col="ub", include_dager=True,
        ),
        "top_signed_html": _build_party_table(
            report.top_signed_bevegelse, navn_hdr=navn_hdr,
            highlight_col=signed_col, include_dager=True,
        ),
        "top_activity_html": _build_party_table(
            report.top_activity, navn_hdr=navn_hdr,
            highlight_col="debet" if not is_kunder else "kredit",
            include_dager=True,
        ),
        "top_transactions_html": _build_transactions_table(report.top_transactions),
        "counter_balance_section": counter_balance_section,
        "motpost_debet_html": _build_motpost_table(report.motpost_debet),
        "motpost_kredit_html": _build_motpost_table(report.motpost_kredit),
        "aging_html": _build_aging(report.aging),
        "concentration_html": _build_concentration(report.concentration),
    }
    return _TEMPLATE.substitute(subs)


def save_report_html(
    path: str | Path,
    report: ReskontroReport,
    *,
    top_n: int = 10,
) -> str:
    html = build_report_html(report, top_n=top_n)
    out = Path(path)
    if out.suffix.lower() not in (".html", ".htm"):
        out = out.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out)


def save_report_pdf(
    path: str | Path,
    report: ReskontroReport,
    *,
    top_n: int = 10,
) -> str:
    """Lagre rapporten som PDF via Playwright (headless Chromium)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ImportError(
            "playwright er ikke installert. Installer med:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        )

    html = build_report_html(report, top_n=top_n)

    out = Path(path)
    if out.suffix.lower() != ".pdf":
        out = out.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    import tempfile
    tmp_html = Path(tempfile.gettempdir()) / f"utvalg_reskontro_{report.mode}_tmp.html"
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
    report: ReskontroReport,
    *,
    top_n: int = 10,
    path: str | Path | None = None,
) -> str:
    """Generer rapport og åpne i standard browser (for utvikling/preview)."""
    if path is None:
        import tempfile
        tmp = Path(tempfile.gettempdir()) / f"utvalg_reskontro_{report.mode}.html"
        path = tmp

    saved = save_report_html(path, report, top_n=top_n)
    try:
        webbrowser.open(Path(saved).as_uri())
    except Exception:
        pass
    return saved


# ---------------------------------------------------------------------------
# Høynivå-convenience (DataFrame → HTML/PDF)
# ---------------------------------------------------------------------------

def build_html_from_df(
    df,
    *,
    mode: str = "kunder",
    client: str = "",
    year: str | int = "",
    reference_date: str = "",
    sb_df=None,
    top_n: int = 10,
) -> str:
    """Ett kall fra DataFrame til HTML."""
    report = compute_reskontro_report(
        df, mode=mode, client=client, year=year,
        reference_date=reference_date, sb_df=sb_df, top_n=top_n,
    )
    return build_report_html(report, top_n=top_n)

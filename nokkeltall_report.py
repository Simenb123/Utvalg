"""nokkeltall_report.py — Generer HTML-rapport med nøkkeltall og SVG-charts.

Bruker string.Template (stdlib) — ingen jinja2/weasyprint dependency.
Rapporten kan åpnes i browser eller skrives ut som PDF.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path
from string import Template

import pandas as pd

from nokkeltall_engine import NokkeltallResult, compute_nokkeltall
from nokkeltall_svg import (
    svg_donut,
    svg_hbar,
    svg_kpi_card,
    svg_vbar,
)


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
@page { size: A4 landscape; margin: 12mm 15mm; }
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
    body { background: white; margin: 0; padding: 0; }
    .page { box-shadow: none; margin: 0; padding: 16px 20px; border-radius: 0; max-width: none; }
    .no-print { display: none !important; }
    .report-header { border-bottom-color: #4472C4; }
    .data-table td { padding: 3px 8px; }
    .data-table th { padding: 5px 8px; }
    .section-title { margin: 16px 0 8px 0; }
    .kpi-grid { gap: 10px; margin-bottom: 16px; }
    .kpi-card { padding: 10px 12px; }
    .kpi-value { font-size: 17px; }
    .chart-row { gap: 20px; margin: 10px 0; }
    .report-footer { margin-top: 10px; }
}

/* Header */
.report-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    border-bottom: 3px solid #4472C4;
    padding-bottom: 10px;
    margin-bottom: 18px;
}
.report-title { font-size: 20px; font-weight: 700; color: #1a1a2e; }
.report-subtitle { font-size: 12px; color: #7f8c8d; }

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
.data-table .num { text-align: right; font-variant-numeric: tabular-nums; }
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

<!-- ============ Side 1: Finansiell oversikt ============ -->
<div class="page">
  <div class="report-header">
    <div>
      <div class="report-title">$client</div>
      <div class="report-subtitle">Finansiell oversikt — $year</div>
    </div>
  </div>

  <div class="chart-row" style="margin-top:0">
    <div class="chart-box">
      <div class="chart-label">Kostnadsfordeling</div>
      $cost_donut_svg
    </div>
    <div class="chart-box">
      <div class="chart-label">Balansefordeling</div>
      $bs_donut_svg
    </div>
  </div>

  <div class="chart-row">
    <div class="chart-box" style="flex:1.4">
      <div class="section-title">Resultatregnskap</div>
      $pl_table_html
    </div>
    <div class="chart-box" style="flex:1">
      <div class="section-title">Balanse</div>
      $bs_table_html
    </div>
  </div>
</div>

<!-- ============ Side 2: Nøkkeltall og analyse ============ -->
<div class="page">
  <div class="report-header">
    <div>
      <div class="report-title">$client</div>
      <div class="report-subtitle">Nøkkeltall og analyse — $year</div>
    </div>
  </div>

  $metrics_table_html

  <div class="chart-row">
    <div class="chart-box" style="flex:1">
      <div class="chart-label">Hovedposter resultat$prev_label</div>
      $pl_bar_svg
    </div>
  </div>

  $activity_html
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

    prev_cols = ""
    if has_prev:
        prev_cols = ('<th class="num">I fjor</th>'
                     '<th class="num">Endring</th>'
                     '<th class="num">%</th>')

    rows: list[str] = []
    for line in lines:
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


def _build_metrics_table(metrics: list, has_prev: bool) -> str:
    if not metrics:
        return ""

    prev_cols = ""
    if has_prev:
        prev_cols = '<th class="num">Forrige år</th><th class="num">Endring</th>'

    rows: list[str] = []
    current_cat = ""
    for m in metrics:
        if m.value is None:
            continue
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
    if not top_activity:
        return ""

    parts = ['<div class="section-title">Topp regnskapslinjer etter transaksjonsvolum</div>']
    parts.append('<div class="activity-grid">')
    for item in top_activity:
        change_html = ""
        if item.get("change_pct") is not None:
            ch = item["change_pct"]
            color = "#27AE60" if ch >= 0 else "#E74C3C"
            sign = "+" if ch >= 0 else ""
            change_html = f' <span style="color:{color};font-weight:600">({sign}{ch:.1f}%)</span>'

        parts.append(
            f'<div class="activity-card">'
            f'<div class="ac-title">{_esc(item["name"])}</div>'
            f'<div class="ac-value">{_esc(item["formatted_ub"])}{change_html}</div>'
            f'<div class="ac-detail">{item["transactions"]:,} transaksjoner</div>'
            f'</div>'.replace(",", " ")
        )
    parts.append("</div>")
    return "\n".join(parts)


def _build_pl_bar_items(pl_summary: list[dict]) -> list[dict]:
    """Velg hovedposter for bar chart."""
    show_regnr = {10, 20, 40, 50, 70, 80, 280}
    return [line for line in pl_summary if line.get("regnr") in show_regnr]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_report_html(result: NokkeltallResult) -> str:
    """Bygg komplett HTML-rapport fra NokkeltallResult."""

    pl_table = _build_summary_table(result.pl_summary, result.has_prev_year)
    bs_table = _build_summary_table(result.bs_summary, result.has_prev_year)
    metrics_table = _build_metrics_table(result.metrics, result.has_prev_year)
    activity_html = _build_activity_html(result.top_activity)

    # SVG charts
    cost_donut = svg_donut(result.cost_breakdown, width=280, height=260)
    bs_donut = svg_donut(result.bs_breakdown, width=280, height=260)

    pl_bar_items = _build_pl_bar_items(result.pl_summary)
    pl_bar = svg_vbar(
        pl_bar_items,
        width=700,
        height=220,
        prev_key="prev" if result.has_prev_year else None,
    )

    prev_label = " (blå = i år, lys = i fjor)" if result.has_prev_year else ""

    return _TEMPLATE.substitute(
        css=_CSS,
        client=_esc(result.client),
        year=_esc(result.year),
        pl_table_html=pl_table,
        bs_table_html=bs_table,
        metrics_table_html=metrics_table,
        cost_donut_svg=cost_donut,
        bs_donut_svg=bs_donut,
        pl_bar_svg=pl_bar,
        prev_label=prev_label,
        activity_html=activity_html,
    )


def save_report_html(
    path: str | Path,
    *,
    rl_df: pd.DataFrame,
    transactions_df: pd.DataFrame | None = None,
    client: str = "",
    year: str | int = "",
) -> str:
    """Beregn nøkkeltall og lagre HTML-rapport.

    Returns path to saved file.
    """
    result = compute_nokkeltall(
        rl_df,
        transactions_df=transactions_df,
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
                margin={"top": "15mm", "bottom": "15mm",
                        "left": "15mm", "right": "15mm"},
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

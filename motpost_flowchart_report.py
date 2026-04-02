"""motpost_flowchart_report.py — HTML/PDF-rapport for motpost-flytdiagram.

Genererer en visuell rapport som viser motpost-relasjoner mellom kontoer
som et flytdiagram med bokser og piler.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

import pandas as pd

from motpost_flowchart_engine import MotpostTree, build_motpost_tree
from motpost_flowchart_svg import render_motpost_flowchart


# ---------------------------------------------------------------------------
# CSS
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
}
@media print {
    body { background: white; margin: 0; padding: 0; }
    .page { box-shadow: none; margin: 0; padding: 16px 20px;
            border-radius: 0; max-width: none; }
}
.report-header {
    border-bottom: 3px solid #4472C4;
    padding-bottom: 10px;
    margin-bottom: 18px;
}
.report-title { font-size: 20px; font-weight: 700; color: #1a1a2e; }
.report-subtitle { font-size: 12px; color: #7f8c8d; }
.flowchart-container {
    overflow-x: auto;
    margin: 16px 0;
    text-align: center;
}
.legend {
    display: flex;
    gap: 24px;
    margin-top: 16px;
    flex-wrap: wrap;
}
.legend-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: #555;
}
.legend-dot {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 2px solid;
}
.summary-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
    margin-top: 16px;
}
.summary-table th {
    background: #f0f4f8;
    color: #4472C4;
    font-weight: 600;
    text-align: left;
    padding: 5px 10px;
    border-bottom: 2px solid #d5dde5;
    font-size: 10px;
    text-transform: uppercase;
}
.summary-table td {
    padding: 4px 10px;
    border-bottom: 1px solid #eef1f5;
}
.summary-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.section-title {
    font-size: 13px;
    font-weight: 700;
    color: #4472C4;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 20px 0 8px 0;
    padding-bottom: 3px;
    border-bottom: 1px solid #e8ecf1;
}
"""


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="utf-8">
<title>Motpostanalyse — $client</title>
<style>$css</style>
</head>
<body>
<div class="page">
  <div class="report-header">
    <div class="report-title">$client</div>
    <div class="report-subtitle">Motpostanalyse — $accounts_label — $year</div>
  </div>

  <div class="flowchart-container">
    $flowchart_svg
  </div>

  <div class="legend">
    <div class="legend-item">
      <div class="legend-dot" style="background:#E8EEF7;border-color:#4472C4"></div>
      $root_label
    </div>
    <div class="legend-item">
      <div class="legend-dot" style="background:#FDF0E5;border-color:#ED7D31"></div>
      Motposter (ledd 1)
    </div>
    <div class="legend-item">
      <div class="legend-dot" style="background:#EFF6EA;border-color:#70AD47"></div>
      Motposter (ledd 2)
    </div>
    <div class="legend-item">
      <span style="color:#95A5A6">→</span> Pilbredde = relativ andel
    </div>
  </div>

  $summary_html
</div>
</body>
</html>
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    import html
    return html.escape(str(text))


def _format_amount(val: float) -> str:
    if abs(val) >= 1e6:
        return f"{val / 1e6:,.1f} M".replace(",", " ")
    if abs(val) >= 1e3:
        return f"{val / 1e3:,.0f} k".replace(",", " ")
    return f"{val:,.0f}".replace(",", " ")


def _build_summary_table(tree: MotpostTree, *, rl_mode: bool = False) -> str:
    """Bygg oppsummeringstabell med motpost-detaljer."""
    rows: list[str] = []

    for root in tree.root_nodes:
        rows.append(
            f'<tr style="font-weight:700;background:#f6f8fb">'
            f'<td>{_esc(root.konto)}</td>'
            f'<td>{_esc(root.konto_name)}</td>'
            f'<td class="num">{_format_amount(root.total_amount)}</td>'
            f'<td></td><td></td></tr>'
        )
        for edge in root.edges:
            rows.append(
                f'<tr>'
                f'<td style="padding-left:24px">→ {_esc(edge.target)}</td>'
                f'<td>{_esc(edge.target_name)}</td>'
                f'<td class="num">{_format_amount(edge.amount)}</td>'
                f'<td class="num">{edge.pct:.1f} %</td>'
                f'<td class="num">{edge.voucher_count:,}</td></tr>'
                .replace(",", " ")
            )
            # Ledd 2
            child = getattr(edge, "_child_node", None)
            if child:
                for edge2 in child.edges:
                    rows.append(
                        f'<tr style="color:#888">'
                        f'<td style="padding-left:48px">→ {_esc(edge2.target)}</td>'
                        f'<td>{_esc(edge2.target_name)}</td>'
                        f'<td class="num">{_format_amount(edge2.amount)}</td>'
                        f'<td class="num">{edge2.pct:.1f} %</td>'
                        f'<td class="num">{edge2.voucher_count:,}</td></tr>'
                        .replace(",", " ")
                    )

    if not rows:
        return ""

    return (
        '<div class="section-title">Detaljert motpostfordeling</div>'
        '<table class="summary-table">'
        '<thead><tr>'
        + (
            '<th>Regnskapslinje</th><th>Navn</th>'
            if rl_mode else
            '<th>Konto</th><th>Kontonavn</th>'
        ) +
        '<th class="num">Beløp</th><th class="num">Andel</th>'
        '<th class="num">Bilag</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_flowchart_html(
    tree: MotpostTree,
    *,
    rl_mode: bool = False,
) -> str:
    """Bygg komplett HTML-rapport fra MotpostTree.

    Parameters
    ----------
    rl_mode : Når True vises "Valgte regnskapslinjer" i forklaring.
    """
    svg = render_motpost_flowchart(tree)
    summary = _build_summary_table(tree, rl_mode=rl_mode)

    accounts_label = ", ".join(
        f"{n.konto_name or n.konto}" for n in tree.root_nodes
    )
    if len(accounts_label) > 80:
        accounts_label = accounts_label[:77] + "…"

    root_label = "Valgte regnskapslinjer" if rl_mode else "Valgte kontoer"

    return _TEMPLATE.substitute(
        css=_CSS,
        client=_esc(tree.client),
        year=_esc(tree.year),
        accounts_label=_esc(accounts_label),
        flowchart_svg=svg,
        summary_html=summary,
        root_label=root_label,
    )


def save_flowchart_html(
    path: str | Path,
    *,
    df: pd.DataFrame,
    start_accounts: list[str],
    max_depth: int = 2,
    client: str = "",
    year: str = "",
    konto_to_rl: dict | None = None,
) -> str:
    """Bygg motpost-flytdiagram og lagre som HTML."""
    rl_mode = bool(konto_to_rl)
    tree = build_motpost_tree(
        df, start_accounts,
        max_depth=max_depth,
        client=client,
        year=year,
        konto_to_rl=konto_to_rl,
    )
    html_content = build_flowchart_html(tree, rl_mode=rl_mode)

    out = Path(path)
    if out.suffix.lower() != ".html":
        out = out.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_content, encoding="utf-8")
    return str(out)


def save_flowchart_pdf(
    path: str | Path,
    *,
    df: pd.DataFrame,
    start_accounts: list[str],
    max_depth: int = 2,
    client: str = "",
    year: str = "",
    konto_to_rl: dict | None = None,
) -> str:
    """Bygg motpost-flytdiagram og lagre som PDF via playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ImportError(
            "playwright er ikke installert. Installer med:\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        )

    rl_mode = bool(konto_to_rl)
    tree = build_motpost_tree(
        df, start_accounts,
        max_depth=max_depth,
        client=client,
        year=year,
        konto_to_rl=konto_to_rl,
    )
    html_content = build_flowchart_html(tree, rl_mode=rl_mode)

    out = Path(path)
    if out.suffix.lower() != ".pdf":
        out = out.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    import tempfile
    tmp_html = Path(tempfile.gettempdir()) / "utvalg_flowchart_tmp.html"
    tmp_html.write_text(html_content, encoding="utf-8")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(tmp_html.as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(out), landscape=True, print_background=True,
                format="A4",
                margin={"top": "12mm", "bottom": "12mm",
                        "left": "15mm", "right": "15mm"},
            )
            browser.close()
    finally:
        try:
            tmp_html.unlink(missing_ok=True)
        except Exception:
            pass

    return str(out)

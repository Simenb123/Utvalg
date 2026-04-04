"""motpost_flowchart_report.py — HTML/PDF-rapport for motpost-flytdiagram.

HTML-versjonen er fullstendig interaktiv: klikk på en boks for å utvide
eller kollapse dens motposter. Tredata embeddes som JSON i siden og
renderes via vanilla JS + SVG — ingen eksterne avhengigheter.

PDF-versjonen bruker den statiske SVG-renderte versjonen.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from motpost_flowchart_engine import MotpostTree, build_motpost_tree, tree_to_dict
from motpost_flowchart_svg import render_motpost_flowchart


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    import html
    return html.escape(str(text))


def _format_amount(val: float) -> str:
    if abs(val) >= 1e6:
        return f"{val / 1e6:,.1f} M".replace(",", "\u202f")
    if abs(val) >= 1e3:
        return f"{val / 1e3:,.0f} k".replace(",", "\u202f")
    return f"{val:,.0f}".replace(",", "\u202f")


# ---------------------------------------------------------------------------
# Interactive HTML (JS-rendered)
# ---------------------------------------------------------------------------

_INTERACTIVE_JS = r"""
(function() {
'use strict';

// ────────────────────────────────────────────────────────────
// Constants
// ────────────────────────────────────────────────────────────
const COLORS  = ['#4472C4','#ED7D31','#70AD47','#FFC000','#5B9BD5'];
const BGCOL   = ['#E8EEF7','#FDF0E5','#EFF6EA','#FFF8E1','#EBF3FA'];
// Kontonivå-modus: grå pallett
const KONTO_COLOR = '#607D8B';
const KONTO_BG    = '#ECEFF1';
const ARROW       = '#95A5A6';
const TEXTCOL     = '#2C3E50';
const BOX_W       = 188;
const BOX_H_MIN   = 62;
const BOX_H_MAX   = 90;
const COL_GAP     = 130;
const ROW_GAP     = 10;

const SVG_NS = 'http://www.w3.org/2000/svg';

// ────────────────────────────────────────────────────────────
// State
// ────────────────────────────────────────────────────────────
// expanded[id]   = true/false  — er RL-motpostene vist?
// acctMode[id]   = true/false  — er vi i konto-drilldown-modus?
const expanded = {};
const acctMode = {};
const treeData = window.__MOTPOST_TREE__;

// ────────────────────────────────────────────────────────────
// Stable IDs
// ────────────────────────────────────────────────────────────
function assignIds(nodes, parentId, isAcct) {
    (nodes || []).forEach(n => {
        let prefix = isAcct ? 'acct:' : 'rl:';
        n._id = parentId ? parentId + '/' + prefix + n.key : prefix + n.key;
        if (n.children) assignIds(n.children, n._id, isAcct);
        if (n.accounts) assignIds(n.accounts, n._id, true);
        if (!parentId) expanded[n._id] = false; // roots collapsed by default
        else if (!(n._id in expanded)) expanded[n._id] = false;
    });
}
assignIds(treeData.root_nodes, null, false);

// ────────────────────────────────────────────────────────────
// Build visible columns
// ────────────────────────────────────────────────────────────
function getActiveChildren(node) {
    if (acctMode[node._id]) {
        return node.accounts || [];
    }
    return node.children || [];
}

function buildColumns() {
    const cols = {};
    function visit(nodes, depth) {
        nodes.forEach(n => {
            if (!cols[depth]) cols[depth] = [];
            cols[depth].push(n);
            if (expanded[n._id]) {
                let kids = getActiveChildren(n);
                if (kids.length) visit(kids, depth + 1);
            }
        });
    }
    visit(treeData.root_nodes, 0);
    return cols;
}

// ────────────────────────────────────────────────────────────
// Layout
// ────────────────────────────────────────────────────────────
function layout(cols) {
    const positions = {};
    const allAmts = Object.values(cols).flat().map(n => n.amount || 0);
    const maxAmt = Math.max(...allAmts) || 1;
    const maxDepth = Math.max(0, ...Object.keys(cols).map(Number));
    const totalW = 40 + (maxDepth + 1) * (BOX_W + COL_GAP);

    for (let depth = 0; depth <= maxDepth; depth++) {
        let col = cols[depth] || [];
        let x = 30 + depth * (BOX_W + COL_GAP);
        let y = 30;
        col.forEach(n => {
            let ratio = n.amount / maxAmt;
            let h = Math.max(BOX_H_MIN, Math.min(BOX_H_MAX,
                BOX_H_MIN + ratio * (BOX_H_MAX - BOX_H_MIN)));
            positions[n._id] = { x, y, w: BOX_W, h };
            y += h + ROW_GAP;
        });
    }
    return { positions, totalW };
}

// ────────────────────────────────────────────────────────────
// SVG helpers
// ────────────────────────────────────────────────────────────
function el(tag, attrs, children) {
    let e = document.createElementNS(SVG_NS, tag);
    if (attrs) Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
    if (children) children.forEach(c => c && e.appendChild(c));
    return e;
}
function txt(s) { return document.createTextNode(String(s)); }
function trunc(s, n) { return s && s.length > n ? s.slice(0, n-1)+'…' : (s||''); }

// ────────────────────────────────────────────────────────────
// Draw box
// ────────────────────────────────────────────────────────────
function drawBox(svg, pos, node) {
    let { x, y, w, h } = pos;
    let isKonto = node.is_konto;
    let depth   = node.depth || 0;
    let ci      = depth % COLORS.length;
    let border  = isKonto ? KONTO_COLOR : COLORS[ci];
    let bg      = isKonto ? KONTO_BG    : BGCOL[ci];

    let hasRlKids    = (node.children || []).length > 0;
    let hasAcctKids  = (node.accounts || []).length > 0;
    let isAcctMd     = acctMode[node._id];
    let isExp        = expanded[node._id];

    let g = el('g', { 'data-id': node._id });

    // ── Background rect ──
    g.appendChild(el('rect', {
        x, y, width: w, height: h, rx: 7,
        fill: bg, stroke: border, 'stroke-width': isKonto ? 1.5 : 2,
    }));

    // ── RL-expand button  (+/−)  — only if has RL children ──
    const BTN_SZ = 16;
    if (hasRlKids && !isKonto) {
        let bx = x + w - BTN_SZ - 4, by = y + 4;
        let btn = el('g', { style: 'cursor:pointer' });
        btn.appendChild(el('rect', {
            x: bx, y: by, width: BTN_SZ, height: BTN_SZ, rx: 3,
            fill: isAcctMd ? '#ccc' : border, opacity: 0.9,
        }));
        btn.appendChild(el('text', {
            x: bx + BTN_SZ/2, y: by + BTN_SZ - 3,
            'text-anchor': 'middle', 'font-size': 13, 'font-weight': 700,
            fill: 'white', style: 'pointer-events:none',
        }, [txt((!isAcctMd && isExp) ? '−' : '+')]));
        btn.addEventListener('click', e => {
            e.stopPropagation();
            if (isAcctMd) { acctMode[node._id] = false; }
            expanded[node._id] = !expanded[node._id];
            render();
        });
        g.appendChild(btn);
    }

    // ── Account drilldown button (⊞) — only if has account detail ──
    if (hasAcctKids && !isKonto) {
        let btnOffset = hasRlKids ? BTN_SZ + 6 : 4;
        let bx = x + w - BTN_SZ - btnOffset - 4 - (hasRlKids ? 0 : 0);
        // place it left of the +/- button (or alone)
        if (hasRlKids) bx = x + w - (BTN_SZ + 4) * 2 - 2;
        let by = y + 4;
        let btn2 = el('g', { style: 'cursor:pointer' });
        btn2.appendChild(el('rect', {
            x: bx, y: by, width: BTN_SZ, height: BTN_SZ, rx: 3,
            fill: isAcctMd ? KONTO_COLOR : '#78909C',
            opacity: isAcctMd ? 1 : 0.75,
        }));
        // Grid icon: 4 small squares
        let gs = 3, gp = 2.5;
        [[0,0],[1,0],[0,1],[1,1]].forEach(([gx,gy]) => {
            btn2.appendChild(el('rect', {
                x: bx+gp + gx*(gs+1.5), y: by+gp + gy*(gs+1.5),
                width: gs, height: gs, rx: 0.5,
                fill: 'white', style: 'pointer-events:none',
            }));
        });
        btn2.addEventListener('click', e => {
            e.stopPropagation();
            let newMode = !acctMode[node._id];
            acctMode[node._id] = newMode;
            expanded[node._id] = newMode;
            render();
        });
        g.appendChild(btn2);
    }

    // ── Text content ──
    let displayName = (node.name && node.name !== node.key) ? node.name : '';
    let pctTxt = node.pct != null ? ` (${Math.round(node.pct)}%)` : '';
    let cx = x + w/2;

    if (isKonto) {
        // Konto-modus: kontonavn bold, konto-nr liten
        g.appendChild(el('text', {
            x: cx, y: y+18, 'text-anchor':'middle',
            'font-size':10, 'font-weight':700, fill: KONTO_COLOR,
        }, [txt(trunc(displayName || node.key, 24))]));
        if (displayName) {
            g.appendChild(el('text', {
                x: cx, y: y+30, 'text-anchor':'middle',
                'font-size':9, fill:'#90A4AE',
            }, [txt(node.key + pctTxt)]));
        }
        g.appendChild(el('text', {
            x: cx, y: y+h-10, 'text-anchor':'middle',
            'font-size':12, 'font-weight':600, fill: TEXTCOL,
        }, [txt(node.amount_fmt)]));
    } else if (displayName) {
        // RL-modus med navn
        g.appendChild(el('text', {
            x: cx, y: y+20, 'text-anchor':'middle',
            'font-size':10, 'font-weight':700, fill: border,
        }, [txt(trunc(displayName, 22) + pctTxt)]));
        g.appendChild(el('text', {
            x: cx, y: y+h-10, 'text-anchor':'middle',
            'font-size':12, 'font-weight':600, fill: TEXTCOL,
        }, [txt(node.amount_fmt)]));
    } else {
        // Kun nøkkel
        g.appendChild(el('text', {
            x: cx, y: y+22, 'text-anchor':'middle',
            'font-size':11, 'font-weight':700, fill: border,
        }, [txt(node.key + pctTxt)]));
        g.appendChild(el('text', {
            x: cx, y: y+h-10, 'text-anchor':'middle',
            'font-size':12, 'font-weight':600, fill: TEXTCOL,
        }, [txt(node.amount_fmt)]));
    }

    svg.appendChild(g);
}

// ────────────────────────────────────────────────────────────
// Draw arrow
// ────────────────────────────────────────────────────────────
function drawArrow(svg, x1, y1, x2, y2, width, label, isAcct) {
    let cx1 = x1 + (x2-x1)*0.45, cx2 = x2 - (x2-x1)*0.45;
    let stroke = isAcct ? KONTO_COLOR : ARROW;
    let path = el('path', {
        d: `M${x1} ${y1} C${cx1} ${y1},${cx2} ${y2},${x2} ${y2}`,
        fill: 'none', stroke, 'stroke-width': width,
        'stroke-dasharray': isAcct ? '4 3' : 'none',
        'marker-end': isAcct ? 'url(#arrowhead-acct)' : 'url(#arrowhead)',
    });
    svg.insertBefore(path, svg.firstChild);
    if (label) {
        let mx=(x1+x2)/2, my=(y1+y2)/2-6;
        svg.insertBefore(el('text', {
            x:mx, y:my, 'text-anchor':'middle', 'font-size':9, fill:'#7F8C8D',
        }, [txt(label)]), svg.firstChild);
    }
}

// ────────────────────────────────────────────────────────────
// Full render
// ────────────────────────────────────────────────────────────
function render() {
    let container = document.getElementById('flowchart-svg-container');
    container.innerHTML = '';

    let cols = buildColumns();
    let { positions, totalW } = layout(cols);

    let totalH = 60;
    Object.values(positions).forEach(p => {
        totalH = Math.max(totalH, p.y + p.h + 30);
    });

    let svg = el('svg', {
        width: totalW, height: totalH, xmlns: SVG_NS,
        style: 'font-family:Segoe UI,system-ui,sans-serif;display:block;',
    });

    // Defs (two arrowheads)
    let defs = el('defs');
    function mkMarker(id, fill) {
        let m = el('marker', { id, markerWidth:8, markerHeight:8, refX:8, refY:4, orient:'auto' });
        m.appendChild(el('polygon', { points:'0 0,8 4,0 8', fill }));
        return m;
    }
    defs.appendChild(mkMarker('arrowhead',      ARROW));
    defs.appendChild(mkMarker('arrowhead-acct', KONTO_COLOR));
    svg.appendChild(defs);

    // Arrows
    Object.values(cols).flat().forEach(node => {
        if (!expanded[node._id]) return;
        let srcPos = positions[node._id];
        if (!srcPos) return;
        let kids = getActiveChildren(node);
        let isAcct = acctMode[node._id];
        kids.forEach(child => {
            let tgtPos = positions[child._id];
            if (!tgtPos) return;
            let aw = Math.max(1, Math.min(4, (child.pct||0) / 20));
            let label = child.pct != null ? Math.round(child.pct)+'%' : '';
            drawArrow(svg,
                srcPos.x + srcPos.w, srcPos.y + srcPos.h/2,
                tgtPos.x, tgtPos.y + tgtPos.h/2,
                aw, label, isAcct
            );
        });
    });

    // Boxes
    Object.values(cols).flat().forEach(node => {
        let pos = positions[node._id];
        if (pos) drawBox(svg, pos, node);
    });

    container.appendChild(svg);
}

render();
})();
"""

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="utf-8">
<title>Motpostanalyse — {client}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    color: #2c3e50;
    background: #f0f2f5;
    font-size: 12px;
}}
.page {{
    background: white;
    max-width: 1200px;
    margin: 24px auto;
    padding: 36px 44px;
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.10);
}}
.report-header {{
    border-bottom: 3px solid #4472C4;
    padding-bottom: 10px;
    margin-bottom: 20px;
}}
.report-title {{ font-size: 22px; font-weight: 700; color: #1a1a2e; }}
.report-subtitle {{ font-size: 12px; color: #7f8c8d; margin-top: 2px; }}
#flowchart-svg-container {{ overflow-x: auto; margin: 0 0 12px 0; min-height: 100px; }}
.hint {{
    font-size: 11px; color: #888; margin-bottom: 10px;
    display: flex; align-items: center; gap: 6px;
}}
.legend {{
    display: flex; gap: 20px; flex-wrap: wrap;
    margin: 12px 0 24px 0;
}}
.legend-item {{
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; color: #555;
}}
.legend-dot {{
    width: 14px; height: 14px; border-radius: 3px; border: 2px solid;
}}
.section-title {{
    font-size: 13px; font-weight: 700; color: #4472C4;
    text-transform: uppercase; letter-spacing: 0.5px;
    margin: 24px 0 8px 0; padding-bottom: 4px;
    border-bottom: 1px solid #e8ecf1;
}}
table {{
    width: 100%; border-collapse: collapse; font-size: 11px;
}}
th {{
    background: #f0f4f8; color: #4472C4; font-weight: 600;
    text-align: left; padding: 5px 10px;
    border-bottom: 2px solid #d5dde5;
    font-size: 10px; text-transform: uppercase;
}}
td {{ padding: 4px 10px; border-bottom: 1px solid #eef1f5; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<div class="page">
  <div class="report-header">
    <div class="report-title">{client}</div>
    <div class="report-subtitle">Motpostanalyse &mdash; {accounts_label} &mdash; {year}</div>
  </div>

  <div class="hint">
    <svg width="14" height="14" viewBox="0 0 14 14" style="flex-shrink:0">
      <rect width="14" height="14" rx="3" fill="#4472C4" opacity=".85"/>
      <text x="7" y="11" text-anchor="middle" font-size="11" font-weight="700" fill="white">+</text>
    </svg>
    Klikk <strong>+</strong> for å utvide RL-motposter
    &nbsp;&nbsp;
    <svg width="14" height="14" viewBox="0 0 14 14" style="flex-shrink:0">
      <rect width="14" height="14" rx="3" fill="#607D8B" opacity=".85"/>
      <rect x="2.5" y="2.5" width="3" height="3" rx=".5" fill="white"/>
      <rect x="7" y="2.5" width="3" height="3" rx=".5" fill="white"/>
      <rect x="2.5" y="7" width="3" height="3" rx=".5" fill="white"/>
      <rect x="7" y="7" width="3" height="3" rx=".5" fill="white"/>
    </svg>
    Klikk <strong>⊞</strong> for å drille ned til kontonivå
  </div>

  <div id="flowchart-svg-container"></div>

  <div class="legend">
    <div class="legend-item">
      <div class="legend-dot" style="background:#E8EEF7;border-color:#4472C4"></div>
      {root_label}
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
      <div class="legend-dot" style="background:#FFF8E1;border-color:#FFC000"></div>
      Motposter (ledd 3+)
    </div>
    <div class="legend-item">
      <div class="legend-dot" style="background:#ECEFF1;border-color:#607D8B"></div>
      Kontonivå (drilldown)
    </div>
    <div class="legend-item">
      <span style="color:#95A5A6;font-size:14px">&#8594;</span>&nbsp;Pilbredde = relativ andel
    </div>
  </div>

  {summary_html}
</div>

<script>
window.__MOTPOST_TREE__ = {tree_json};
</script>
<script>
{interactive_js}
</script>
</body>
</html>
"""


def _build_summary_table(tree: MotpostTree, *, rl_mode: bool = False) -> str:
    rows: list[str] = []

    for root in tree.root_nodes:
        rows.append(
            f'<tr style="font-weight:700;background:#f6f8fb">'
            f'<td>{_esc(root.konto_name or root.konto)}</td>'
            f'<td class="num">{_format_amount(root.total_amount)}</td>'
            f'<td></td><td></td></tr>'
        )
        for edge in root.edges:
            rows.append(
                f'<tr>'
                f'<td style="padding-left:20px">&rarr; {_esc(edge.target_name or edge.target)}'
                f' <span style="color:#aaa;font-size:10px">({_esc(edge.target)})</span></td>'
                f'<td class="num">{_format_amount(edge.amount)}</td>'
                f'<td class="num">{edge.pct:.1f}&thinsp;%</td>'
                f'<td class="num">{edge.voucher_count:,}</td></tr>'
                .replace(",", "\u202f")
            )
            child = getattr(edge, "_child_node", None)
            if child:
                for e2 in child.edges:
                    rows.append(
                        f'<tr style="color:#888">'
                        f'<td style="padding-left:40px">&rarr; {_esc(e2.target_name or e2.target)}'
                        f' <span style="font-size:10px">({_esc(e2.target)})</span></td>'
                        f'<td class="num">{_format_amount(e2.amount)}</td>'
                        f'<td class="num">{e2.pct:.1f}&thinsp;%</td>'
                        f'<td class="num">{e2.voucher_count:,}</td></tr>'
                        .replace(",", "\u202f")
                    )

    if not rows:
        return ""

    key_header = "Regnskapslinje" if rl_mode else "Konto / Kontonavn"
    return (
        '<div class="section-title">Detaljert motpostfordeling</div>'
        '<table>'
        '<thead><tr>'
        f'<th>{key_header}</th>'
        '<th class="num">Beløp</th>'
        '<th class="num">Andel</th>'
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
    """Bygg interaktiv HTML-rapport fra MotpostTree."""
    tree_json = json.dumps(tree_to_dict(tree), ensure_ascii=False)
    summary = _build_summary_table(tree, rl_mode=rl_mode)

    accounts_label = ", ".join(
        n.konto_name or n.konto for n in tree.root_nodes
    )
    if len(accounts_label) > 80:
        accounts_label = accounts_label[:77] + "…"

    root_label = "Valgte regnskapslinjer" if rl_mode else "Valgte kontoer"

    return _HTML_TEMPLATE.format(
        client=_esc(tree.client),
        year=_esc(tree.year),
        accounts_label=_esc(accounts_label),
        root_label=root_label,
        summary_html=summary,
        tree_json=tree_json,
        interactive_js=_INTERACTIVE_JS,
    )


def save_flowchart_html(
    path: str | Path,
    *,
    df: pd.DataFrame,
    start_accounts: list[str],
    max_depth: int = 3,
    client: str = "",
    year: str = "",
    konto_to_rl: dict | None = None,
) -> str:
    """Bygg interaktivt motpost-flytdiagram og lagre som HTML."""
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
    """Bygg statisk motpost-flytdiagram og lagre som PDF via playwright."""
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
    # PDF bruker statisk SVG (ikke interaktiv JS)
    from motpost_flowchart_svg import render_motpost_flowchart
    svg = render_motpost_flowchart(tree)
    summary = _build_summary_table(tree, rl_mode=rl_mode)
    accounts_label = ", ".join(n.konto_name or n.konto for n in tree.root_nodes)
    if len(accounts_label) > 80:
        accounts_label = accounts_label[:77] + "…"
    root_label = "Valgte regnskapslinjer" if rl_mode else "Valgte kontoer"

    html_content = f"""<!DOCTYPE html>
<html lang="no"><head><meta charset="utf-8">
<style>
* {{ margin:0;padding:0;box-sizing:border-box; }}
@page {{ size:A4 landscape;margin:12mm 15mm; }}
body {{ font-family:"Segoe UI",system-ui,sans-serif;color:#2c3e50;font-size:12px;
        -webkit-print-color-adjust:exact;print-color-adjust:exact; }}
.page {{ padding:20px; }}
.title {{ font-size:20px;font-weight:700;border-bottom:3px solid #4472C4;
          padding-bottom:8px;margin-bottom:14px; }}
.subtitle {{ font-size:11px;color:#7f8c8d;margin-bottom:14px; }}
.legend {{ display:flex;gap:16px;margin:10px 0 18px 0;flex-wrap:wrap; }}
.ld {{ display:flex;align-items:center;gap:5px;font-size:10px;color:#555; }}
.dot {{ width:12px;height:12px;border-radius:2px;border:2px solid; }}
table {{ width:100%;border-collapse:collapse;font-size:10px;margin-top:14px; }}
th {{ background:#f0f4f8;color:#4472C4;font-weight:600;text-align:left;
     padding:4px 8px;border-bottom:2px solid #d5dde5;text-transform:uppercase; }}
td {{ padding:3px 8px;border-bottom:1px solid #eef1f5; }}
.num {{ text-align:right; }}
</style></head><body><div class="page">
<div class="title">{_esc(tree.client)}</div>
<div class="subtitle">Motpostanalyse &mdash; {_esc(accounts_label)} &mdash; {_esc(tree.year)}</div>
<div style="text-align:center;overflow:hidden">{svg}</div>
<div class="legend">
  <div class="ld"><div class="dot" style="background:#E8EEF7;border-color:#4472C4"></div>{root_label}</div>
  <div class="ld"><div class="dot" style="background:#FDF0E5;border-color:#ED7D31"></div>Motposter (ledd 1)</div>
  <div class="ld"><div class="dot" style="background:#EFF6EA;border-color:#70AD47"></div>Motposter (ledd 2)</div>
</div>
{summary}
</div></body></html>"""

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

"""Tests for motpost_flowchart_engine, motpost_flowchart_svg, and motpost_flowchart_report."""

from __future__ import annotations

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Sample data — HB transactions with Konto, Kontonavn, Bilag, Beløp
# ---------------------------------------------------------------------------

def _sample_hb_df() -> pd.DataFrame:
    """Minimal HB-transaksjoner med motpost-relasjoner.

    Bilag 1: Salg — Salgsinntekt (3000) krediteres, Kundefordring (1500) debiteres
    Bilag 2: Innbetaling — Kundefordring (1500) krediteres, Bank (1920) debiteres
    Bilag 3: Varekjøp — Varekostnad (4000) debiteres, Leverandørgjeld (2400) krediteres
    Bilag 4: Lønn — Lønnskostnad (5000) debiteres, Bank (1920) krediteres
    Bilag 5: Salg 2 — Salgsinntekt (3000) krediteres, Kundefordring (1500) debiteres
    """
    rows = [
        # Bilag 1: Salg
        {"Konto": "3000", "Kontonavn": "Salgsinntekt", "Bilag": "1", "Beløp": -100_000},
        {"Konto": "1500", "Kontonavn": "Kundefordringer", "Bilag": "1", "Beløp": 100_000},
        # Bilag 2: Innbetaling fra kunde
        {"Konto": "1500", "Kontonavn": "Kundefordringer", "Bilag": "2", "Beløp": -80_000},
        {"Konto": "1920", "Kontonavn": "Bankinnskudd", "Bilag": "2", "Beløp": 80_000},
        # Bilag 3: Varekjøp
        {"Konto": "4000", "Kontonavn": "Varekostnad", "Bilag": "3", "Beløp": 50_000},
        {"Konto": "2400", "Kontonavn": "Leverandørgjeld", "Bilag": "3", "Beløp": -50_000},
        # Bilag 4: Lønn
        {"Konto": "5000", "Kontonavn": "Lønnskostnad", "Bilag": "4", "Beløp": 60_000},
        {"Konto": "1920", "Kontonavn": "Bankinnskudd", "Bilag": "4", "Beløp": -60_000},
        # Bilag 5: Salg 2
        {"Konto": "3000", "Kontonavn": "Salgsinntekt", "Bilag": "5", "Beløp": -70_000},
        {"Konto": "1500", "Kontonavn": "Kundefordringer", "Bilag": "5", "Beløp": 70_000},
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Engine tests
# ---------------------------------------------------------------------------

class TestMotpostEngine:
    def test_build_tree_single_root(self):
        from motpost_flowchart_engine import build_motpost_tree

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=1, client="Test AS", year="2025")

        assert tree.client == "Test AS"
        assert tree.year == "2025"
        assert len(tree.root_nodes) == 1

        root = tree.root_nodes[0]
        assert root.konto == "3000"
        assert root.konto_name == "Salgsinntekt"
        assert root.total_amount > 0
        assert len(root.edges) >= 1

        # Kundefordringer should be the top counterpart
        targets = {e.target for e in root.edges}
        assert "1500" in targets

    def test_build_tree_depth_2(self):
        from motpost_flowchart_engine import build_motpost_tree

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=2)

        root = tree.root_nodes[0]
        assert len(root.edges) >= 1

        # Find edge to 1500 (Kundefordringer)
        edge_1500 = next((e for e in root.edges if e.target == "1500"), None)
        assert edge_1500 is not None

        # Should have child node with motposter (Bank, Salgsinntekt)
        child = getattr(edge_1500, "_child_node", None)
        assert child is not None
        assert child.konto == "1500"
        assert len(child.edges) >= 1

    def test_build_tree_multiple_roots(self):
        from motpost_flowchart_engine import build_motpost_tree

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000", "4000"], max_depth=1)

        assert len(tree.root_nodes) == 2
        kontos = {n.konto for n in tree.root_nodes}
        assert kontos == {"3000", "4000"}

    def test_build_tree_unknown_account(self):
        from motpost_flowchart_engine import build_motpost_tree

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["9999"], max_depth=1)

        # Unknown account should be skipped
        assert len(tree.root_nodes) == 0

    def test_edge_percentages_sum_close_to_100(self):
        from motpost_flowchart_engine import build_motpost_tree

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=1, min_pct=0)

        root = tree.root_nodes[0]
        total_pct = sum(e.pct for e in root.edges)
        assert 95.0 <= total_pct <= 100.1

    def test_edge_has_voucher_count(self):
        from motpost_flowchart_engine import build_motpost_tree

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=1)

        root = tree.root_nodes[0]
        edge_1500 = next((e for e in root.edges if e.target == "1500"), None)
        assert edge_1500 is not None
        # 3000 appears in bilag 1 and 5, both with 1500
        assert edge_1500.voucher_count >= 2

    def test_min_pct_filters(self):
        from motpost_flowchart_engine import build_motpost_tree

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=1, min_pct=99.0)

        root = tree.root_nodes[0]
        # With min_pct=99, only the dominant counterpart should remain (or none)
        assert len(root.edges) <= 1

    def test_top_n_limits_edges(self):
        from motpost_flowchart_engine import build_motpost_tree

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=1, top_n=1)

        root = tree.root_nodes[0]
        assert len(root.edges) <= 1

    def test_empty_df(self):
        from motpost_flowchart_engine import build_motpost_tree

        df = pd.DataFrame(columns=["Konto", "Kontonavn", "Bilag", "Beløp"])
        tree = build_motpost_tree(df, ["3000"], max_depth=1)
        assert len(tree.root_nodes) == 0


# ---------------------------------------------------------------------------
# SVG renderer tests
# ---------------------------------------------------------------------------

class TestMotpostSvg:
    def test_render_produces_svg(self):
        from motpost_flowchart_engine import build_motpost_tree
        from motpost_flowchart_svg import render_motpost_flowchart

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=2)
        svg = render_motpost_flowchart(tree)

        assert svg.startswith("<svg")
        assert "</svg>" in svg

    def test_render_contains_account_numbers(self):
        from motpost_flowchart_engine import build_motpost_tree
        from motpost_flowchart_svg import render_motpost_flowchart

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=1)
        svg = render_motpost_flowchart(tree)

        assert "3000" in svg
        assert "1500" in svg  # counterpart

    def test_render_contains_arrows(self):
        from motpost_flowchart_engine import build_motpost_tree
        from motpost_flowchart_svg import render_motpost_flowchart

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=1)
        svg = render_motpost_flowchart(tree)

        assert "arrowhead" in svg
        assert "<path" in svg

    def test_render_empty_tree(self):
        from motpost_flowchart_engine import MotpostTree
        from motpost_flowchart_svg import render_motpost_flowchart

        tree = MotpostTree()
        svg = render_motpost_flowchart(tree)
        assert svg == ""

    def test_render_multiple_roots(self):
        from motpost_flowchart_engine import build_motpost_tree
        from motpost_flowchart_svg import render_motpost_flowchart

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000", "4000"], max_depth=1)
        svg = render_motpost_flowchart(tree)

        assert "3000" in svg
        assert "4000" in svg


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------

class TestMotpostReport:
    def test_build_flowchart_html(self):
        from motpost_flowchart_engine import build_motpost_tree
        from motpost_flowchart_report import build_flowchart_html

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=2, client="Test AS", year="2025")
        html = build_flowchart_html(tree)

        assert "<!DOCTYPE html>" in html
        assert "Test AS" in html
        assert "2025" in html
        assert "<svg" in html
        assert "Motpostanalyse" in html

    def test_build_summary_table(self):
        from motpost_flowchart_engine import build_motpost_tree
        from motpost_flowchart_report import _build_summary_table

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=2)
        table = _build_summary_table(tree)

        assert "3000" in table
        assert "Salgsinntekt" in table
        assert "1500" in table
        assert "%" in table

    def test_save_flowchart_html(self, tmp_path):
        from motpost_flowchart_report import save_flowchart_html

        df = _sample_hb_df()
        out = save_flowchart_html(
            tmp_path / "test_flowchart",
            df=df,
            start_accounts=["3000"],
            max_depth=2,
            client="Test AS",
            year="2025",
        )

        assert out.endswith(".html")
        from pathlib import Path
        content = Path(out).read_text(encoding="utf-8")
        assert "Test AS" in content
        assert "<svg" in content

    def test_save_html_adds_extension(self, tmp_path):
        from motpost_flowchart_report import save_flowchart_html

        df = _sample_hb_df()
        out = save_flowchart_html(
            tmp_path / "no_ext",
            df=df,
            start_accounts=["3000"],
        )
        assert out.endswith(".html")

    def test_legend_in_html(self):
        from motpost_flowchart_engine import build_motpost_tree
        from motpost_flowchart_report import build_flowchart_html

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=2)
        html = build_flowchart_html(tree)

        assert "Valgte kontoer" in html
        assert "Motposter (ledd 1)" in html
        assert "Motposter (ledd 2)" in html

    def test_format_amount(self):
        from motpost_flowchart_report import _format_amount

        assert "M" in _format_amount(5_000_000)
        assert "k" in _format_amount(50_000)
        assert _format_amount(500) == "500"

    def test_rl_mode_legend(self):
        from motpost_flowchart_engine import build_motpost_tree
        from motpost_flowchart_report import build_flowchart_html

        df = _sample_hb_df()
        tree = build_motpost_tree(df, ["3000"], max_depth=1)
        html = build_flowchart_html(tree, rl_mode=True)

        assert "Valgte regnskapslinjer" in html
        assert "Regnskapslinje" in html  # table header

    def test_rl_mode_engine_aggregates_accounts(self):
        """Med konto_to_rl skal kontoer i samme RL slås sammen til én node."""
        from motpost_flowchart_engine import build_motpost_tree

        df = _sample_hb_df()
        # Map begge salgskontiene (3000 og 1500) til samme RL
        konto_to_rl = {
            "3000": (10, "Salgsinntekter"),
            "1500": (6, "Kundefordringer"),
            "1920": (7, "Bank"),
            "4000": (20, "Varekostnad"),
            "2400": (8, "Leverandørgjeld"),
            "5000": (40, "Lønnskostnad"),
        }
        tree = build_motpost_tree(
            df, ["3000"],
            max_depth=1,
            konto_to_rl=konto_to_rl,
        )

        # Root node skal ha regnr "10" som nøkkel og "Salgsinntekter" som navn
        assert len(tree.root_nodes) == 1
        root = tree.root_nodes[0]
        assert root.konto == "10"
        assert root.konto_name == "Salgsinntekter"

        # Motpost-noden skal være "Kundefordringer" (regnr 6)
        targets = {e.target for e in root.edges}
        assert "6" in targets

    def test_rl_mode_groups_multiple_accounts(self):
        """To kontoer i samme RL slås til én node."""
        from motpost_flowchart_engine import build_motpost_tree

        # Legg til en ekstra salgskonto i samme RL som 3000
        extra_rows = [
            {"Konto": "3001", "Kontonavn": "Salgsinntekt 2", "Bilag": "6", "Beløp": -30_000},
            {"Konto": "1500", "Kontonavn": "Kundefordringer", "Bilag": "6", "Beløp": 30_000},
        ]
        import pandas as pd
        df = pd.concat([_sample_hb_df(), pd.DataFrame(extra_rows)], ignore_index=True)

        konto_to_rl = {
            "3000": (10, "Salgsinntekter"),
            "3001": (10, "Salgsinntekter"),  # samme RL som 3000
            "1500": (6, "Kundefordringer"),
            "1920": (7, "Bank"),
            "4000": (20, "Varekostnad"),
            "2400": (8, "Leverandørgjeld"),
            "5000": (40, "Lønnskostnad"),
        }
        tree = build_motpost_tree(
            df, ["3000", "3001"],
            max_depth=1,
            konto_to_rl=konto_to_rl,
        )

        # Begge kontoene tilhører RL 10 → én rotnode
        assert len(tree.root_nodes) == 1
        assert tree.root_nodes[0].konto == "10"

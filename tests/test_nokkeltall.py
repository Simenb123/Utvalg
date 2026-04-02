"""Tests for nokkeltall_engine, nokkeltall_svg, and nokkeltall_report."""

from __future__ import annotations

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

def _sample_rl_df(*, with_prev: bool = False) -> pd.DataFrame:
    """Minimal regnskapslinje-pivot med realistiske SAF-T-fortegn.

    SAF-T-konvensjon: kredit = negativ, debet = positiv.
    Inntekter, resultat, EK og gjeld lagres som negative verdier.
    """
    rows = [
        # Resultatregnskap — inntekter (kredit/negativ)
        {"regnr": 10,  "regnskapslinje": "Salgsinntekt",           "IB": 0, "Endring": -5_000_000, "UB": -5_000_000, "Antall": 1200},
        {"regnr": 19,  "regnskapslinje": "Sum driftsinntekter",    "IB": 0, "Endring": -5_200_000, "UB": -5_200_000, "Antall": 1250},
        # Kostnader (debet/positiv)
        {"regnr": 20,  "regnskapslinje": "Varekostnad",            "IB": 0, "Endring": 2_000_000, "UB": 2_000_000, "Antall": 800},
        {"regnr": 40,  "regnskapslinje": "Lønnskostnad",           "IB": 0, "Endring": 1_500_000, "UB": 1_500_000, "Antall": 400},
        {"regnr": 50,  "regnskapslinje": "Avskrivning",            "IB": 0, "Endring": 200_000,   "UB": 200_000,   "Antall": 12},
        {"regnr": 70,  "regnskapslinje": "Annen driftskostnad",    "IB": 0, "Endring": 800_000,   "UB": 800_000,   "Antall": 600},
        {"regnr": 79,  "regnskapslinje": "Sum driftskostnader",    "IB": 0, "Endring": 4_500_000, "UB": 4_500_000, "Antall": 1812},
        # Resultatlinjer (kredit/negativ ved overskudd)
        {"regnr": 80,  "regnskapslinje": "Driftsresultat",         "IB": 0, "Endring": -700_000,  "UB": -700_000,  "Antall": 0},
        {"regnr": 135, "regnskapslinje": "Sum finansinntekter",    "IB": 0, "Endring": -50_000,   "UB": -50_000,   "Antall": 10},
        {"regnr": 145, "regnskapslinje": "Sum finanskostnader",    "IB": 0, "Endring": 100_000,   "UB": 100_000,   "Antall": 12},
        {"regnr": 160, "regnskapslinje": "Resultat før skatt",     "IB": 0, "Endring": -650_000,  "UB": -650_000,  "Antall": 0},
        {"regnr": 280, "regnskapslinje": "Årsresultat",            "IB": 0, "Endring": -480_000,  "UB": -480_000,  "Antall": 0},
        # Balanse — eiendeler (debet/positiv)
        {"regnr": 555, "regnskapslinje": "Sum varige driftsmidler", "IB": 1_000_000,  "Endring": -200_000, "UB": 800_000,    "Antall": 50},
        {"regnr": 590, "regnskapslinje": "Sum anleggsmidler",       "IB": 1_200_000,  "Endring": -200_000, "UB": 1_000_000,  "Antall": 60},
        {"regnr": 605, "regnskapslinje": "Varelager",               "IB": 300_000,    "Endring": 50_000,   "UB": 350_000,    "Antall": 200},
        {"regnr": 610, "regnskapslinje": "Kundefordringer",         "IB": 400_000,    "Endring": 100_000,  "UB": 500_000,    "Antall": 950},
        {"regnr": 655, "regnskapslinje": "Bankinnskudd",            "IB": 600_000,    "Endring": -150_000, "UB": 450_000,    "Antall": 3000},
        {"regnr": 660, "regnskapslinje": "Sum omløpsmidler",        "IB": 1_300_000,  "Endring": 0,        "UB": 1_300_000,  "Antall": 4150},
        {"regnr": 665, "regnskapslinje": "Sum eiendeler",           "IB": 2_500_000,  "Endring": -200_000, "UB": 2_300_000,  "Antall": 4210},
        # Balanse — EK og gjeld (kredit/negativ)
        {"regnr": 715, "regnskapslinje": "Sum egenkapital",         "IB": -1_000_000, "Endring": -480_000, "UB": -1_480_000, "Antall": 20},
        {"regnr": 780, "regnskapslinje": "Leverandørgjeld",         "IB": -200_000,   "Endring": -50_000,  "UB": -250_000,   "Antall": 500},
        {"regnr": 810, "regnskapslinje": "Sum kortsiktig gjeld",    "IB": -700_000,   "Endring": 80_000,   "UB": -620_000,   "Antall": 800},
        {"regnr": 820, "regnskapslinje": "Sum gjeld",               "IB": -1_500_000, "Endring": 680_000,  "UB": -820_000,   "Antall": 900},
        {"regnr": 830, "regnskapslinje": "Sum EK og gjeld",         "IB": -2_500_000, "Endring": 200_000,  "UB": -2_300_000, "Antall": 920},
    ]
    df = pd.DataFrame(rows)
    if with_prev:
        # Simuler fjorårstall: 10% lavere i absoluttverdi (bevarer fortegn)
        df["UB_fjor"] = df["UB"] * 0.90
        df["Endring_fjor"] = df["UB"] - df["UB_fjor"]
        df["Endring_pct"] = (df["Endring_fjor"] / df["UB_fjor"].abs().replace(0, float("nan"))) * 100
    return df


# ---------------------------------------------------------------------------
# Engine tests
# ---------------------------------------------------------------------------

class TestNokkeltallEngine:

    def test_compute_returns_result(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df(), client="Test AS", year="2025")
        assert result.client == "Test AS"
        assert result.year == "2025"
        assert len(result.metrics) > 0
        assert len(result.kpi_cards) > 0
        assert len(result.pl_summary) > 0
        assert len(result.bs_summary) > 0

    def test_driftsmargin_correct(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df())
        dm = next(m for m in result.metrics if m.id == "driftsmargin")
        # Driftsresultat 700k / Driftsinntekter 5.2M = 13.46%
        assert dm.value is not None
        assert abs(dm.value - (700_000 / 5_200_000 * 100)) < 0.1

    def test_likviditetsgrad_1(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df())
        l1 = next(m for m in result.metrics if m.id == "likv1")
        # Omløpsmidler 1.3M / Kortsiktig gjeld 620k = 2.10
        assert l1.value is not None
        assert abs(l1.value - (1_300_000 / 620_000)) < 0.01

    def test_egenkapitalandel(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df())
        ek = next(m for m in result.metrics if m.id == "ek_andel")
        # EK 1.48M / Eiendeler 2.3M = 64.3%
        assert ek.value is not None
        assert abs(ek.value - (1_480_000 / 2_300_000 * 100)) < 0.1

    def test_with_prev_year(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df(with_prev=True))
        assert result.has_prev_year is True
        dm = next(m for m in result.metrics if m.id == "driftsmargin")
        assert dm.prev_value is not None

    def test_without_prev_year(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df(with_prev=False))
        assert result.has_prev_year is False
        dm = next(m for m in result.metrics if m.id == "driftsmargin")
        assert dm.prev_value is None

    def test_cost_breakdown(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df())
        assert len(result.cost_breakdown) == 4
        labels = {d["label"] for d in result.cost_breakdown}
        assert "Varekostnad" in labels
        assert "Lønnskostnad" in labels

    def test_top_activity(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df())
        assert len(result.top_activity) == 3
        # Bankinnskudd has most transactions (3000)
        assert result.top_activity[0]["regnr"] == 655

    def test_kpi_cards(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df())
        labels = [c["label"] for c in result.kpi_cards]
        assert "Bruttofortjeneste" in labels
        assert "Driftsmargin" in labels
        assert "Egenkapitalandel" in labels
        assert "Likviditetsgrad 1" in labels

    def test_empty_df(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(pd.DataFrame())
        assert result.metrics == []
        assert result.kpi_cards == []

    def test_format_value(self):
        from nokkeltall_engine import _format_value
        assert "%" in _format_value(12.5, "pct")
        assert _format_value(None, "pct") == "–"
        assert "M" in _format_value(5_000_000, "amount")
        assert "k" in _format_value(500_000, "amount")


# ---------------------------------------------------------------------------
# SVG tests
# ---------------------------------------------------------------------------

class TestSvgCharts:

    def test_donut_produces_svg(self):
        from nokkeltall_svg import svg_donut
        items = [
            {"label": "Varekostnad", "value": 2000},
            {"label": "Lønn", "value": 1500},
            {"label": "Annet", "value": 800},
        ]
        svg = svg_donut(items)
        assert svg.startswith("<svg")
        assert "</svg>" in svg
        assert "Varekostnad" in svg

    def test_donut_empty(self):
        from nokkeltall_svg import svg_donut
        assert svg_donut([]) == ""

    def test_hbar_produces_svg(self):
        from nokkeltall_svg import svg_hbar
        items = [
            {"name": "Post A", "value": 100, "formatted": "100 k"},
            {"name": "Post B", "value": 50, "formatted": "50 k"},
        ]
        svg = svg_hbar(items)
        assert "<svg" in svg
        assert "Post A" in svg

    def test_vbar_produces_svg(self):
        from nokkeltall_svg import svg_vbar
        items = [
            {"name": "Salg", "value": 5000},
            {"name": "Kostnad", "value": 3000},
        ]
        svg = svg_vbar(items)
        assert "<svg" in svg

    def test_vbar_with_prev(self):
        from nokkeltall_svg import svg_vbar
        items = [
            {"name": "Salg", "value": 5000, "prev": 4500},
            {"name": "Kostnad", "value": 3000, "prev": 2800},
        ]
        svg = svg_vbar(items, prev_key="prev")
        assert "<svg" in svg
        # Should have more rects (2 per item)
        assert svg.count("<rect") >= 4

    def test_kpi_card_html(self):
        from nokkeltall_svg import svg_kpi_card
        html = svg_kpi_card("Driftsinntekter", "5.2 M", change_pct=11.1)
        assert "kpi-card" in html
        assert "5.2 M" in html
        assert "+11.1%" in html

    def test_kpi_card_negative_change(self):
        from nokkeltall_svg import svg_kpi_card
        html = svg_kpi_card("Resultat", "480 k", change_pct=-5.0)
        assert "-5.0%" in html
        assert "#E74C3C" in html  # red


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------

class TestReport:

    def test_build_report_html(self):
        from nokkeltall_engine import compute_nokkeltall
        from nokkeltall_report import build_report_html
        result = compute_nokkeltall(_sample_rl_df(with_prev=True), client="Demo AS", year="2025")
        html = build_report_html(result)
        assert "<!DOCTYPE html>" in html
        assert "Demo AS" in html
        assert "2025" in html
        assert "Finansiell oversikt" in html
        assert "Nøkkeltall og analyse" in html
        assert "Kostnadsfordeling" in html
        assert "Balansefordeling" in html
        assert "<svg" in html

    def test_build_report_without_prev(self):
        from nokkeltall_engine import compute_nokkeltall
        from nokkeltall_report import build_report_html
        result = compute_nokkeltall(_sample_rl_df(with_prev=False), client="Test", year="2024")
        html = build_report_html(result)
        assert "Forrige" not in html
        assert "Test" in html

    def test_save_report_html(self, tmp_path):
        from nokkeltall_report import save_report_html
        path = tmp_path / "rapport.html"
        saved = save_report_html(
            path,
            rl_df=_sample_rl_df(with_prev=True),
            client="Test AS",
            year="2025",
        )
        assert saved.endswith(".html")
        content = open(saved, encoding="utf-8").read()
        assert "Test AS" in content
        assert "<svg" in content

    def test_save_adds_html_extension(self, tmp_path):
        from nokkeltall_report import save_report_html
        path = tmp_path / "rapport"
        saved = save_report_html(path, rl_df=_sample_rl_df())
        assert saved.endswith(".html")

    def test_save_report_pdf(self, tmp_path):
        from nokkeltall_report import save_report_pdf
        path = tmp_path / "rapport.pdf"
        saved = save_report_pdf(
            path,
            rl_df=_sample_rl_df(with_prev=True),
            client="Test AS",
            year="2025",
        )
        assert saved.endswith(".pdf")
        # Verify file exists and starts with PDF header
        with open(saved, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_save_pdf_adds_extension(self, tmp_path):
        from nokkeltall_report import save_report_pdf
        path = tmp_path / "rapport"
        saved = save_report_pdf(path, rl_df=_sample_rl_df())
        assert saved.endswith(".pdf")

    def test_save_pdf_without_prev_year(self, tmp_path):
        from nokkeltall_report import save_report_pdf
        path = tmp_path / "no_prev.pdf"
        saved = save_report_pdf(
            path,
            rl_df=_sample_rl_df(with_prev=False),
            client="Demo",
            year="2024",
        )
        assert saved.endswith(".pdf")
        import os
        assert os.path.getsize(saved) > 1000  # non-trivial PDF

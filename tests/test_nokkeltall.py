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
        # Topp-10 leaf-regnskapslinjer etter volum (bilag eller transaksjoner)
        assert 1 <= len(result.top_activity) <= 10
        # Bankinnskudd har flest transaksjoner (3000) i sample
        assert result.top_activity[0]["regnr"] == 655
        assert result.top_activity[0]["count"] == 3000
        assert result.top_activity[0]["count_label"] in {"bilag", "transaksjoner"}

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
        assert _format_value(5_000_000, "amount") == "5 000 000"
        assert _format_value(500_000, "amount") == "500 000"
        assert _format_value(-1_234_567, "amount") == "-1 234 567"

    # ---- Standardvurderinger / observasjoner ---------------------------

    def test_observations_built_for_all_thresholds(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df())
        ids = {o.metric_id for o in result.observations}
        expected = {
            "likv1", "likv2", "arb_kap", "ek_andel",
            "gjeldsgrad", "driftsmargin", "nettoresmargin",
        }
        assert expected.issubset(ids)

    def test_observation_critical_when_likv1_below_1(self):
        from nokkeltall_engine import compute_nokkeltall
        df = _sample_rl_df()
        # Blåse opp kortsiktig gjeld → likv1 = 1.3M / 1.5M ≈ 0.87
        df.loc[df["regnr"] == 810, "UB"] = -1_500_000
        result = compute_nokkeltall(df)
        obs = next(o for o in result.observations if o.metric_id == "likv1")
        assert obs.severity == "critical"

    def test_observation_watch_when_likv1_between_1_and_2(self):
        from nokkeltall_engine import compute_nokkeltall
        df = _sample_rl_df()
        # likv1 = 1.3M / 900k ≈ 1.44 → watch
        df.loc[df["regnr"] == 810, "UB"] = -900_000
        result = compute_nokkeltall(df)
        obs = next(o for o in result.observations if o.metric_id == "likv1")
        assert obs.severity == "watch"

    def test_observation_ok_when_ek_andel_above_30(self):
        from nokkeltall_engine import compute_nokkeltall
        # Sample gir EK-andel ~64% som er klart > 30
        result = compute_nokkeltall(_sample_rl_df())
        obs = next(o for o in result.observations if o.metric_id == "ek_andel")
        assert obs.severity == "ok"

    def test_observation_skipped_when_metric_missing(self):
        from nokkeltall_engine import compute_nokkeltall
        df = _sample_rl_df()
        # Fjern kortsiktig gjeld helt → likv1.value = None
        df = df[df["regnr"] != 810].reset_index(drop=True)
        result = compute_nokkeltall(df)
        assert not any(o.metric_id == "likv1" for o in result.observations)

    # ---- Top changes og konsentrasjon ---------------------------------

    def test_top_changes_classifies_increases_and_decreases(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df(with_prev=True))
        inc = result.top_changes["increases"]
        dec = result.top_changes["decreases"]
        # Alle \u00f8kninger har positiv diff, alle reduksjoner negativ
        assert all(item["diff"] > 0 for item in inc)
        assert all(item["diff"] < 0 for item in dec)
        # Sortert avtagende (\u00f8kninger) / tiltagende (reduksjoner) etter |diff|
        if len(inc) >= 2:
            assert inc[0]["diff"] >= inc[1]["diff"]
        if len(dec) >= 2:
            assert dec[0]["diff"] <= dec[1]["diff"]

    def test_top_changes_empty_without_prev(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df(with_prev=False))
        assert result.top_changes == {"increases": [], "decreases": []}

    def test_concentration_includes_cost_metric(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df())
        labels = [c["label"] for c in result.concentration]
        assert any("kostnadslinjer" in lbl.lower() for lbl in labels)
        # Alle verdier er prosent mellom 0 og 100
        for c in result.concentration:
            assert 0.0 <= c["value_pct"] <= 100.0

    def test_observation_gjeldsgrad_uses_above_thresholds(self):
        from nokkeltall_engine import compute_nokkeltall
        # gjeldsgrad = sum_gjeld / sum_ek. Sample EK = 1.48M.
        # 6.0 → critical:  gjeld = 6 * 1.48M = 8.88M
        df = _sample_rl_df()
        df.loc[df["regnr"] == 820, "UB"] = -8_880_000
        result_crit = compute_nokkeltall(df)
        o = next(x for x in result_crit.observations if x.metric_id == "gjeldsgrad")
        assert o.severity == "critical"

        # 3.5 → watch:  gjeld = 3.5 * 1.48M ≈ 5.18M
        df2 = _sample_rl_df()
        df2.loc[df2["regnr"] == 820, "UB"] = -5_180_000
        result_watch = compute_nokkeltall(df2)
        o2 = next(x for x in result_watch.observations if x.metric_id == "gjeldsgrad")
        assert o2.severity == "watch"

        # 2.0 → ok: gjeld = 2 * 1.48M = 2.96M
        df3 = _sample_rl_df()
        df3.loc[df3["regnr"] == 820, "UB"] = -2_960_000
        result_ok = compute_nokkeltall(df3)
        o3 = next(x for x in result_ok.observations if x.metric_id == "gjeldsgrad")
        assert o3.severity == "ok"


# ---------------------------------------------------------------------------
# Reskontro tests
# ---------------------------------------------------------------------------

def _sample_reskontro_df() -> pd.DataFrame:
    """Minimal transaksjonstabell med reskontro-kolonner."""
    return pd.DataFrame({
        "Kundenr":       ["K1", "K1", "K2", "K3", None, None],
        "Kundenavn":     ["Alpha AS", "Alpha AS", "Beta AS", "Gamma AS", None, None],
        "KundeIB":       [10000.0, 10000.0, 5000.0, 0.0, None, None],
        "KundeUB":       [50000.0, 50000.0, 3000.0, 12000.0, None, None],
        "Leverandørnr":  [None, None, None, None, "L1", "L2"],
        "Leverandørnavn":[None, None, None, None, "Fabrikk AS", "Service AS"],
        "LeverandørIB":  [None, None, None, None, -8000.0, -2000.0],
        "LeverandørUB":  [None, None, None, None, -20000.0, -1000.0],
        "Beløp":         [60000.0, -20000.0, -2000.0, 12000.0, -15000.0, 1000.0],
    })


class TestReskontro:

    def test_no_reskontro_data_yields_empty_lists(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(_sample_rl_df(), reskontro_df=None)
        assert result.reskontro_kunder_top_ub == []
        assert result.reskontro_lev_top_ub == []
        assert result.reskontro_kunder_top_debet == []
        assert result.reskontro_lev_top_kredit == []

    def test_kunder_top_ub_sorted_descending_by_abs(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(
            _sample_rl_df(), reskontro_df=_sample_reskontro_df()
        )
        tops = result.reskontro_kunder_top_ub
        assert len(tops) == 3
        assert tops[0].nr == "K1"
        assert tops[0].ub == 50000.0
        assert tops[1].nr == "K3"
        assert tops[2].nr == "K2"

    def test_lev_ub_flipped_to_positive(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(
            _sample_rl_df(), reskontro_df=_sample_reskontro_df()
        )
        tops = result.reskontro_lev_top_ub
        assert len(tops) == 2
        assert tops[0].nr == "L1"
        assert tops[0].ub == 20000.0  # -(-20000)
        assert tops[1].ub == 1000.0

    def test_debet_kredit_split_from_belop_sign(self):
        from nokkeltall_engine import compute_nokkeltall
        result = compute_nokkeltall(
            _sample_rl_df(), reskontro_df=_sample_reskontro_df()
        )
        k1 = next(r for r in result.reskontro_kunder_top_ub if r.nr == "K1")
        assert k1.debet == 60000.0
        assert k1.kredit == 20000.0

    def test_reskontro_page_rendered_when_data_present(self):
        from nokkeltall_engine import compute_nokkeltall
        from nokkeltall_report import build_report_html
        result = compute_nokkeltall(
            _sample_rl_df(), reskontro_df=_sample_reskontro_df(),
            client="Demo", year="2025",
        )
        html = build_report_html(result)
        assert "Reskontro" in html
        assert "resk-table" in html
        assert "Alpha AS" in html

    def test_reskontro_page_skipped_when_no_data(self):
        from nokkeltall_engine import compute_nokkeltall
        from nokkeltall_report import build_report_html
        result = compute_nokkeltall(_sample_rl_df(), reskontro_df=None)
        html = build_report_html(result)
        # Ingen reskontro-tabell i DOM (CSS-regelen er alltid i <style>)
        assert '<table class="resk-table"' not in html
        assert "class=\"resk-grid\"" not in html
        assert "report-subtitle\">Reskontro" not in html


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
        pytest.importorskip("playwright", reason="playwright not installed")
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
        pytest.importorskip("playwright", reason="playwright not installed")
        from nokkeltall_report import save_report_pdf
        path = tmp_path / "rapport"
        saved = save_report_pdf(path, rl_df=_sample_rl_df())
        assert saved.endswith(".pdf")

    def test_save_pdf_without_prev_year(self, tmp_path):
        pytest.importorskip("playwright", reason="playwright not installed")
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

    # ---- Standardvurderinger på side 3 ---------------------------------

    def test_side3_contains_standardvurderinger(self):
        from nokkeltall_engine import compute_nokkeltall
        from nokkeltall_report import build_report_html
        result = compute_nokkeltall(_sample_rl_df(), client="Demo", year="2025")
        html = build_report_html(result)
        assert '<div class="section-title">Standardvurderinger</div>' in html
        assert 'class="obs-grid"' in html
        assert "tommelfingerregler" in html

    def test_side3_observation_cards_have_severity_classes(self):
        from nokkeltall_engine import compute_nokkeltall
        from nokkeltall_report import build_report_html
        result = compute_nokkeltall(_sample_rl_df(), client="Demo", year="2025")
        html = build_report_html(result)
        has_severity = any(cls in html for cls in
                           ("obs-ok", "obs-watch", "obs-critical"))
        assert has_severity

    def test_side3_observations_grouped_by_category(self):
        from nokkeltall_engine import compute_nokkeltall
        from nokkeltall_report import build_report_html
        result = compute_nokkeltall(_sample_rl_df(), client="Demo", year="2025")
        html = build_report_html(result)
        # Kategori-overskrifter vises med egen CSS-klasse
        assert 'class="obs-category">L\u00f8nnsomhet<' in html
        assert 'class="obs-category">Likviditet<' in html
        assert 'class="obs-category">Soliditet<' in html

    def test_side3_no_observations_when_empty(self):
        from nokkeltall_engine import compute_nokkeltall
        from nokkeltall_report import build_report_html
        result = compute_nokkeltall(_sample_rl_df(), client="Demo", year="2025")
        result.observations = []
        html = build_report_html(result)
        assert 'class="obs-grid"' not in html
        # "Standardvurderinger" finnes i CSS-kommentar; sjekk heller at
        # selve section-title-divet ikke rendres.
        assert '<div class="section-title">Standardvurderinger</div>' not in html

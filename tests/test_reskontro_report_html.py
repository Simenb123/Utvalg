"""Tester for reskontro_report_html — sanity-sjekk at HTML bygges."""
from __future__ import annotations

import pandas as pd
import pytest

from reskontro_report_engine import compute_reskontro_report
from reskontro_report_html import build_report_html, build_html_from_df


def _make_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"Bilag": "1001", "Dato": "2025-01-10", "Konto": "1500", "Kontonavn": "Kundefordringer",
         "Beløp": 12500.0, "Tekst": "Faktura", "Kundenr": "K1", "Kundenavn": "Alpha AS",
         "Kundeorgnr": "111111111", "KundeIB": 0.0, "KundeUB": 7500.0, "KundeKonto": "1500"},
        {"Bilag": "1001", "Dato": "2025-01-10", "Konto": "3000", "Kontonavn": "Salgsinntekt",
         "Beløp": -10000.0, "Tekst": "Salg", "Kundenr": "", "Kundenavn": "",
         "Kundeorgnr": "", "KundeIB": None, "KundeUB": None, "KundeKonto": ""},
        {"Bilag": "1001", "Dato": "2025-01-10", "Konto": "2700", "Kontonavn": "Utgående MVA",
         "Beløp": -2500.0, "Tekst": "MVA", "Kundenr": "", "Kundenavn": "",
         "Kundeorgnr": "", "KundeIB": None, "KundeUB": None, "KundeKonto": ""},
        {"Bilag": "1050", "Dato": "2025-03-05", "Konto": "1500", "Kontonavn": "Kundefordringer",
         "Beløp": -5000.0, "Tekst": "Innbetaling", "Kundenr": "K1", "Kundenavn": "Alpha AS",
         "Kundeorgnr": "111111111", "KundeIB": 0.0, "KundeUB": 7500.0, "KundeKonto": "1500"},
        {"Bilag": "1050", "Dato": "2025-03-05", "Konto": "1920", "Kontonavn": "Bank",
         "Beløp": 5000.0, "Tekst": "Bank", "Kundenr": "", "Kundenavn": "",
         "Kundeorgnr": "", "KundeIB": None, "KundeUB": None, "KundeKonto": ""},
    ])


class TestBuildHtml:
    def test_html_inneholder_klient_og_år(self):
        df = _make_df()
        report = compute_reskontro_report(
            df, mode="kunder", client="TestAS", year=2025, reference_date="2025-12-31",
        )
        html = build_report_html(report)
        assert "<!DOCTYPE html>" in html
        assert "TestAS" in html
        assert "2025" in html
        assert "theme-kunder" in html

    def test_html_kunder_tittel_og_label(self):
        df = _make_df()
        report = compute_reskontro_report(
            df, mode="kunder", client="TestAS", reference_date="2025-12-31",
        )
        html = build_report_html(report)
        assert "Kunder" in html
        assert "kredit-bevegelse" in html.lower() or "kredit" in html.lower()

    def test_html_leverandorer_tittel(self):
        # Bygg et lev-dataset
        df = pd.DataFrame([
            {"Bilag": "2001", "Dato": "2025-01-15", "Konto": "2400", "Kontonavn": "Leverandørgjeld",
             "Beløp": -8000.0, "Tekst": "Faktura", "Leverandørnr": "L1", "Leverandørnavn": "Sup One",
             "Leverandørorgnr": "999999999", "LeverandørIB": 0.0, "LeverandørUB": -8000.0,
             "LeverandørKonto": "2400"},
            {"Bilag": "2001", "Dato": "2025-01-15", "Konto": "4000", "Kontonavn": "Varekost",
             "Beløp": 8000.0, "Tekst": "Kjøp", "Leverandørnr": "", "Leverandørnavn": "",
             "Leverandørorgnr": "", "LeverandørIB": None, "LeverandørUB": None,
             "LeverandørKonto": ""},
        ])
        report = compute_reskontro_report(
            df, mode="leverandorer", client="TestAS", reference_date="2025-12-31",
        )
        html = build_report_html(report)
        assert "Leverandører" in html or "Leverand\u00f8rer" in html
        assert "theme-lev" in html
        assert "debet-bevegelse" in html.lower() or "debet" in html.lower()

    def test_html_inneholder_alle_fire_sider(self):
        df = _make_df()
        report = compute_reskontro_report(
            df, mode="kunder", client="TestAS", reference_date="2025-12-31",
        )
        html = build_report_html(report)
        assert html.count('class="page"') == 8

    def test_tomt_df_gir_fortsatt_gyldig_html(self):
        report = compute_reskontro_report(
            pd.DataFrame(), mode="kunder", client="TestAS",
        )
        html = build_report_html(report)
        assert "<!DOCTYPE html>" in html
        assert html.count('class="page"') == 8

    def test_html_har_avstemming_mot_sb(self):
        df = _make_df()
        sb = pd.DataFrame([{"konto": "1500", "ub": 7500.0}])
        report = compute_reskontro_report(
            df, mode="kunder", client="TestAS", reference_date="2025-12-31", sb_df=sb,
        )
        html = build_report_html(report)
        assert "Avstemming" in html
        assert "Reskontro UB" in html

    def test_build_from_df_convenience(self):
        df = _make_df()
        html = build_html_from_df(
            df, mode="kunder", client="TestAS", reference_date="2025-12-31",
        )
        assert "<!DOCTYPE html>" in html
        assert "TestAS" in html

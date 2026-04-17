"""Tester for reskontro_report_engine."""
from __future__ import annotations

import pandas as pd
import pytest

from reskontro_report_engine import (
    compute_reskontro_report,
    _build_party_rows,
    _build_hb_accounts,
    _build_motpost,
    _build_concentration,
)


def _make_kunde_df() -> pd.DataFrame:
    """Minimal SAF-T-style kundefordringer-dataset.

    K1: salg 10000 + MVA 2500 (bilag 1001), delvis bet 5000 (bilag 1050) → UB 7500
    K2: salg 4000 (bilag 1002), betaling 4000 (bilag 1060) → UB 0
    K3: kun kreditnota -2000 (bilag 1003) → UB -2000 (forskudd/feil)
    """
    return pd.DataFrame([
        # K1 salg: debet 1500, kredit 3000 + 2700
        {"Bilag": "1001", "Dato": "2025-01-10", "Konto": "1500", "Kontonavn": "Kundefordringer",
         "Beløp": 12500.0, "Tekst": "Faktura 1001", "Kundenr": "K1", "Kundenavn": "Alpha AS",
         "Kundeorgnr": "111111111", "KundeIB": 0.0, "KundeUB": 7500.0, "KundeKonto": "1500"},
        {"Bilag": "1001", "Dato": "2025-01-10", "Konto": "3000", "Kontonavn": "Salgsinntekt",
         "Beløp": -10000.0, "Tekst": "Salg K1", "Kundenr": "", "Kundenavn": "",
         "Kundeorgnr": "", "KundeIB": None, "KundeUB": None, "KundeKonto": ""},
        {"Bilag": "1001", "Dato": "2025-01-10", "Konto": "2700", "Kontonavn": "Utgående MVA",
         "Beløp": -2500.0, "Tekst": "MVA", "Kundenr": "", "Kundenavn": "",
         "Kundeorgnr": "", "KundeIB": None, "KundeUB": None, "KundeKonto": ""},
        # K1 innbetaling: debet 1920, kredit 1500
        {"Bilag": "1050", "Dato": "2025-03-05", "Konto": "1500", "Kontonavn": "Kundefordringer",
         "Beløp": -5000.0, "Tekst": "Betaling faktura 1001", "Kundenr": "K1", "Kundenavn": "Alpha AS",
         "Kundeorgnr": "111111111", "KundeIB": 0.0, "KundeUB": 7500.0, "KundeKonto": "1500"},
        {"Bilag": "1050", "Dato": "2025-03-05", "Konto": "1920", "Kontonavn": "Bank",
         "Beløp": 5000.0, "Tekst": "Bank innbetaling", "Kundenr": "", "Kundenavn": "",
         "Kundeorgnr": "", "KundeIB": None, "KundeUB": None, "KundeKonto": ""},
        # K2 salg + betaling — UB 0
        {"Bilag": "1002", "Dato": "2025-02-01", "Konto": "1500", "Kontonavn": "Kundefordringer",
         "Beløp": 4000.0, "Tekst": "Faktura 1002", "Kundenr": "K2", "Kundenavn": "Beta AS",
         "Kundeorgnr": "222222222", "KundeIB": 0.0, "KundeUB": 0.0, "KundeKonto": "1500"},
        {"Bilag": "1002", "Dato": "2025-02-01", "Konto": "3000", "Kontonavn": "Salgsinntekt",
         "Beløp": -4000.0, "Tekst": "Salg K2", "Kundenr": "", "Kundenavn": "",
         "Kundeorgnr": "", "KundeIB": None, "KundeUB": None, "KundeKonto": ""},
        {"Bilag": "1060", "Dato": "2025-04-15", "Konto": "1500", "Kontonavn": "Kundefordringer",
         "Beløp": -4000.0, "Tekst": "Innbetaling K2", "Kundenr": "K2", "Kundenavn": "Beta AS",
         "Kundeorgnr": "222222222", "KundeIB": 0.0, "KundeUB": 0.0, "KundeKonto": "1500"},
        {"Bilag": "1060", "Dato": "2025-04-15", "Konto": "1920", "Kontonavn": "Bank",
         "Beløp": 4000.0, "Tekst": "Bank K2", "Kundenr": "", "Kundenavn": "",
         "Kundeorgnr": "", "KundeIB": None, "KundeUB": None, "KundeKonto": ""},
        # K3 kreditnota (forskuddsbetaling) — UB negativ
        {"Bilag": "1003", "Dato": "2025-05-10", "Konto": "1500", "Kontonavn": "Kundefordringer",
         "Beløp": -2000.0, "Tekst": "Kreditnota K3", "Kundenr": "K3", "Kundenavn": "Gamma AS",
         "Kundeorgnr": "333333333", "KundeIB": 0.0, "KundeUB": -2000.0, "KundeKonto": "1500"},
        {"Bilag": "1003", "Dato": "2025-05-10", "Konto": "1920", "Kontonavn": "Bank",
         "Beløp": 2000.0, "Tekst": "Forskudd K3", "Kundenr": "", "Kundenavn": "",
         "Kundeorgnr": "", "KundeIB": None, "KundeUB": None, "KundeKonto": ""},
    ])


def _make_leverandor_df() -> pd.DataFrame:
    """Minimal lev-dataset — speilvendt.

    L1: kjøp -8000 (bilag 2001), betaling 8000 (bilag 2050) → UB 0
    L2: kjøp -5000 (bilag 2002) åpen → UB -5000 (rå SAF-T)
    """
    return pd.DataFrame([
        {"Bilag": "2001", "Dato": "2025-01-15", "Konto": "2400", "Kontonavn": "Leverandørgjeld",
         "Beløp": -8000.0, "Tekst": "Faktura L1", "Leverandørnr": "L1", "Leverandørnavn": "Supplier One",
         "Leverandørorgnr": "999999999", "LeverandørIB": 0.0, "LeverandørUB": 0.0, "LeverandørKonto": "2400"},
        {"Bilag": "2001", "Dato": "2025-01-15", "Konto": "4000", "Kontonavn": "Varekost",
         "Beløp": 6400.0, "Tekst": "Kjøp L1", "Leverandørnr": "", "Leverandørnavn": "",
         "Leverandørorgnr": "", "LeverandørIB": None, "LeverandørUB": None, "LeverandørKonto": ""},
        {"Bilag": "2001", "Dato": "2025-01-15", "Konto": "2710", "Kontonavn": "Inngående MVA",
         "Beløp": 1600.0, "Tekst": "MVA", "Leverandørnr": "", "Leverandørnavn": "",
         "Leverandørorgnr": "", "LeverandørIB": None, "LeverandørUB": None, "LeverandørKonto": ""},
        {"Bilag": "2050", "Dato": "2025-02-20", "Konto": "2400", "Kontonavn": "Leverandørgjeld",
         "Beløp": 8000.0, "Tekst": "Betaling L1", "Leverandørnr": "L1", "Leverandørnavn": "Supplier One",
         "Leverandørorgnr": "999999999", "LeverandørIB": 0.0, "LeverandørUB": 0.0, "LeverandørKonto": "2400"},
        {"Bilag": "2050", "Dato": "2025-02-20", "Konto": "1920", "Kontonavn": "Bank",
         "Beløp": -8000.0, "Tekst": "Bank ut L1", "Leverandørnr": "", "Leverandørnavn": "",
         "Leverandørorgnr": "", "LeverandørIB": None, "LeverandørUB": None, "LeverandørKonto": ""},
        {"Bilag": "2002", "Dato": "2025-03-20", "Konto": "2400", "Kontonavn": "Leverandørgjeld",
         "Beløp": -5000.0, "Tekst": "Faktura L2", "Leverandørnr": "L2", "Leverandørnavn": "Supplier Two",
         "Leverandørorgnr": "888888888", "LeverandørIB": 0.0, "LeverandørUB": -5000.0, "LeverandørKonto": "2400"},
        {"Bilag": "2002", "Dato": "2025-03-20", "Konto": "6000", "Kontonavn": "Avskrivning",
         "Beløp": 5000.0, "Tekst": "Kjøp L2", "Leverandørnr": "", "Leverandørnavn": "",
         "Leverandørorgnr": "", "LeverandørIB": None, "LeverandørUB": None, "LeverandørKonto": ""},
    ])


class TestPartyRows:
    def test_kunder_ub_og_bevegelse(self):
        df = _make_kunde_df()
        rows = _build_party_rows(df, mode="kunder", reference_date="2025-12-31")
        by_nr = {r.nr: r for r in rows}
        assert set(by_nr) == {"K1", "K2", "K3"}
        assert by_nr["K1"].ub == pytest.approx(7500.0)
        assert by_nr["K1"].debet == pytest.approx(12500.0)
        assert by_nr["K1"].kredit == pytest.approx(5000.0)
        assert by_nr["K3"].ub == pytest.approx(-2000.0)

    def test_leverandorer_flipper_fortegn(self):
        df = _make_leverandor_df()
        rows = _build_party_rows(df, mode="leverandorer", reference_date="2025-12-31")
        by_nr = {r.nr: r for r in rows}
        # L1 har 0 UB; L2 rå UB=-5000 → leverandørgjeld vises som +5000
        assert by_nr["L2"].ub == pytest.approx(5000.0)
        assert by_nr["L1"].ub == pytest.approx(0.0)

    def test_dager_siden_siste(self):
        df = _make_kunde_df()
        rows = _build_party_rows(df, mode="kunder", reference_date="2025-12-31")
        by_nr = {r.nr: r for r in rows}
        # K2 siste dato 2025-04-15 → 2025-12-31 diff = 260 dager
        assert by_nr["K2"].dager_siden_siste == 260


class TestHbAccounts:
    def test_kunder_hb_konto_aggregering(self):
        df = _make_kunde_df()
        hb = _build_hb_accounts(df, mode="kunder")
        assert len(hb) == 1
        assert hb[0].konto == "1500"
        # Sum party-UB: 7500 + 0 + (-2000) = 5500
        assert hb[0].ub == pytest.approx(5500.0)


class TestMotpost:
    def test_kunder_kredit_motposter(self):
        df = _make_kunde_df()
        mp = _build_motpost(df, mode="kunder", side="kredit")
        # Kreditsiden (negativt beløp) på kundebilag: 3000 (salg) + 2700 (MVA)
        kontoer = {r.konto for r in mp}
        assert "3000" in kontoer
        assert "2700" in kontoer

    def test_kunder_debet_motposter(self):
        df = _make_kunde_df()
        mp = _build_motpost(df, mode="kunder", side="debet")
        # Debetsiden (positivt beløp) på kundebilag: 1920 (bank innbetaling)
        kontoer = {r.konto for r in mp}
        assert "1920" in kontoer


class TestConcentration:
    def test_hhi_og_topp_andel(self):
        df = _make_kunde_df()
        rows = _build_party_rows(df, mode="kunder", reference_date="2025-12-31")
        c = _build_concentration(rows)
        assert c["count"] == 3
        assert c["total_ub"] == pytest.approx(7500.0 + 0.0 + 2000.0)
        assert c["top5_pct"] == pytest.approx(100.0)


class TestFullReport:
    def test_kunder_rapport_end_to_end(self):
        df = _make_kunde_df()
        report = compute_reskontro_report(
            df, mode="kunder", client="TestAS", year=2025,
            reference_date="2025-12-31", top_n=10,
        )
        assert report.mode == "kunder"
        assert report.client == "TestAS"
        assert report.kpi["antall_total"] == 3
        # K3 har negativ UB → counter_balance_rows inneholder K3
        cb_nrs = {r.nr for r in report.counter_balance_rows}
        assert "K3" in cb_nrs
        # Topp UB er K1 (7500)
        assert report.top_ub[0].nr == "K1"

    def test_leverandorer_rapport_end_to_end(self):
        df = _make_leverandor_df()
        report = compute_reskontro_report(
            df, mode="leverandorer", client="TestAS", year=2025,
            reference_date="2025-12-31", top_n=10,
        )
        assert report.mode == "leverandorer"
        # Topp UB etter flipp: L2 (5000)
        assert report.top_ub[0].nr == "L2"
        assert report.top_ub[0].ub == pytest.approx(5000.0)

    def test_hb_avstemming_mot_sb(self):
        df = _make_kunde_df()
        sb = pd.DataFrame([{"konto": "1500", "ub": 5500.0}])
        report = compute_reskontro_report(
            df, mode="kunder", reference_date="2025-12-31",
            sb_df=sb, top_n=10,
        )
        rec = report.hb_reconciliation
        assert rec["has_sb"] is True
        assert rec["reskontro_ub"] == pytest.approx(5500.0)
        assert rec["sb_ub"] == pytest.approx(5500.0)
        assert abs(rec["diff"]) < 0.01

    def test_tomt_df_gir_tom_rapport(self):
        report = compute_reskontro_report(
            pd.DataFrame(), mode="kunder", reference_date="2025-12-31",
        )
        assert report.top_ub == []
        assert report.kpi == {}

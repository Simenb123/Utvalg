"""Tests for reskontro_brreg_helpers and reskontro_open_items."""
from __future__ import annotations

import pandas as pd
import pytest

from src.pages.reskontro.backend.brreg_helpers import (
    _brreg_has_risk,
    _brreg_status_text,
    _compute_nokkeltall,
    _fmt_nok,
    _fmt_pct,
)
from src.pages.reskontro.backend.open_items import (
    _compute_aging_buckets,
    _compute_open_items,
    _compute_open_items_with_confidence,
    _extract_faktura_nr,
    _is_invoice_tekst,
    _is_non_invoice_tekst,
    _is_payment_tekst,
)


# ---------------------------------------------------------------------------
# _brreg_status_text
# ---------------------------------------------------------------------------

class TestBrregStatusText:
    def test_active(self):
        assert "Aktiv" in _brreg_status_text({})

    def test_konkurs(self):
        assert "Konkurs" in _brreg_status_text({"konkurs": "2025-01-01"})

    def test_slettet(self):
        assert "Slettet" in _brreg_status_text({"slettedato": "2024-06-15"})

    def test_multiple_flags(self):
        text = _brreg_status_text({"konkurs": True, "underAvvikling": True})
        assert "Konkurs" in text
        assert "Avvikling" in text


# ---------------------------------------------------------------------------
# _brreg_has_risk
# ---------------------------------------------------------------------------

class TestBrregHasRisk:
    def test_no_risk(self):
        assert _brreg_has_risk({}) is False

    def test_konkurs(self):
        assert _brreg_has_risk({"konkurs": True}) is True

    def test_slettet(self):
        assert _brreg_has_risk({"slettedato": "2024-01-01"}) is True


# ---------------------------------------------------------------------------
# _fmt_nok / _fmt_pct
# ---------------------------------------------------------------------------

class TestFormatting:
    def test_fmt_nok_none(self):
        assert _fmt_nok(None) == "\u2014"

    def test_fmt_nok_value(self):
        result = _fmt_nok(1234567.0)
        assert "1" in result  # should contain the number in some formatted form

    def test_fmt_pct_none(self):
        assert _fmt_pct(None) == "\u2014"

    def test_fmt_pct_value(self):
        assert "%" in _fmt_pct(12.5)
        assert "12.5" in _fmt_pct(12.5)


# ---------------------------------------------------------------------------
# _compute_nokkeltall
# ---------------------------------------------------------------------------

class TestComputeNokkeltall:
    def test_empty_dict(self):
        assert _compute_nokkeltall({}) == []

    def test_basic_regnskap(self):
        regnsk = {
            "sum_omloepsmidler": 1_000_000,
            "kortsiktig_gjeld": 500_000,
            "sum_egenkapital": 800_000,
            "sum_eiendeler": 2_000_000,
            "sum_gjeld": 1_200_000,
            "aarsresultat": 200_000,
            "driftsinntekter": 3_000_000,
        }
        rows = _compute_nokkeltall(regnsk)
        labels = [r[0] for r in rows]
        assert "Likviditetsgrad 1" in labels
        assert "Egenkapitalandel" in labels
        assert "Gjeldsgrad" in labels
        assert "Resultatmargin" in labels

    def test_likviditetsgrad_ok(self):
        regnsk = {"sum_omloepsmidler": 1_500_000, "kortsiktig_gjeld": 500_000}
        rows = _compute_nokkeltall(regnsk)
        lg1 = next(r for r in rows if r[0] == "Likviditetsgrad 1")
        assert lg1[2] == "ok"  # 3.0 >= 1.5

    def test_likviditetsgrad_bad(self):
        regnsk = {"sum_omloepsmidler": 400_000, "kortsiktig_gjeld": 500_000}
        rows = _compute_nokkeltall(regnsk)
        lg1 = next(r for r in rows if r[0] == "Likviditetsgrad 1")
        assert lg1[2] == "bad"  # 0.8 < 1.0

    def test_negativ_egenkapital(self):
        # When eiendeler is 0 or missing, the elif branch triggers
        regnsk = {"sum_egenkapital": -100_000}
        rows = _compute_nokkeltall(regnsk)
        ek = next(r for r in rows if "Negativ" in r[1])
        assert ek[2] == "bad"

    def test_negativ_egenkapital_with_eiendeler(self):
        # When eiendeler is present, egenkapitalandel is computed (negative %)
        regnsk = {"sum_egenkapital": -100_000, "sum_eiendeler": 500_000}
        rows = _compute_nokkeltall(regnsk)
        labels = [r[0] for r in rows]
        assert "Egenkapitalandel" in labels
        eka = next(r for r in rows if r[0] == "Egenkapitalandel")
        assert eka[2] == "bad"  # -20% < 10

    def test_negativt_aarsresultat_uten_driftsinntekter(self):
        regnsk = {"aarsresultat": -50_000}
        rows = _compute_nokkeltall(regnsk)
        neg = next(r for r in rows if "Negativt" in r[1])
        assert neg[2] == "bad"


# ---------------------------------------------------------------------------
# Invoice/payment text classification
# ---------------------------------------------------------------------------

class TestTextClassification:
    def test_is_invoice_tekst(self):
        assert _is_invoice_tekst("Faktura 12345") is True
        assert _is_invoice_tekst("Kreditnota 100") is True
        assert _is_invoice_tekst("Betaling mottatt") is False

    def test_is_payment_tekst(self):
        assert _is_payment_tekst("Innbetaling fra kunde") is True
        assert _is_payment_tekst("Betaling mottatt") is True
        assert _is_payment_tekst("Avregning konto") is True
        assert _is_payment_tekst("Faktura 12345") is False

    def test_is_non_invoice_tekst(self):
        assert _is_non_invoice_tekst("Periodisering jan") is True
        assert _is_non_invoice_tekst("Avskrivning inventar") is True
        assert _is_non_invoice_tekst("Faktura 12345") is False


# ---------------------------------------------------------------------------
# _extract_faktura_nr
# ---------------------------------------------------------------------------

class TestExtractFakturaNr:
    def test_basic_extraction(self):
        nr = _extract_faktura_nr("Faktura 12345 fra leverandør")
        assert nr == "12345"

    def test_kreditnota(self):
        nr = _extract_faktura_nr("Kreditnota 98765")
        assert nr == "98765"

    def test_no_number(self):
        assert _extract_faktura_nr("Generell tekst uten nummer") is None


# ---------------------------------------------------------------------------
# _compute_open_items
# ---------------------------------------------------------------------------

class TestComputeOpenItems:
    def _make_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "Leverandørnr": ["1001"] * 4,
            "Dato": ["2025-01-15", "2025-02-10", "2025-03-01", "2025-04-01"],
            "Bilag": ["B1", "B2", "B3", "B4"],
            "Tekst": [
                "Faktura 100 fra Leverandør",
                "Faktura 200 fra Leverandør",
                "Betaling faktura 100",
                "Faktura 300 fra Leverandør",
            ],
            "Beløp": [10000.0, 5000.0, -10000.0, 8000.0],
        })

    def test_basic_open_items(self):
        df = self._make_df()
        result = _compute_open_items(df, nr="1001", mode="leverandorer", ub=13000.0)
        assert not result.empty
        assert "Status" in result.columns
        assert "Gjenstår" in result.columns

    def test_open_items_with_confidence(self):
        df = self._make_df()
        result_df, confidence = _compute_open_items_with_confidence(
            df, nr="1001", mode="leverandorer", ub=13000.0, ib=0.0)
        assert not result_df.empty
        assert "level" in confidence
        assert confidence["level"] in ("høy", "middels", "lav")


# ---------------------------------------------------------------------------
# _compute_aging_buckets
# ---------------------------------------------------------------------------

class TestAgingBuckets:
    def test_basic_aging(self):
        items = [
            {"Dato": "2025-01-15", "Gjenstår": 5000.0},
            {"Dato": "2025-06-01", "Gjenstår": 3000.0},
            {"Dato": "2025-10-01", "Gjenstår": 2000.0},
        ]
        buckets = _compute_aging_buckets(items, reference_date="2025-12-31")
        assert len(buckets) > 0
        # Each bucket is (label, amount, count)
        for label, amount, count in buckets:
            assert isinstance(label, str)
            assert isinstance(amount, (int, float))
            assert isinstance(count, int)

    def test_empty_items(self):
        result = _compute_aging_buckets([], reference_date="2025-12-31")
        # Returns buckets even for empty items (with zero amounts)
        for label, amount, count in result:
            assert count == 0
            assert amount == 0.0

    def test_invalid_reference_date(self):
        assert _compute_aging_buckets([], reference_date="not-a-date") == []


# ---------------------------------------------------------------------------
# Module import smoke tests
# ---------------------------------------------------------------------------

def test_reskontro_brreg_panel_importable():
    import src.pages.reskontro.frontend.brreg_panel as reskontro_brreg_panel
    assert hasattr(reskontro_brreg_panel, "build_brreg_panel")
    assert hasattr(reskontro_brreg_panel, "update_brreg_panel")


def test_reskontro_popups_importable():
    import src.pages.reskontro.frontend.popups as reskontro_popups
    assert hasattr(reskontro_popups, "open_bilag_popup")
    assert hasattr(reskontro_popups, "show_open_items_popup")
    assert hasattr(reskontro_popups, "show_saldoliste_popup")
    assert hasattr(reskontro_popups, "show_subsequent_match_popup")


def test_analyse_drilldown_importable():
    import analyse_drilldown
    assert hasattr(analyse_drilldown, "restore_rl_pivot_selection")
    assert hasattr(analyse_drilldown, "reload_rl_drilldown_df")
    assert hasattr(analyse_drilldown, "open_rl_drilldown_from_pivot_selection")
    assert hasattr(analyse_drilldown, "refresh_nokkeltall_view")

"""Tester for mva_kontroller — K4, K5, K6."""
from __future__ import annotations

import pandas as pd
import pytest

from src.pages.mva.backend.avstemming import SkatteetatenData
from src.pages.mva.backend.kontroller import (
    KontrollResult,
    run_all_controls,
    run_k4_korreksjoner,
    run_k5_forsinkelsesrente,
    run_k6_klassifisering_vs_kode,
)


class TestK4Korreksjoner:
    def _df(self, rows):
        return pd.DataFrame(
            rows, columns=["Bilag", "MVA-kode", "MVA-beløp", "Beløp", "Dato", "Konto"]
        )

    def test_normale_transaksjoner_er_ok(self):
        # SAF-T: kode 3 = utgående 25%, kode 11 = inngående 15%
        df = self._df([
            ["1", "3", -250.0, -1000.0, "2025-01-15", "3000"],
            ["2", "11", 100.0, 400.0, "2025-01-20", "4300"],
        ])
        r = run_k4_korreksjoner(df)
        assert r.status == "OK"
        assert r.treff == 0

    def test_storno_utgaaende_mva_merkes(self):
        # Utgående kode "3" med POSITIVT MVA-beløp = storno
        df = self._df([
            ["1", "3", 250.0, 1000.0, "2025-01-15", "3000"],  # storno
            ["2", "3", -250.0, -1000.0, "2025-02-15", "3000"],
        ])
        r = run_k4_korreksjoner(df)
        assert r.status == "MERK"
        assert r.treff == 1
        assert r.detaljer is not None

    def test_storno_inngaaende_mva_merkes(self):
        df = self._df([
            ["1", "11", -100.0, -400.0, "2025-01-15", "4300"],  # storno
        ])
        r = run_k4_korreksjoner(df)
        assert r.status == "MERK"
        assert r.treff == 1


class TestK5Forsinkelsesrente:
    def test_uten_data_gir_mangler(self):
        r = run_k5_forsinkelsesrente(None)
        assert r.status == "MANGLER"

    def test_mva_krav_uten_rente(self):
        sd = SkatteetatenData(
            raw_krav=pd.DataFrame([
                {"Kravgruppe": "Merverdiavgift", "Påløpte renter": 0.0},
            ]),
        )
        r = run_k5_forsinkelsesrente(sd)
        assert r.status == "OK"

    def test_mva_krav_med_rente_merkes(self):
        sd = SkatteetatenData(
            raw_krav=pd.DataFrame([
                {"Kravgruppe": "Merverdiavgift", "Påløpte renter": 1500.0},
                {"Kravgruppe": "Merverdiavgift", "Påløpte renter": 0.0},
            ]),
        )
        r = run_k5_forsinkelsesrente(sd)
        assert r.status == "MERK"
        assert r.treff == 1
        assert r.beløp == pytest.approx(1500.0)


class TestK6KlassifiseringVsKode:
    def _df(self, rows):
        return pd.DataFrame(
            rows, columns=["Bilag", "Konto", "MVA-kode", "Beløp", "Dato"]
        )

    def test_konsistent_klassifisering_er_ok(self):
        # SAF-T: kode 3 = utgående 25% → stemmer med Utgående MVA-konto
        df = self._df([
            ["1", "2700", "3", -1000.0, "2025-01-15"],
        ])
        mapping = {"2700": "Utgående MVA"}
        r = run_k6_klassifisering_vs_kode(df, mapping)
        assert r.status == "OK"

    def test_inkonsistens_merkes(self):
        # Konto klassifisert som inngående, men kode 3 = utgående → avvik
        df = self._df([
            ["1", "2710", "3", -1000.0, "2025-01-15"],
        ])
        mapping = {"2710": "Inngående MVA"}
        r = run_k6_klassifisering_vs_kode(df, mapping)
        assert r.status == "AVVIK"
        assert r.treff == 1

    def test_uten_klassifisering_er_ok(self):
        df = self._df([["1", "2700", "3", -1000.0, "2025-01-15"]])
        r = run_k6_klassifisering_vs_kode(df, {})
        assert r.status in ("OK", "MANGLER")


class TestRunAll:
    def test_returnerer_minst_k1_til_k6(self):
        df = pd.DataFrame([
            {"Bilag": "1", "Konto": "3000", "MVA-kode": "1",
             "MVA-beløp": -250.0, "Beløp": -1000.0, "Dato": "2025-01-15"},
        ])
        result = run_all_controls(df)
        ids = [r.id for r in result.results]
        assert "K1" in ids
        assert "K4" in ids
        assert "K5" in ids
        assert "K6" in ids

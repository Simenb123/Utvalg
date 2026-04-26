"""Tester for MVA-avstemming end-to-end:

- SkatteetatenData.to_dict/from_dict roundtrip
- save/load_skatteetaten_data + save/load_mva_melding via klient-overrides
- 3-veis avstemming HB vs MVA-melding vs Skatteetaten.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.pages.mva.backend.avstemming import SkatteetatenData, build_reconciliation
from src.pages.mva.backend.melding_parser import MvaMeldingData
from page_analyse_mva import build_mva_pivot


class TestSkatteetatenRoundtrip:
    def test_to_from_dict_preserves_terminer(self):
        sd = SkatteetatenData(
            org_nr="999999999",
            company="DemoAS",
            period="2025",
            mva_per_termin={1: 100.0, 3: 200.0},
            aga_per_termin={1: 50.0},
            year=2025,
        )
        d = sd.to_dict()
        restored = SkatteetatenData.from_dict(d)
        assert restored.org_nr == "999999999"
        assert restored.mva_per_termin[1] == 100.0
        assert restored.mva_per_termin[3] == 200.0
        assert restored.aga_per_termin[1] == 50.0
        assert restored.year == 2025

    def test_empty_dict_gir_tom_data(self):
        sd = SkatteetatenData.from_dict({})
        assert sd.org_nr == ""
        assert sd.mva_per_termin == {}

    def test_dataframe_roundtrip(self):
        sd = SkatteetatenData(
            mva_per_termin={1: 100.0},
            raw_krav=pd.DataFrame([
                {"Kravgruppe": "Merverdiavgift", "Periode": 1, "Beløp": 100.0},
            ]),
        )
        restored = SkatteetatenData.from_dict(sd.to_dict())
        assert restored.raw_krav is not None
        assert len(restored.raw_krav) == 1


class TestClientPersistence:
    def _setup_overrides_path(self, tmp_path, monkeypatch):
        """Omdirigerer app-data-dir så tester ikke rører ekte klientfiler."""
        import app_paths
        monkeypatch.setattr(app_paths, "data_dir", lambda: Path(tmp_path))

    def test_save_and_load_skatteetaten(self, tmp_path, monkeypatch):
        self._setup_overrides_path(tmp_path, monkeypatch)
        import src.shared.regnskap.client_overrides as rco

        sd = SkatteetatenData(mva_per_termin={1: 100.0, 2: 200.0})
        rco.save_skatteetaten_data("DemoAS", 2025, sd.to_dict())

        raw = rco.load_skatteetaten_data("DemoAS", 2025)
        assert raw is not None
        restored = SkatteetatenData.from_dict(raw)
        assert restored.mva_per_termin[1] == 100.0
        assert restored.mva_per_termin[2] == 200.0

    def test_load_skatteetaten_missing_year(self, tmp_path, monkeypatch):
        self._setup_overrides_path(tmp_path, monkeypatch)
        import src.shared.regnskap.client_overrides as rco

        rco.save_skatteetaten_data("DemoAS", 2025, {"mva_per_termin": {"1": 10.0}})
        assert rco.load_skatteetaten_data("DemoAS", 2024) is None

    def test_save_and_load_mva_melding_per_termin(self, tmp_path, monkeypatch):
        self._setup_overrides_path(tmp_path, monkeypatch)
        import src.shared.regnskap.client_overrides as rco

        md1 = MvaMeldingData(år=2025, termin=1, post1_avgift_25=100.0)
        md2 = MvaMeldingData(år=2025, termin=2, post1_avgift_25=200.0)
        rco.save_mva_melding("DemoAS", 2025, 1, md1.to_dict())
        rco.save_mva_melding("DemoAS", 2025, 2, md2.to_dict())

        single = rco.load_mva_melding("DemoAS", 2025, termin=1)
        assert single is not None
        restored = MvaMeldingData.from_dict(single)
        assert restored.post1_avgift_25 == 100.0

        all_terminer = rco.load_mva_melding("DemoAS", 2025)
        assert set(all_terminer.keys()) == {"1", "2"}


class TestTreeWayReconciliation:
    def _make_df(self) -> pd.DataFrame:
        # SAF-T StandardTaxCode: "3" = utgående 25%, "11" = inngående 15%
        return pd.DataFrame([
            {"MVA-kode": "3", "MVA-beløp": -250.0,  "Dato": "2025-01-15",
             "Konto": "3000", "Beløp": -1000.0},
            {"MVA-kode": "11", "MVA-beløp": 100.0,  "Dato": "2025-01-20",
             "Konto": "4300", "Beløp": 400.0},
        ])

    def test_hb_mot_skatteetaten_gir_avvik_rapport(self):
        pivot = build_mva_pivot(self._make_df())
        sd = SkatteetatenData(mva_per_termin={1: 150.0})
        recon = build_reconciliation(pivot, sd)
        assert not recon.empty
        # T1: HB netto = |250|-|100| = 150, innrapportert = 150 → differanse 0
        t1_row = recon[recon["Termin"] == "T1"].iloc[0]
        assert abs(t1_row["Differanse"]) < 0.01

    def test_hb_mot_skatteetaten_med_avvik(self):
        pivot = build_mva_pivot(self._make_df())
        sd = SkatteetatenData(mva_per_termin={1: 100.0})  # Skatt rapporterer mindre
        recon = build_reconciliation(pivot, sd)
        t1_row = recon[recon["Termin"] == "T1"].iloc[0]
        assert t1_row["Differanse"] == pytest.approx(50.0)

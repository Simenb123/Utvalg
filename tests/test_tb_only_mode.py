"""Tests for TB-only (Saldobalanse) first-class input mode.

Covers:
  1. session.set_tb() / set_dataset() version_type tracking
  2. bus.emit("TB_LOADED") → App._on_tb_ready() dispatch
  3. ConsolidationPage._update_session_tb_button() visibility logic
  4. ConsolidationPage._on_use_session_tb() imports TB as company
"""

from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from models import Columns


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_tb() -> pd.DataFrame:
    return pd.DataFrame({
        "konto": ["1000", "3000"],
        "kontonavn": ["Bank", "Salg"],
        "ib": [0.0, 0.0],
        "ub": [100.0, -200.0],
        "netto": [100.0, -200.0],
    })


def _sample_hb_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Konto": [1000],
        "Kontonavn": ["Testkonto"],
        "Beloep": [123.45],
        "Bilag": ["1"],
    })


# ---------------------------------------------------------------------------
# 1. session.set_tb / set_dataset
# ---------------------------------------------------------------------------

class TestSessionTbState:
    def setup_method(self):
        import session
        # Reset state before each test
        session.tb_df = None
        session.version_type = None
        session.dataset = None

    def test_set_tb_sets_tb_df_and_version_type(self):
        import session
        tb = _sample_tb()
        session.set_tb(tb)

        assert session.tb_df is tb
        assert session.version_type == "sb"

    def test_set_dataset_sets_version_type_hb(self):
        import session
        df = _sample_hb_df()
        cols = Columns(konto="Konto", kontonavn="Kontonavn", bilag="Bilag", belop="Beloep")
        session.set_dataset(df, cols)

        assert session.version_type == "hb"
        assert session.dataset is df

    def test_set_tb_after_set_dataset_switches_to_sb(self):
        import session
        df = _sample_hb_df()
        cols = Columns(konto="Konto", kontonavn="Kontonavn", bilag="Bilag", belop="Beloep")
        session.set_dataset(df, cols)
        assert session.version_type == "hb"

        tb = _sample_tb()
        session.set_tb(tb)
        assert session.version_type == "sb"
        assert session.tb_df is tb
        # HB dataset should still be available
        assert session.dataset is df

    def test_set_dataset_after_set_tb_switches_to_hb(self):
        import session
        tb = _sample_tb()
        session.set_tb(tb)
        assert session.version_type == "sb"

        df = _sample_hb_df()
        cols = Columns(konto="Konto", kontonavn="Kontonavn", bilag="Bilag", belop="Beloep")
        session.set_dataset(df, cols)
        assert session.version_type == "hb"
        # TB should still be available (not cleared)
        assert session.tb_df is tb

    def test_initial_state_is_none(self):
        import session
        session.tb_df = None
        session.version_type = None
        assert session.tb_df is None
        assert session.version_type is None


# ---------------------------------------------------------------------------
# 2. bus.emit("TB_LOADED")
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def _restore_session_and_bus():
    """Restore sys.modules['session'] and reload bus after test."""
    original_session = sys.modules.get("session")
    import bus as _bus
    yield
    if original_session is not None:
        sys.modules["session"] = original_session
    elif "session" in sys.modules:
        del sys.modules["session"]
    importlib.reload(_bus)


class TestBusTbLoaded:
    def test_tb_loaded_calls_on_tb_ready(self, _restore_session_and_bus):
        """bus.emit('TB_LOADED') should call App._on_tb_ready()."""
        fake_session = types.ModuleType("session")
        called = []

        class FakeApp:
            def _on_tb_ready(self):
                called.append("tb_ready")

        fake_session.APP = FakeApp()
        sys.modules["session"] = fake_session

        import bus
        importlib.reload(bus)

        tb = _sample_tb()
        bus.emit("TB_LOADED", tb)

        assert called == ["tb_ready"]

    def test_tb_loaded_no_app_does_not_crash(self, _restore_session_and_bus):
        """TB_LOADED with no APP set should not crash."""
        fake_session = types.ModuleType("session")
        fake_session.APP = None
        sys.modules["session"] = fake_session

        import bus
        importlib.reload(bus)

        bus.emit("TB_LOADED", _sample_tb())
        # No exception = pass

    def test_tb_loaded_app_without_on_tb_ready_does_not_crash(self, _restore_session_and_bus):
        """APP without _on_tb_ready method should not crash."""
        fake_session = types.ModuleType("session")
        fake_session.APP = SimpleNamespace()  # no _on_tb_ready
        sys.modules["session"] = fake_session

        import bus
        importlib.reload(bus)

        bus.emit("TB_LOADED", _sample_tb())
        # No exception = pass


# ---------------------------------------------------------------------------
# 3. ui_main._on_data_ready sets version_type
# ---------------------------------------------------------------------------

class TestUiMainVersionType:
    def test_on_data_ready_sets_version_type_hb(self):
        import session
        import ui_main

        session.version_type = None
        app = ui_main.create_app()
        try:
            try:
                app.withdraw()
            except Exception:
                pass

            # Make after/after_idle synchronous
            setattr(app, "after_idle", lambda fn: fn())
            setattr(app, "after", lambda _ms, fn: fn())

            df = _sample_hb_df()
            app._on_data_ready(df)

            assert session.version_type == "hb"
        finally:
            try:
                app.destroy()
            except Exception:
                pass

    def test_on_tb_ready_refreshes_consolidation(self):
        import session
        import ui_main

        session.set_tb(_sample_tb())
        app = ui_main.create_app()
        try:
            try:
                app.withdraw()
            except Exception:
                pass

            setattr(app, "after_idle", lambda fn: fn())
            setattr(app, "after", lambda _ms, fn: fn())

            refreshed = []
            setattr(
                app.page_consolidation,
                "refresh_from_session",
                lambda sess: refreshed.append("consolidation"),
            )

            app._on_tb_ready()

            assert "consolidation" in refreshed
        finally:
            try:
                app.destroy()
            except Exception:
                pass

    def test_on_tb_ready_does_not_navigate_to_consolidation(self):
        """Bruker skal bli værende på gjeldende fane etter SB-valg."""
        import session
        import ui_main

        session.set_tb(_sample_tb())
        app = ui_main.create_app()
        try:
            try:
                app.withdraw()
            except Exception:
                pass

            setattr(app, "after_idle", lambda fn: fn())
            setattr(app, "after", lambda _ms, fn: fn())

            selected = []

            class _NB:
                def select(self, tab):
                    selected.append(tab)
            app.nb = _NB()  # type: ignore[assignment]

            app._on_tb_ready()

            assert selected == [], f"Skulle ikke auto-navigere, men valgte: {selected}"
        finally:
            try:
                app.destroy()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 4. ConsolidationPage._update_session_tb_button
# ---------------------------------------------------------------------------

class TestConsolidationSessionTb:
    def test_update_session_tb_button_shows_when_tb_available(self):
        """Button should be visible when _resolve_active_client_tb returns data."""
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = None

        # Minimal stub for button
        btn = MagicMock()
        page._btn_use_session_tb = btn
        page._btn_run = MagicMock()

        # Mock _resolve_active_client_tb to return data
        page._resolve_active_client_tb = MagicMock(return_value=(_sample_tb(), "TestClient", "session"))
        page._update_session_tb_button(None)

        btn.pack.assert_called_once()
        btn.pack_forget.assert_not_called()

    def test_update_session_tb_button_hides_when_no_tb(self):
        """Button should be hidden when _resolve_active_client_tb returns None."""
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = None

        btn = MagicMock()
        page._btn_use_session_tb = btn

        page._resolve_active_client_tb = MagicMock(return_value=None)
        page._update_session_tb_button(None)

        btn.pack_forget.assert_called_once()
        btn.pack.assert_not_called()

    def test_update_session_tb_button_hides_when_already_imported(self):
        """Button should be hidden when parent is already a session company."""
        from src.pages.consolidation.frontend.page import ConsolidationPage
        from src.pages.consolidation.backend.models import CompanyTB, ConsolidationProject

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False

        proj = ConsolidationProject(
            client="Test", year="2025",
            companies=[CompanyTB(name="Foo", source_type="session")],
        )
        # Set parent_company_id to the session company
        proj.parent_company_id = proj.companies[0].company_id
        page._project = proj

        btn = MagicMock()
        page._btn_use_session_tb = btn

        page._resolve_active_client_tb = MagicMock(return_value=(_sample_tb(), "Test", "session"))
        page._update_session_tb_button(None)

        btn.pack_forget.assert_called_once()
        btn.pack.assert_not_called()

    def test_on_use_session_tb_imports_company(self, monkeypatch, tmp_path):
        """_on_use_session_tb should create a CompanyTB with source_type='session'."""
        import session as _session
        import client_store
        from src.pages.consolidation.frontend.page import ConsolidationPage
        from src.pages.consolidation.backend.models import ConsolidationProject
        from src.pages.consolidation.backend import storage

        # Setup session
        tb = _sample_tb()
        _session.set_tb(tb)
        _session.client = "TestKonsern"
        _session.year = "2025"

        # Mock storage to tmp_path
        monkeypatch.setattr(
            client_store, "years_dir",
            lambda client, year: tmp_path / client / "years" / year,
        )

        # Create page without Tk
        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = ConsolidationProject(client="TestKonsern", year="2025")
        page._company_tbs = {}
        page._mapped_tbs = {}
        page._mapping_pct = {}
        page._mapping_unmapped = {}
        page._btn_use_session_tb = MagicMock()

        # Stub out methods that need Tk
        page._compute_mapping_status = MagicMock()
        page._refresh_company_tree = MagicMock()
        page._update_status = MagicMock()
        page._select_and_show_company = MagicMock()

        # Mock simpledialog to return a name
        monkeypatch.setattr(
            "src.pages.consolidation.frontend.page.simpledialog.askstring",
            lambda *a, **kw: "Morselskap AS",
        )
        # Mock messagebox to avoid Tk requirement
        monkeypatch.setattr(
            "src.pages.consolidation.frontend.page.messagebox", MagicMock(),
        )

        page._on_use_session_tb()

        # Verify company was added
        assert len(page._project.companies) == 1
        c = page._project.companies[0]
        assert c.name == "Morselskap AS"
        assert c.source_type == "session"
        assert c.row_count == 2

        # Verify TB was stored
        assert c.company_id in page._company_tbs
        pd.testing.assert_frame_equal(page._company_tbs[c.company_id], tb)

        # Verify persisted to disk
        loaded = storage.load_company_tb("TestKonsern", "2025", c.company_id)
        assert loaded is not None
        assert len(loaded) == 2
        assert list(loaded["konto"]) == ["1000", "3000"]

        # Verify project was saved
        reloaded_proj = storage.load_project("TestKonsern", "2025")
        assert reloaded_proj is not None
        assert len(reloaded_proj.companies) == 1
        assert reloaded_proj.companies[0].source_type == "session"

    def test_on_use_session_tb_no_tb_does_not_crash(self, monkeypatch):
        """_on_use_session_tb with no session.tb_df should show info, not crash."""
        import session as _session
        from src.pages.consolidation.frontend.page import ConsolidationPage

        _session.tb_df = None
        _session.client = "Test"

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = None

        # Mock messagebox
        shown = []
        monkeypatch.setattr(
            "src.pages.consolidation.frontend.page.messagebox.showinfo",
            lambda *a, **kw: shown.append(a),
        )

        page._on_use_session_tb()

        assert len(shown) == 1
        assert "Ingen" in shown[0][1]


# ---------------------------------------------------------------------------
# 5. DatasetPane SB mode switching
# ---------------------------------------------------------------------------

class TestDatasetPaneSbMode:
    def _get_real_dp(self):
        """Create app and return real DatasetPane, or None if headless."""
        import ui_main
        app = ui_main.create_app()
        try:
            app.withdraw()
        except Exception:
            pass
        dp = app.page_dataset.dp
        if not hasattr(dp, "_source_mode"):
            # Headless stub — can't test real widget behaviour
            try:
                app.destroy()
            except Exception:
                pass
            return None, None
        return app, dp

    def test_sb_mode_sets_source_mode(self):
        """DatasetPane._source_mode should switch between 'hb' and 'sb'."""
        app, dp = self._get_real_dp()
        if dp is None:
            pytest.skip("Tk not available (headless)")
        try:
            assert dp._source_mode == "hb"

            dp.set_sb_mode(True)
            assert dp._source_mode == "sb"

            dp.set_sb_mode(False)
            assert dp._source_mode == "hb"
        finally:
            try:
                app.destroy()
            except Exception:
                pass

    def test_sb_mode_readiness_shows_tb_only(self):
        """In SB mode, readiness label should show TB-only message."""
        app, dp = self._get_real_dp()
        if dp is None:
            pytest.skip("Tk not available (headless)")
        try:
            dp.set_sb_mode(True)
            dp._update_build_readiness()
            lbl = getattr(dp, "_readiness_lbl", None)
            if lbl is not None:
                text = lbl.cget("text")
                assert "TB-only" in text or "Saldobalanse" in text
        finally:
            try:
                app.destroy()
            except Exception:
                pass

    def test_sb_mode_required_fields_are_relaxed(self):
        """In SB mode, required fields should only be Konto (not Bilag/Beloep)."""
        from src.pages.dataset.frontend.pane import _REQUIRED_HB, _REQUIRED_SB

        assert "Konto" in _REQUIRED_HB
        assert "Bilag" in _REQUIRED_HB
        assert "Beløp" in _REQUIRED_HB

        assert "Konto" in _REQUIRED_SB
        assert "Bilag" not in _REQUIRED_SB
        assert "Beløp" not in _REQUIRED_SB

    def test_sb_mode_readiness_does_not_check_combos(self):
        """In SB mode, _update_build_readiness should show 'TB-only' without checking combos."""
        app, dp = self._get_real_dp()
        if dp is None:
            pytest.skip("Tk not available (headless)")
        try:
            dp.path_var.set("")
            dp.set_sb_mode(True)
            dp._update_build_readiness()

            lbl = getattr(dp, "_readiness_lbl", None)
            if lbl is not None:
                text = lbl.cget("text")
                assert "TB-only" in text or "Saldobalanse" in text
        finally:
            try:
                app.destroy()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 6. numpy.bool_ JSON serialization safety net
# ---------------------------------------------------------------------------

class TestNumpyBoolSerialization:
    def test_save_project_with_numpy_bool(self, monkeypatch, tmp_path):
        """Project with numpy.bool_ in has_ib should save without error."""
        import numpy as np
        import client_store
        from src.pages.consolidation.backend.models import CompanyTB, ConsolidationProject
        from src.pages.consolidation.backend import storage

        monkeypatch.setattr(
            client_store, "years_dir",
            lambda client, year: tmp_path / client / "years" / year,
        )

        proj = ConsolidationProject(
            client="NumpyTest", year="2025",
            companies=[
                CompanyTB(
                    company_id="x",
                    name="TestCo",
                    has_ib=np.True_,  # numpy bool, not Python bool
                    row_count=5,
                ),
            ],
        )

        # This should NOT raise TypeError
        storage.save_project(proj)

        # Verify it round-trips
        loaded = storage.load_project("NumpyTest", "2025")
        assert loaded is not None
        assert len(loaded.companies) == 1
        assert loaded.companies[0].has_ib is True  # deserialized as Python bool
        assert loaded.companies[0].name == "TestCo"

    def test_safe_encoder_handles_numpy_types(self):
        """_SafeEncoder should handle numpy.bool_, numpy.int64, numpy.float64."""
        import json
        import numpy as np
        from src.pages.consolidation.backend.storage import _SafeEncoder

        data = {
            "bool_val": np.True_,
            "int_val": np.int64(42),
            "float_val": np.float64(3.14),
            "normal_bool": True,
            "normal_int": 7,
        }

        result = json.dumps(data, cls=_SafeEncoder)
        parsed = json.loads(result)

        assert parsed["bool_val"] is True
        assert parsed["int_val"] == 42
        assert abs(parsed["float_val"] - 3.14) < 0.001
        assert parsed["normal_bool"] is True
        assert parsed["normal_int"] == 7

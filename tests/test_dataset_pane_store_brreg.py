"""Tests for BRREG-anriket klientinfo i Datakilde-blokken."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest


class MiniVar:
    def __init__(self, value: str = "") -> None:
        self._v = value

    def get(self) -> str:
        return self._v

    def set(self, value: str) -> None:
        self._v = value


class FakeLabel:
    def __init__(self) -> None:
        self.text = ""
        self.foreground = None
        self.visible = True  # grid/grid_remove-tracking

    def configure(self, **kwargs) -> None:
        if "text" in kwargs:
            self.text = kwargs["text"]
        if "foreground" in kwargs:
            self.foreground = kwargs["foreground"]

    def grid(self, *a, **kw) -> None:
        self.visible = True

    def grid_remove(self, *a, **kw) -> None:
        self.visible = False


class FakeFrame:
    def after(self, _ms, _cb, *args):  # pragma: no cover - not used in tests
        return "after-id"


def _make_section(monkeypatch, tmp_path) -> "dataset_pane_store.ClientStoreSection":
    monkeypatch.setenv("UTVALG_DATA_DIR", str(tmp_path / "data"))
    import dataset_pane_store
    importlib.reload(dataset_pane_store)

    sec = dataset_pane_store.ClientStoreSection(
        frame=FakeFrame(),  # type: ignore[arg-type]
        client_var=MiniVar(""),
        year_var=MiniVar("2025"),
        hb_var=MiniVar(""),
        on_path_selected=lambda _p: None,
        get_current_path=lambda: "",
    )
    sec._company_labels = {  # type: ignore[attr-defined]
        "orgnr": FakeLabel(),
        "knr": FakeLabel(),
        "orgform": FakeLabel(),
        "naering": FakeLabel(),
        "mva": FakeLabel(),
        "address": FakeLabel(),
        "status": FakeLabel(),
    }
    sec._company_key_labels = {  # type: ignore[attr-defined]
        "orgnr": FakeLabel(),
        "knr": FakeLabel(),
        "orgform": FakeLabel(),
        "naering": FakeLabel(),
        "mva": FakeLabel(),
        "address": FakeLabel(),
        "status": FakeLabel(),
    }
    sec._role_labels = {  # type: ignore[attr-defined]
        "daglig_leder": FakeLabel(),
        "styreleder": FakeLabel(),
        "nestleder": FakeLabel(),
        "styremedlemmer": FakeLabel(),
        "varamedlemmer": FakeLabel(),
        "revisor": FakeLabel(),
        "regnskapsforer": FakeLabel(),
    }
    sec._team_labels = {  # type: ignore[attr-defined]
        "partner": FakeLabel(),
        "manager": FakeLabel(),
        "medarbeidere": FakeLabel(),
    }
    return sec


# ---------------------------------------------------------------------------
# Selskap-felt: org.form / næring / MVA / adresse
# ---------------------------------------------------------------------------

def test_render_brreg_labels_fills_orgform_naering_mva_address(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    enhet = {
        "organisasjonsform": "Aksjeselskap",
        "registrertIMvaregisteret": True,
        "naeringsnavn": "Utvikling av programvare",
        "forretningsadresse": "Storgata 1, 0155 Oslo",
    }
    sec._render_brreg_labels(enhet, [])

    assert sec._company_labels["orgform"].text == "Aksjeselskap"
    assert sec._company_labels["naering"].text == "Utvikling av programvare"
    assert sec._company_labels["mva"].text == "\u2713"
    assert sec._company_labels["address"].text == "Storgata 1, 0155 Oslo"


def test_render_brreg_labels_mva_dash_when_not_registered(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    enhet = {"organisasjonsform": "AS", "registrertIMvaregisteret": False}
    sec._render_brreg_labels(enhet, [])

    assert sec._company_labels["mva"].text == "\u2013"


def test_render_brreg_labels_missing_fields_show_dash(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    sec._render_brreg_labels({}, [])

    assert sec._company_labels["orgform"].text == "\u2013"
    assert sec._company_labels["naering"].text == "\u2013"
    assert sec._company_labels["mva"].text == "\u2013"
    assert sec._company_labels["address"].text == "\u2013"


# ---------------------------------------------------------------------------
# Status-rad: skjules når alt er i orden, vises ved rødt flagg
# ---------------------------------------------------------------------------

def test_status_row_hidden_when_no_flag(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    sec._render_brreg_labels({"organisasjonsform": "AS"}, [])

    assert sec._company_labels["status"].visible is False
    assert sec._company_key_labels["status"].visible is False
    assert sec._company_labels["status"].text == ""


def test_status_row_shown_on_konkurs(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    sec._render_brreg_labels({"organisasjonsform": "AS", "konkurs": True}, [])

    status = sec._company_labels["status"]
    assert status.visible is True
    assert status.text == "Konkurs"
    assert status.foreground == "#c62828"
    assert sec._company_key_labels["status"].visible is True


def test_status_row_shown_on_under_avvikling(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    sec._render_brreg_labels({"organisasjonsform": "AS", "underAvvikling": True}, [])

    status = sec._company_labels["status"]
    assert status.visible is True
    assert status.text == "Under avvikling"
    assert status.foreground == "#c62828"


def test_status_row_shown_on_slettedato(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    sec._render_brreg_labels(
        {"organisasjonsform": "AS", "slettedato": "2024-06-01"}, []
    )

    assert sec._company_labels["status"].text == "Slettet 2024-06-01"
    assert sec._company_labels["status"].visible is True


def test_status_row_re_hides_when_switching_to_healthy(monkeypatch, tmp_path):
    """Etter konkurs → aktiv klient: status-raden skal gjemmes igjen."""
    sec = _make_section(monkeypatch, tmp_path)
    sec._render_brreg_labels({"organisasjonsform": "AS", "konkurs": True}, [])
    assert sec._company_labels["status"].visible is True

    sec._render_brreg_labels({"organisasjonsform": "AS"}, [])
    assert sec._company_labels["status"].visible is False
    assert sec._company_labels["status"].text == ""


# ---------------------------------------------------------------------------
# Cache + threading
# ---------------------------------------------------------------------------

def test_update_brreg_fields_renders_from_cache(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    sec._brreg_cache["915321445"] = {
        "enhet": {
            "organisasjonsform": "Aksjeselskap",
            "registrertIMvaregisteret": True,
            "naeringsnavn": "Utvikling av programvare",
        },
        "roller": [
            {"rolle": "Daglig leder", "rolle_kode": "DAGL", "navn": "Ola Nordmann"},
            {"rolle": "Styrets leder", "rolle_kode": "LEDE", "navn": "Kari Hansen"},
        ],
    }

    called = []
    monkeypatch.setattr(
        "threading.Thread",
        lambda *a, **kw: called.append((a, kw)) or MagicMock(start=lambda: None),
    )

    sec._update_brreg_fields({"org_number": "915321445"})

    assert sec._company_labels["orgform"].text == "Aksjeselskap"
    assert sec._company_labels["mva"].text == "\u2713"
    assert sec._company_labels["naering"].text == "Utvikling av programvare"
    assert sec._role_labels["daglig_leder"].text == "Ola Nordmann"
    assert sec._role_labels["styreleder"].text == "Kari Hansen"
    assert called == []


def test_update_brreg_fields_no_orgnr_sets_dash_and_hides_status(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)

    started = []
    monkeypatch.setattr(
        "threading.Thread",
        lambda *a, **kw: started.append((a, kw)) or MagicMock(start=lambda: None),
    )

    sec._update_brreg_fields({})

    for key in ("orgform", "naering", "mva", "address"):
        assert sec._company_labels[key].text == "\u2013"
    assert sec._company_labels["status"].visible is False
    assert sec._role_labels["daglig_leder"].text == "\u2013"
    assert sec._role_labels["styreleder"].text == "\u2013"
    assert started == []


def test_update_brreg_fields_shows_laster_in_orgform_while_pending(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    monkeypatch.setattr("threading.Thread", lambda *a, **kw: MagicMock(start=lambda: None))

    sec._update_brreg_fields({"org_number": "915321445"})

    assert sec._company_labels["orgform"].text == "Laster\u2026"
    assert sec._company_labels["status"].visible is False


def test_brreg_apply_result_drops_stale_request(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    sec._brreg_request_id = 5
    sec._brreg_current_orgnr = "915321445"
    sec._company_labels["orgform"].text = "Laster\u2026"

    sec._brreg_apply_result(
        3,
        "915321445",
        {"organisasjonsform": "AS", "registrertIMvaregisteret": False},
        [],
    )

    assert sec._company_labels["orgform"].text == "Laster\u2026"  # uendret
    assert "915321445" in sec._brreg_cache  # men cachen er fylt


def test_brreg_apply_result_caches_even_on_stale(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    sec._brreg_request_id = 10
    sec._brreg_current_orgnr = "999888777"

    sec._brreg_apply_result(
        10,
        "915321445",
        {"organisasjonsform": "AS"},
        [{"rolle": "Daglig leder", "rolle_kode": "DAGL", "navn": "X"}],
    )

    assert "915321445" in sec._brreg_cache
    assert sec._brreg_cache["915321445"]["enhet"]["organisasjonsform"] == "AS"


# ---------------------------------------------------------------------------
# Roller: match på rolle_kode (ikke beskrivelse)
# ---------------------------------------------------------------------------

def test_render_brreg_labels_picks_daglig_leder_and_styreleder(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    roller = [
        {"rolle": "Styremedlem", "rolle_kode": "MEDL", "navn": "Per Person"},
        {"rolle": "Daglig leder", "rolle_kode": "DAGL", "navn": "Ola Nordmann"},
        {"rolle": "Varamedlem", "rolle_kode": "VARA", "navn": "Eva Vara"},
        {"rolle": "Styrets leder", "rolle_kode": "LEDE", "navn": "Kari Hansen"},
    ]
    sec._render_brreg_labels({"organisasjonsform": "AS"}, roller)

    assert sec._role_labels["daglig_leder"].text == "Ola Nordmann"
    assert sec._role_labels["styreleder"].text == "Kari Hansen"


def test_render_brreg_labels_styrets_leder_normalized(monkeypatch, tmp_path):
    """Regresjon: BRREG returnerer rolle='Styrets leder' (ikke 'Styreleder').

    Vi må matche på rolle_kode=LEDE, ellers faller styreleder ut.
    """
    sec = _make_section(monkeypatch, tmp_path)
    roller = [
        {"rolle": "Styrets leder", "rolle_kode": "LEDE", "navn": "Kari Hansen"},
    ]
    sec._render_brreg_labels({"organisasjonsform": "AS"}, roller)

    assert sec._role_labels["styreleder"].text == "Kari Hansen"


def test_render_brreg_labels_ignores_rolle_beskrivelse(monkeypatch, tmp_path):
    """Rolle uten rolle_kode skal IKKE plukkes (robust mot beskrivelse-endringer)."""
    sec = _make_section(monkeypatch, tmp_path)
    roller = [
        {"rolle": "Daglig leder", "navn": "Skal ikke plukkes"},
    ]
    sec._render_brreg_labels({"organisasjonsform": "AS"}, roller)

    assert sec._role_labels["daglig_leder"].text == "\u2013"


def test_render_brreg_labels_picks_revisor_and_regnskapsforer(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    roller = [
        {"rolle": "Daglig leder", "rolle_kode": "DAGL", "navn": "Ola"},
        {"rolle": "Revisor", "rolle_kode": "REVI", "navn": "BDO AS"},
        {"rolle": "Regnskapsfører", "rolle_kode": "REGN", "navn": "Azets AS"},
    ]
    sec._render_brreg_labels({"organisasjonsform": "AS"}, roller)

    assert sec._role_labels["revisor"].text == "BDO AS"
    assert sec._role_labels["regnskapsforer"].text == "Azets AS"


def test_render_brreg_labels_collects_styremedlemmer_and_varamedlemmer(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)
    roller = [
        {"rolle": "Styrets leder", "rolle_kode": "LEDE", "navn": "Kari Leder"},
        {"rolle": "Styremedlem", "rolle_kode": "MEDL", "navn": "Per Person"},
        {"rolle": "Styremedlem", "rolle_kode": "MEDL", "navn": "Anne Andersen"},
        {"rolle": "Varamedlem", "rolle_kode": "VARA", "navn": "Eva Vara"},
        {"rolle": "Nestleder", "rolle_kode": "NEST", "navn": "Nils Nest"},
    ]
    sec._render_brreg_labels({"organisasjonsform": "AS"}, roller)

    assert sec._role_labels["nestleder"].text == "Nils Nest"
    assert sec._role_labels["styremedlemmer"].text == "Per Person, Anne Andersen"
    assert sec._role_labels["varamedlemmer"].text == "Eva Vara"


# ---------------------------------------------------------------------------
# Team-labels
# ---------------------------------------------------------------------------

def test_update_team_labels_resolves_partner_initials(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)

    import team_config
    monkeypatch.setattr(team_config, "resolve_initials_to_name",
                        lambda i: "Simen Bjørndalen" if i.lower() == "sb" else "")

    sec._update_team_labels({"responsible": "sb", "manager": "Anne Manager", "team_members": ""})

    assert sec._team_labels["partner"].text == "Simen Bjørndalen (SB)"
    assert sec._team_labels["manager"].text == "Anne Manager"


def test_update_team_labels_falls_back_to_initials_when_unknown(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)

    import team_config
    monkeypatch.setattr(team_config, "resolve_initials_to_name", lambda _i: "")

    sec._update_team_labels({"responsible": "amn"})

    assert sec._team_labels["partner"].text == "AMN"


def test_update_team_labels_joins_medarbeidere(monkeypatch, tmp_path):
    sec = _make_section(monkeypatch, tmp_path)

    import team_config
    monkeypatch.setattr(team_config, "resolve_initials_to_name", lambda _i: "")

    sec._update_team_labels({
        "responsible": "",
        "manager": "",
        "team_members": "Per Person\nAnne Andersen",
    })

    assert sec._team_labels["medarbeidere"].text == "Per Person, Anne Andersen"

"""Tests for konto_klassifisering.py."""
from __future__ import annotations

import konto_klassifisering as kk


class _FakeApi:
    def __init__(self, *, loaded: dict[str, str] | None = None) -> None:
        self.loaded = dict(loaded or {})
        self.load_calls: list[dict[str, object]] = []
        self.save_calls: list[dict[str, object]] = []
        self.control_statement_calls: list[dict[str, object]] = []

    def load_mapping(self, *, client: str, getter=None, **_kwargs):
        self.load_calls.append({"client": client, "getter": getter})
        return dict(self.loaded)

    def save_mapping(
        self,
        *,
        client: str,
        mapping: dict[str, str],
        setter=None,
        getter=None,
        **_kwargs,
    ):
        cleaned = {
            str(account_no).strip(): str(group_name).strip()
            for account_no, group_name in mapping.items()
            if str(account_no).strip() and str(group_name).strip()
        }
        self.save_calls.append(
            {
                "client": client,
                "mapping": dict(cleaned),
                "setter": setter,
                "getter": getter,
            }
        )
        if setter is not None:
            setter(kk._pref_key(client), dict(cleaned))
        return None

    def build_control_statement_rows(
        self,
        *,
        client: str,
        gl_df,
        year=None,
        getter=None,
        include_unclassified: bool = False,
        **_kwargs,
    ):
        self.control_statement_calls.append(
            {
                "client": client,
                "gl_df": gl_df,
                "year": year,
                "getter": getter,
                "include_unclassified": include_unclassified,
            }
        )
        return ["ok"]


# ---------------------------------------------------------------------------
# DEFAULT_GROUPS
# ---------------------------------------------------------------------------

def test_default_groups_contains_mva() -> None:
    assert "Inngående MVA" in kk.DEFAULT_GROUPS
    assert "Utgående MVA" in kk.DEFAULT_GROUPS
    assert "Skyldig MVA" in kk.DEFAULT_GROUPS


def test_default_groups_contains_lonn() -> None:
    assert "Lønnskostnad" in kk.DEFAULT_GROUPS
    assert "Feriepenger" in kk.DEFAULT_GROUPS
    assert "Skyldig lønn" in kk.DEFAULT_GROUPS


def test_default_groups_contains_skatt_balanse() -> None:
    assert "Betalbar skatt" in kk.DEFAULT_GROUPS
    assert "Utsatt skatt" in kk.DEFAULT_GROUPS


def test_default_groups_no_duplicates() -> None:
    assert len(kk.DEFAULT_GROUPS) == len(set(kk.DEFAULT_GROUPS))


# ---------------------------------------------------------------------------
# _pref_key
# ---------------------------------------------------------------------------

def test_pref_key_safe_characters() -> None:
    key = kk._pref_key("Klient AS")
    assert " " not in key
    assert key.startswith("konto_klassifisering.")
    assert key.endswith(".mapping")


def test_pref_key_default_for_empty() -> None:
    key = kk._pref_key("")
    assert "default" in key


def test_pref_key_different_clients_differ() -> None:
    assert kk._pref_key("KlientA") != kk._pref_key("KlientB")


# ---------------------------------------------------------------------------
# load / save via profile-backed API
# ---------------------------------------------------------------------------

def test_load_returns_empty_if_no_data(monkeypatch) -> None:
    api = _FakeApi(loaded={})
    monkeypatch.setattr(kk, "_api", lambda: api)
    result = kk.load("TestKlient")
    assert result == {}
    assert api.load_calls[0]["client"] == "TestKlient"


def test_load_returns_empty_if_not_dict(monkeypatch) -> None:
    api = _FakeApi(loaded={})
    monkeypatch.setattr(kk, "_api", lambda: api)
    result = kk.load("TestKlient")
    assert result == {}


def test_load_returns_profile_backed_mapping(monkeypatch) -> None:
    api = _FakeApi(loaded={"1000": "Inngående MVA", "3000": "Skyldig MVA"})
    monkeypatch.setattr(kk, "_api", lambda: api)
    result = kk.load("TestKlient")
    assert result == {"1000": "Inngående MVA", "3000": "Skyldig MVA"}


def test_load_uses_profile_api_not_raw_preferences(monkeypatch) -> None:
    api = _FakeApi(loaded={"1000": "Gruppe A"})
    monkeypatch.setattr(kk, "_api", lambda: api)
    monkeypatch.setattr("preferences.get", lambda key: {"9999": "Stale legacy"})
    result = kk.load("KlientY")
    assert result == {"1000": "Gruppe A"}


def test_save_calls_preferences_set(monkeypatch) -> None:
    api = _FakeApi()
    monkeypatch.setattr(kk, "_api", lambda: api)
    saved: dict = {}
    monkeypatch.setattr("preferences.set", lambda key, value: saved.update({key: value}))
    kk.save("TestKlient", {"1000": "Inngående MVA", "2000": ""})
    stored = list(saved.values())[0]
    assert "1000" in stored
    assert "2000" not in stored
    assert api.save_calls[0]["mapping"] == {"1000": "Inngående MVA"}


def test_save_filters_blank_values(monkeypatch) -> None:
    api = _FakeApi()
    monkeypatch.setattr(kk, "_api", lambda: api)
    saved: dict = {}
    monkeypatch.setattr("preferences.set", lambda key, value: saved.update({key: value}))
    kk.save("KlientX", {"1000": "Gruppe A", "2000": "", "3000": "Gruppe B"})
    stored = list(saved.values())[0]
    assert len(stored) == 2
    assert stored["1000"] == "Gruppe A"
    assert stored["3000"] == "Gruppe B"


# ---------------------------------------------------------------------------
# get_group
# ---------------------------------------------------------------------------

def test_get_group_returns_gruppe() -> None:
    mapping = {"1000": "Inngående MVA"}
    assert kk.get_group(mapping, "1000") == "Inngående MVA"


def test_get_group_strips_whitespace() -> None:
    mapping = {"1000": "Skyldig MVA"}
    assert kk.get_group(mapping, " 1000 ") == "Skyldig MVA"


def test_get_group_returns_empty_for_missing() -> None:
    assert kk.get_group({}, "9999") == ""


# ---------------------------------------------------------------------------
# all_groups_in_use
# ---------------------------------------------------------------------------

def test_all_groups_in_use_sorted() -> None:
    mapping = {"1000": "Z-gruppe", "2000": "A-gruppe", "3000": "M-gruppe"}
    result = kk.all_groups_in_use(mapping)
    assert result == sorted(result)


def test_all_groups_in_use_excludes_blank() -> None:
    mapping = {"1000": "Gruppe A", "2000": ""}
    result = kk.all_groups_in_use(mapping)
    assert "" not in result
    assert "Gruppe A" in result


def test_all_groups_in_use_unique() -> None:
    mapping = {"1000": "MVA", "2000": "MVA", "3000": "Lønn"}
    result = kk.all_groups_in_use(mapping)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# kontoer_for_group
# ---------------------------------------------------------------------------

def test_kontoer_for_group_returns_matching() -> None:
    mapping = {"1000": "MVA", "2000": "Lønn", "3000": "MVA"}
    result = kk.kontoer_for_group(mapping, "MVA")
    assert set(result) == {"1000", "3000"}


def test_kontoer_for_group_sorted() -> None:
    mapping = {"3000": "MVA", "1000": "MVA", "2000": "MVA"}
    result = kk.kontoer_for_group(mapping, "MVA")
    assert result == sorted(result)


def test_kontoer_for_group_empty_for_unknown() -> None:
    mapping = {"1000": "MVA"}
    assert kk.kontoer_for_group(mapping, "Ukjent") == []


# ---------------------------------------------------------------------------
# build_group_lookup
# ---------------------------------------------------------------------------

def test_build_group_lookup_filters_to_given_kontoer() -> None:
    mapping = {"1000": "MVA", "2000": "Lønn", "3000": "MVA"}
    result = kk.build_group_lookup(mapping, ["1000", "3000"])
    assert result == {"1000": "MVA", "3000": "MVA"}


def test_build_group_lookup_excludes_unmapped() -> None:
    mapping = {"1000": "MVA"}
    result = kk.build_group_lookup(mapping, ["1000", "9999"])
    assert "9999" not in result


def test_build_group_lookup_empty_kontoer() -> None:
    mapping = {"1000": "MVA"}
    assert kk.build_group_lookup(mapping, []) == {}


# ---------------------------------------------------------------------------
# control statement bridge
# ---------------------------------------------------------------------------

def test_build_control_statement_rows_uses_profile_api(monkeypatch) -> None:
    api = _FakeApi()
    monkeypatch.setattr(kk, "_api", lambda: api)
    gl_df = object()
    result = kk.build_control_statement_rows(
        "KlientZ",
        gl_df,
        year=2025,
        include_unclassified=True,
    )
    assert result == ["ok"]
    assert api.control_statement_calls == [
        {
            "client": "KlientZ",
            "gl_df": gl_df,
            "year": 2025,
            "getter": kk.preferences.get,
            "include_unclassified": True,
        }
    ]

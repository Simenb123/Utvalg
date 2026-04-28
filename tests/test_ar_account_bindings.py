from __future__ import annotations

from src.pages.ar.backend import account_bindings


class _FakeProfile:
    def __init__(
        self,
        *,
        account_no: str = "",
        account_name: str = "",
        owned_company_orgnr: str | None = None,
    ) -> None:
        self.account_no = account_no
        self.account_name = account_name
        self.owned_company_orgnr = owned_company_orgnr


class _FakeDocument:
    def __init__(self, profiles: dict[str, _FakeProfile]) -> None:
        self.profiles = profiles


def test_account_bindings_returns_orgnr_to_accounts_map() -> None:
    profiles = {
        "1321": _FakeProfile(account_no="1321", account_name="Aksjer i GPC", owned_company_orgnr="979791739"),
        "1322": _FakeProfile(account_no="1322", account_name="Aksjer i GPC II", owned_company_orgnr="979791739"),
        "1500": _FakeProfile(account_no="1500", account_name="Kundefordringer", owned_company_orgnr=None),
    }
    fake_doc = _FakeDocument(profiles)

    bindings = account_bindings.account_bindings_for_owned(
        "ACME AS", 2025, load_document=lambda client, year: fake_doc
    )

    assert "979791739" in bindings
    accounts = bindings["979791739"]
    assert len(accounts) == 2
    # Sortert etter konto-nummer
    assert accounts[0][0] == "1321"
    assert accounts[1][0] == "1322"
    # Profil uten orgnr ikke med
    assert "1500" not in [pair[0] for pair_list in bindings.values() for pair in pair_list]


def test_account_bindings_empty_when_no_client_or_year() -> None:
    assert account_bindings.account_bindings_for_owned(None, 2025) == {}
    assert account_bindings.account_bindings_for_owned("ACME AS", None) == {}
    assert account_bindings.account_bindings_for_owned("", 2025) == {}


def test_account_bindings_handles_load_failure() -> None:
    def _failing_loader(client, year):
        raise RuntimeError("boom")
    bindings = account_bindings.account_bindings_for_owned(
        "ACME AS", 2025, load_document=_failing_loader
    )
    assert bindings == {}


def test_format_account_binding_single_account() -> None:
    bindings = {"979791739": [("1321", "Aksjer i GPC")]}
    assert account_bindings.format_account_binding("979791739", bindings) == "1321"
    # Med mellomrom og bindestreker
    assert account_bindings.format_account_binding("979 791 739", bindings) == "1321"


def test_format_account_binding_two_accounts() -> None:
    bindings = {"979791739": [("1321", "A"), ("1322", "B")]}
    assert account_bindings.format_account_binding("979791739", bindings) == "1321, 1322"


def test_format_account_binding_three_or_more_accounts() -> None:
    bindings = {"979791739": [("1321", "A"), ("1322", "B"), ("1323", "C"), ("1324", "D")]}
    out = account_bindings.format_account_binding("979791739", bindings)
    assert out == "1321, 1322 (+ 2)"


def test_format_account_binding_returns_empty_when_no_match() -> None:
    bindings = {"979791739": [("1321", "A")]}
    assert account_bindings.format_account_binding("123456789", bindings) == "—"
    assert account_bindings.format_account_binding("", bindings) == "—"
    assert account_bindings.format_account_binding(None, bindings) == "—"


def test_format_account_binding_custom_empty_token() -> None:
    bindings = {"979791739": [("1321", "A")]}
    assert account_bindings.format_account_binding(
        "123456789", bindings, empty=""
    ) == ""

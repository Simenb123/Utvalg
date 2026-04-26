from __future__ import annotations

from types import SimpleNamespace

from src.pages.scoping.frontend.page import ScopingPage, _detail_amount_line
from src.pages.scoping.backend.engine import ScopingLine


class _FakeTree:
    def __init__(self) -> None:
        self.headings: dict[str, str] = {}
        self.displaycolumns = ()
        self.columns = (
            "regnr",
            "regnskapslinje",
            "type",
            "ub",
            "ub_fjor",
            "endring",
            "endring_pct",
            "pct_pm",
            "klassifisering",
            "scoping",
            "revisjon",
            "handlinger",
        )

    def heading(self, column: str, text: str = "") -> None:
        self.headings[column] = text

    def configure(self, **kwargs) -> None:
        if "displaycolumns" in kwargs:
            self.displaycolumns = kwargs["displaycolumns"]

    def cget(self, option: str):
        if option == "displaycolumns":
            return self.displaycolumns
        raise KeyError(option)

    def __getitem__(self, key: str):
        if key == "columns":
            return self.columns
        raise KeyError(key)


class _FakePage:
    def __init__(self, year: str, lines: list[ScopingLine]) -> None:
        self._year = year
        self._result = SimpleNamespace(lines=lines)
        self._tree = _FakeTree()

    def _resolve_year_int(self):
        return ScopingPage._resolve_year_int(self)


def test_detail_amount_line_uses_ub_year_and_prior_year():
    line = ScopingLine(
        regnr="10",
        regnskapslinje="Salgsinntekt",
        amount=12_000_000,
        amount_prior=10_000_000,
        change_amount=2_000_000,
        change_pct=20.0,
    )

    text = _detail_amount_line(2025, line)

    assert "UB 2025: 12 000 000" in text
    assert "UB 2024: 10 000 000" in text
    assert "Endring: 2 000 000" in text
    assert "Endring %: +20.0%" in text


def test_configure_tree_columns_sets_year_in_headers():
    """``_configure_tree_columns`` skal sette årstall i UB- og UB-fjor-
    overskriftene. Synlighet av kolonnene styres nå av brukerens valg
    via ManagedTreeview, ikke av denne metoden."""
    page = _FakePage(
        "2025",
        [ScopingLine(regnr="10", regnskapslinje="Salgsinntekt", amount=100.0, amount_prior=90.0)],
    )

    ScopingPage._configure_tree_columns(page)

    assert page._tree.headings["ub"] == "UB 2025"
    assert page._tree.headings["ub_fjor"] == "UB 2024"


def test_configure_tree_columns_falls_back_when_year_missing():
    """Uten gyldig år skal generiske labels brukes."""
    page = _FakePage(
        None,
        [ScopingLine(regnr="10", regnskapslinje="Salgsinntekt", amount=100.0, amount_prior=None)],
    )

    ScopingPage._configure_tree_columns(page)

    assert page._tree.headings["ub"] == "UB"
    assert page._tree.headings["ub_fjor"] == "UB i fjor"

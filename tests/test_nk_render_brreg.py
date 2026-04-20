"""Tester for BRREG-integrasjon i _nk_render (Nøkkeltall-panel)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class _FakeText:
    """Minimal Text-widget-stub som samler all insert-tekst."""
    def __init__(self) -> None:
        self._buf: list[str] = []

    def configure(self, **_kw: Any) -> None:
        pass

    def delete(self, *_a: Any, **_kw: Any) -> None:
        self._buf.clear()

    def insert(self, _where: str, text: str, *_tags: Any) -> None:
        self._buf.append(str(text))

    def tag_configure(self, *_a: Any, **_kw: Any) -> None:
        pass

    @property
    def content(self) -> str:
        return "".join(self._buf)


def _mk_result(has_prev: bool = False, year: str = "2025") -> Any:
    pl = [
        {"name": "Sum driftsinntekter", "formatted": "1 000 000",
         "value": 1_000_000.0, "is_sum": True,
         "prev_formatted": "950 000" if has_prev else None,
         "change_amount": 50_000 if has_prev else None,
         "change_amount_formatted": "50 000" if has_prev else None},
        {"name": "Sum driftskostnader", "formatted": "800 000",
         "value": 800_000.0, "is_sum": True,
         "prev_formatted": "750 000" if has_prev else None,
         "change_amount": 50_000 if has_prev else None,
         "change_amount_formatted": "50 000" if has_prev else None},
    ]
    bs = [
        {"name": "Sum eiendeler", "formatted": "500 000",
         "value": 500_000.0, "is_sum": True,
         "prev_formatted": "450 000" if has_prev else None,
         "change_amount": 50_000 if has_prev else None,
         "change_amount_formatted": "50 000" if has_prev else None},
    ]
    return SimpleNamespace(
        client="Demo AS", year=year,
        kpi_cards=[],
        metrics=[],
        pl_summary=pl,
        bs_summary=bs,
        has_prev_year=has_prev,
    )


def _mk_brreg_multiyear() -> dict:
    return {
        "regnskapsaar": "2024",
        "driftsinntekter": 950_000.0,
        "driftskostnader": 780_000.0,
        "sum_eiendeler": 480_000.0,
        "linjer": {
            "driftsinntekter": 950_000.0,
            "driftskostnader": 780_000.0,
            "sum_eiendeler": 480_000.0,
        },
        "years": {
            2024: {"regnskapsaar": "2024", "driftsinntekter": 950_000.0},
            2023: {"regnskapsaar": "2023", "driftsinntekter": 900_000.0},
            2022: {"regnskapsaar": "2022", "driftsinntekter": 850_000.0},
        },
        "available_years": [2024, 2023, 2022],
    }


def test_nk_render_shows_brreg_year_in_header() -> None:
    from page_analyse_nokkeltall_render import _nk_render

    widget = _FakeText()
    _nk_render(widget, _mk_result(has_prev=False), brreg_data=_mk_brreg_multiyear())

    # Header må inneholde "BRREG 2024" (år fra available_years[0])
    assert "BRREG 2024" in widget.content


def test_nk_render_shows_both_fjor_and_brreg_when_both_present() -> None:
    """Fix av bug der 'elif has_brreg' skjulte BRREG når fjorstall var lastet."""
    from page_analyse_nokkeltall_render import _nk_render

    widget = _FakeText()
    _nk_render(widget, _mk_result(has_prev=True), brreg_data=_mk_brreg_multiyear())

    content = widget.content
    # Begge kolonneoverskrifter skal være til stede — ikke gjensidig utelukkende
    assert "Fjor" in content
    assert "BRREG 2024" in content


def test_nk_render_footer_lists_multiple_years() -> None:
    from page_analyse_nokkeltall_render import _nk_render

    widget = _FakeText()
    _nk_render(widget, _mk_result(), brreg_data=_mk_brreg_multiyear())

    # Flertall + alle år listet
    assert "regnskapsårene" in widget.content
    assert "2024" in widget.content
    assert "2023" in widget.content
    assert "2022" in widget.content


def test_nk_render_footer_singular_when_one_year() -> None:
    from page_analyse_nokkeltall_render import _nk_render

    brreg = {
        "regnskapsaar": "2024",
        "linjer": {"driftsinntekter": 950_000.0},
        "years": {2024: {"regnskapsaar": "2024"}},
        "available_years": [2024],
    }
    widget = _FakeText()
    _nk_render(widget, _mk_result(), brreg_data=brreg)

    # Entall
    assert "regnskapsåret 2024" in widget.content
    assert "regnskapsårene" not in widget.content


def test_nk_render_without_brreg_omits_brreg_column() -> None:
    """Uten brreg_data skal ingen BRREG-referanse dukke opp."""
    from page_analyse_nokkeltall_render import _nk_render

    widget = _FakeText()
    _nk_render(widget, _mk_result(has_prev=True), brreg_data=None)

    content = widget.content
    assert "BRREG" not in content

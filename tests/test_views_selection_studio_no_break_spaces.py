import pytest

from views_selection_studio_ui import no_break_spaces_in_numbers


def test_no_break_spaces_in_numbers_replaces_spaces_between_digits_only():
    # Norske tusenskiller er mellomrom. I Tk Label med wrap kan det gi linjeskift inni tallet.
    txt = "Populasjon: 3 476 | Netto: 13 851 272 | Abs: 20 821 734,42 | Forslag: 32 bilag"
    out = no_break_spaces_in_numbers(txt)

    # Spaces mellom sifre skal bli NBSP
    assert "3\u00A0476" in out
    assert "13\u00A0851\u00A0272" in out
    assert "20\u00A0821\u00A0734,42" in out

    # Space mellom siffer og bokstaver skal IKKE endres
    assert "32 bilag" in out

    # Fortsatt vanlige mellomrom rundt skilletegn/ord
    assert " | " in out

import math

from selection_studio_bilag import _format_interval_no


def test_format_interval_no_sorts_bounds_and_formats_norwegian() -> None:
    # Reversed bounds should be swapped and formatted with spaces and comma
    s = _format_interval_no(1_000_000, 250_000)
    assert s == "250 000,00 – 1 000 000,00"

    # Mixed sign: smallest (negative) first
    s2 = _format_interval_no(6255, -1054584)
    assert s2 == "-1 054 584,00 – 6 255,00"
    assert "–" in s2
    assert "," in s2
    assert "\u00A0" not in s2


def test_format_interval_no_handles_nan_and_none() -> None:
    assert _format_interval_no(None, None) == ""
    assert _format_interval_no(math.nan, math.nan) == ""

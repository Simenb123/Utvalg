import header_detection as hd


def test_detect_header_row_picks_third_row_for_gl_example():
    # Simuler en fil der rad 0-1 har "støy", og rad 2 har faktiske kolonnenavn
    rows = [
        ["", "", "", ""],  # rad 0 – tom / uinteressant
        ["Rapport generert", "", "", ""],  # rad 1 – fritekst
        ["Dato", "Bilag", "Konto", "Beløp"],  # rad 2 – typisk header
        ["01.01.2024", "1", "3000", "1000"],  # data
    ]

    idx = hd.detect_header_row(rows, max_lookahead=10)
    assert idx == 2


def test_detect_header_row_returns_none_for_empty_input():
    assert hd.detect_header_row([]) is None


def test_detect_header_row_handles_rows_with_all_numbers():
    # Her er rad 0 bare tall (dårlig header), rad 1 bedre med tekst
    rows = [
        [1, 2, 3],
        ["Dato", "Bilag", "Konto"],
        ["01.01.2024", "1", "3000"],
    ]

    idx = hd.detect_header_row(rows)
    assert idx == 1

# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import datetime

from smart_mapping import suggest_mapping_intelligent


def test_suggest_mapping_intelligent_happy_path_blank_headers():
    """Når alle headers er kol1/kol2/... skal vi fortsatt gjette riktig."""

    headers = ["kol1", "kol2", "kol3", "kol4", "kol5"]
    sample = [
        [3000, 1008577, datetime(2025, 12, 31), -20625.0, "Husleie 1. kv 2025"],
        [2710, 1008577, datetime(2025, 12, 31), 4125.0, "Inngående mva høy sats"],
        [6300, 1008582, datetime(2026, 1, 5), 87869.21, "Forretningsfør..."],
        [2400, 23274, datetime(2026, 2, 2), -4470.0, "Avregning AutoPay"],
    ]

    guess = suggest_mapping_intelligent(headers, sample)
    assert guess is not None

    assert guess.get("Konto") == "kol1"
    assert guess.get("Bilag") == "kol2"
    assert guess.get("Dato") == "kol3"
    assert guess.get("Beløp") == "kol4"
    assert guess.get("Tekst") == "kol5"


def test_suggest_mapping_intelligent_returns_none_when_no_signal():
    headers = ["kol1", "kol2", "kol3"]
    sample = [
        ["hei", "verden", "x"],
        ["foo", "bar", "baz"],
        ["a", "b", "c"],
    ]

    # Ingen date/numeric/text-signal som gjør at vi kan finne Konto/Bilag/Beløp.
    guess = suggest_mapping_intelligent(headers, sample)

    # Kan være None eller tom dict – men i vår implementasjon skal det være None.
    assert guess is None


def test_suggest_mapping_intelligent_does_not_override_header_guess():
    headers = ["Konto", "Bilag", "Dato", "Beløp", "Tekst"]
    sample = [
        [3000, 1, datetime(2025, 12, 31), 100.0, "OK"],
        [3001, 2, datetime(2025, 12, 31), 200.0, "OK"],
        [3002, 3, datetime(2025, 12, 31), 300.0, "OK"],
    ]

    guess = suggest_mapping_intelligent(headers, sample)
    assert guess is not None

    # Når alias/header-match allerede finner feltene, skal de beholdes.
    assert guess.get("Konto") == "Konto"
    assert guess.get("Bilag") == "Bilag"
    assert guess.get("Dato") == "Dato"
    assert guess.get("Beløp") == "Beløp"
    assert guess.get("Tekst") == "Tekst"


def test_suggest_mapping_intelligent_guesses_mva_and_currency_on_blank_headers():
    """Når headers er tomme, skal vi *også* kunne foreslå MVA/Valuta-felter.

    Dette er spesielt nyttig for eksporter hvor enkelte kolonneoverskrifter
    mangler (kol1/kol2/...).
    """

    headers = [f"kol{i}" for i in range(1, 12)]
    sample = [
        # Konto, Kontonavn, Bilag, Dato, Tekst, MVA kode, MVA rate, MVA beløp, Beløp, Beløp i valuta, Valuta
        [3000, "Salgsinntekter", 1008577, datetime(2025, 12, 31), "Faktura 10001 - salg av varer", 0, 0, 0.0, 1000.0, 1000.0, "NOK"],
        [2710, "Inngående mva høy sats", 1008577, datetime(2025, 12, 31), "Inngående mva på kjøp", 1, 25, 250.0, 250.0, 250.0, "NOK"],
        [6300, "Husleie", 1008582, datetime(2026, 1, 5), "Husleie januar (USD)", 14, 0, 0.0, -2500.0, -250.0, "USD"],
        [2400, "Leverandørgjeld", 23274, datetime(2026, 2, 2), "Avregning AutoPay", 0, 0, 0.0, -4470.0, -4470.0, "NOK"],
        [2400, "Leverandørgjeld", 23275, datetime(2026, 2, 3), "Avregning AutoPay 2", 0, 0, 0.0, -100.0, -100.0, "NOK"],
    ]

    guess = suggest_mapping_intelligent(headers, sample)
    assert guess is not None

    assert guess.get("Konto") == "kol1"
    assert guess.get("Kontonavn") == "kol2"
    assert guess.get("Bilag") == "kol3"
    assert guess.get("Dato") == "kol4"
    assert guess.get("Tekst") == "kol5"
    assert guess.get("MVA-kode") == "kol6"
    assert guess.get("MVA-prosent") == "kol7"
    assert guess.get("MVA-beløp") == "kol8"
    assert guess.get("Beløp") == "kol9"
    assert guess.get("Valutabeløp") == "kol10"
    assert guess.get("Valuta") == "kol11"
def test_suggest_mapping_intelligent_maps_header_mva_to_mva_kode_and_avoids_false_mva_rate():
    """Headeren 'Mva' forekommer ofte i hovedbokeksporter.

    Når den er til stede, skal vi mappe den til MVA-kode (ikke avdeling/prosjekt),
    og vi skal være konservative med å gjette MVA-prosent dersom vi ikke ser
    typiske mva-satser (12/15/25).
    """

    headers = [
        "Kontonr",
        "Kontonavn",
        "Bilagsdato",
        "Bilagsnummer",
        "Bilagsart",
        "Beskrivelse",
        "Avdeling",
        "Prosjekt",
        "Produsent",
        "Mva",
        "Avg.klasse",
        "Debet",
        "Kredit",
        "Totalt",
    ]

    sample = [
        # Konto, Kontonavn, Dato, Bilag, Bilagsart, Tekst, Avdeling, Prosjekt, Produsent, Mva, Avg.klasse, Debet, Kredit, Totalt
        [1230, "Cars", datetime(2024, 10, 17), 22319, 3, "51474 Haria AS", 0, 50, 0, 0, 1, 514000.0, 0.0, 514000.0],
        [1230, "Cars", datetime(2024, 10, 17), 22320, 3, "traded in Avensis", 0, 50, 0, 0, 1, 0.0, 225000.0, -225000.0],
        [2400, "Leverandørgjeld", datetime(2024, 10, 17), 22321, 3, "Inngående mva høy sats", 2, 0, 0, 2, 1, 0.0, 4125.0, -4125.0],
    ]

    guess = suggest_mapping_intelligent(headers, sample)
    assert guess is not None

    # Viktig: 'Mva' skal treffe MVA-kode via alias, ikke dimensjonsfeltene
    assert guess.get("MVA-kode") == "Mva"

    # Og vi skal være konservative med å gjette MVA-prosent når satser ikke er tydelige
    assert guess.get("MVA-prosent") not in ("Avdeling", "Prosjekt", "Produsent")


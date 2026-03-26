from __future__ import annotations

import pandas as pd

from series_control import (
    AUTO_FIELD_KEY,
    BILAG_FIELD_KEY,
    REFERENCE_FIELD_KEY,
    TEXT_INVOICE_FIELD_KEY,
    analyze_series,
    custom_column_field_key,
    list_series_field_options,
    pick_default_series_field,
)


def test_list_series_field_options_includes_known_and_custom_fields() -> None:
    df = pd.DataFrame(
        {
            "Bilag": ["100443", "100444"],
            "Referanse": ["443", "444"],
            "Tekst": ["Faktura nummer 443", "Faktura nummer 444"],
            "Dokumentnr": ["INV-443", "INV-444"],
            "SerieX": ["X443", "X444"],
        }
    )

    keys = [opt.key for opt in list_series_field_options(df)]
    assert AUTO_FIELD_KEY in keys
    assert REFERENCE_FIELD_KEY in keys
    assert BILAG_FIELD_KEY in keys
    assert TEXT_INVOICE_FIELD_KEY in keys
    assert custom_column_field_key("SerieX") in keys


def test_pick_default_series_field_prefers_reference_over_bilag() -> None:
    df = pd.DataFrame(
        {
            "Bilag": ["100443", "100444", "100445"],
            "Referanse": ["443", "444", "445"],
            "Tekst": [
                "Faktura nummer 443 til kunde (10059)",
                "Faktura nummer 444 til kunde (10060)",
                "Faktura nummer 445 til kunde (10061)",
            ],
        }
    )

    picked = pick_default_series_field(df)

    assert picked is not None
    assert picked.field_key == REFERENCE_FIELD_KEY


def test_pick_default_series_field_auto_ignores_custom_columns(monkeypatch) -> None:
    import series_control.analyze as analyze_mod

    df = pd.DataFrame(
        {
            "Bilag": ["100443", "100444", "100445"],
            "Referanse": ["443", "444", "445"],
            "SerieX": ["X443", "X444", "X445"],
        }
    )

    seen: list[str] = []
    real_build_series_rows = analyze_mod.build_series_rows

    def spy_build_series_rows(frame, field_key):
        seen.append(str(field_key))
        return real_build_series_rows(frame, field_key)

    monkeypatch.setattr(analyze_mod, "build_series_rows", spy_build_series_rows)

    picked = analyze_mod.pick_default_series_field(df)

    assert picked is not None
    assert picked.field_key == REFERENCE_FIELD_KEY
    assert custom_column_field_key("SerieX") not in seen


def test_analyze_series_finds_gap_and_hit_in_full_ledger() -> None:
    scope_df = pd.DataFrame(
        {
            "Bilag": ["100443", "100444", "100446"],
            "Referanse": ["443", "444", "446"],
            "Konto": ["3000", "3000", "3000"],
            "Tekst": [
                "Faktura nummer 443 til kunde",
                "Faktura nummer 444 til kunde",
                "Faktura nummer 446 til kunde",
            ],
        }
    )
    all_df = pd.DataFrame(
        {
            "Bilag": ["100443", "100444", "100445", "100446"],
            "Referanse": ["443", "444", "445", "446"],
            "Konto": ["3000", "3000", "1500", "3000"],
            "Dato": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"]),
            "Tekst": [
                "Faktura nummer 443 til kunde",
                "Faktura nummer 444 til kunde",
                "Faktura nummer 445 til kunde",
                "Faktura nummer 446 til kunde",
            ],
        }
    )

    result = analyze_series(scope_df, all_df, field_key=REFERENCE_FIELD_KEY)

    assert result.selected_field_key == REFERENCE_FIELD_KEY
    assert result.selected_family_key == "|3"
    assert result.gaps_df["number"].tolist() == [445]
    assert result.hits_df["gap_number"].tolist() == [445]
    assert result.hits_df["Konto"].tolist() == ["1500"]


def test_analyze_series_aggregates_duplicate_rows_per_number() -> None:
    scope_df = pd.DataFrame(
        {
            "Bilag": ["100466", "100466", "100467"],
            "Referanse": ["466", "466", "467"],
            "Konto": ["3000", "3000", "3000"],
            "Tekst": [
                "Faktura nummer 466 til kunde",
                "Faktura nummer 466 til kunde",
                "Faktura nummer 467 til kunde",
            ],
        }
    )

    result = analyze_series(scope_df, scope_df, field_key=REFERENCE_FIELD_KEY)

    assert result.families_df.iloc[0]["count_rows"] == 3
    assert result.families_df.iloc[0]["count_distinct"] == 2
    assert result.families_df.iloc[0]["duplicate_count"] == 1


def test_text_field_extracts_invoice_number_not_parenthesized_customer_number() -> None:
    scope_df = pd.DataFrame(
        {
            "Bilag": ["100443", "100444", "100446"],
            "Tekst": [
                "Faktura nummer 443 til Vespa.ai AS (10059)",
                "Faktura nummer 444 til Rentelligent Group AS (10060)",
                "Kreditnota nummer 446 til Rentelligent Group AS (10060)",
            ],
        }
    )

    result = analyze_series(scope_df, scope_df, field_key=TEXT_INVOICE_FIELD_KEY)

    assert result.scope_rows_df["number"].tolist() == [443, 444, 446]

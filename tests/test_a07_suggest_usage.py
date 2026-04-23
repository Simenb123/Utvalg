from __future__ import annotations

import json

import pandas as pd

from a07_feature.suggest import build_account_usage_features, suggest_mappings
from a07_feature.suggest.models import AccountUsageFeatures


def _write_rulebook(tmp_path, *, code: str, label: str, keywords: list[str]) -> str:
    path = tmp_path / "rulebook.json"
    path.write_text(
        json.dumps(
            {
                "rules": {
                    code: {
                        "label": label,
                        "keywords": keywords,
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return str(path)


def test_build_account_usage_features_extracts_counterparties_and_periodicity() -> None:
    df = pd.DataFrame(
        [
            {"Konto": "5000", "Bilag": "1", "Dato": "2025-01-31", "Beløp": 1000.0, "Tekst": "Lønn januar"},
            {"Konto": "2770", "Bilag": "1", "Dato": "2025-01-31", "Beløp": -300.0, "Tekst": "AGA januar"},
            {"Konto": "5000", "Bilag": "2", "Dato": "2025-02-28", "Beløp": 1000.0, "Tekst": "Lønn februar"},
            {"Konto": "2770", "Bilag": "2", "Dato": "2025-02-28", "Beløp": -300.0, "Tekst": "AGA februar"},
            {"Konto": "5000", "Bilag": "3", "Dato": "2025-03-31", "Beløp": 1000.0, "Tekst": "Lønn mars"},
            {"Konto": "2770", "Bilag": "3", "Dato": "2025-03-31", "Beløp": -300.0, "Tekst": "AGA mars"},
        ]
    )

    out = build_account_usage_features(df)

    usage = out["5000"]
    assert usage.posting_count == 3
    assert usage.unique_vouchers == 3
    assert usage.active_months == 3
    assert usage.monthly_regularity == 1.0
    assert usage.repeat_amount_ratio == 1.0
    assert "2770" in usage.top_counterparty_accounts
    assert "loenn" in usage.top_text_tokens


def test_suggest_mappings_uses_usage_features_for_tie_breaking(tmp_path) -> None:
    rulebook_path = _write_rulebook(
        tmp_path,
        code="customLoenn",
        label="Custom lønn",
        keywords=["lønn"],
    )
    a07_df = pd.DataFrame([{"Kode": "customLoenn", "Navn": "Custom lønn", "Belop": 1000.0}])
    gl_df = pd.DataFrame(
        [
            {"Konto": "4100", "Navn": "Diverse kostnad", "Endring": 1000.0},
            {"Konto": "4200", "Navn": "Diverse kostnad", "Endring": 1000.0},
        ]
    )
    usage_features = {
        "4100": AccountUsageFeatures(
            posting_count=12,
            unique_vouchers=12,
            active_months=12,
            monthly_regularity=1.0,
            repeat_amount_ratio=0.9,
            top_text_tokens=("loenn", "ansatt"),
            top_counterparty_accounts=("2770",),
            top_counterparty_prefixes=("27",),
        ),
        "4200": AccountUsageFeatures(),
    }

    out = suggest_mappings(
        a07_codes_df=a07_df,
        gl_df=gl_df,
        basis="Endring",
        rulebook_path=rulebook_path,
        usage_features=usage_features,
    )

    assert not out.empty
    assert out.iloc[0]["ForslagKontoer"] == "4100"
    assert "bruk=" in str(out.iloc[0]["Explain"])


def test_suggest_mappings_uses_monthly_df_as_usage_fallback(tmp_path) -> None:
    rulebook_path = _write_rulebook(
        tmp_path,
        code="customLoenn",
        label="Custom lønn",
        keywords=["lønn"],
    )
    a07_df = pd.DataFrame([{"Kode": "customLoenn", "Navn": "Custom lønn", "Belop": 1000.0}])
    gl_df = pd.DataFrame(
        [
            {"Konto": "4100", "Navn": "Diverse kostnad", "Endring": 1000.0},
            {"Konto": "4200", "Navn": "Diverse kostnad", "Endring": 1000.0},
        ]
    )
    monthly_df = pd.DataFrame(
        [
            {"Konto": "4100", "Bilag": "1", "Dato": "2025-01-31", "Beløp": 1000.0, "Tekst": "Lønn januar"},
            {"Konto": "4100", "Bilag": "2", "Dato": "2025-02-28", "Beløp": 1000.0, "Tekst": "Lønn februar"},
            {"Konto": "4200", "Bilag": "3", "Dato": "2025-01-31", "Beløp": 1000.0, "Tekst": "Diverse"},
        ]
    )

    out = suggest_mappings(
        a07_codes_df=a07_df,
        gl_df=gl_df,
        basis="Endring",
        rulebook_path=rulebook_path,
        monthly_df=monthly_df,
    )

    assert not out.empty
    assert out.iloc[0]["ForslagKontoer"] == "4100"


def test_default_rulebook_supports_feriepenger_with_special_add() -> None:
    a07_df = pd.DataFrame([{"Kode": "feriepenger", "Navn": "Feriepenger", "Belop": 547527.28}])
    gl_df = pd.DataFrame(
        [
            {"Konto": "5092", "Navn": "Feriepenger", "UB": 629890.90, "Endring": 629890.90},
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "UB": -629890.90, "Endring": -82363.62},
            {"Konto": "5200", "Navn": "Fri bil", "UB": 466317.48, "Endring": 466317.48},
        ]
    )

    out = suggest_mappings(a07_codes_df=a07_df, gl_df=gl_df)

    assert not out.empty
    best = out.iloc[0]
    assert best["ForslagKontoer"] == "5092,2940"
    assert bool(best["WithinTolerance"]) is True
    assert "special_add" in str(best["Explain"])


def test_default_rulebook_matches_feriepenger_balance_accrual_range() -> None:
    a07_df = pd.DataFrame([{"Kode": "feriepenger", "Navn": "Feriepenger", "Belop": 862608.92}])
    gl_df = pd.DataFrame(
        [
            {"Konto": "5020", "Navn": "Feriepenger", "UB": 866816.10, "Endring": 866816.10},
            {"Konto": "5096", "Navn": "Periodisering av feriepenger", "UB": 6861.97, "Endring": 6861.97},
            {"Konto": "2932", "Navn": "Feriepenger mer tid", "UB": -17712.97, "Endring": -6861.97},
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "UB": -747698.87, "Endring": -4207.18},
        ]
    )

    out = suggest_mappings(
        a07_codes_df=a07_df,
        gl_df=gl_df,
        mapping={"5020": "feriepenger", "5096": "feriepenger"},
        tolerance_abs=1.0,
        tolerance_rel=0.001,
    )

    assert not out.empty
    best = out.iloc[0]
    assert best["ForslagKontoer"] == "2932,2940"
    assert abs(float(best["GL_Sum"]) - 862608.92) <= 0.01
    assert abs(float(best["Diff"])) <= 0.01
    assert bool(best["WithinTolerance"]) is True
    assert bool(best["UsedSpecialAdd"]) is True


def test_default_rulebook_keeps_special_add_suggestion_when_current_mapping_is_inside_tolerance() -> None:
    a07_df = pd.DataFrame([{"Kode": "feriepenger", "Navn": "Feriepenger", "Belop": 862608.92}])
    gl_df = pd.DataFrame(
        [
            {"Konto": "2930", "Navn": "Skyldig loenn", "UB": -136299.73, "Endring": -45709.73},
            {"Konto": "2932", "Navn": "Feriepenger mertid", "UB": -17712.97, "Endring": -6861.97},
            {"Konto": "2940", "Navn": "Skyldig feriepenger", "UB": -747698.87, "Endring": -4207.18},
            {"Konto": "2960", "Navn": "Annen palopt kostnad", "UB": -295473.0, "Endring": -295473.0},
            {"Konto": "5020", "Navn": "Feriepenger", "UB": 866816.10, "Endring": 866816.10},
            {"Konto": "5096", "Navn": "Periodisering av feriepenger", "UB": 6861.97, "Endring": 6861.97},
        ]
    )

    out = suggest_mappings(
        a07_codes_df=a07_df,
        gl_df=gl_df,
        mapping={"5020": "feriepenger", "5096": "feriepenger"},
    )

    assert not out.empty
    best = out.iloc[0]
    assert best["ForslagKontoer"] == "2932,2940"
    assert abs(float(best["GL_Sum"]) - 862608.92) <= 0.01
    assert abs(float(best["Diff"])) <= 0.01
    assert bool(best["WithinTolerance"]) is True
    assert bool(best["UsedSpecialAdd"]) is True


def test_default_rulebook_matches_styrehonorar_balance_accrual_range() -> None:
    a07_df = pd.DataFrame(
        [
            {
                "Kode": "styrehonorarOgGodtgjoerelseVerv",
                "Navn": "Styrehonorar og godtgjorelse verv",
                "Belop": 110000.0,
            }
        ]
    )
    gl_df = pd.DataFrame(
        [
            {
                "Konto": "5330",
                "Navn": "Godtgjorelse til styre- og bedriftsforsamling",
                "UB": 60000.0,
                "Endring": 60000.0,
            },
            {
                "Konto": "2977",
                "Navn": "Avsetning Styrehonorar",
                "IB": -50000.0,
                "UB": 0.0,
                "Endring": 50000.0,
            },
            {
                "Konto": "2983",
                "Navn": "Avsetning fastprisprosjekter",
                "IB": -350000.0,
                "UB": -350000.0,
                "Endring": 0.0,
            },
        ]
    )

    out = suggest_mappings(
        a07_codes_df=a07_df,
        gl_df=gl_df,
        mapping={"5330": "styrehonorarOgGodtgjoerelseVerv"},
        tolerance_abs=1.0,
        tolerance_rel=0.001,
    )

    assert not out.empty
    best = out.iloc[0]
    assert best["ForslagKontoer"] == "2977"
    assert abs(float(best["GL_Sum"]) - 110000.0) <= 0.01
    assert abs(float(best["Diff"])) <= 0.01
    assert bool(best["WithinTolerance"]) is True
    assert bool(best["UsedSpecialAdd"]) is True
    assert "2983" not in ",".join(out["ForslagKontoer"].astype(str).tolist())


def test_default_rulebook_keeps_revision_fee_out_of_car_codes() -> None:
    a07_df = pd.DataFrame(
        [{"Kode": "yrkebilTjenstligbehovListepris", "Navn": "Yrkebil tjenstlig behov listepris", "Belop": 466317.48}]
    )
    gl_df = pd.DataFrame(
        [
            {"Konto": "5200", "Navn": "Fri bil", "UB": 466317.48, "Endring": 466317.48},
            {"Konto": "6705", "Navn": "Revisjonshonorar", "UB": 180000.0, "Endring": 180000.0},
        ]
    )

    out = suggest_mappings(a07_codes_df=a07_df, gl_df=gl_df)

    assert not out.empty
    assert out.iloc[0]["ForslagKontoer"] == "5200"
    assert "6705" not in ",".join(out["ForslagKontoer"].astype(str).tolist())


def test_custom_rulebook_uses_explicit_rule_keywords_for_bil_name_match(tmp_path) -> None:
    rulebook_path = _write_rulebook(
        tmp_path,
        code="bil",
        label="Bil",
        keywords=["firmabil"],
    )
    a07_df = pd.DataFrame([{"Kode": "bil", "Navn": "Bil", "Belop": 1000.0}])
    gl_df = pd.DataFrame(
        [
            {"Konto": "5202", "Navn": "Diverse kostnad", "Endring": 1000.0},
            {"Konto": "5201", "Navn": "Firmabil", "Endring": 1000.0},
        ]
    )

    out = suggest_mappings(
        a07_codes_df=a07_df,
        gl_df=gl_df,
        basis="Endring",
        rulebook_path=rulebook_path,
    )

    assert not out.empty
    assert out.iloc[0]["ForslagKontoer"] == "5201"

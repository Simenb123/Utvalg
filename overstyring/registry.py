from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

import pandas as pd

from .checks_amounts import large_vouchers, round_amount_vouchers
from .checks_duplicates import duplicate_lines_vouchers
from .checks_risk import override_risk_vouchers
from .core import CheckResult


@dataclass(frozen=True)
class ParamSpec:
    """
    Beskriver et parameter som kan vises i UI.

    kind:
      - "float"
      - "int"
      - "bool"
      - "text"
      - "csv_accounts"  (kommaseparert tekst)
      - "csv_keywords"  (kommaseparert tekst)
    """

    key: str
    label: str
    kind: str
    default: Any
    help: str = ""


CheckRunner = Callable[[pd.DataFrame, Any | None, dict[str, Any], dict[str, CheckResult] | None], CheckResult]


@dataclass(frozen=True)
class CheckSpec:
    id: str
    title: str
    runner: CheckRunner
    params: Sequence[ParamSpec]


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    return s in {"1", "true", "t", "yes", "y", "ja", "on"}


def get_override_check_specs() -> list[CheckSpec]:
    """
    Returnerer en liste av tilgjengelige kontroller.

    Dette er bevisst en "registry" og ikke hardkodet i UI, slik at det er lett å legge til nye kontroller.
    """
    return [
        CheckSpec(
            id="large_vouchers",
            title="Store bilag",
            runner=lambda df_all, cols, params, _prev: large_vouchers(
                df_all,
                cols=cols,
                threshold=float(params.get("threshold", 1_500_000.0)),
                top_n=int(params.get("top_n", 200)),
                include_only_accounts=_split_csv(params.get("include_only_accounts")),
                exclude_accounts=_split_csv(params.get("exclude_accounts")),
            ),
            params=[
                ParamSpec("threshold", "Terskel (abs netto)", "float", 1_500_000.0, "Bilag med netto over terskel flagges."),
                ParamSpec("top_n", "Maks antall bilag", "int", 200, "Begrens antall i listen (sortert på størrelse)."),
                ParamSpec("include_only_accounts", "Kun kontoer (CSV)", "csv_accounts", "", "Valgfritt. Eksempel: 2400, 2710"),
                ParamSpec("exclude_accounts", "Ekskluder kontoer (CSV)", "csv_accounts", "", "Valgfritt. Eks: 1500"),
            ],
        ),
        CheckSpec(
            id="round_amounts",
            title="Runde beløp",
            runner=lambda df_all, cols, params, _prev: round_amount_vouchers(
                df_all,
                cols=cols,
                round_base=float(params.get("round_base", 10_000.0)),
                require_zero_cents=_to_bool(params.get("require_zero_cents", True)),
                min_netto_abs=float(params.get("min_netto_abs", 0.0)),
                top_n=int(params.get("top_n", 200)),
            ),
            params=[
                # Default som heltall (vises penere i UI enn "10000.0")
                ParamSpec(
                    "round_base",
                    "Rundhetsbase",
                    "float",
                    10_000,
                    "Eksempler: 10 000, 50 000, 100 000, 1 000 000. Sjekker base, base/10 og base/100.",
                ),
                ParamSpec("min_netto_abs", "Min netto (abs)", "float", 0, "Filtrer bort bilag med abs(netto) under terskel."),
                ParamSpec("require_zero_cents", "Krev 0 øre", "bool", True, "Kun beløp uten desimaler (0 øre)."),
                ParamSpec("top_n", "Maks antall bilag", "int", 200, "Begrens antall bilag som vises."),
            ],
        ),
        CheckSpec(
            id="risk_vouchers",
            title="Risiko-bilag",
            runner=lambda df_all, cols, params, _prev: override_risk_vouchers(
                df_all,
                cols=cols,
                keywords_csv=str(params.get("keywords_csv", "")) or None,
                min_score=float(params.get("min_score", 1.5)),
                min_abs_amount=float(params.get("min_abs_amount", 100_000.0)),
                rare_account_max_bilag=int(params.get("rare_account_max_bilag", 3)),
                rare_account_min_line_abs=float(params.get("rare_account_min_line_abs", 100_000.0)),
                exclude_accounts=_split_csv(params.get("exclude_accounts")),
            ),
            params=[
                ParamSpec("keywords_csv", "Nøkkelord (CSV)", "csv_keywords", "kontant, cash, private, lån, loan, mellomværende, korrigering", "Ord som gir økt risiko når de finnes i tekst."),
                ParamSpec("min_score", "Min score", "float", 1.5, "Bilag må ha minst denne risikoscoren."),
                ParamSpec("min_abs_amount", "Min abs beløp", "float", 100_000.0, "Bilag må ha abs(netto) over dette beløpet."),
                ParamSpec("rare_account_max_bilag", "Sjeldne kontoer: max bilag", "int", 3, "Kontoer brukt i få bilag regnes som sjeldne."),
                ParamSpec("rare_account_min_line_abs", "Sjeldne kontoer: min linje abs", "float", 100_000.0, "Kun store linjer teller for dette signalet."),
                ParamSpec("exclude_accounts", "Ekskluder kontoer (CSV)", "csv_accounts", "", "Fjerner bilag som inneholder disse kontoene."),
            ],
        ),
        CheckSpec(
            id="duplicate_lines",
            title="Dupliserte linjer",
            runner=lambda df_all, cols, params, _prev: duplicate_lines_vouchers(
                df_all,
                cols=cols,
                min_count=int(params.get("min_count", 2)),
                include_only_same_sign=_to_bool(params.get("include_only_same_sign", True)),
            ),
            params=[
                ParamSpec("min_count", "Min antall like linjer", "int", 2, "Hvor mange like linjer som må finnes i bilaget."),
                ParamSpec("include_only_same_sign", "Krev samme fortegn", "bool", True, "Hvis False: +100 og -100 regnes som likt."),
            ],
        ),
    ]


def _split_csv(v: Any) -> list[str]:
    if v is None:
        return []
    s = str(v).strip()
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def run_override_check_by_id(
    check_id: str,
    df_all: pd.DataFrame,
    cols: Any | None = None,
    params: dict[str, Any] | None = None,
    prev_results: dict[str, CheckResult] | None = None,
) -> CheckResult:
    specs = {s.id: s for s in get_override_check_specs()}
    if check_id not in specs:
        raise KeyError(f"Ukjent overstyrings-kontroll: {check_id}")

    spec = specs[check_id]
    return spec.runner(df_all, cols, params or {}, prev_results or {})

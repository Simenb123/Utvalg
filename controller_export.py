"""
controller_export.py

Eksport til Excel.

Denne modulen brukes både av GUI og tester. Historisk har flere deler av
kodebasen importert ``export_to_excel`` direkte fra ``controller_export``.
Under en refaktorering ble eksport-logikken flyttet til en controller-mixin,
men importen i GUI/tester ble ikke oppdatert.

For å unngå at hele applikasjonen stopper under import (og dermed at pytest
feiler under *collection*), tilbyr vi derfor en bakoverkompatibel
toppnivå-funksjon: ``export_to_excel(...)``.

Samtidig beholder vi eksisterende funksjonalitet:
- DataControllerExport.export_scope_excel(...) for scope-eksport
- enkel "polish" av ark (hvis tilgjengelig)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Set, Tuple

import pandas as pd

# analyzers er en intern "facade" som brukes ved scope-eksport
import analyzers  # type: ignore


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Robust import av ScopeConfig (slik at modulen fortsatt kan importeres i tester
# selv om ScopeConfig mangler midlertidig under refaktorering).
# ---------------------------------------------------------------------------
try:
    from models import ScopeConfig  # type: ignore
except Exception:  # pragma: no cover
    @dataclass
    class ScopeConfig:  # type: ignore
        """Fallback for import-robusthet. Riktig ScopeConfig skal ligge i models.py."""
        pop_accounts: Set[int] = field(default_factory=set)
        underpops: Dict[str, Set[int]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Robust import av sheet-polish.
# Tidligere het funksjonen f.eks. polish_excel_writer(...) – nå forventes
# polish_sheet(ws). Vi gjør det best-effort.
# ---------------------------------------------------------------------------
try:
    from excel_formatting import polish_sheet  # type: ignore
except Exception:  # pragma: no cover
    polish_sheet = None  # type: ignore


def _maybe_polish_sheet(ws: Any) -> None:
    """Kjør sheet-formattering hvis tilgjengelig. Best-effort (skal ikke krasje)."""
    try:
        if callable(polish_sheet):
            polish_sheet(ws)
    except Exception as e:  # pragma: no cover
        logger.debug("polish_sheet feilet (ignoreres): %s", e)


def _sheet(name: str) -> str:
    """Excel-kompatibelt ark-navn (maks 31 tegn, uten : \\ / ? * [ ])."""
    name = re.sub(r"[:\\/?*\[\]]", "_", str(name)).strip()
    return name[:31] if len(name) > 31 else name


# ---------------------------------------------------------------------------
# Backwards compatible API (for GUI + tester)
# ---------------------------------------------------------------------------
def export_to_excel(path: str | Path, *args: Any, **kwargs: Any) -> str:
    """
    Eksporter en eller flere pandas DataFrames til en Excel-fil.

    Støttede kall (for kompatibilitet med eldre GUI-kode):
      - export_to_excel(path, df)
      - export_to_excel(path, strata_df, sample_df)
      - export_to_excel(path, {"Ark1": df1, "Ark2": df2})
      - export_to_excel(path, sheets={"Ark": df})

    Returnerer path som str.
    """
    out_path = Path(path)

    # Tillat Path uten suffix – men ikke tving suffix (GUI kan allerede gi .xlsx)
    if out_path.suffix == "":
        # vi legger på .xlsx for å være hjelpsom (lav risiko)
        out_path = out_path.with_suffix(".xlsx")

    # 1) Plukk ut "sheets" fra kwargs eller mapping-argument
    sheets: Optional[Dict[str, pd.DataFrame]] = None

    if "sheets" in kwargs and kwargs["sheets"] is not None:
        maybe = kwargs.pop("sheets")
        if isinstance(maybe, Mapping):
            sheets = dict(maybe)  # type: ignore[arg-type]

    if sheets is None and len(args) >= 1 and isinstance(args[0], Mapping):
        sheets = dict(args[0])  # type: ignore[arg-type]
        args = args[1:]

    # 2) Støtt named-args for df/strata/sample
    if sheets is None:
        df = (
            kwargs.pop("df", None)
            or kwargs.pop("dataframe", None)
            or kwargs.pop("data", None)
        )
        strata_df = kwargs.pop("strata_df", None) or kwargs.pop("strata", None)
        sample_df = (
            kwargs.pop("sample_df", None)
            or kwargs.pop("sample", None)
            or kwargs.pop("utvalg_df", None)
        )

        if df is not None and isinstance(df, pd.DataFrame):
            sheets = {"Data": df}
        elif isinstance(strata_df, pd.DataFrame) and isinstance(sample_df, pd.DataFrame):
            sheets = {"Grupper": strata_df, "Utvalg": sample_df}

    # 3) Støtt posisjonelle DataFrame-argumenter
    if sheets is None:
        if len(args) == 1 and isinstance(args[0], pd.DataFrame):
            sheets = {"Data": args[0]}
        elif len(args) == 2 and isinstance(args[0], pd.DataFrame) and isinstance(args[1], pd.DataFrame):
            sheets = {"Grupper": args[0], "Utvalg": args[1]}

    if sheets is None:
        raise ValueError(
            "export_to_excel: Ugyldige argumenter. "
            "Bruk df, (strata_df, sample_df) eller sheets={...}."
        )

    # 4) Skriv excel
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        for sheet_name, df in sheets.items():
            if df is None:
                continue
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)
            df.to_excel(xw, sheet_name=_sheet(sheet_name), index=False)

        # Best-effort polish
        try:
            wb = xw.book
            for nm in wb.sheetnames:
                _maybe_polish_sheet(wb[nm])
        except Exception as e:  # pragma: no cover
            logger.debug("Polish av workbook feilet (ignoreres): %s", e)

    return str(out_path)


# ---------------------------------------------------------------------------
# Existing mixin: scope export (unchanged behaviour)
# ---------------------------------------------------------------------------
class DataControllerExport:
    """Controller-mixin for eksportrelaterte funksjoner."""

    def export_scope_excel(self, scope: ScopeConfig, path: str | Path) -> str:
        """
        Eksporter scope (populasjon + underpop) til Excel.

        Forventet at controller har:
          - self.df (hoveddataframe)
          - self.scope.get_scope_data(...) som returnerer df for gitt kontoliste
        """
        path = str(path)

        # Scope-data for populasjon og underpop
        pop_scope = self.scope.get_scope_data(scope.pop_accounts)
        underpop_scopes = {
            name: self.scope.get_scope_data(accs)
            for name, accs in scope.underpops.items()
        }

        # Analyser (best-effort: manglende felt => hopp over)
        def safe_analyze(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
            try:
                return analyzers.run_all(df)
            except Exception as e:
                logger.debug("Analyser feilet for scope-eksport (ignoreres): %s", e)
                return {}

        pop_analysis = safe_analyze(pop_scope)

        underpop_analysis = {
            name: safe_analyze(df) for name, df in underpop_scopes.items()
        }

        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            # Populasjon
            pop_scope.to_excel(xw, sheet_name=_sheet("Populasjon"), index=False)
            for sheet_name, adf in pop_analysis.items():
                adf.to_excel(xw, sheet_name=_sheet(f"Pop_{sheet_name}"), index=False)

            # Underpopulasjoner
            for name, df in underpop_scopes.items():
                df.to_excel(xw, sheet_name=_sheet(f"Underpop_{name}"), index=False)
                for sheet_name, adf in underpop_analysis[name].items():
                    adf.to_excel(
                        xw, sheet_name=_sheet(f"{name}_{sheet_name}"), index=False
                    )

            # Best-effort polish
            try:
                wb = xw.book
                for nm in wb.sheetnames:
                    _maybe_polish_sheet(wb[nm])
            except Exception as e:  # pragma: no cover
                logger.debug("Polish av workbook feilet (ignoreres): %s", e)

        return path

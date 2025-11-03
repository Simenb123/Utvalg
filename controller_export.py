"""
controller_export.py
--------------------
Eksporter scope (populasjon + underpop) til Excel.
Etter skriving kjører vi enkel formatering (norsk tallformat, kolonnebredder,
og fargekart på enkelte analysetabber).
"""

from __future__ import annotations
from typing import Any, Dict, List, Set, Tuple
import re
import pandas as pd

from models import ScopeConfig
import analyzers  # façade
from excel_formatting import polish_sheet


def _sheet(name: str) -> str:
    """Excel‑kompatibelt ark‑navn (maks 31 tegn, uten : \ / ? * [ ])."""
    name = re.sub(r"[:\\/\?\*\[\]]", "_", str(name))
    return name[:31] if len(name) > 31 else name


class DataControllerExport:
    """Mixin som forventer compute_population/compute_subpopulation fra core, og 'cols' i self."""

    def export_scope_excel(
        self,
        path: str,
        population_cfg: ScopeConfig,
        sub_cfgs: List[ScopeConfig],
        analysis_cfg: Any | None = None,
    ) -> str:
        # Beregn populasjon
        pres = self.compute_population(population_cfg)  # type: ignore[attr-defined]
        if not pres.get("ok"):
            raise RuntimeError("Ingen data i populasjon.")
        pop_df = pres["df_population"]; pop_out = pres["df_scoped_out"]

        # Underpopulasjoner
        sub_results: List[Dict[str, Any]] = []
        union_idx: Set[int] = set()
        for cfg in sub_cfgs:
            r = self.compute_subpopulation(cfg)  # type: ignore[attr-defined]
            sub_results.append(r)
            if r.get("df_kept") is not None and not r["df_kept"].empty:
                union_idx.update(r["df_kept"].index.tolist())

        union_df = pop_df.loc[sorted(list(union_idx))] if union_idx else pop_df.iloc[0:0]
        rest_df = pop_df.loc[~pop_df.index.isin(union_df.index)] if not pop_df.empty else pop_df

        # Oppsummering
        c = self.cols  # type: ignore[attr-defined]
        def S(dfx: pd.DataFrame) -> Tuple[int, int, float, float]:
            if dfx is None or dfx.empty:
                return (0, 0, 0.0, 0.0)
            s = dfx[c.belop].astype(float)
            return (len(dfx), dfx[c.bilag].astype(str).nunique(), float(s.sum()), float(s.abs().sum()))

        rows = []
        rows.append(["Populasjon", "Beholdt", *S(pop_df)])
        rows.append(["Populasjon", "Scoped out", *S(pop_out)])
        for r in sub_results:
            rows.append([f"Underpop: {r['name']}", "Beholdt", *S(r["df_kept"])])
            rows.append([f"Underpop: {r['name']}", "Scoped out", *S(r["df_scoped_out"])])
        rows.append(["Union (underpop beholdt)", "Beholdt", *S(union_df)])
        rows.append(["Rest i populasjon", "Beholdt", *S(rest_df)])
        oppsummer = pd.DataFrame(rows, columns=["Navn", "Type", "Linjer", "Bilag (unik)", "Sum netto", "Sum |beløp|"])

        # Skriv
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            # datasider
            oppsummer.to_excel(xw, _sheet("Oppsummering"), index=False)
            pop_df.to_excel(xw, _sheet("Populasjon (beholdt)"), index=False)
            pop_out.to_excel(xw, _sheet("Populasjon (scoped out)"), index=False)
            for r in sub_results:
                nm = str(r["name"]).strip() or "Underpop"
                r["df_kept"].to_excel(xw, _sheet(f"UP {nm} (beholdt)"), index=False)
                r["df_scoped_out"].to_excel(xw, _sheet(f"UP {nm} (scoped out)"), index=False)

            union_df.to_excel(xw, _sheet("Union (beholdt)"), index=False)
            rest_df.to_excel(xw, _sheet("Rest i populasjon"), index=False)

            # analyser
            if analysis_cfg is not None:
                if getattr(analysis_cfg, "include_duplicates_doc_account", False):
                    analyzers.duplicates_doc_account(pop_df, c).to_excel(xw, _sheet("Analyse – dupl. dok+konto"), index=False)
                if getattr(analysis_cfg, "include_round_amounts", False):
                    analyzers.round_amounts(pop_df, c, getattr(analysis_cfg, "round_bases", (1000,500,100)),
                                            getattr(analysis_cfg, "round_tolerance", 0.0)).to_excel(xw, _sheet("Analyse – runde beløp"), index=False)
                if getattr(analysis_cfg, "include_out_of_period", False):
                    last = getattr(self, "last_population_cfg", None)  # type: ignore[attr-defined]
                    analyzers.out_of_period(pop_df, c, getattr(last, "date_from", None), getattr(last, "date_to", None))\
                        .to_excel(xw, _sheet("Analyse – utenfor periode"), index=False)
                if getattr(analysis_cfg, "include_outliers", False):
                    analyzers.outliers_by_group(pop_df, c,
                                                method=getattr(analysis_cfg, "outlier_method", "MAD"),
                                                threshold=getattr(analysis_cfg, "outlier_threshold", 3.5),
                                                group_by=getattr(analysis_cfg, "outlier_group_by", "Konto"),
                                                min_group=getattr(analysis_cfg, "outlier_min_group_size", 20),
                                                basis=getattr(analysis_cfg, "outlier_basis", "abs"))\
                        .to_excel(xw, _sheet("Analyse – outliers"), index=False)
                if getattr(analysis_cfg, "include_round_share_by_group", False):
                    analyzers.round_share_by_group(pop_df, c,
                                                   group_by=getattr(analysis_cfg, "round_share_group_by", "Konto"),
                                                   bases=getattr(analysis_cfg, "round_bases", (1000,500,100)),
                                                   tol=getattr(analysis_cfg, "round_tolerance", 0.0),
                                                   threshold=getattr(analysis_cfg, "round_share_threshold", 0.30),
                                                   min_rows=getattr(analysis_cfg, "round_share_min_rows", 20))\
                        .to_excel(xw, _sheet("Analyse – runde andel"), index=False)

            # --- polish alle ark vi har skrevet ---
            wb = xw.book
            for nm in list(wb.sheetnames):
                ws = wb[nm]
                polish_sheet(ws)

        return path

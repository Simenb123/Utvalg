# controller_scope.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional

import pandas as pd

from models import Columns
from scope import ScopeRule, parse_accounts


@dataclass
class ScopeResult:
    population_df: pd.DataFrame
    population_stats: Dict[str, Any]
    sub_dfs: List[Tuple[ScopeRule, pd.DataFrame, Dict[str, Any]]]
    rest_df: pd.DataFrame
    rest_stats: Dict[str, Any]


class ScopeController:
    def __init__(self):
        self.cols = Columns()
        self.df: Optional[pd.DataFrame] = None
        self._population = ScopeRule("Populasjon")
        self._subs: List[ScopeRule] = []

    def set_dataset(self, df: pd.DataFrame, cols: Columns) -> None:
        self.df = df.copy()
        self.cols = cols

    def set_population(self, rule: ScopeRule) -> None:
        self._population = rule.normalized()

    def set_subpopulations(self, rules: List[ScopeRule]) -> None:
        self._subs = [r.normalized() for r in rules]

    # ---- helpers ----
    def _apply_rule_mask(self, rule: ScopeRule) -> pd.Series:
        assert self.df is not None
        c = self.cols
        df = self.df

        mask = pd.Series(True, index=df.index)

        # konto(er)
        if c.konto in df.columns and rule.accounts_spec.strip():
            existing = df[c.konto].dropna().astype("Int64").astype(int).unique().tolist()
            acc = parse_accounts(rule.accounts_spec, existing)
            mask &= df[c.konto].astype("Int64").astype(int).isin(acc) if acc else False

        # retning
        if rule.direction == "Debet":
            mask &= df[c.belop] > 0
        elif rule.direction == "Kredit":
            mask &= df[c.belop] < 0

        # beløp
        if (rule.min_amount is not None) or (rule.max_amount is not None):
            s = df[c.belop].abs() if rule.basis == "abs" else df[c.belop]
            if rule.min_amount is not None:
                mask &= s >= float(rule.min_amount)
            if rule.max_amount is not None:
                mask &= s <= float(rule.max_amount)

        # periode
        if self.cols.dato and (self.cols.dato in df.columns) and (rule.date_from or rule.date_to):
            d = pd.to_datetime(df[self.cols.dato], errors="coerce", dayfirst=True)
            if rule.date_from is not None:
                mask &= d >= rule.date_from
            if rule.date_to is not None:
                mask &= d <= rule.date_to

        return mask

    @staticmethod
    def _stats(df: pd.DataFrame, cols: Columns) -> Dict[str, Any]:
        if df is None or df.empty:
            return {k: 0.0 for k in (
                "rows","vouchers","accounts","sum_net","sum_abs","debet","kredit",
                "min","p25","median","p75","max","mean","std")}
        s = pd.to_numeric(df[cols.belop], errors="coerce").dropna()
        out = {
            "rows": int(len(df)),
            "vouchers": int(df[cols.bilag].astype(str).nunique()),
            "accounts": int(df[cols.konto].astype(str).nunique()),
            "sum_net": float(s.sum()),
            "sum_abs": float(s.abs().sum()),
            "debet": float(s[s > 0].sum()),
            "kredit": float((-s[s < 0]).sum()),
            "min": float(s.min()) if len(s) else 0.0,
            "p25": float(s.quantile(0.25)) if len(s) else 0.0,
            "median": float(s.quantile(0.50)) if len(s) else 0.0,
            "p75": float(s.quantile(0.75)) if len(s) else 0.0,
            "max": float(s.max()) if len(s) else 0.0,
            "mean": float(s.mean()) if len(s) else 0.0,
            "std": float(s.std(ddof=1)) if len(s) > 1 else 0.0,
        }
        return out

    # ---- compute ----
    def compute(self) -> ScopeResult:
        assert self.df is not None
        pop_mask = self._apply_rule_mask(self._population)
        pop_df = self.df[pop_mask].copy()

        sub_dfs: List[Tuple[ScopeRule, pd.DataFrame, Dict[str, Any]]] = []
        union_mask = pd.Series(False, index=self.df.index)
        for rule in self._subs:
            m = pop_mask & self._apply_rule_mask(rule)
            df_sub = self.df[m].copy()
            sub_dfs.append((rule, df_sub, self._stats(df_sub, self.cols)))
            union_mask |= m

        rest_mask = pop_mask & (~union_mask)
        rest_df = self.df[rest_mask].copy()

        return ScopeResult(
            population_df=pop_df,
            population_stats=self._stats(pop_df, self.cols),
            sub_dfs=sub_dfs,
            rest_df=rest_df,
            rest_stats=self._stats(rest_df, self.cols),
        )

    # ---- eksport ----
    def export_to_excel(self, path: str, res: ScopeResult) -> None:
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            res.population_df.to_excel(excel_writer=xw, sheet_name="Populasjon", index=False)
            for i, (rule, df_sub, _) in enumerate(res.sub_dfs, start=1):
                df_sub.to_excel(excel_writer=xw, sheet_name=f"Underpop_{i}", index=False)
            res.rest_df.to_excel(excel_writer=xw, sheet_name="Rest", index=False)

            # Oppsummering (bred tabell)
            from stats_utils import STAT_ORDER
            wide = {"Nøkkel": [label for _, label in STAT_ORDER]}
            labels_stats = [("Populasjon", res.population_stats)]
            labels_stats += [(f"Underpop_{i}: {rule.name}", st) for i, (rule, _d, st) in enumerate(res.sub_dfs, 1)]
            labels_stats += [("Rest", res.rest_stats)]
            for label, stat in labels_stats:
                wide[label] = [stat.get(key, 0.0) for key, _ in STAT_ORDER]
            pd.DataFrame(wide).to_excel(excel_writer=xw, sheet_name="Oppsummering", index=False)

            try:
                from excel_formatting import polish_excel_writer  # optional
                polish_excel_writer(xw)
            except Exception:
                pass

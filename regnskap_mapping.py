from __future__ import annotations

"""Konto → regnskapslinje mapping + aggregering.

Dette bygger på to Excel-baserte oppsett:
  1) Intervall-mapping (kontoplan → regnnr)
  2) Regnskapslinjer (definisjoner + evt. sum-formler)

I første omgang fokuserer vi på leaf-linjer (sumpost == "nei"), men
modulen støtter også å beregne sumlinjer (Formel) dersom ønskelig.
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


log = logging.getLogger("app")


_ALLOWED_FORMULA_RE = re.compile(r"^[0-9+\-*/().=\s]+$")
_INT_RE = re.compile(r"(?<!\d)(\d{1,6})(?!\d)")


@dataclass(frozen=True)
class MappingResult:
    mapped: "pd.DataFrame"
    unmapped_konto: List[str]


def normalize_intervals(df: "pd.DataFrame") -> "pd.DataFrame":
    """Normaliserer intervall-mapping til kolonnene: fra, til, regnr."""

    import pandas as pd

    if df is None or df.empty:
        raise ValueError("Intervall-mapping er tom.")

    cols = {str(c).strip().lower(): c for c in df.columns}

    def pick(*names: str) -> str:
        for n in names:
            if n in cols:
                return cols[n]
        raise ValueError(f"Mangler kolonne {names} i intervall-mapping. Kolonner: {list(df.columns)}")

    c_from = pick("fra", "from", "konto_fra", "kontofra")
    c_to = pick("til", "to", "konto_til", "kontotil")
    c_reg = pick("regnr", "regnnr", "regnr.", "regnnr.")

    out = df[[c_from, c_to, c_reg]].copy()
    out.columns = ["fra", "til", "regnr"]

    out = out.dropna(axis=0, how="all")
    out["fra"] = out["fra"].map(_to_int)
    out["til"] = out["til"].map(_to_int)
    out["regnr"] = out["regnr"].map(_to_int)
    out = out.dropna(subset=["fra", "til", "regnr"]).copy()
    out["fra"] = out["fra"].astype(int)
    out["til"] = out["til"].astype(int)
    out["regnr"] = out["regnr"].astype(int)

    out = out.sort_values(["fra", "til", "regnr"]).reset_index(drop=True)
    return out


def normalize_regnskapslinjer(df: "pd.DataFrame") -> "pd.DataFrame":
    """Normaliserer regnskapslinjer til kolonnene:

    regnr (int), regnskapslinje (str), sumpost (bool), formel (str|None)
    """

    import pandas as pd

    if df is None or df.empty:
        raise ValueError("Regnskapslinjer er tom.")

    cols = {str(c).strip().lower(): c for c in df.columns}

    def pick(*names: str, optional: bool = False) -> Optional[str]:
        for n in names:
            if n.lower() in cols:
                return cols[n.lower()]
        if optional:
            return None
        raise ValueError(f"Mangler kolonne {names} i regnskapslinjer. Kolonner: {list(df.columns)}")

    c_nr = pick("nr", "regnr", "regnnr", "regnnr.", "regnr.")
    c_name = pick("regnskapslinje", "linje", "tekst", "name")
    c_sum = pick("sumpost", "sum", optional=True)
    c_formula = pick("formel", "formula", optional=True)

    out = pd.DataFrame()
    out["regnr"] = df[c_nr].map(_to_int)
    out["regnskapslinje"] = df[c_name].astype(str).fillna("").map(lambda s: s.strip())

    if c_sum:
        out["sumpost"] = df[c_sum].astype(str).fillna("").map(_to_bool)
    else:
        out["sumpost"] = False

    if c_formula:
        out["formel"] = df[c_formula].astype(str).replace({"nan": ""}).map(lambda s: s.strip())
        out.loc[out["formel"].eq(""), "formel"] = None
    else:
        out["formel"] = None

    out = out.dropna(subset=["regnr"]).copy()
    out["regnr"] = out["regnr"].astype(int)

    return out.reset_index(drop=True)


def map_konto_to_regnr(konto: Sequence[str], intervals: "pd.DataFrame") -> List[Optional[int]]:
    """Map konto (string-digits) til regnr via intervall."""

    import numpy as np

    ints = normalize_intervals(intervals)
    starts = ints["fra"].to_numpy(dtype=int)
    ends = ints["til"].to_numpy(dtype=int)
    regs = ints["regnr"].to_numpy(dtype=int)

    acc = np.array([_to_int(k) for k in konto], dtype=float)
    # NaN-håndtering
    out: List[Optional[int]] = [None] * len(acc)

    # For hvert konto: finn siste start <= konto
    # NB: np.searchsorted krever sortert starts
    idx = np.searchsorted(starts, acc, side="right") - 1
    for i, (a, j) in enumerate(zip(acc, idx)):
        if j < 0 or not (a == a):  # NaN
            out[i] = None
            continue
        aj = int(a)
        if aj <= ends[j]:
            out[i] = int(regs[j])
        else:
            out[i] = None
    return out


def apply_interval_mapping(
    tb: "pd.DataFrame",
    intervals: "pd.DataFrame",
    *,
    konto_col: str = "konto",
) -> MappingResult:
    """Legg på regnr basert på konto-intervaller."""

    import pandas as pd

    if konto_col not in tb.columns:
        raise ValueError(f"tb mangler kolonne '{konto_col}'")

    out = tb.copy()
    regnr = map_konto_to_regnr(out[konto_col].astype(str).tolist(), intervals)
    out["regnr"] = pd.Series(regnr, dtype="Int64")
    unmapped = out.loc[out["regnr"].isna(), konto_col].astype(str).unique().tolist()
    return MappingResult(mapped=out, unmapped_konto=sorted(unmapped))


def aggregate_by_regnskapslinje(
    tb_mapped: "pd.DataFrame",
    regnskapslinjer: "pd.DataFrame",
    *,
    amount_col: str = "ub",
    include_sum_lines: bool = False,
) -> "pd.DataFrame":
    """Aggreger saldobalanse til regnskapslinje-nivå.

    Args:
        tb_mapped: DataFrame med kolonnene "regnr" og beløpskolonne.
        regnskapslinjer: Regnskapslinjer-definisjoner.
        amount_col: "ub" (default) eller "netto".
        include_sum_lines: hvis True beregnes sumlinjer med formel.
    """

    import pandas as pd

    if "regnr" not in tb_mapped.columns:
        raise ValueError("tb_mapped mangler kolonne 'regnr' (kjør apply_interval_mapping først).")
    if amount_col not in tb_mapped.columns:
        raise ValueError(f"tb_mapped mangler beløpskolonne '{amount_col}'.")

    regn = normalize_regnskapslinjer(regnskapslinjer)

    # Leaf-linjer: sumpost == False
    leaf = regn.loc[~regn["sumpost"]].copy()

    sums = (
        tb_mapped.dropna(subset=["regnr"])
        .groupby("regnr", as_index=False)[amount_col]
        .sum()
        .rename(columns={amount_col: "belop"})
    )

    merged = leaf.merge(sums, how="left", on="regnr")
    merged["belop"] = merged["belop"].fillna(0.0)

    if include_sum_lines:
        # Legg til sumlinjer i samme output
        base = {int(r): float(v) for r, v in zip(merged["regnr"], merged["belop"]) if r == r}
        extra = compute_sumlinjer(base_values=base, regnskapslinjer=regn)

        sum_df = regn.loc[regn["sumpost"]].copy()
        sum_df["belop"] = sum_df["regnr"].map(lambda r: float(extra.get(int(r), 0.0)))

        merged = (
            pd.concat([merged, sum_df[["regnr", "regnskapslinje", "sumpost", "formel", "belop"]]], axis=0)
            .sort_values("regnr")
            .reset_index(drop=True)
        )

    return merged[["regnr", "regnskapslinje", "belop", "sumpost", "formel"]]


def compute_sumlinjer(*, base_values: Dict[int, float], regnskapslinjer: "pd.DataFrame") -> Dict[int, float]:
    """Beregner sumlinjer (formler) rekursivt.

    base_values: leaf-linjer som allerede er beregnet.
    regnskapslinjer: normalisert (normalize_regnskapslinjer).

    Returnerer dict med *alle* regnr (inkl leaf + sum) der vi har verdi.
    """

    regn = normalize_regnskapslinjer(regnskapslinjer)
    formulas = {
        int(r.regnr): (str(r.formel).strip() if r.formel else None)
        for r in regn.itertuples(index=False)
        if bool(r.sumpost)
    }

    cache: Dict[int, float] = dict(base_values)
    visiting: set[int] = set()

    def get(regnr: int) -> float:
        if regnr in cache:
            return float(cache[regnr])
        if regnr in visiting:
            raise ValueError(f"Syklisk formel i regnskapslinjer: {regnr}")

        f = formulas.get(regnr)
        if not f:
            cache[regnr] = 0.0
            return 0.0

        visiting.add(regnr)
        val = _eval_formula(f, get)
        visiting.remove(regnr)
        cache[regnr] = float(val)
        return float(val)

    # Beregn alle
    for regnr in list(formulas.keys()):
        try:
            get(int(regnr))
        except Exception as e:
            log.warning("Kunne ikke beregne formel for regnr=%s: %s", regnr, e)
            cache[int(regnr)] = 0.0

    return cache


def _eval_formula(formula: str, get_fn) -> float:
    f = formula.strip()
    if f.startswith("="):
        f = f[1:].strip()

    if not _ALLOWED_FORMULA_RE.match("=" + f):
        raise ValueError(f"Ugyldig formel: {formula!r}")

    # Bytt ut tall-referanser med get(<nr>)
    def repl(m: re.Match) -> str:
        nr = int(m.group(1))
        return f"get({nr})"

    expr = _INT_RE.sub(repl, f)

    # Sikker eval: kun get, ingen builtins
    return float(eval(expr, {"__builtins__": {}}, {"get": get_fn}))


def _to_bool(v: object) -> bool:
    s = str(v).strip().lower()
    if s in {"1", "true", "ja", "yes", "y"}:
        return True
    if s in {"0", "false", "nei", "no", "n", ""}:
        return False
    # fallback: alt annet behandles som False
    return False


def _to_int(v: object) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v != v:  # NaN
            return None
        return int(v)
    s = str(v).strip()
    if s == "" or s.lower() == "nan":
        return None
    m = re.search(r"-?\d+", s)
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None

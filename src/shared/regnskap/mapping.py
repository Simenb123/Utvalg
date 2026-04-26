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
    samt evt. hierarkikolonner for del-/sum-linjer.
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
    c_sumnivaa = pick("sumnivå", "sumnivaa", "sumnivaa", optional=True)
    c_delsumnr = pick("delsumnr", optional=True)
    c_sumnr = pick("sumnr", optional=True)
    c_sumnr2 = pick("sumnr2", optional=True)
    c_sluttsumnr = pick("sluttsumnr", optional=True)
    c_rb = pick("resultat/balanse", "resultatbalanse", "rb", optional=True)

    out = pd.DataFrame()
    out["regnr"] = df[c_nr].map(_to_int)
    out["regnskapslinje"] = df[c_name].astype(str).fillna("").map(lambda s: s.strip())

    if c_sum:
        out["sumpost"] = df[c_sum].astype(str).fillna("").map(_to_bool)
    else:
        out["sumpost"] = False

    if c_formula:
        out["formel"] = (
            df[c_formula]
            .map(lambda v: None if pd.isna(v) else str(v).strip())
            .astype(object)
        )
        out.loc[out["formel"].map(lambda v: str(v).strip().lower() if v is not None else "").isin({"", "nan", "none"}), "formel"] = None
    else:
        out["formel"] = None

    out["sumnivaa"] = df[c_sumnivaa].map(_to_int) if c_sumnivaa else None
    out["delsumnr"] = df[c_delsumnr].map(_to_int) if c_delsumnr else None
    out["sumnr"] = df[c_sumnr].map(_to_int) if c_sumnr else None
    out["sumnr2"] = df[c_sumnr2].map(_to_int) if c_sumnr2 else None
    out["sluttsumnr"] = df[c_sluttsumnr].map(_to_int) if c_sluttsumnr else None

    if c_rb:
        def _rb_norm(v):
            s = str(v).strip().lower() if v is not None else ""
            if s.startswith("balans"):
                return "balanse"
            if s.startswith("resultat"):
                return "resultat"
            return None
        out["rb"] = df[c_rb].map(_rb_norm)
    else:
        out["rb"] = None

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


def apply_account_overrides(
    tb_mapped: "pd.DataFrame",
    overrides: Dict[str, int] | None,
    *,
    konto_col: str = "konto",
    regnr_col: str = "regnr",
) -> "pd.DataFrame":
    """Overstyr regnr for eksplisitte kontoer."""

    import pandas as pd

    if tb_mapped is None:
        return pd.DataFrame()
    if tb_mapped.empty or not overrides:
        return tb_mapped.copy()
    if konto_col not in tb_mapped.columns:
        raise ValueError(f"tb_mapped mangler kolonne '{konto_col}'")

    clean: Dict[str, int] = {}
    for konto, regnr in overrides.items():
        konto_s = str(konto or "").strip()
        if not konto_s:
            continue
        try:
            clean[konto_s] = int(regnr)
        except Exception:
            continue

    if not clean:
        return tb_mapped.copy()

    out = tb_mapped.copy()
    forced = out[konto_col].astype(str).map(clean)
    mask = forced.notna()
    if not bool(mask.any()):
        return out

    if regnr_col not in out.columns:
        out[regnr_col] = pd.Series([pd.NA] * len(out), dtype="Int64")

    out.loc[mask, regnr_col] = forced.loc[mask].astype("Int64")
    return out


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
    hierarchy_leafs = _build_sumline_leaf_descendants(regn)

    cache: Dict[int, float] = dict(base_values)
    visiting: set[int] = set()

    def get(regnr: int) -> float:
        if regnr in cache:
            return float(cache[regnr])
        if regnr in visiting:
            raise ValueError(f"Syklisk formel i regnskapslinjer: {regnr}")

        f = formulas.get(regnr)
        if f:
            visiting.add(regnr)
            val = _eval_formula(f, get)
            visiting.remove(regnr)
            cache[regnr] = float(val)
            return float(val)

        leaves = hierarchy_leafs.get(regnr)
        if leaves:
            val = float(sum(float(cache.get(int(leaf), 0.0)) for leaf in leaves))
            cache[regnr] = val
            return val

        if not f:
            cache[regnr] = 0.0
            return 0.0

    # Beregn alle
    for regnr in list(formulas.keys()):
        try:
            get(int(regnr))
        except Exception as e:
            log.warning("Kunne ikke beregne formel for regnr=%s: %s", regnr, e)
            cache[int(regnr)] = 0.0

    return cache


def expand_regnskapslinje_selection(
    *,
    regnskapslinjer: "pd.DataFrame",
    selected_regnr: Sequence[int],
) -> List[int]:
    """Utvid valgte regnskapslinjer til underliggende leaf-linjer.

    Leaf-linjer returneres som seg selv. Sumposter utvides rekursivt via
    formelreferansene sine. Ugyldige eller ukjente referanser ignoreres.
    """

    regn = normalize_regnskapslinjer(regnskapslinjer)
    leaf_regnr = {int(v) for v in regn.loc[~regn["sumpost"], "regnr"].astype(int).tolist()}
    formulas = {
        int(r.regnr): (str(r.formel).strip() if r.formel else None)
        for r in regn.itertuples(index=False)
    }
    hierarchy_leafs = _build_sumline_leaf_descendants(regn)

    cache: Dict[int, set[int]] = {}
    visiting: set[int] = set()

    def expand_one(regnr: int) -> set[int]:
        if regnr in cache:
            return set(cache[regnr])
        if regnr in visiting:
            raise ValueError(f"Syklisk formel i regnskapslinjer: {regnr}")
        if regnr in leaf_regnr:
            cache[regnr] = {regnr}
            return {regnr}

        formula = formulas.get(regnr)
        if not formula:
            leaves = hierarchy_leafs.get(regnr)
            if leaves:
                cache[regnr] = set(leaves)
                return set(leaves)
            cache[regnr] = set()
            return set()

        if formula.startswith("="):
            formula = formula[1:].strip()

        refs = {int(v) for v in _INT_RE.findall(formula or "")}
        if not refs:
            cache[regnr] = set()
            return set()

        visiting.add(regnr)
        expanded: set[int] = set()
        for ref in refs:
            try:
                expanded.update(expand_one(int(ref)))
            except Exception as exc:
                log.warning("Kunne ikke utvide regnskapslinje %s via %s: %s", regnr, ref, exc)
        visiting.remove(regnr)
        cache[regnr] = set(expanded)
        return set(expanded)

    out: List[int] = []
    seen: set[int] = set()
    for raw in selected_regnr:
        try:
            regnr = int(raw)
        except Exception:
            continue
        try:
            expanded = expand_one(regnr)
        except Exception as exc:
            log.warning("Kunne ikke utvide valgt regnskapslinje %s: %s", regnr, exc)
            expanded = {regnr} if regnr in leaf_regnr else set()
        for leaf in sorted(expanded):
            if leaf in seen:
                continue
            out.append(leaf)
            seen.add(leaf)
    return out


def _build_sumline_leaf_descendants(regn: "pd.DataFrame") -> Dict[int, set[int]]:
    import pandas as pd

    if regn is None or regn.empty:
        return {}

    ref_cols = [c for c in ("delsumnr", "sumnr", "sumnr2", "sluttsumnr") if c in regn.columns]
    if not ref_cols:
        return {}

    leaf = regn.loc[~regn["sumpost"], ["regnr", *ref_cols]].copy()
    if leaf.empty:
        return {}

    descendants: Dict[int, set[int]] = {}
    for row in leaf.itertuples(index=False):
        try:
            leaf_regnr = int(getattr(row, "regnr"))
        except Exception:
            continue
        for col in ref_cols:
            ref = getattr(row, col, None)
            if ref is None or pd.isna(ref):
                continue
            try:
                descendants.setdefault(int(ref), set()).add(leaf_regnr)
            except Exception:
                continue
    return descendants


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

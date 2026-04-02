"""motpost_flowchart_engine.py — Bygg motpost-tre fra HB-transaksjoner.

Tar inn en transaksjons-DataFrame og en startkonto, og bygger et tre
der hver node er en konto (eller regnskapslinje) med sine motposter.
Støtter rekursiv utvidelse: motpost av motpost, 2-3 ledd.

Når konto_to_rl sendes inn, aggregeres alle kontoer til sin regnskapslinje
slik at flytdiagrammet vises på RL-nivå i stedet for kontonivå.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import pandas as pd


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MotpostEdge:
    """Kant mellom to kontoer/regnskapslinjer i motpost-treet."""
    target: str            # Nøkkel (kontonummer eller regnr-streng)
    target_name: str       # Visningsnavn
    amount: float          # Absolutt beløp som flyter mellom
    pct: float             # Prosent av total flyt fra kilden
    voucher_count: int     # Antall bilag som binder dem


@dataclass
class MotpostNode:
    """En konto eller regnskapslinje i motpost-treet."""
    konto: str             # Nøkkel (kontonummer eller regnr-streng)
    konto_name: str        # Visningsnavn
    total_amount: float    # Totalbeløp (abs) på kontoen/RL-en
    edges: list[MotpostEdge] = field(default_factory=list)
    depth: int = 0


@dataclass
class MotpostTree:
    """Komplett motpost-tre klart for rendering."""
    root_nodes: list[MotpostNode] = field(default_factory=list)
    max_depth: int = 0
    client: str = ""
    year: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_konto(val) -> str:
    """Normaliser kontonummer til ren streng."""
    try:
        s = str(val).strip()
        if "." in s:
            s = s.split(".")[0]
        return s
    except Exception:
        return ""


def _build_bilag_konto_map(
    df: pd.DataFrame,
    konto_to_rl: dict[str, tuple[int, str]] | None,
) -> pd.DataFrame:
    """Forbered DataFrame med normaliserte kolonner.

    Når konto_to_rl er satt legges GroupKey/GroupName til:
    - GroupKey = str(regnr) for mappede kontoer
    - GroupKey = konto_str som fallback (umappede)
    """
    out = df.copy()
    if "Konto_str" not in out.columns:
        out["Konto_str"] = out["Konto"].apply(_normalize_konto)
    if "Bilag_str" not in out.columns:
        out["Bilag_str"] = out["Bilag"].astype(str).str.strip().str.replace(".", "", regex=False)
    if "Beløp_num" not in out.columns:
        out["Beløp_num"] = pd.to_numeric(out.get("Beløp", 0), errors="coerce").fillna(0.0)
    if "Kontonavn" not in out.columns:
        out["Kontonavn"] = ""

    if konto_to_rl:
        out["GroupKey"] = out["Konto_str"].map(
            lambda k: str(konto_to_rl[k][0]) if k in konto_to_rl else k
        )
        out["GroupName"] = out["Konto_str"].map(
            lambda k: konto_to_rl[k][1] if k in konto_to_rl else str(out.loc[out["Konto_str"] == k, "Kontonavn"].iloc[0] if (out["Konto_str"] == k).any() else k)
        )
    else:
        out["GroupKey"] = out["Konto_str"]
        out["GroupName"] = out["Kontonavn"].astype(str)

    return out


def _find_counterparts(
    df: pd.DataFrame,
    source_keys: set[str],
    *,
    top_n: int = 5,
    min_pct: float = 2.0,
) -> list[MotpostEdge]:
    """Finn motposter for et sett med gruppe-nøkler (konto eller RL-regnr).

    For hvert bilag som inneholder source_keys, finn alle andre grupper.
    Aggreger beløp per motpost-gruppe og returner topp-N.

    Forventer at df har kolonnene GroupKey, GroupName, Bilag_str, Beløp_num.
    """
    mask_source = df["GroupKey"].isin(source_keys)
    bilags_with_source = set(df.loc[mask_source, "Bilag_str"].unique())

    if not bilags_with_source:
        return []

    df_bilags = df[df["Bilag_str"].isin(bilags_with_source)]
    df_counter = df_bilags[~df_bilags["GroupKey"].isin(source_keys)]

    if df_counter.empty:
        return []

    agg = df_counter.groupby("GroupKey").agg(
        amount=("Beløp_num", lambda s: s.abs().sum()),
        vouchers=("Bilag_str", "nunique"),
        name=("GroupName", "first"),
    ).reset_index()

    total = agg["amount"].sum()
    if total < 1e-9:
        return []

    agg["pct"] = (agg["amount"] / total) * 100
    agg = agg.sort_values("amount", ascending=False)

    edges: list[MotpostEdge] = []
    for _, row in agg.head(top_n).iterrows():
        if row["pct"] < min_pct:
            continue
        edges.append(MotpostEdge(
            target=str(row["GroupKey"]),
            target_name=str(row["name"] or ""),
            amount=float(row["amount"]),
            pct=float(row["pct"]),
            voucher_count=int(row["vouchers"]),
        ))

    return edges


# ---------------------------------------------------------------------------
# Tree builder
# ---------------------------------------------------------------------------

def build_motpost_tree(
    df: pd.DataFrame,
    start_accounts: Sequence[str],
    *,
    max_depth: int = 2,
    top_n: int = 5,
    min_pct: float = 2.0,
    client: str = "",
    year: str = "",
    konto_to_rl: dict[str, tuple[int, str]] | None = None,
) -> MotpostTree:
    """Bygg motpost-tre rekursivt fra startkonto(er).

    Parameters
    ----------
    df : HB-transaksjoner med kolonner Konto, Kontonavn, Bilag, Beløp
    start_accounts : Kontonumre å starte fra
    max_depth : Maks antall ledd (1=bare direkte motposter, 2=motpost-av-motpost)
    top_n : Maks antall motposter per node
    min_pct : Minste prosentandel for å inkludere en motpost
    konto_to_rl : Valgfri mapping konto_str → (regnr, rl_name) for RL-modus.
        Når satt aggregeres alle kontoer til sin regnskapslinje.
    """
    prep = _build_bilag_konto_map(df, konto_to_rl)

    norm_start = {_normalize_konto(a) for a in start_accounts}

    # Totalbeløp per gruppe
    totals = prep.groupby("GroupKey")["Beløp_num"].apply(lambda s: s.abs().sum()).to_dict()

    # Gruppenavn oppslag
    name_map: dict[str, str] = (
        prep.drop_duplicates("GroupKey").set_index("GroupKey")["GroupName"].to_dict()
    )

    # Finn hvilke group-keys de valgte kontone tilhører
    start_key_map: dict[str, set[str]] = {}  # group_key → set av konto_str i start
    for konto in norm_start:
        if konto not in prep["Konto_str"].values:
            continue
        gkey = prep.loc[prep["Konto_str"] == konto, "GroupKey"].iloc[0]
        start_key_map.setdefault(gkey, set()).add(konto)

    if not start_key_map:
        return MotpostTree(max_depth=max_depth, client=client, year=year)

    visited: set[str] = set()

    def _build_node(group_key: str, depth: int) -> MotpostNode:
        visited.add(group_key)
        node = MotpostNode(
            konto=group_key,
            konto_name=name_map.get(group_key, group_key),
            total_amount=totals.get(group_key, 0.0),
            depth=depth,
        )
        if depth >= max_depth:
            return node

        edges = _find_counterparts(prep, {group_key}, top_n=top_n, min_pct=min_pct)
        node.edges = edges
        return node

    # Bygg rotnoder — én per valgt gruppe-key (RL eller konto)
    roots: list[MotpostNode] = []
    for gkey in sorted(start_key_map.keys()):
        root = _build_node(gkey, depth=0)
        roots.append(root)

    # Bygg ledd 2+ (motpostenes motposter)
    if max_depth >= 2:
        for root in roots:
            for edge in root.edges:
                if edge.target not in visited:
                    child = _build_node(edge.target, depth=1)
                    edge._child_node = child  # type: ignore[attr-defined]

    return MotpostTree(
        root_nodes=roots,
        max_depth=max_depth,
        client=client,
        year=year,
    )

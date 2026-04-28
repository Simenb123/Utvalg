"""motpost_flowchart_engine.py — Bygg motpost-tre fra HB-transaksjoner.

Tar inn en transaksjons-DataFrame og en startkonto, og bygger et tre
der hver node er en konto (eller regnskapslinje) med sine motposter.
Støtter rekursiv utvidelse: motpost av motpost, 2-3 ledd.

Når konto_to_rl sendes inn, aggregeres alle kontoer til sin regnskapslinje
slik at flytdiagrammet vises på RL-nivå i stedet for kontonivå.
Hver RL-node inneholder også et `accounts`-felt med kontonivå-breakdown
til bruk for interaktiv drilldown i HTML-rapporten.
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
    # Kontonivå-breakdown (kun satt for RL-rotnoder)
    account_detail: list[dict] = field(default_factory=list)


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
    """Forbered DataFrame med normaliserte kolonner."""
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
            lambda k: konto_to_rl[k][1] if k in konto_to_rl else str(
                out.loc[out["Konto_str"] == k, "Kontonavn"].iloc[0]
                if (out["Konto_str"] == k).any() else k
            )
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
    key_col: str = "GroupKey",
    name_col: str = "GroupName",
) -> list[MotpostEdge]:
    """Finn motposter for et sett med gruppe-nøkler.

    key_col / name_col angir hvilke kolonner som brukes som nøkkel og navn.
    Standard: GroupKey/GroupName (RL-nivå).
    For kontonivå: key_col="Konto_str", name_col="Kontonavn".
    """
    mask_source = df[key_col].isin(source_keys)
    bilags_with_source = set(df.loc[mask_source, "Bilag_str"].unique())

    if not bilags_with_source:
        return []

    df_bilags = df[df["Bilag_str"].isin(bilags_with_source)]
    df_counter = df_bilags[~df_bilags[key_col].isin(source_keys)]

    if df_counter.empty:
        return []

    agg = df_counter.groupby(key_col).agg(
        amount=("Beløp_num", lambda s: s.abs().sum()),
        vouchers=("Bilag_str", "nunique"),
        name=(name_col, "first"),
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
            target=str(row[key_col]),
            target_name=str(row["name"] or ""),
            amount=float(row["amount"]),
            pct=float(row["pct"]),
            voucher_count=int(row["vouchers"]),
        ))

    return edges


def _build_account_detail(
    prep: pd.DataFrame,
    group_key: str,
    *,
    top_n: int = 5,
    min_pct: float = 2.0,
) -> list[dict]:
    """Bygg kontonivå-breakdown for en RL-gruppe.

    For hver konto i gruppen: beløp, prosentandel og topp motpost-kontoer.
    Brukes til interaktiv drilldown i HTML-rapporten.
    """
    df_group = prep[prep["GroupKey"] == group_key]
    if df_group.empty:
        return []

    konto_agg = df_group.groupby("Konto_str").agg(
        amount=("Beløp_num", lambda s: s.abs().sum()),
        name=("Kontonavn", "first"),
    ).reset_index()

    total = konto_agg["amount"].sum()
    if total < 1e-9:
        return []

    konto_agg["pct"] = (konto_agg["amount"] / total) * 100
    konto_agg = konto_agg.sort_values("amount", ascending=False)

    result: list[dict] = []
    for _, row in konto_agg.iterrows():
        konto = str(row["Konto_str"])
        # Finn motposter på kontonivå (ikke RL-aggregert)
        motpost_edges = _find_counterparts(
            prep, {konto},
            top_n=top_n, min_pct=min_pct,
            key_col="Konto_str", name_col="Kontonavn",
        )
        result.append({
            "key": konto,
            "name": str(row["name"] or ""),
            "amount": float(row["amount"]),
            "amount_fmt": _format_amount_py(float(row["amount"])),
            "pct": round(float(row["pct"]), 1),
            "depth": 1,
            "children": [
                {
                    "key": e.target,
                    "name": e.target_name,
                    "amount": e.amount,
                    "amount_fmt": _format_amount_py(e.amount),
                    "pct": round(e.pct, 1),
                    "vouchers": e.voucher_count,
                    "depth": 2,
                    "children": [],
                    "accounts": [],
                    "is_konto": True,
                }
                for e in motpost_edges
            ],
            "accounts": [],
            "is_konto": True,
        })

    return result


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
    """Bygg motpost-tre rekursivt fra startkonto(er)."""
    prep = _build_bilag_konto_map(df, konto_to_rl)
    norm_start = {_normalize_konto(a) for a in start_accounts}

    totals = prep.groupby("GroupKey")["Beløp_num"].apply(lambda s: s.abs().sum()).to_dict()
    name_map: dict[str, str] = (
        prep.drop_duplicates("GroupKey").set_index("GroupKey")["GroupName"].to_dict()
    )

    start_key_map: dict[str, set[str]] = {}
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

    roots: list[MotpostNode] = []
    for gkey in sorted(start_key_map.keys()):
        root = _build_node(gkey, depth=0)
        # Legg til kontonivå-breakdown for RL-rotnoder
        if konto_to_rl:
            root.account_detail = _build_account_detail(
                prep, gkey, top_n=top_n, min_pct=min_pct,
            )
        roots.append(root)

    if max_depth >= 2:
        for root in roots:
            for edge in root.edges:
                if edge.target not in visited:
                    child = _build_node(edge.target, depth=1)
                    # Kontonivå-breakdown også for motpost-noder
                    if konto_to_rl:
                        child.account_detail = _build_account_detail(
                            prep, edge.target, top_n=top_n, min_pct=min_pct,
                        )
                    edge._child_node = child  # type: ignore[attr-defined]

    return MotpostTree(
        root_nodes=roots,
        max_depth=max_depth,
        client=client,
        year=year,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _format_amount_py(val: float) -> str:
    if abs(val) >= 1e6:
        return f"{val / 1e6:,.1f}\u202fM".replace(",", "\u202f")
    if abs(val) >= 1e3:
        return f"{val / 1e3:,.0f}\u202fk".replace(",", "\u202f")
    return f"{val:,.0f}".replace(",", "\u202f")


def node_to_dict(node: MotpostNode) -> dict:
    """Serialiser MotpostNode til JSON-serialiserbart dict."""
    children = []
    for edge in node.edges:
        child_dict = {
            "key": edge.target,
            "name": edge.target_name,
            "amount": edge.amount,
            "amount_fmt": _format_amount_py(edge.amount),
            "pct": round(edge.pct, 1),
            "vouchers": edge.voucher_count,
            "depth": node.depth + 1,
            "children": [],
            "accounts": [],
            "is_konto": False,
        }
        child_node = getattr(edge, "_child_node", None)
        if child_node:
            child_dict["children"] = [
                {
                    "key": e2.target,
                    "name": e2.target_name,
                    "amount": e2.amount,
                    "amount_fmt": _format_amount_py(e2.amount),
                    "pct": round(e2.pct, 1),
                    "vouchers": e2.voucher_count,
                    "depth": node.depth + 2,
                    "children": [],
                    "accounts": child_node.account_detail,
                    "is_konto": False,
                }
                for e2 in child_node.edges
            ]
            child_dict["accounts"] = child_node.account_detail
        children.append(child_dict)

    return {
        "key": node.konto,
        "name": node.konto_name,
        "amount": node.total_amount,
        "amount_fmt": _format_amount_py(node.total_amount),
        "pct": None,
        "vouchers": None,
        "depth": node.depth,
        "children": children,
        "accounts": node.account_detail,
        "is_konto": False,
    }


def tree_to_dict(tree: MotpostTree) -> dict:
    return {
        "client": tree.client,
        "year": tree.year,
        "root_nodes": [node_to_dict(n) for n in tree.root_nodes],
    }

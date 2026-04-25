"""Delt BFS-helper for indirekte eierkjeder i aksjonærregisteret.

Brukes av både Excel-kryssreferansen i ``workpaper_klientinfo`` og
organisasjonskartet i ``page_ar_chart``. Holder BFS-logikken på ett
sted slik at Excel og GUI alltid ser samme kjede og samme brudd.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable


def walk_indirect_chain(
    start_owners: Iterable[dict[str, Any]],
    indirect_owners_fn: Callable[[str], list[dict[str, Any]]],
    max_depth: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """BFS oppover gjennom selskaps-aksjonærer.

    Returnerer ``(chain_nodes, chain_break_orgnrs)``:

    - ``chain_nodes``: liste av prosesserte noder. Hver node er et dict med
      ``{"orgnr", "chain", "depth", "sub_owners"}`` der ``chain`` er en liste
      av ``(name, pct)`` fra direkte holding ned til denne noden, og
      ``sub_owners`` er rådata fra ``indirect_owners_fn(orgnr)`` (kan være
      tom liste hvis kjeden brytes her).
    - ``chain_break_orgnrs``: orgnrs hvor ``sub_owners`` var tom — kjeden
      kunne ikke følges videre opp (typisk fordi orgnr ikke finnes i
      registeret for det aktuelle året). Brukes for diagnostikk og
      visualisering.

    ``visited``-sett beskytter mot sykler. Kun selskaps-aksjonærer (ikke
    personer) enqueues for videre rekursjon.
    """
    visited: set[str] = set()
    breaks: list[str] = []
    nodes: list[dict[str, Any]] = []

    queue: list[dict[str, Any]] = []
    for owner in start_owners or []:
        kind = str(owner.get("shareholder_kind") or "").lower()
        if kind in {"person", "unknown"}:
            continue
        orgnr = str(owner.get("shareholder_orgnr") or "").strip()
        if not orgnr:
            continue
        holding_name = str(owner.get("shareholder_name") or "")
        holding_pct = float(owner.get("ownership_pct") or 0.0)
        queue.append({
            "orgnr": orgnr,
            "chain": [(holding_name, holding_pct)],
            "depth": 1,
        })

    while queue:
        node = queue.pop(0)
        if node["orgnr"] in visited:
            continue
        visited.add(node["orgnr"])

        try:
            sub_owners = list(indirect_owners_fn(node["orgnr"]) or [])
        except Exception:
            sub_owners = []

        if not sub_owners:
            breaks.append(node["orgnr"])

        node["sub_owners"] = sub_owners
        nodes.append(node)

        if node["depth"] >= max_depth:
            continue

        for sub in sub_owners:
            sub_kind = str(sub.get("shareholder_kind") or "").lower()
            if sub_kind in {"person", "unknown"}:
                continue
            sub_orgnr = str(sub.get("shareholder_orgnr") or "").strip()
            if not sub_orgnr or sub_orgnr in visited:
                continue
            sub_name = str(sub.get("shareholder_name") or "")
            sub_pct = float(sub.get("ownership_pct") or 0.0)
            queue.append({
                "orgnr": sub_orgnr,
                "chain": node["chain"] + [(sub_name, sub_pct)],
                "depth": node["depth"] + 1,
            })

    return nodes, breaks

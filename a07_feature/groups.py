from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


@dataclass
class A07Group:
    group_id: str
    group_name: str
    member_codes: List[str]

    @property
    def name(self) -> str:
        return self.group_name

    @name.setter
    def name(self, value: str) -> None:
        self.group_name = value

    @property
    def codes(self) -> List[str]:
        return self.member_codes

    @codes.setter
    def codes(self, value: List[str]) -> None:
        self.member_codes = value


def default_a07_groups() -> Dict[str, A07Group]:
    return {}


def derive_groups_path(mapping_path: str | Path) -> Path:
    return Path(mapping_path).with_name("a07_groups.json")


def load_a07_groups(path: str | Path) -> Dict[str, A07Group]:
    p = Path(path)
    if not p.exists():
        return {}

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

    groups: Dict[str, A07Group] = {}
    if isinstance(raw, list):
        for g in raw:
            if not isinstance(g, dict):
                continue
            gid = str(g.get("group_id") or g.get("id") or "").strip()
            if not gid:
                continue
            groups[gid] = A07Group(
                group_id=gid,
                group_name=str(g.get("group_name") or g.get("name") or gid),
                member_codes=[str(x) for x in (g.get("member_codes") or g.get("codes") or [])],
            )
        return groups

    if not isinstance(raw, dict):
        return {}

    for gid, g in raw.items():
        if not isinstance(g, dict):
            continue
        groups[str(gid)] = A07Group(
            group_id=str(gid),
            group_name=str(g.get("group_name") or g.get("name") or gid),
            member_codes=[str(x) for x in (g.get("member_codes") or g.get("codes") or [])],
        )
    return groups


def save_a07_groups(groups: Dict[str, A07Group], path: str | Path) -> None:
    p = Path(path)
    payload = {
        gid: {
            "group_name": g.group_name,
            "member_codes": list(g.member_codes),
        }
        for gid, g in sorted(groups.items(), key=lambda kv: kv[0])
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _code_aliases(code: str) -> List[str]:
    aliases = {code}
    if "godtgjoerelse" in code:
        aliases.add(code.replace("godtgjoerelse", "godtjoerelse"))
    if "godtjoerelse" in code:
        aliases.add(code.replace("godtjoerelse", "godtgjoerelse"))
    return list(aliases)


def build_grouped_a07_df(
    a07_df: pd.DataFrame,
    groups: Dict[str, A07Group] | List[A07Group],
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    if a07_df is None or a07_df.empty:
        return a07_df.copy() if a07_df is not None else pd.DataFrame(), {}

    group_list = list(groups.values()) if isinstance(groups, dict) else list(groups)
    df = a07_df.copy()
    if "Kode" not in df.columns:
        return df, {}

    df_codes = set(df["Kode"].astype(str).tolist())
    group_rows = []
    consumed = set()
    membership: Dict[str, str] = {}

    for g in group_list:
        candidate_codes = set()
        for mc in g.member_codes:
            for alias in _code_aliases(str(mc)):
                candidate_codes.add(alias)

        present_codes = [c for c in candidate_codes if c in df_codes and c not in consumed]
        if not present_codes:
            continue

        present_rows = df[df["Kode"].astype(str).isin(present_codes)]
        belop_sum = present_rows.get("Belop", pd.Series(dtype=object)).sum()
        diff_sum = present_rows.get("Diff", pd.Series(dtype=object)).sum()
        group_name = (g.group_name or "").strip() or str(g.group_id)
        group_rows.append(
            {
                "Kode": g.group_id,
                "Navn": group_name,
                "Belop": belop_sum,
                "Diff": diff_sum,
            }
        )

        for c in present_codes:
            membership[c] = g.group_id
        consumed.update(present_codes)

    leftover = df[~df["Kode"].astype(str).isin(consumed)].copy()
    if group_rows:
        cols = list(df.columns)
        grouped = pd.concat([pd.DataFrame(group_rows, columns=cols), leftover], ignore_index=True)
    else:
        grouped = leftover

    return grouped, membership


def apply_groups_to_mapping(mapping: Dict[str, str], membership: Dict[str, str]) -> Dict[str, str]:
    if not mapping:
        return {}
    out: Dict[str, str] = {}
    for acc, code in mapping.items():
        c = str(code) if code is not None else ""
        out[str(acc)] = membership.get(c, c)
    return out

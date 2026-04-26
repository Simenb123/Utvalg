from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

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


TREKK_LOENN_FOR_FERIE_CODES: tuple[str, ...] = (
    "trekkILoennForFerie",
    "trekkLoennForFerie",
    "trekkloennForFerie",
    "TrekkILoennForFerie",
)

SMART_PAYROLL_GROUP_CODES: tuple[str, ...] = (
    "trekkILoennForFerie",
    "fastloenn",
    "fastTillegg",
    "timeloenn",
    "overtidsgodtgjoerelse",
)


def a07_code_aliases(code: object) -> tuple[str, ...]:
    text = str(code or "").strip()
    if not text:
        return ()

    aliases = {text}
    folded = text.casefold()
    if "godtgjoerelse" in text:
        aliases.add(text.replace("godtgjoerelse", "godtjoerelse"))
    if "godtjoerelse" in text:
        aliases.add(text.replace("godtjoerelse", "godtgjoerelse"))
    if "Tjenstlig" in text:
        aliases.add(text.replace("Tjenstlig", "Tjenestlig"))
        aliases.add(text.replace("Tjenstlig", "Tjenestelig"))
    if "Tjenestlig" in text:
        aliases.add(text.replace("Tjenestlig", "Tjenstlig"))
        aliases.add(text.replace("Tjenestlig", "Tjenestelig"))
    if "Tjenestelig" in text:
        aliases.add(text.replace("Tjenestelig", "Tjenstlig"))
        aliases.add(text.replace("Tjenestelig", "Tjenestlig"))
    if folded in {value.casefold() for value in TREKK_LOENN_FOR_FERIE_CODES}:
        aliases.update(TREKK_LOENN_FOR_FERIE_CODES)
    return tuple(sorted(aliases, key=lambda value: (value.casefold(), value)))


def canonical_a07_code(code: object) -> str:
    text = str(code or "").strip()
    if not text:
        return ""
    if text.casefold() in {value.casefold() for value in TREKK_LOENN_FOR_FERIE_CODES}:
        return "trekkILoennForFerie"
    return text


def a07_group_member_signature(codes: Iterable[object]) -> tuple[str, ...]:
    normalized = [canonical_a07_code(code) for code in (codes or ()) if canonical_a07_code(code)]
    return tuple(sorted(dict.fromkeys(normalized), key=lambda value: value.casefold()))


def _number_series(df: pd.DataFrame, column: str) -> pd.Series:
    if df is None or df.empty or column not in df.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


def _payroll_account_mask(gl_df: pd.DataFrame) -> pd.Series:
    accounts = gl_df.get("Konto", pd.Series("", index=gl_df.index)).fillna("").astype(str).str.strip()
    names = gl_df.get("Navn", pd.Series("", index=gl_df.index)).fillna("").astype(str).str.casefold()
    account_hit = accounts.str.startswith(("50", "51", "52", "53", "54", "55", "56", "57", "58", "59"))
    name_hit = names.str.contains(
        "lonn|lønn|loenn|ferie|overtid|bonus|godtgj|honorar|trekk",
        regex=True,
        na=False,
    )
    return account_hit | name_hit


def _existing_group_signatures(groups: dict[str, A07Group]) -> set[tuple[str, ...]]:
    return {
        a07_group_member_signature(group.member_codes)
        for group in (groups or {}).values()
        if a07_group_member_signature(group.member_codes)
    }


def _group_member_codes_from_id(code: object) -> list[str]:
    text = str(code or "").strip()
    prefix = "A07_GROUP:"
    if not text.casefold().startswith(prefix.casefold()):
        return []
    tail = text[len(prefix) :]
    return [part.strip() for part in tail.split("+") if part.strip()]


def _add_mapping_backed_groups(out: dict[str, A07Group], mapping: dict[str, str] | None) -> None:
    signatures = _existing_group_signatures(out)
    for raw_code in (mapping or {}).values():
        group_id = str(raw_code or "").strip()
        members = _group_member_codes_from_id(group_id)
        signature = a07_group_member_signature(members)
        if not group_id or not members or not signature or signature in signatures:
            continue
        out[group_id] = A07Group(
            group_id=group_id,
            group_name=" + ".join(members),
            member_codes=members,
        )
        signatures.add(signature)


def build_smart_a07_groups(
    a07_df: pd.DataFrame,
    gl_df: pd.DataFrame,
    groups: dict[str, A07Group] | None,
    *,
    basis_col: str = "UB",
    mapping: dict[str, str] | None = None,
    tolerance: float = 0.01,
) -> dict[str, A07Group]:
    """Add conservative virtual payroll groups when A07 codes sum exactly to GL.

    The solver only considers common salary components and requires an exact
    single-account amount match in the payroll account area. It returns a new
    dict and never mutates the caller's group object in place.
    """

    out = dict(groups or {})
    _add_mapping_backed_groups(out, mapping)
    if a07_df is None or a07_df.empty or gl_df is None or gl_df.empty:
        return out
    if "Kode" not in a07_df.columns or "Belop" not in a07_df.columns or "Konto" not in gl_df.columns:
        return out

    a07_work = a07_df.copy()
    a07_work["Kode"] = a07_work["Kode"].fillna("").astype(str).str.strip()
    a07_work["Belop"] = _number_series(a07_work, "Belop")
    code_lookup: dict[str, tuple[str, str, float]] = {}
    for _, row in a07_work.iterrows():
        actual_code = str(row.get("Kode") or "").strip()
        if not actual_code:
            continue
        canonical = canonical_a07_code(actual_code)
        if canonical not in SMART_PAYROLL_GROUP_CODES:
            continue
        if canonical in code_lookup:
            continue
        code_lookup[canonical] = (
            actual_code,
            str(row.get("Navn") or actual_code).strip() or actual_code,
            float(row.get("Belop") or 0.0),
        )

    present = [code for code in SMART_PAYROLL_GROUP_CODES if code in code_lookup]
    if len(present) < 2:
        return out

    gl_work = gl_df.copy()
    gl_work["Konto"] = gl_work["Konto"].fillna("").astype(str).str.strip()
    basis = str(basis_col or "UB").strip() or "UB"
    if basis not in gl_work.columns:
        basis = "UB" if "UB" in gl_work.columns else "Endring"
    gl_work["__amount"] = _number_series(gl_work, basis)
    gl_work = gl_work.loc[_payroll_account_mask(gl_work)].copy()
    mapped_accounts = {str(account).strip() for account in (mapping or {}) if str(account).strip()}
    if mapped_accounts:
        gl_work = gl_work.loc[~gl_work["Konto"].isin(mapped_accounts)].copy()
    if gl_work.empty:
        return out

    signatures = _existing_group_signatures(out)
    consumed_codes: set[str] = set()
    combo_rows: list[tuple[float, tuple[str, ...], str]] = []
    for size in range(min(len(present), 5), 1, -1):
        for combo in combinations(present, size):
            if consumed_codes & set(combo):
                continue
            signature = a07_group_member_signature(combo)
            if not signature or signature in signatures:
                continue
            amount = float(sum(code_lookup[code][2] for code in combo))
            if abs(amount) <= tolerance:
                continue
            matches = gl_work.loc[(gl_work["__amount"] - amount).abs() <= tolerance]
            if matches.empty:
                continue
            account = str(matches.iloc[0].get("Konto") or "").strip()
            combo_rows.append((abs(amount), tuple(combo), account))

    for _amount_abs, combo, _account in sorted(combo_rows, reverse=True):
        if consumed_codes & set(combo):
            continue
        actual_codes = [code_lookup[code][0] for code in combo]
        signature = a07_group_member_signature(actual_codes)
        if not signature or signature in signatures:
            continue
        group_id = "A07_GROUP:" + "+".join(actual_codes)
        if group_id in out:
            continue
        group_name = " + ".join(code_lookup[code][1] for code in combo)
        out[group_id] = A07Group(
            group_id=group_id,
            group_name=group_name or group_id,
            member_codes=actual_codes,
        )
        signatures.add(signature)
        consumed_codes.update(combo)

    return out


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
    seen_signatures: set[tuple[str, ...]] = set()

    def _add_group(group: A07Group) -> None:
        members = [str(x).strip() for x in (group.member_codes or []) if str(x).strip()]
        signature = a07_group_member_signature(members)
        if not signature or signature in seen_signatures:
            return
        seen_signatures.add(signature)
        group.member_codes = members
        groups[group.group_id] = group

    if isinstance(raw, list):
        for g in raw:
            if not isinstance(g, dict):
                continue
            gid = str(g.get("group_id") or g.get("id") or "").strip()
            if not gid:
                continue
            _add_group(
                A07Group(
                    group_id=gid,
                    group_name=str(g.get("group_name") or g.get("name") or gid),
                    member_codes=[str(x) for x in (g.get("member_codes") or g.get("codes") or [])],
                )
            )
        return groups

    if not isinstance(raw, dict):
        return {}

    for gid, g in raw.items():
        if not isinstance(g, dict):
            continue
        _add_group(
            A07Group(
                group_id=str(gid),
                group_name=str(g.get("group_name") or g.get("name") or gid),
                member_codes=[str(x) for x in (g.get("member_codes") or g.get("codes") or [])],
            )
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
    return list(a07_code_aliases(code))


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

from __future__ import annotations

from itertools import combinations
import re
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from ..groups import a07_code_aliases
from .helpers import (
    _auto_basis_for_code,
    _get_series,
    _is_a07_relevant_account,
    _konto_in_ranges,
    _konto_int,
    _safe_float,
    _score_account,
    _tokenize,
    available_basis,
)
from .models import (
    AccountUsageFeatures,
    BASIS_ENDRING,
    BASIS_UB,
    EXCLUDED_A07_CODES,
    PAYROLL_TOKENS,
    SUGGEST_OUT_COLUMNS,
    SuggestConfig,
    SuggestionRow,
)
from .rulebook import RulebookRule, load_rulebook
from .usage import build_account_usage_features, score_usage_signal


def _effective_target_value(target: float, rule: Optional[RulebookRule]) -> float:
    if rule is None or rule.expected_sign is None or rule.expected_sign == 0:
        return float(target)
    if rule.expected_sign > 0:
        return abs(float(target))
    return -abs(float(target))


def _a07_group_members(code: object) -> tuple[str, ...]:
    code_s = str(code or "").strip()
    prefix = "A07_GROUP:"
    if not code_s.casefold().startswith(prefix.casefold()):
        return ()
    tail = code_s[len(prefix) :]
    members: list[str] = []
    for raw in tail.replace(";", "+").replace(",", "+").split("+"):
        member = raw.strip()
        if member:
            members.append(member)
    return tuple(members)


def _lookup_rule(rulebook: dict[str, RulebookRule], code: object) -> RulebookRule | None:
    code_s = str(code or "").strip()
    if not code_s:
        return None
    for alias in a07_code_aliases(code_s):
        found = rulebook.get(alias) or rulebook.get(alias.strip()) or rulebook.get(alias.lower())
        if found is not None:
            return found
    members = _a07_group_members(code_s)
    if not members:
        return None
    member_rules = [_lookup_rule(rulebook, member) for member in members]
    member_rules = [rule for rule in member_rules if rule is not None]
    if not member_rules:
        return None

    def _uniq(values: list[object]) -> tuple:
        out: list[object] = []
        seen: set[str] = set()
        for value in values:
            key = repr(value)
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
        return tuple(out)

    rf_groups = {str(rule.rf1022_group or "").strip() for rule in member_rules if str(rule.rf1022_group or "").strip()}
    basis_values = {str(rule.basis or "").strip() for rule in member_rules if str(rule.basis or "").strip()}
    aga_values = {rule.aga_pliktig for rule in member_rules if rule.aga_pliktig is not None}
    return RulebookRule(
        label=" + ".join(str(rule.label or "").strip() or member for rule, member in zip(member_rules, members)),
        category="a07_group",
        rf1022_group=next(iter(rf_groups)) if len(rf_groups) == 1 else None,
        aga_pliktig=next(iter(aga_values)) if len(aga_values) == 1 else None,
        allowed_ranges=_uniq([rng for rule in member_rules for rng in rule.allowed_ranges]),
        keywords=_uniq([kw for rule in member_rules for kw in (rule.keywords or ())] + list(members)),
        exclude_keywords=_uniq([kw for rule in member_rules for kw in (rule.exclude_keywords or ())]),
        boost_accounts=_uniq([acct for rule in member_rules for acct in (rule.boost_accounts or ())]),
        special_add=_uniq([item for rule in member_rules for item in (rule.special_add or ())]),
        basis=next(iter(basis_values)) if len(basis_values) == 1 else None,
        expected_sign=None,
    )


def _special_add_total(
    gl_df: pd.DataFrame,
    *,
    rule: Optional[RulebookRule],
    selected_basis: str,
    include_accounts: Optional[Set[str]] = None,
    exclude_accounts: Optional[Set[str]] = None,
) -> float:
    total, _accounts = _special_add_details(
        gl_df,
        rule=rule,
        selected_basis=selected_basis,
        include_accounts=include_accounts,
        exclude_accounts=exclude_accounts,
    )
    return total


def _special_add_ranges(account_expr: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    for part in re.split(r"[|;,\n]+", str(account_expr or "")):
        text = part.strip()
        if not text:
            continue
        range_match = re.match(r"^(\d+)\s*-\s*(\d+)$", text)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            ranges.append((min(start, end), max(start, end)))
            continue
        single_match = re.match(r"^(\d+)$", text)
        if single_match:
            value = int(single_match.group(1))
            ranges.append((value, value))
    return tuple(ranges)


def _special_add_matches_row(item: Any, row: pd.Series) -> bool:
    account_expr = str(getattr(item, "account", "") or "").strip()
    if not account_expr:
        return False
    ranges = _special_add_ranges(account_expr)
    if not ranges or not _konto_in_ranges(row.get("Konto"), ranges):
        return False

    keywords = tuple(str(value or "").strip() for value in getattr(item, "keywords", ()) if str(value or "").strip())
    if not keywords:
        return True
    keyword_tokens: set[str] = set()
    for keyword in keywords:
        keyword_tokens |= _tokenize(keyword)
    if not keyword_tokens:
        return True
    name_tokens = row.get("__tokens")
    if not isinstance(name_tokens, set):
        name_tokens = _tokenize(str(row.get("Navn") or ""))
    return bool(keyword_tokens & set(name_tokens))


def _special_add_details(
    gl_df: pd.DataFrame,
    *,
    rule: Optional[RulebookRule],
    selected_basis: str,
    include_accounts: Optional[Set[str]] = None,
    exclude_accounts: Optional[Set[str]] = None,
) -> tuple[float, tuple[str, ...]]:
    include = (
        None
        if include_accounts is None
        else {str(account).strip() for account in include_accounts if str(account).strip()}
    )
    exclude = {str(account).strip() for account in (exclude_accounts or set()) if str(account).strip()}
    if rule is None or not rule.special_add or gl_df is None or gl_df.empty:
        return 0.0, ()

    gl_lookup = gl_df.copy()
    gl_lookup["Konto"] = gl_lookup["Konto"].astype(str).str.strip()
    total = 0.0
    accounts: List[str] = []
    if "__tokens" not in gl_lookup.columns:
        gl_lookup["__tokens"] = (
            gl_lookup["Navn"].map(_tokenize)
            if "Navn" in gl_lookup.columns
            else [set()] * len(gl_lookup)
        )

    for item in rule.special_add:
        basis_name = str(item.basis or selected_basis or BASIS_UB).strip() or BASIS_UB
        series = _get_series(gl_lookup, basis_name)
        mask = gl_lookup.apply(lambda gl_row: _special_add_matches_row(item, gl_row), axis=1)
        if include is not None:
            mask = mask & gl_lookup["Konto"].isin(include)
        if exclude:
            mask = mask & ~gl_lookup["Konto"].isin(exclude)
        if accounts:
            mask = mask & ~gl_lookup["Konto"].isin(accounts)
        if not bool(mask.any()):
            continue
        matched = gl_lookup.loc[mask, ["Konto"]].copy()
        matched["__amount"] = series.loc[mask]
        for account, group in matched.groupby("Konto", sort=False):
            account_s = str(account).strip()
            if not account_s or account_s in accounts:
                continue
            try:
                subtotal = float(group["__amount"].sum())
            except Exception:
                subtotal = 0.0
            if abs(subtotal) <= 0.000001:
                continue
            total += float(item.weight) * subtotal
            accounts.append(account_s)
    return float(total), tuple(accounts)


def _build_explain_text(
    *,
    selected_basis: str,
    rule: Optional[RulebookRule],
    hit_tokens: Set[str],
    history_accounts: Set[str],
    usage_reasons: Set[str],
    residual_target: float,
    special_add_raw: float,
    diff_total: float,
) -> str:
    parts: List[str] = [f"basis={selected_basis}"]

    if hit_tokens:
        parts.append("navn=" + ",".join(sorted(hit_tokens)))

    rule_parts: List[str] = []
    if rule:
        if rule.allowed_ranges:
            rule_parts.append("kontonr")
        if rule.boost_accounts:
            rule_parts.append("boost")
        if rule.expected_sign is not None:
            rule_parts.append(f"sign={rule.expected_sign}")
        if rule.special_add:
            rule_parts.append("special_add")
    if rule_parts:
        parts.append("regel=" + ",".join(rule_parts))

    if history_accounts:
        parts.append("historikk=" + ",".join(sorted(history_accounts)))
    if usage_reasons:
        parts.append("bruk=" + ",".join(sorted(usage_reasons)))

    parts.append(f"residual={float(residual_target):.2f}")
    if abs(float(special_add_raw)) > 0.000001:
        parts.append(f"special={float(special_add_raw):.2f}")
    parts.append(f"diff={float(diff_total):.2f}")
    return " | ".join(parts)


def suggest_mappings(
    a07_codes_df: pd.DataFrame,
    gl_df: pd.DataFrame,
    mapping: Optional[Dict[str, str]] = None,
    *,
    max_combo: Optional[int] = None,
    candidates_per_code: Optional[int] = None,
    top_suggestions_per_code: Optional[int] = None,
    top_codes: Optional[int] = None,
    exclude_mapped_accounts: Optional[bool] = None,
    override_existing_mapping: Optional[bool] = None,
    filter_mode: Optional[str] = None,
    basis_strategy: Optional[str] = None,
    basis: Optional[str] = None,
    basis_by_code: Optional[Dict[str, str]] = None,
    tolerance_rel: Optional[float] = None,
    tolerance_abs: Optional[float] = None,
    rulebook_path: Optional[str] = None,
    use_residual: Optional[bool] = None,
    hide_solved_codes: Optional[bool] = None,
    basis_col: Optional[str] = None,
    max_candidates_per_code: Optional[int] = None,
    override_existing: Optional[bool] = None,
    top_per_code: Optional[int] = None,
    config: Optional[SuggestConfig] = None,
    cfg: Optional[SuggestConfig] = None,
    mapping_existing: Optional[Dict[str, str]] = None,
    mapping_prior: Optional[Dict[str, str]] = None,
    mapping_previous_year: Optional[Dict[str, str]] = None,
    usage_features: Optional[Dict[str, AccountUsageFeatures]] = None,
    monthly_df: Optional[pd.DataFrame] = None,
    **_ignored_kwargs: Any,
) -> pd.DataFrame:
    base_cfg = config or cfg or SuggestConfig()
    usage_by_account = {
        str(account).strip(): features
        for account, features in (usage_features or {}).items()
        if str(account).strip()
    }
    if not usage_by_account and monthly_df is not None:
        try:
            usage_by_account = build_account_usage_features(monthly_df)
        except Exception:
            usage_by_account = {}

    eff_cfg = SuggestConfig(
        max_combo=int(max_combo) if max_combo is not None else base_cfg.max_combo,
        candidates_per_code=(
            int(candidates_per_code)
            if candidates_per_code is not None
            else base_cfg.candidates_per_code
        ),
        top_suggestions_per_code=(
            int(top_suggestions_per_code)
            if top_suggestions_per_code is not None
            else base_cfg.top_suggestions_per_code
        ),
        top_codes=int(top_codes) if top_codes is not None else base_cfg.top_codes,
        exclude_mapped_accounts=(
            bool(exclude_mapped_accounts)
            if exclude_mapped_accounts is not None
            else base_cfg.exclude_mapped_accounts
        ),
        override_existing_mapping=(
            bool(override_existing_mapping)
            if override_existing_mapping is not None
            else base_cfg.override_existing_mapping
        ),
        use_residual=bool(use_residual) if use_residual is not None else getattr(base_cfg, "use_residual", True),
        hide_solved_codes=(
            bool(hide_solved_codes)
            if hide_solved_codes is not None
            else getattr(base_cfg, "hide_solved_codes", True)
        ),
        filter_mode=str(filter_mode) if filter_mode is not None else base_cfg.filter_mode,
        basis_strategy=str(basis_strategy) if basis_strategy is not None else base_cfg.basis_strategy,
        basis=str(basis) if basis is not None else base_cfg.basis,
        basis_by_code=dict(basis_by_code) if basis_by_code is not None else dict(base_cfg.basis_by_code or {}),
        tolerance_rel=float(tolerance_rel) if tolerance_rel is not None else base_cfg.tolerance_rel,
        tolerance_abs=float(tolerance_abs) if tolerance_abs is not None else base_cfg.tolerance_abs,
        rulebook_path=str(rulebook_path) if rulebook_path is not None else base_cfg.rulebook_path,
        historical_account_boost=float(getattr(base_cfg, "historical_account_boost", 0.12)),
        historical_combo_boost=float(getattr(base_cfg, "historical_combo_boost", 0.10)),
        basis_col=basis_col if basis_col is not None else base_cfg.basis_col,
        max_candidates_per_code=(
            max_candidates_per_code
            if max_candidates_per_code is not None
            else base_cfg.max_candidates_per_code
        ),
        override_existing=override_existing if override_existing is not None else base_cfg.override_existing,
        top_per_code=top_per_code if top_per_code is not None else base_cfg.top_per_code,
    )

    mapping_used = mapping if mapping is not None else (mapping_existing or {})
    mapping_used = {str(k): ("" if v is None else str(v)) for k, v in (mapping_used or {}).items()}
    mapping_prior_used = mapping_prior if mapping_prior is not None else (mapping_previous_year or {})
    mapping_prior_used = {
        str(k): ("" if v is None else str(v))
        for k, v in (mapping_prior_used or {}).items()
        if str(v).strip()
    }

    rulebook = load_rulebook(eff_cfg.rulebook_path)

    if a07_codes_df is None or len(a07_codes_df) == 0:
        return pd.DataFrame(columns=list(SUGGEST_OUT_COLUMNS))

    a07_df = a07_codes_df.copy()
    cols_l = {str(c).strip().lower(): c for c in a07_df.columns}
    code_col = cols_l.get("kode") or cols_l.get("a07") or cols_l.get("code") or list(a07_df.columns)[0]
    name_col = cols_l.get("navn") or cols_l.get("kodenavn") or cols_l.get("name")
    amount_col = (
        cols_l.get("belop")
        or cols_l.get("a07_belop")
        or cols_l.get("amount")
        or cols_l.get("sum")
    )
    if amount_col is None:
        raise ValueError("A07 dataframe mangler belop-kolonne (Belop/A07_Belop).")

    a07_df["Kode"] = a07_df[code_col].astype(str).str.strip()
    a07_df["KodeNavn"] = a07_df[name_col].astype(str) if name_col else a07_df["Kode"]
    a07_df["A07_Belop"] = a07_df[amount_col].map(_safe_float)
    a07_df = a07_df[~a07_df["Kode"].str.lower().isin(EXCLUDED_A07_CODES)].copy()
    a07_df["__abs"] = a07_df["A07_Belop"].abs()
    a07_df = a07_df.sort_values("__abs", ascending=False).head(int(eff_cfg.top_codes)).copy()
    a07_df.drop(columns=["__abs"], inplace=True, errors="ignore")

    gl_all = gl_df.copy()
    gl_cols_l = {str(c).strip().lower(): c for c in gl_all.columns}
    konto_col = (
        gl_cols_l.get("konto")
        or gl_cols_l.get("account")
        or gl_cols_l.get("accountid")
        or gl_cols_l.get("kontonr")
    )
    if konto_col is None:
        raise ValueError("GL dataframe mangler konto-kolonne (Konto/Account/AccountId).")
    navn_col = (
        gl_cols_l.get("navn")
        or gl_cols_l.get("name")
        or gl_cols_l.get("accountname")
        or gl_cols_l.get("kontonavn")
    )

    gl_all["Konto"] = gl_all[konto_col].astype(str).str.strip()
    gl_all["Navn"] = gl_all[navn_col].astype(str) if navn_col else ""
    gl_all["__tokens"] = gl_all["Navn"].map(_tokenize)
    avail = available_basis(gl_all)

    mapping_nonempty = {str(k): str(v) for k, v in mapping_used.items() if str(v).strip()}
    mapped_accounts_nonexcluded: Set[str] = {
        str(k)
        for k, v in mapping_nonempty.items()
        if str(v).strip().lower() not in EXCLUDED_A07_CODES
    }

    code_to_accounts: Dict[str, Set[str]] = {}
    for account, code in mapping_nonempty.items():
        code_l = str(code).strip().lower()
        if not code_l or code_l in EXCLUDED_A07_CODES:
            continue
        code_to_accounts.setdefault(code_l, set()).add(str(account).strip())

    historical_code_to_accounts: Dict[str, Set[str]] = {}
    for account, code in mapping_prior_used.items():
        code_l = str(code).strip().lower()
        if not code_l or code_l in EXCLUDED_A07_CODES:
            continue
        historical_code_to_accounts.setdefault(code_l, set()).add(str(account).strip())

    gl_candidates = gl_all.copy()
    if (
        eff_cfg.exclude_mapped_accounts
        and not eff_cfg.override_existing_mapping
        and mapped_accounts_nonexcluded
    ):
        gl_candidates = gl_candidates[~gl_candidates["Konto"].isin(mapped_accounts_nonexcluded)].copy()

    basis_series_cache: Dict[str, pd.Series] = {}

    def _series_for_basis(selected_basis: str) -> pd.Series:
        basis_name = str(selected_basis or "").strip() or BASIS_UB
        if basis_name not in basis_series_cache:
            basis_series_cache[basis_name] = _get_series(gl_all, basis_name)
        return basis_series_cache[basis_name]

    out_rows: List[Dict[str, Any]] = []

    for _, row in a07_df.iterrows():
        code = str(row["Kode"])
        code_l = code.strip().lower()
        code_name = str(row.get("KodeNavn", code))
        target = float(row.get("A07_Belop", 0.0))

        code_tokens = _tokenize(code) | _tokenize(code_name)
        for member_code in _a07_group_members(code):
            code_tokens |= _tokenize(member_code)
        rule = _lookup_rule(rulebook, code)
        if rule and rule.keywords:
            for keyword in rule.keywords:
                code_tokens |= _tokenize(keyword)

        selected_basis = (
            _auto_basis_for_code(
                code=code,
                code_name=code_name,
                avail=avail,
                default_basis=eff_cfg.basis,
                basis_by_code=eff_cfg.basis_by_code,
                rule=rule,
            )
            if eff_cfg.basis_strategy.lower() == "per_code"
            else (
                eff_cfg.basis
                if eff_cfg.basis in avail
                else (BASIS_UB if BASIS_UB in avail else BASIS_ENDRING)
            )
        )

        mapped_for_code = code_to_accounts.get(code_l, set())
        historical_for_code = historical_code_to_accounts.get(code_l, set())
        series_all = _series_for_basis(selected_basis)
        target_effective = _effective_target_value(target, rule)
        special_current_raw, special_current_accounts = _special_add_details(
            gl_all,
            rule=rule,
            selected_basis=selected_basis,
            include_accounts=set(mapped_for_code),
        )

        current_raw = 0.0
        if mapped_for_code:
            try:
                ordinary_mapped_accounts = set(mapped_for_code) - set(special_current_accounts)
                mask = gl_all["Konto"].isin(ordinary_mapped_accounts)
                current_raw = float(series_all[mask].sum())
            except Exception:
                current_raw = 0.0

        special_proposal_raw, special_proposal_accounts = _special_add_details(
            gl_all,
            rule=rule,
            selected_basis=selected_basis,
            exclude_accounts=mapped_accounts_nonexcluded,
        )
        current_total = float(current_raw + special_current_raw)
        target_abs = abs(float(target_effective))
        tol = max(float(eff_cfg.tolerance_abs), float(eff_cfg.tolerance_rel) * max(target_abs, 1.0))
        diff_current = float(target_effective - current_total)
        within_current = abs(diff_current) <= tol
        diff_with_special = float(target_effective - (current_total + special_proposal_raw))
        special_improves_current = bool(
            special_proposal_accounts
            and abs(diff_with_special) + 0.01 < abs(diff_current)
        )
        if eff_cfg.hide_solved_codes and within_current and not special_improves_current:
            continue

        residual_target = float(target_effective)
        if eff_cfg.use_residual and mapped_for_code:
            residual_target = float(target_effective - current_total)
        residual_abs = abs(residual_target)

        gl_pool = gl_candidates.copy()
        try:
            gl_pool["__amount"] = series_all.loc[gl_pool.index]
        except Exception:
            gl_pool["__amount"] = _get_series(gl_pool, selected_basis)

        if rule and rule.allowed_ranges:
            in_range_mask = gl_pool["Konto"].map(lambda k: _konto_in_ranges(k, rule.allowed_ranges))
            boost_set = set(rule.boost_accounts)
            boost_mask = gl_pool["Konto"].map(lambda k: _konto_int(k) in boost_set)
            gl_pool = gl_pool[in_range_mask | boost_mask].copy()
        elif str(eff_cfg.filter_mode).lower() == "a07":
            def _usage_is_payroll_relevant(konto_value: object) -> bool:
                usage = usage_by_account.get(str(konto_value or "").strip())
                if usage is None:
                    return False
                usage_tokens = {str(token).strip() for token in usage.top_text_tokens if str(token).strip()}
                usage_prefixes = {str(prefix).strip() for prefix in usage.top_counterparty_prefixes if str(prefix).strip()}
                if usage_tokens & PAYROLL_TOKENS:
                    return True
                if usage_prefixes & {"26", "27", "28", "29", "50", "51", "52", "53", "54", "55", "56", "57", "58", "59"}:
                    return True
                return bool(usage.monthly_regularity >= 0.5 and usage.repeat_amount_ratio >= 0.5)

            gl_pool = gl_pool[
                gl_pool.apply(
                    lambda gl_row: (
                        _is_a07_relevant_account(gl_row["Konto"], gl_row["__tokens"])
                        or (bool(code_tokens & set(gl_row["__tokens"])) if rule is not None else False)
                        or _usage_is_payroll_relevant(gl_row["Konto"])
                    ),
                    axis=1,
                )
            ].copy()

        special_accounts_for_rule = set(special_current_accounts) | set(special_proposal_accounts)
        if special_accounts_for_rule:
            gl_pool = gl_pool[~gl_pool["Konto"].isin(special_accounts_for_rule)].copy()

        if len(gl_pool) == 0 and not special_proposal_accounts:
            continue

        cand_list: List[tuple[str, float, float, tuple[str, ...], bool, tuple[str, ...], float]] = []
        for _, gl_row in gl_pool.iterrows():
            konto = gl_row["Konto"]
            amount = float(gl_row["__amount"])
            acct_tokens = set(gl_row["__tokens"])
            usage = usage_by_account.get(str(konto).strip())
            usage_score, usage_reasons = score_usage_signal(
                code_tokens=code_tokens,
                rule=rule,
                usage=usage,
                historical_accounts=historical_for_code,
            )
            cand_score, hits = _score_account(
                target_abs=residual_abs,
                gl_amount=amount,
                code_tokens=code_tokens,
                acct_tokens=acct_tokens,
                konto=konto,
                rule=rule,
                usage_score=usage_score,
            )
            is_historical = str(konto).strip() in historical_for_code
            if is_historical:
                cand_score = min(1.0, float(cand_score) + float(eff_cfg.historical_account_boost))
            cand_list.append((konto, amount, cand_score, hits, is_historical, usage_reasons, usage_score))

        cand_list.sort(key=lambda x: (-x[2], 1 if x[4] else 0, -x[6], abs(float(x[1]) - residual_target)))
        cand_list = cand_list[: int(eff_cfg.candidates_per_code)]
        if not cand_list and not special_proposal_accounts:
            continue

        combo_rows: List[tuple[SuggestionRow, str, Set[str], Dict[str, Any]]] = []
        max_k = min(max(1, int(eff_cfg.max_combo)), len(cand_list))
        score_denom = max(abs(residual_target) if eff_cfg.use_residual else target_abs, 1.0)

        rule_boost_set: Set[int] = set(int(x) for x in (rule.boost_accounts if rule else ()))
        rule_keyword_tokens: Set[str] = set()
        if rule and rule.keywords:
            for keyword in rule.keywords:
                rule_keyword_tokens |= _tokenize(keyword)
        special_add_active = abs(float(special_proposal_raw)) > 1e-6
        used_residual_flag = bool(eff_cfg.use_residual and mapped_for_code)

        combo_sizes = list(range(1, max_k + 1))
        if special_proposal_accounts:
            combo_sizes.insert(0, 0)

        for combo_size in combo_sizes:
            combo_iter = ((),) if combo_size == 0 else combinations(range(len(cand_list)), combo_size)
            for idxs in combo_iter:
                accounts = tuple(str(cand_list[i][0]) for i in idxs)
                suggestion_accounts = tuple(dict.fromkeys([*accounts, *special_proposal_accounts]))
                amounts = [float(cand_list[i][1]) for i in idxs]
                scores = [float(cand_list[i][2]) for i in idxs]
                hits_union: Set[str] = set()
                historical_hits = 0
                usage_reason_union: Set[str] = set()
                for i in idxs:
                    hits_union |= set(cand_list[i][3])
                    if cand_list[i][4]:
                        historical_hits += 1
                    usage_reason_union |= set(cand_list[i][5])

                combo_raw = float(sum(amounts))
                base_total = float(special_proposal_raw + (current_total if eff_cfg.use_residual else 0.0))
                total_raw = float(base_total + combo_raw)
                gl_sum_total = float(total_raw)
                diff_total = float(target_effective - gl_sum_total)
                within = abs(diff_total) <= tol

                amount_score = 1.0 - min(abs(diff_total) / score_denom, 1.0)
                token_score = (len(hits_union) / max(len(code_tokens), 1)) if code_tokens else 0.0
                base = 0.65 * amount_score + 0.20 * token_score + 0.15 * (sum(scores) / max(len(scores), 1))
                avg_cand = sum(scores) / max(len(scores), 1)
                size_penalty = 0.98 ** max(combo_size - 1, 0)
                final_score = base * (0.85 + 0.15 * avg_cand) * size_penalty
                if historical_for_code and historical_hits:
                    history_score = historical_hits / max(combo_size, 1)
                    final_score += float(eff_cfg.historical_combo_boost) * float(history_score)
                final_score = max(0.0, min(1.0, final_score))
                history_accounts = {account for account in accounts if account in historical_for_code}
                explain = _build_explain_text(
                    selected_basis=selected_basis,
                    rule=rule,
                    hit_tokens=hits_union,
                    history_accounts=history_accounts,
                    usage_reasons=usage_reason_union,
                    residual_target=residual_target,
                    special_add_raw=special_proposal_raw,
                    diff_total=diff_total,
                )

                amount_diff_abs = abs(float(diff_total))
                if amount_diff_abs <= 0.01:
                    amount_evidence = "exact"
                elif within:
                    amount_evidence = "within_tolerance"
                elif amount_score >= 0.70:
                    amount_evidence = "near"
                else:
                    amount_evidence = "weak"

                range_match = bool(
                    rule
                    and rule.allowed_ranges
                    and any(_konto_in_ranges(account, rule.allowed_ranges) for account in accounts)
                )
                boost_match = bool(
                    rule_boost_set
                    and any(_konto_int(account) in rule_boost_set for account in accounts)
                )
                sign_active = False
                if rule and rule.expected_sign in (-1, 1):
                    expected_sign = int(rule.expected_sign)
                    if expected_sign > 0 and gl_sum_total >= 0:
                        sign_active = True
                    elif expected_sign < 0 and gl_sum_total <= 0:
                        sign_active = True
                keyword_match = bool(rule_keyword_tokens and (hits_union & rule_keyword_tokens))
                used_rulebook = bool(
                    rule is not None
                    and (
                        range_match
                        or boost_match
                        or sign_active
                        or keyword_match
                        or (rule.special_add and special_add_active)
                    )
                )

                anchor_signals: List[str] = []
                if range_match:
                    anchor_signals.append("konto-intervall")
                if boost_match:
                    anchor_signals.append("konto-boost")
                if hits_union:
                    anchor_signals.append("navnetreff")
                if usage_reason_union:
                    anchor_signals.append("kontobruk")
                if history_accounts:
                    anchor_signals.append("historikk")
                if sign_active:
                    anchor_signals.append("sign")
                if special_add_active:
                    anchor_signals.append("special_add")

                evidence: Dict[str, Any] = {
                    "UsedRulebook": used_rulebook,
                    "UsedHistory": bool(history_accounts),
                    "UsedUsage": bool(usage_reason_union),
                    "UsedSpecialAdd": special_add_active,
                    "UsedResidual": used_residual_flag,
                    "AmountEvidence": amount_evidence,
                    "AmountDiffAbs": float(amount_diff_abs),
                    "AnchorSignals": ",".join(anchor_signals),
                }

                combo_rows.append(
                    (
                        SuggestionRow(
                            code=code,
                            accounts=suggestion_accounts,
                            gl_sum=float(gl_sum_total),
                            diff=float(diff_total),
                            score=float(final_score),
                            within_tolerance=bool(within),
                            hit_tokens=tuple(sorted(hits_union)),
                        ),
                        explain,
                        history_accounts,
                        evidence,
                    )
                )

        combo_rows.sort(
            key=lambda item: (
                1 if item[0].within_tolerance else 0,
                item[0].score,
                -abs(item[0].diff),
                -len(item[0].accounts),
            ),
            reverse=True,
        )
        combo_rows = combo_rows[: int(eff_cfg.top_suggestions_per_code)]

        for suggestion, explain, history_accounts, evidence in combo_rows:
            out_rows.append(
                {
                    "Kode": code,
                    "KodeNavn": code_name,
                    "Basis": selected_basis,
                    "A07_Belop": float(target),
                    "ForslagKontoer": ",".join(suggestion.accounts),
                    "GL_Sum": float(suggestion.gl_sum),
                    "Diff": float(suggestion.diff),
                    "Score": float(suggestion.score),
                    "ComboSize": int(len(suggestion.accounts)),
                    "WithinTolerance": bool(suggestion.within_tolerance),
                    "HitTokens": ",".join(suggestion.hit_tokens),
                    "HistoryAccounts": ",".join(sorted(history_accounts)),
                    "Explain": explain,
                    "UsedRulebook": bool(evidence["UsedRulebook"]),
                    "UsedHistory": bool(evidence["UsedHistory"]),
                    "UsedUsage": bool(evidence["UsedUsage"]),
                    "UsedSpecialAdd": bool(evidence["UsedSpecialAdd"]),
                    "UsedResidual": bool(evidence["UsedResidual"]),
                    "AmountEvidence": str(evidence["AmountEvidence"]),
                    "AmountDiffAbs": float(evidence["AmountDiffAbs"]),
                    "AnchorSignals": str(evidence["AnchorSignals"]),
                }
            )

    if not out_rows:
        return pd.DataFrame(columns=list(SUGGEST_OUT_COLUMNS))

    df_out = pd.DataFrame(out_rows)
    return df_out.sort_values(
        by=["WithinTolerance", "Score", "Kode", "ComboSize"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)

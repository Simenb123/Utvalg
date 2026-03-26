from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Optional, Set

import pandas as pd

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
    BASIS_ENDRING,
    BASIS_UB,
    EXCLUDED_A07_CODES,
    SUGGEST_OUT_COLUMNS,
    SuggestConfig,
    SuggestionRow,
)
from .rulebook import RulebookRule, load_rulebook


def _effective_target_value(target: float, rule: Optional[RulebookRule]) -> float:
    if rule is None or rule.expected_sign is None or rule.expected_sign == 0:
        return float(target)
    if rule.expected_sign > 0:
        return abs(float(target))
    return -abs(float(target))


def _special_add_total(
    gl_df: pd.DataFrame,
    *,
    rule: Optional[RulebookRule],
    selected_basis: str,
) -> float:
    if rule is None or not rule.special_add or gl_df is None or gl_df.empty:
        return 0.0

    gl_lookup = gl_df.copy()
    gl_lookup["Konto"] = gl_lookup["Konto"].astype(str).str.strip()
    total = 0.0
    for item in rule.special_add:
        basis_name = str(item.basis or selected_basis or BASIS_UB).strip() or BASIS_UB
        series = _get_series(gl_lookup, basis_name)
        mask = gl_lookup["Konto"] == str(item.account).strip()
        if not bool(mask.any()):
            continue
        try:
            subtotal = float(series.loc[mask].sum())
        except Exception:
            subtotal = 0.0
        total += float(item.weight) * subtotal
    return float(total)


def _build_explain_text(
    *,
    selected_basis: str,
    rule: Optional[RulebookRule],
    hit_tokens: Set[str],
    history_accounts: Set[str],
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
    monthly_df: Optional[pd.DataFrame] = None,
    **_ignored_kwargs: Any,
) -> pd.DataFrame:
    _ = monthly_df
    base_cfg = config or cfg or SuggestConfig()

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
        rule = rulebook.get(code) or rulebook.get(code.strip()) or rulebook.get(code.lower())
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

        current_raw = 0.0
        if mapped_for_code:
            try:
                mask = gl_all["Konto"].isin(mapped_for_code)
                current_raw = float(series_all[mask].sum())
            except Exception:
                current_raw = 0.0

        special_add_raw = _special_add_total(
            gl_all,
            rule=rule,
            selected_basis=selected_basis,
        )
        current_total = float(current_raw + special_add_raw)
        target_abs = abs(float(target_effective))
        current_abs = abs(float(current_total))
        tol = max(float(eff_cfg.tolerance_abs), float(eff_cfg.tolerance_rel) * max(target_abs, 1.0))
        diff_current = float(target_effective - current_total)
        within_current = abs(diff_current) <= tol
        if eff_cfg.hide_solved_codes and within_current:
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
            gl_pool = gl_pool[
                gl_pool.apply(lambda gl_row: _is_a07_relevant_account(gl_row["Konto"], gl_row["__tokens"]), axis=1)
            ].copy()

        if rule and rule.special_add:
            special_accounts = {str(item.account).strip() for item in rule.special_add if str(item.account).strip()}
            if special_accounts:
                gl_pool = gl_pool[~gl_pool["Konto"].isin(special_accounts)].copy()

        if len(gl_pool) == 0:
            continue

        cand_list: List[tuple[str, float, float, tuple[str, ...], bool]] = []
        for _, gl_row in gl_pool.iterrows():
            konto = gl_row["Konto"]
            amount = float(gl_row["__amount"])
            acct_tokens = set(gl_row["__tokens"])
            cand_score, hits = _score_account(
                target_abs=residual_abs,
                gl_amount=amount,
                code_tokens=code_tokens,
                acct_tokens=acct_tokens,
                konto=konto,
                rule=rule,
            )
            is_historical = str(konto).strip() in historical_for_code
            if is_historical:
                cand_score = min(1.0, float(cand_score) + float(eff_cfg.historical_account_boost))
            cand_list.append((konto, amount, cand_score, hits, is_historical))

        cand_list.sort(key=lambda x: (-x[2], 1 if x[4] else 0, abs(float(x[1]) - residual_target)))
        cand_list = cand_list[: int(eff_cfg.candidates_per_code)]
        if not cand_list:
            continue

        combo_rows: List[tuple[SuggestionRow, str, Set[str]]] = []
        max_k = min(max(1, int(eff_cfg.max_combo)), len(cand_list))
        score_denom = max(abs(residual_target) if eff_cfg.use_residual else target_abs, 1.0)

        for combo_size in range(1, max_k + 1):
            for idxs in combinations(range(len(cand_list)), combo_size):
                accounts = tuple(str(cand_list[i][0]) for i in idxs)
                amounts = [float(cand_list[i][1]) for i in idxs]
                scores = [float(cand_list[i][2]) for i in idxs]
                hits_union: Set[str] = set()
                historical_hits = 0
                for i in idxs:
                    hits_union |= set(cand_list[i][3])
                    if cand_list[i][4]:
                        historical_hits += 1

                combo_raw = float(sum(amounts))
                base_total = float(special_add_raw + (current_raw if eff_cfg.use_residual else 0.0))
                total_raw = float(base_total + combo_raw)
                gl_sum_total = float(total_raw)
                diff_total = float(target_effective - gl_sum_total)
                within = abs(diff_total) <= tol

                amount_score = 1.0 - min(abs(diff_total) / score_denom, 1.0)
                token_score = (len(hits_union) / max(len(code_tokens), 1)) if code_tokens else 0.0
                base = 0.70 * amount_score + 0.30 * token_score
                avg_cand = sum(scores) / max(len(scores), 1)
                size_penalty = 0.98 ** (combo_size - 1)
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
                    residual_target=residual_target,
                    special_add_raw=special_add_raw,
                    diff_total=diff_total,
                )

                combo_rows.append(
                    (
                        SuggestionRow(
                            code=code,
                            accounts=accounts,
                            gl_sum=float(gl_sum_total),
                            diff=float(diff_total),
                            score=float(final_score),
                            within_tolerance=bool(within),
                            hit_tokens=tuple(sorted(hits_union)),
                        ),
                        explain,
                        history_accounts,
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

        for suggestion, explain, history_accounts in combo_rows:
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
                }
            )

    if not out_rows:
        return pd.DataFrame(columns=list(SUGGEST_OUT_COLUMNS))

    df_out = pd.DataFrame(out_rows)
    return df_out.sort_values(
        by=["WithinTolerance", "Score", "Kode", "ComboSize"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)

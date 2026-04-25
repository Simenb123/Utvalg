from __future__ import annotations

from itertools import combinations
from typing import Any

import pandas as pd

from .explain import _build_explain_text
from .helpers import (
    _auto_basis_for_code,
    _get_series,
    _is_a07_relevant_account,
    _konto_in_ranges,
    _konto_int,
    _score_account,
    _tokenize,
)
from .models import BASIS_ENDRING, BASIS_UB, PAYROLL_TOKENS, SuggestionRow
from .rule_lookup import _a07_group_members, _effective_target_value, _lookup_rule
from .solver_prepare import SuggestEngineContext
from .special_add import _special_add_details
from .usage import score_usage_signal


def build_code_suggestion_rows(row: pd.Series, *, context: SuggestEngineContext) -> list[dict[str, Any]]:
    eff_cfg = context.eff_cfg
    code = str(row["Kode"])
    code_l = code.strip().lower()
    code_name = str(row.get("KodeNavn", code))
    target = float(row.get("A07_Belop", 0.0))

    code_tokens = _tokenize(code) | _tokenize(code_name)
    for member_code in _a07_group_members(code):
        code_tokens |= _tokenize(member_code)
    rule = _lookup_rule(context.rulebook, code)
    if rule and rule.keywords:
        for keyword in rule.keywords:
            code_tokens |= _tokenize(keyword)

    selected_basis = (
        _auto_basis_for_code(
            code=code,
            code_name=code_name,
            avail=context.avail,
            default_basis=eff_cfg.basis,
            basis_by_code=eff_cfg.basis_by_code,
            rule=rule,
        )
        if eff_cfg.basis_strategy.lower() == "per_code"
        else (
            eff_cfg.basis
            if eff_cfg.basis in context.avail
            else (BASIS_UB if BASIS_UB in context.avail else BASIS_ENDRING)
        )
    )

    basis_series_cache: dict[str, pd.Series] = {}

    def _series_for_basis(selected_basis_name: str) -> pd.Series:
        basis_name = str(selected_basis_name or "").strip() or BASIS_UB
        if basis_name not in basis_series_cache:
            basis_series_cache[basis_name] = _get_series(context.gl_all, basis_name)
        return basis_series_cache[basis_name]

    mapped_for_code = context.code_to_accounts.get(code_l, set())
    historical_for_code = context.historical_code_to_accounts.get(code_l, set())
    series_all = _series_for_basis(selected_basis)
    target_effective = _effective_target_value(target, rule)
    special_current_raw, special_current_accounts = _special_add_details(
        context.gl_all,
        rule=rule,
        selected_basis=selected_basis,
        include_accounts=set(mapped_for_code),
    )

    current_raw = 0.0
    if mapped_for_code:
        try:
            ordinary_mapped_accounts = set(mapped_for_code) - set(special_current_accounts)
            mask = context.gl_all["Konto"].isin(ordinary_mapped_accounts)
            current_raw = float(series_all[mask].sum())
        except Exception:
            current_raw = 0.0

    special_proposal_raw, special_proposal_accounts = _special_add_details(
        context.gl_all,
        rule=rule,
        selected_basis=selected_basis,
        exclude_accounts=context.mapped_accounts_nonexcluded,
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
        return []

    residual_target = float(target_effective)
    if eff_cfg.use_residual and mapped_for_code:
        residual_target = float(target_effective - current_total)
    residual_abs = abs(residual_target)

    gl_pool = context.gl_candidates.copy()
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
            usage = context.usage_by_account.get(str(konto_value or "").strip())
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
        return []

    cand_list: list[tuple[str, float, float, tuple[str, ...], bool, tuple[str, ...], float]] = []
    for _, gl_row in gl_pool.iterrows():
        konto = gl_row["Konto"]
        amount = float(gl_row["__amount"])
        acct_tokens = set(gl_row["__tokens"])
        usage = context.usage_by_account.get(str(konto).strip())
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
        return []

    combo_rows: list[dict[str, Any]] = []
    max_k = min(max(1, int(eff_cfg.max_combo)), len(cand_list))
    score_denom = max(abs(residual_target) if eff_cfg.use_residual else target_abs, 1.0)
    rule_boost_set: set[int] = set(int(x) for x in (rule.boost_accounts if rule else ()))
    rule_keyword_tokens: set[str] = set()
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
            hits_union: set[str] = set()
            historical_hits = 0
            usage_reason_union: set[str] = set()
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

            anchor_signals: list[str] = []
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

            suggestion = SuggestionRow(
                code=code,
                accounts=suggestion_accounts,
                gl_sum=float(gl_sum_total),
                diff=float(diff_total),
                score=float(final_score),
                within_tolerance=bool(within),
                hit_tokens=tuple(sorted(hits_union)),
            )
            combo_rows.append(
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
                    "UsedRulebook": bool(used_rulebook),
                    "UsedHistory": bool(history_accounts),
                    "UsedUsage": bool(usage_reason_union),
                    "UsedSpecialAdd": special_add_active,
                    "UsedResidual": used_residual_flag,
                    "AmountEvidence": amount_evidence,
                    "AmountDiffAbs": float(amount_diff_abs),
                    "AnchorSignals": ",".join(anchor_signals),
                }
            )

    combo_rows.sort(
        key=lambda item: (
            1 if item["WithinTolerance"] else 0,
            item["Score"],
            -abs(item["Diff"]),
            -item["ComboSize"],
        ),
        reverse=True,
    )
    return combo_rows[: int(eff_cfg.top_suggestions_per_code)]


__all__ = ["build_code_suggestion_rows"]

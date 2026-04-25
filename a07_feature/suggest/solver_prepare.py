from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

import pandas as pd

from .helpers import available_basis, _tokenize
from .models import AccountUsageFeatures, EXCLUDED_A07_CODES, SuggestConfig
from .rulebook import Rulebook, load_rulebook
from .usage import build_account_usage_features


@dataclass(frozen=True)
class SuggestEngineContext:
    eff_cfg: SuggestConfig
    rulebook: Rulebook
    a07_df: pd.DataFrame
    gl_all: pd.DataFrame
    gl_candidates: pd.DataFrame
    usage_by_account: dict[str, AccountUsageFeatures]
    code_to_accounts: dict[str, set[str]]
    historical_code_to_accounts: dict[str, set[str]]
    mapped_accounts_nonexcluded: set[str]
    avail: tuple[str, ...]


def _build_usage_by_account(
    usage_features: Optional[Dict[str, AccountUsageFeatures]],
    monthly_df: Optional[pd.DataFrame],
) -> dict[str, AccountUsageFeatures]:
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
    return usage_by_account


def _build_effective_config(
    *,
    base_cfg: SuggestConfig,
    max_combo: Optional[int],
    candidates_per_code: Optional[int],
    top_suggestions_per_code: Optional[int],
    top_codes: Optional[int],
    exclude_mapped_accounts: Optional[bool],
    override_existing_mapping: Optional[bool],
    filter_mode: Optional[str],
    basis_strategy: Optional[str],
    basis: Optional[str],
    basis_by_code: Optional[Dict[str, str]],
    tolerance_rel: Optional[float],
    tolerance_abs: Optional[float],
    rulebook_path: Optional[str],
    use_residual: Optional[bool],
    hide_solved_codes: Optional[bool],
    basis_col: Optional[str],
    max_candidates_per_code: Optional[int],
    override_existing: Optional[bool],
    top_per_code: Optional[int],
) -> SuggestConfig:
    return SuggestConfig(
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


def _normalize_mapping_inputs(
    mapping: Optional[Dict[str, str]],
    mapping_existing: Optional[Dict[str, str]],
    mapping_prior: Optional[Dict[str, str]],
    mapping_previous_year: Optional[Dict[str, str]],
) -> tuple[dict[str, str], dict[str, str], set[str], dict[str, set[str]], dict[str, set[str]]]:
    mapping_used = mapping if mapping is not None else (mapping_existing or {})
    mapping_used = {str(k): ("" if v is None else str(v)) for k, v in (mapping_used or {}).items()}
    mapping_prior_used = mapping_prior if mapping_prior is not None else (mapping_previous_year or {})
    mapping_prior_used = {
        str(k): ("" if v is None else str(v))
        for k, v in (mapping_prior_used or {}).items()
        if str(v).strip()
    }

    mapping_nonempty = {str(k): str(v) for k, v in mapping_used.items() if str(v).strip()}
    mapped_accounts_nonexcluded: Set[str] = {
        str(k)
        for k, v in mapping_nonempty.items()
        if str(v).strip().lower() not in EXCLUDED_A07_CODES
    }

    code_to_accounts: dict[str, set[str]] = {}
    for account, code in mapping_nonempty.items():
        code_l = str(code).strip().lower()
        if not code_l or code_l in EXCLUDED_A07_CODES:
            continue
        code_to_accounts.setdefault(code_l, set()).add(str(account).strip())

    historical_code_to_accounts: dict[str, set[str]] = {}
    for account, code in mapping_prior_used.items():
        code_l = str(code).strip().lower()
        if not code_l or code_l in EXCLUDED_A07_CODES:
            continue
        historical_code_to_accounts.setdefault(code_l, set()).add(str(account).strip())

    return mapping_used, mapping_prior_used, mapped_accounts_nonexcluded, code_to_accounts, historical_code_to_accounts


def _prepare_a07_df(a07_codes_df: pd.DataFrame, eff_cfg: SuggestConfig) -> pd.DataFrame:
    if a07_codes_df is None or len(a07_codes_df) == 0:
        return pd.DataFrame()

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

    from .helpers import _safe_float

    a07_df["Kode"] = a07_df[code_col].astype(str).str.strip()
    a07_df["KodeNavn"] = a07_df[name_col].astype(str) if name_col else a07_df["Kode"]
    a07_df["A07_Belop"] = a07_df[amount_col].map(_safe_float)
    a07_df = a07_df[~a07_df["Kode"].str.lower().isin(EXCLUDED_A07_CODES)].copy()
    a07_df["__abs"] = a07_df["A07_Belop"].abs()
    a07_df = a07_df.sort_values("__abs", ascending=False).head(int(eff_cfg.top_codes)).copy()
    a07_df.drop(columns=["__abs"], inplace=True, errors="ignore")
    return a07_df


def _prepare_gl_frames(
    gl_df: pd.DataFrame,
    *,
    eff_cfg: SuggestConfig,
    mapped_accounts_nonexcluded: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
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
    avail = tuple(available_basis(gl_all))

    gl_candidates = gl_all.copy()
    if (
        eff_cfg.exclude_mapped_accounts
        and not eff_cfg.override_existing_mapping
        and mapped_accounts_nonexcluded
    ):
        gl_candidates = gl_candidates[~gl_candidates["Konto"].isin(mapped_accounts_nonexcluded)].copy()

    return gl_all, gl_candidates, avail


def build_engine_context(
    *,
    a07_codes_df: pd.DataFrame,
    gl_df: pd.DataFrame,
    base_cfg: SuggestConfig,
    mapping: Optional[Dict[str, str]],
    mapping_existing: Optional[Dict[str, str]],
    mapping_prior: Optional[Dict[str, str]],
    mapping_previous_year: Optional[Dict[str, str]],
    usage_features: Optional[Dict[str, AccountUsageFeatures]],
    monthly_df: Optional[pd.DataFrame],
    max_combo: Optional[int],
    candidates_per_code: Optional[int],
    top_suggestions_per_code: Optional[int],
    top_codes: Optional[int],
    exclude_mapped_accounts: Optional[bool],
    override_existing_mapping: Optional[bool],
    filter_mode: Optional[str],
    basis_strategy: Optional[str],
    basis: Optional[str],
    basis_by_code: Optional[Dict[str, str]],
    tolerance_rel: Optional[float],
    tolerance_abs: Optional[float],
    rulebook_path: Optional[str],
    use_residual: Optional[bool],
    hide_solved_codes: Optional[bool],
    basis_col: Optional[str],
    max_candidates_per_code: Optional[int],
    override_existing: Optional[bool],
    top_per_code: Optional[int],
) -> SuggestEngineContext:
    eff_cfg = _build_effective_config(
        base_cfg=base_cfg,
        max_combo=max_combo,
        candidates_per_code=candidates_per_code,
        top_suggestions_per_code=top_suggestions_per_code,
        top_codes=top_codes,
        exclude_mapped_accounts=exclude_mapped_accounts,
        override_existing_mapping=override_existing_mapping,
        filter_mode=filter_mode,
        basis_strategy=basis_strategy,
        basis=basis,
        basis_by_code=basis_by_code,
        tolerance_rel=tolerance_rel,
        tolerance_abs=tolerance_abs,
        rulebook_path=rulebook_path,
        use_residual=use_residual,
        hide_solved_codes=hide_solved_codes,
        basis_col=basis_col,
        max_candidates_per_code=max_candidates_per_code,
        override_existing=override_existing,
        top_per_code=top_per_code,
    )
    usage_by_account = _build_usage_by_account(usage_features, monthly_df)
    (
        _mapping_used,
        _mapping_prior_used,
        mapped_accounts_nonexcluded,
        code_to_accounts,
        historical_code_to_accounts,
    ) = _normalize_mapping_inputs(mapping, mapping_existing, mapping_prior, mapping_previous_year)
    rulebook = load_rulebook(eff_cfg.rulebook_path)
    a07_df = _prepare_a07_df(a07_codes_df, eff_cfg)
    gl_all, gl_candidates, avail = _prepare_gl_frames(
        gl_df,
        eff_cfg=eff_cfg,
        mapped_accounts_nonexcluded=mapped_accounts_nonexcluded,
    )
    return SuggestEngineContext(
        eff_cfg=eff_cfg,
        rulebook=rulebook,
        a07_df=a07_df,
        gl_all=gl_all,
        gl_candidates=gl_candidates,
        usage_by_account=usage_by_account,
        code_to_accounts=code_to_accounts,
        historical_code_to_accounts=historical_code_to_accounts,
        mapped_accounts_nonexcluded=mapped_accounts_nonexcluded,
        avail=avail,
    )


__all__ = ["SuggestEngineContext", "build_engine_context"]

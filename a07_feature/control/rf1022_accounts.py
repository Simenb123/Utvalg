from __future__ import annotations

import pandas as pd

from .rf1022_contract import (
    RF1022_ACCOUNT_COLUMNS,
    rf1022_aga_flag,
    rf1022_flags_from_tags,
    rf1022_taxable_amount,
)
from .rf1022_support import _safe_float, rf1022_post_for_group, rf1022_treatment_details


def _empty_rf1022_accounts_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(RF1022_ACCOUNT_COLUMNS))


def _profile_for_account(profile_document: object | None, account_no: object):
    if profile_document is None:
        return None
    getter = getattr(profile_document, "get", None)
    if not callable(getter):
        return None
    try:
        return getter(str(account_no or "").strip())
    except Exception:
        return None


def _profile_tags(profile: object | None) -> tuple[str, ...]:
    if profile is None:
        return ()
    try:
        return tuple(
            str(tag or "").strip()
            for tag in (getattr(profile, "control_tags", ()) or ())
            if str(tag or "").strip()
        )
    except Exception:
        return ()


def _standard_tags_for_code(code: object) -> tuple[str, ...]:
    code_s = str(code or "").strip()
    if not code_s:
        return ()
    try:
        from a07_feature.payroll.classification_catalog import required_control_tags_for_code
    except Exception:
        return ()
    try:
        return tuple(required_control_tags_for_code(code_s) or ())
    except Exception:
        return ()


def _flags_for_row(row: pd.Series, profile: object | None):
    tags = _profile_tags(profile)
    if tags:
        return rf1022_flags_from_tags(tags, source="profile")
    standard_tags = _standard_tags_for_code(row.get("Kode"))
    if standard_tags:
        return rf1022_flags_from_tags(standard_tags, source="a07_standard")
    return rf1022_flags_from_tags((), source="unknown")


def build_rf1022_accounts_df(
    control_gl_df: pd.DataFrame | None,
    control_statement_df: pd.DataFrame | None,
    group_id: str | None,
    *,
    basis_col: str = "Endring",
    profile_document: object | None = None,
) -> pd.DataFrame:
    from .statement_data import build_control_statement_accounts_df

    accounts_df = build_control_statement_accounts_df(control_gl_df, control_statement_df, group_id)
    if accounts_df is None or accounts_df.empty:
        return _empty_rf1022_accounts_df()

    work = accounts_df.copy()
    value_col = "BelopAktiv" if "BelopAktiv" in work.columns else (basis_col if basis_col in work.columns else "Endring")
    work["Konto"] = work["Konto"].astype(str).str.strip()

    control_row = pd.DataFrame()
    group_text = str(group_id or "").strip()
    if control_statement_df is not None and not control_statement_df.empty and group_text:
        try:
            control_row = control_statement_df.loc[
                control_statement_df["Gruppe"].astype(str).str.strip() == group_text
            ]
        except Exception:
            control_row = pd.DataFrame()

    if control_row is not None and not control_row.empty:
        control_meta = control_row.iloc[0]
        control_label = str(control_meta.get("Navn") or "").strip() or group_text
    else:
        control_label = group_text
    post_no, post_label = rf1022_post_for_group(group_text, control_label)
    post_value = f"Post {post_no} {post_label}".strip()

    rows: list[dict[str, object]] = []
    for _, row in work.iterrows():
        account_no = str(row.get("Konto") or "").strip()
        account_name = str(row.get("Navn") or "").strip()
        ib = _safe_float(row.get("IB")) or 0.0
        ub = _safe_float(row.get("UB")) or 0.0
        movement = _safe_float(row.get(value_col))
        profile = _profile_for_account(profile_document, account_no)
        flags = _flags_for_row(row, profile)

        treatment = rf1022_treatment_details(
            account_no=account_no,
            account_name=account_name,
            ib=ib,
            endring=movement,
            ub=ub,
            group_id=group_text,
            post_text=post_value,
            aga_pliktig=flags.aga_pliktig,
        )
        rows.append(
            {
                "Post": post_value,
                "Konto": account_no,
                "Navn": account_name,
                "KostnadsfortYtelse": treatment.cost_amount,
                "TilleggTidligereAar": treatment.addition_amount,
                "FradragPaalopt": treatment.deduction_amount,
                "SamledeYtelser": rf1022_taxable_amount(
                    treatment.taxable_amount,
                    flags=flags,
                    fallback_when_unknown=flags.source == "unknown",
                ),
                "AgaPliktig": rf1022_aga_flag(flags=flags, treatment_kind=treatment.kind),
                "AgaGrunnlag": treatment.aga_amount,
                "Feriepengegrunnlag": flags.feriepengegrunnlag,
            }
        )

    return pd.DataFrame(rows).reindex(columns=list(RF1022_ACCOUNT_COLUMNS), fill_value="").reset_index(drop=True)


__all__ = ["build_rf1022_accounts_df"]

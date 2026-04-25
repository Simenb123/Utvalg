from __future__ import annotations

from .queue_shared import *  # noqa: F403


def build_control_gl_df(
    gl_df: pd.DataFrame,
    mapping: dict[str, str],
    *,
    basis_col: str = "Endring",
    rulebook: object | None = None,
) -> pd.DataFrame:
    if gl_df is None or gl_df.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    mapping_clean = {str(account).strip(): str(code).strip() for account, code in (mapping or {}).items()}
    effective_rulebook = _load_effective_rulebook(rulebook)
    rows: list[dict[str, object]] = []
    for _, row in gl_df.iterrows():
        konto = str(row.get("Konto") or "").strip()
        if not konto:
            continue
        value_column = control_gl_basis_column_for_account(
            konto,
            row.get("Navn"),
            requested_basis=basis_col,
        )
        mapped_code = mapping_clean.get(konto, "")
        rf1022_group_id = a07_code_rf1022_group(mapped_code) if mapped_code else ""
        rows.append(
            {
                "Konto": konto,
                "Navn": row.get("Navn"),
                "IB": row.get("IB"),
                "Endring": row.get("Endring"),
                "UB": row.get("UB"),
                "BelopAktiv": row.get(value_column),
                "Kol": value_column,
                "Kode": mapped_code,
                "Rf1022GroupId": rf1022_group_id,
                "AliasStatus": _evaluate_alias_status(mapped_code, row.get("Navn"), effective_rulebook),
                "WorkFamily": work_family_for_rf1022_group(rf1022_group_id) if rf1022_group_id else "unknown",
            }
        )

    return pd.DataFrame(rows, columns=list(_CONTROL_GL_DATA_COLUMNS))

def build_control_selected_account_df(
    gl_df: pd.DataFrame,
    mapping: dict[str, str],
    code: str | None,
    *,
    basis_col: str = "Endring",
) -> pd.DataFrame:
    code_s = str(code or "").strip()
    if not code_s:
        return pd.DataFrame(columns=list(_CONTROL_SELECTED_ACCOUNT_COLUMNS))

    control_gl_df = build_control_gl_df(gl_df, mapping, basis_col=basis_col)
    if control_gl_df.empty:
        return pd.DataFrame(columns=list(_CONTROL_SELECTED_ACCOUNT_COLUMNS))

    selected = control_gl_df.loc[control_gl_df["Kode"].astype(str).str.strip() == code_s].copy()
    if selected.empty:
        return pd.DataFrame(columns=list(_CONTROL_SELECTED_ACCOUNT_COLUMNS))
    return selected[list(_CONTROL_SELECTED_ACCOUNT_COLUMNS)].reset_index(drop=True)


from __future__ import annotations

import pandas as pd


def account_int(value: object) -> int | None:
    text = "".join(ch for ch in str(value or "").strip() if ch.isdigit())
    if not text:
        return None
    try:
        return int(text)
    except Exception:
        return None


def normalize_gl_basis_column(value: object, *, default: str = "Endring") -> str:
    basis = str(value or "").strip()
    lookup = {"ib": "IB", "ub": "UB", "endring": "Endring"}
    return lookup.get(basis.casefold(), default)


def control_gl_basis_column_for_account(
    account_no: object,
    account_name: object | None = None,
    *,
    requested_basis: object = "Endring",
) -> str:
    """Return the saldobalance basis column A07 should use for this account row."""

    account_i = account_int(account_no)
    if account_i is not None:
        if 3000 <= account_i <= 9999:
            return "UB"
        if 1000 <= account_i <= 2999:
            return "Endring"

    text = f"{account_no or ''} {account_name or ''}".casefold()
    if any(token in text for token in ("skyldig", "avsatt", "avsetning", "påløpt", "palopt", "periodisering")):
        return "Endring"
    return normalize_gl_basis_column(requested_basis)


def control_gl_basis_column_for_row(row: pd.Series, *, requested_basis: object = "Endring") -> str:
    return control_gl_basis_column_for_account(
        row.get("Konto"),
        row.get("Navn"),
        requested_basis=requested_basis,
    )

from __future__ import annotations

import pandas as pd


def from_trial_balance(tb_df: pd.DataFrame) -> pd.DataFrame:
    if tb_df is None:
        return pd.DataFrame(columns=["Konto", "Navn", "IB", "UB", "Endring", "Belop"])

    out = pd.DataFrame()
    out["Konto"] = tb_df.get("konto", pd.Series(dtype="object")).astype("string").fillna("").str.strip()
    out["Navn"] = tb_df.get("kontonavn", pd.Series(dtype="object")).astype("string").fillna("").str.strip()
    out["IB"] = pd.to_numeric(tb_df.get("ib", pd.Series(dtype="float64")), errors="coerce").fillna(0.0)
    out["UB"] = pd.to_numeric(tb_df.get("ub", pd.Series(dtype="float64")), errors="coerce").fillna(0.0)
    out["Endring"] = pd.to_numeric(tb_df.get("netto", out["UB"] - out["IB"]), errors="coerce").fillna(0.0)
    out["Belop"] = out["Endring"]
    out = out.loc[out["Konto"].str.len() > 0].copy()
    return out.reset_index(drop=True)

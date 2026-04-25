from __future__ import annotations

from .queue_shared import *  # noqa: F403


def build_a07_overview_df(a07_df: pd.DataFrame, reconcile_df: pd.DataFrame) -> pd.DataFrame:
    if a07_df is None or a07_df.empty:
        return _empty_a07_df()

    reconcile_lookup: dict[str, pd.Series] = {}
    if reconcile_df is not None and not reconcile_df.empty and "Kode" in reconcile_df.columns:
        for _, row in reconcile_df.iterrows():
            code = str(row.get("Kode") or "").strip()
            if code:
                reconcile_lookup[code] = row

    rows: list[dict[str, object]] = []
    for _, row in a07_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        navn = str(row.get("Navn") or "").strip()
        belop = row.get("Belop")
        status = "Ikke mappet"
        kontoer = ""
        gl_belop = None
        diff = None
        account_count = 0

        if code.lower() in EXCLUDED_A07_CODES:
            status = "Ekskludert"
        elif code in reconcile_lookup:
            reconcile_row = reconcile_lookup[code]
            kontoer = str(reconcile_row.get("Kontoer") or "").strip()
            gl_belop = reconcile_row.get("GL_Belop")
            diff = reconcile_row.get("Diff")
            account_count = int(reconcile_row.get("AntallKontoer", 0) or 0)
            if bool(reconcile_row.get("WithinTolerance", False)):
                status = "OK"
            elif account_count > 0:
                status = "Avvik"

        rows.append(
            {
                "Kode": code,
                "Navn": navn,
                "Belop": belop,
                "AgaPliktig": row.get("AgaPliktig"),
                "GL_Belop": gl_belop,
                "Diff": diff,
                "AntallKontoer": account_count,
                "Status": status,
                "Kontoer": kontoer,
            }
        )

    return pd.DataFrame(rows, columns=list(_empty_a07_df().columns))

def filter_a07_overview_df(a07_overview_df: pd.DataFrame, filter_key: str | None) -> pd.DataFrame:
    if a07_overview_df is None:
        return _empty_a07_df()
    if a07_overview_df.empty:
        return a07_overview_df.reset_index(drop=True)

    filter_s = str(filter_key or "alle").strip().lower()
    if filter_s in {"", "alle"}:
        return a07_overview_df.reset_index(drop=True)

    if "Status" not in a07_overview_df.columns:
        return a07_overview_df.reset_index(drop=True)

    statuses = a07_overview_df["Status"].astype(str).str.strip()
    if filter_s == "uloste":
        mask = statuses.isin(["Ikke mappet", "Avvik"])
    elif filter_s == "avvik":
        mask = statuses == "Avvik"
    elif filter_s == "ikke_mappet":
        mask = statuses == "Ikke mappet"
    elif filter_s == "ok":
        mask = statuses == "OK"
    elif filter_s == "ekskludert":
        mask = statuses == "Ekskludert"
    else:
        return a07_overview_df.reset_index(drop=True)

    return a07_overview_df.loc[mask].reset_index(drop=True)

def unresolved_codes(a07_overview_df: pd.DataFrame) -> list[str]:
    if a07_overview_df is None or a07_overview_df.empty or "Kode" not in a07_overview_df.columns:
        return []

    filtered = filter_a07_overview_df(a07_overview_df, "uloste")
    return [str(code).strip() for code in filtered["Kode"].tolist() if str(code).strip()]


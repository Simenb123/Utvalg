from __future__ import annotations

from .queue_shared import *  # noqa: F403


def build_history_comparison_df(
    a07_df: pd.DataFrame,
    gl_df: pd.DataFrame,
    *,
    mapping_current: dict[str, str],
    mapping_previous: dict[str, str],
) -> pd.DataFrame:
    if a07_df is None or a07_df.empty:
        return _empty_history_df()

    gl_accounts = _gl_accounts(gl_df)
    rows: list[dict[str, object]] = []
    for _, row in a07_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        navn = str(row.get("Navn") or "").strip()
        current_accounts = accounts_for_code(mapping_current, code)
        previous_accounts = accounts_for_code(mapping_previous, code)
        safe_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=mapping_current,
            mapping_previous=mapping_previous,
            gl_df=gl_df,
        )

        missing_accounts = [account for account in previous_accounts if account not in gl_accounts]
        conflict_accounts = [
            account
            for account in previous_accounts
            if str((mapping_current or {}).get(account) or "").strip()
            and str((mapping_current or {}).get(account) or "").strip() != code
        ]

        notes: list[str] = []
        if code.lower() in EXCLUDED_A07_CODES:
            status = "Ekskludert"
        elif current_accounts and previous_accounts and set(current_accounts) == set(previous_accounts):
            status = "Samme"
            notes.append("Lik fjorarets mapping.")
        elif safe_accounts:
            status = "Klar fra historikk"
            notes.append("Kan brukes direkte.")
        elif previous_accounts and not current_accounts:
            if conflict_accounts:
                status = "Konflikt"
            elif missing_accounts:
                status = "Mangler konto"
            else:
                status = "Historikk"
        elif current_accounts and previous_accounts:
            status = "Avviker"
        elif current_accounts:
            status = "Ny i aar"
        else:
            status = "Ingen historikk"

        if missing_accounts:
            notes.append("Mangler i SB: " + ", ".join(missing_accounts))
        if conflict_accounts:
            notes.append(
                "Konflikt: "
                + ", ".join(
                    f"{account}->{str((mapping_current or {}).get(account) or '').strip()}"
                    for account in conflict_accounts
                )
            )

        rows.append(
            {
                "Kode": code,
                "Navn": navn,
                "AarKontoer": ",".join(current_accounts),
                "HistorikkKontoer": ",".join(previous_accounts),
                "Status": status,
                "KanBrukes": bool(safe_accounts),
                "Merknad": " | ".join(note for note in notes if note),
            }
        )

    return pd.DataFrame(rows, columns=list(_HISTORY_COLUMNS))

def build_control_accounts_summary(
    accounts_df: pd.DataFrame,
    code: str | None,
    *,
    basis_col: str = "Endring",
) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return "Velg A07-kode til hoyre for aa se hva som er koblet na."
    if accounts_df is None or accounts_df.empty:
        return f"Ingen kontoer er koblet til {code_s} ennÃ¥. Velg kontoer til venstre og trykk ->."

    count = int(len(accounts_df))
    value_column = str(basis_col or "Endring").strip()
    if value_column not in accounts_df.columns:
        value_column = "BelopAktiv" if "BelopAktiv" in accounts_df.columns else "Endring"
    total_raw = accounts_df.get(value_column, pd.Series(dtype=object)).sum()
    total_endring = _format_amount(total_raw)
    labels: list[str] = []
    for _, row in accounts_df.head(3).iterrows():
        konto = str(row.get("Konto") or "").strip()
        navn = str(row.get("Navn") or "").strip()
        if konto or navn:
            labels.append(f"{konto} {navn}".strip())
    kontoer = ", ".join(labels)
    if count > 3:
        kontoer = f"{kontoer}, ..."
    if not kontoer:
        kontoer = "-"
    suffix = "konto" if count == 1 else "kontoer"
    return f"{count} {suffix} koblet | {value_column} {total_endring} | {kontoer}"

def build_mapping_history_details(
    code: str | None,
    *,
    mapping_current: dict[str, str],
    mapping_previous: dict[str, str],
    previous_year: str | None = None,
) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return "Velg en kode for aa se historikk."

    current_accounts = accounts_for_code(mapping_current, code_s)
    previous_accounts = accounts_for_code(mapping_previous, code_s)
    current_text = ", ".join(current_accounts) if current_accounts else "ingen mapping i aar"
    previous_text = ", ".join(previous_accounts) if previous_accounts else "ingen tidligere mapping"

    if current_accounts and previous_accounts:
        relation = "Samme som historikk." if set(current_accounts) == set(previous_accounts) else "Avviker fra historikk."
    elif current_accounts:
        relation = "Ny mapping i aar."
    elif previous_accounts:
        relation = "Historikk finnes, men ikke mapping i aar."
    else:
        relation = "Ingen mapping ennÃ¥."

    history_label = previous_year or "tidligere aar"
    return f"{code_s} | I aar: {current_text} | {history_label}: {previous_text} | {relation}"


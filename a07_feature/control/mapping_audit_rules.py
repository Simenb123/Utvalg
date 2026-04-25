from __future__ import annotations

from typing import Mapping

import pandas as pd

from .data import (
    _MAPPING_AUDIT_COLUMNS,
    EXCLUDED_A07_CODES,
    a07_code_rf1022_group,
    control_gl_basis_column_for_account,
)
from .matching import infer_semantic_family


_AUDIT_NON_PAYROLL_SCOPE_TOKENS = (
    "honorar",
    "konsulent",
    "advokat",
    "revisjon",
    "frakt",
    "porto",
    "telefonkost",
    "kontorrekvisita",
    "kontorrekvisita",
    "it drift",
    "drift it",
    "reisekost",
    "representasjon",
    "husleie",
    "strÃ¸m",
    "renhold",
    "markedsfÃ¸ring",
    "annonsering",
)
_AUDIT_SPECIFIC_REFUND_TOKENS = (
    "sykepengerefusjon",
    "refusjon sykepenger",
    "foreldrepengerefusjon",
    "refusjon foreldrepenger",
    "nav refusjon",
)
_AUDIT_PAYROLL_TOKENS = (
    "lÃ¸nn",
    "lonn",
    "ferie",
    "feriepenger",
    "etterlÃ¸nn",
    "etterlonn",
    "trekk",
    "bonus",
    "overtid",
    "timelÃ¸nn",
    "timelonn",
    "fastlÃ¸nn",
    "fastlonn",
)
_AUDIT_BOARD_FEE_TOKENS = (
    "styrehonorar",
    "styre honorar",
    "styre- og",
    "styre og",
    "bedriftsforsamling",
)
_AUDIT_NATURAL_TOKENS = ("telefon", "mobil", "ekom", "kommunikasjon", "forsikring", "bil")
_AUDIT_PENSION_TOKENS = ("pensjon", "otp", "premie")


def _normalize_audit_text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value or "").strip().casefold()


def _audit_account_text(account: object, name: object) -> str:
    return _normalize_audit_text(f"{account or ''} {name or ''}")


def _audit_is_board_fee_scope(account: object, name: object) -> bool:
    text = _audit_account_text(account, name)
    if any(token in text for token in _AUDIT_BOARD_FEE_TOKENS):
        return True
    return "godtgj" in text and "styre" in text


def _audit_is_non_payroll_scope(account: object, name: object) -> bool:
    account_s = str(account or "").strip()
    if _audit_is_board_fee_scope(account_s, name):
        return False
    if account_s.startswith(("3", "6", "7")) and not account_s.startswith(("50", "51", "52", "54", "57", "58")):
        return True
    text = _audit_account_text(account, name)
    return any(token in text for token in _AUDIT_NON_PAYROLL_SCOPE_TOKENS)


def _audit_is_specific_refund(account: object, name: object) -> bool:
    account_s = str(account or "").strip()
    text = _audit_account_text(account, name)
    return account_s == "5800" or any(token in text for token in _AUDIT_SPECIFIC_REFUND_TOKENS)


def _audit_is_generic_refund(account: object, name: object) -> bool:
    text = _audit_account_text(account, name)
    return "refusjon" in text and not _audit_is_specific_refund(account, name)


def _audit_expected_rf1022_group(account: object, name: object) -> str:
    account_s = str(account or "").strip()
    text = _audit_account_text(account, name)
    if _audit_is_board_fee_scope(account_s, name):
        return "100_loenn_ol"
    if any(token in text for token in _AUDIT_PENSION_TOKENS):
        return "112_pensjon"
    if any(token in text for token in _AUDIT_NATURAL_TOKENS):
        return "111_naturalytelser"
    if _audit_is_specific_refund(account_s, name) or _audit_is_generic_refund(account_s, name):
        return "100_refusjon"
    if any(token in text for token in _AUDIT_PAYROLL_TOKENS):
        return "100_loenn_ol"
    return ""


def _audit_suggestion_rows_for_account_code(
    suggestions_df: pd.DataFrame | None,
    account: str,
    code: str,
) -> pd.DataFrame:
    if suggestions_df is None or suggestions_df.empty:
        return pd.DataFrame()
    work = suggestions_df.copy()
    if "Kode" not in work.columns:
        return pd.DataFrame()
    work["Kode"] = work["Kode"].fillna("").astype(str).str.strip()
    work = work.loc[work["Kode"] == code]
    if work.empty:
        return pd.DataFrame()
    suggestion_accounts = (
        work.get("ForslagKontoer", pd.Series(index=work.index, dtype="object"))
        .fillna("")
        .astype(str)
        .str.strip()
    )
    mask = suggestion_accounts.str.split(",").apply(
        lambda values: account in {str(value).strip() for value in values if str(value).strip()}
    )
    return work.loc[mask].copy()


def _audit_evidence_for_mapping(
    *,
    account: str,
    code: str,
    name: object,
    suggestions_df: pd.DataFrame | None,
    mapping_previous: Mapping[str, str] | None,
    profile_state: Mapping[str, object],
) -> set[str]:
    evidence: set[str] = set()
    if not code:
        return evidence

    previous_code = str((mapping_previous or {}).get(account) or "").strip()
    if previous_code:
        evidence.add("historikk")
        if previous_code == code:
            evidence.add("historikk_samme")

    suggestion_rows = _audit_suggestion_rows_for_account_code(
        suggestions_df=suggestions_df,
        account=account,
        code=code,
    )
    if not suggestion_rows.empty:
        evidence.add("belop")
        if any(str(value or "").strip().lower() == "accepted" for value in suggestion_rows.get("SuggestionGuardrail", [])):
            evidence.add("accepted")

    alias_hits = str(profile_state.get("why_summary") or "").strip().casefold()
    if "alias" in alias_hits:
        evidence.add("alias")
    if "katalog" in alias_hits:
        evidence.add("katalog")
    if "kontobruk" in alias_hits:
        evidence.add("kontobruk")
    if "special_add" in alias_hits:
        evidence.add("special_add")
    if str(profile_state.get("source") or "").strip():
        evidence.add(str(profile_state.get("source") or "").strip())
    return evidence


def _audit_status_for_mapping(
    *,
    account: str,
    name: object,
    code: str,
    current_group: str,
    expected_group: str,
    evidence: set[str],
) -> tuple[str, str]:
    if not code:
        return "Uavklart", "Konto mangler A07-kode."
    if code in {"aga", "forskuddstrekk"}:
        return "Feil", "A07-koden er en kontrollverdi og skal ikke brukes som lÃ¸nnskode."
    if str(code or "").strip().casefold() in {str(value).casefold() for value in EXCLUDED_A07_CODES}:
        return "Uavklart", "A07-koden er ekskludert fra RF-1022-bro og krever manuell vurdering."
    if current_group == "uavklart_rf1022":
        return "Uavklart", "A07-koden mangler RF-1022-bro."
    if current_group == "100_loenn_ol" and _audit_is_non_payroll_scope(account, name):
        return "Feil", "Kontoen ser ut som drifts-/honorarkostnad utenfor A07-lonn."
    if current_group == "100_refusjon" and _audit_is_generic_refund(account, name):
        return "Mistenkelig", "Generisk refusjonstekst er ikke nok til trygg refusjonsmapping."
    if current_group and expected_group and current_group != expected_group:
        return "Feil", "Konto og RF-1022-gruppe peker i ulike retninger."
    if current_group and not expected_group and _audit_is_non_payroll_scope(account, name):
        return "Feil", "Kontoen ser ikke ut til aa hore hjemme i A07/RF-1022."

    semantic_evidence = {"alias", "katalog", "kontobruk", "special_add", "accepted"}
    has_semantic = bool(evidence & semantic_evidence)
    has_amount = "belop" in evidence
    if "special_add" in evidence:
        return "Trygg", "Eksplisitt spesialregel for periodisering/balansepost."
    if current_group and expected_group == current_group and (
        has_semantic
        or _audit_is_board_fee_scope(account, name)
        or any(
            token in _audit_account_text(account, name)
            for token in _AUDIT_PAYROLL_TOKENS + _AUDIT_NATURAL_TOKENS + _AUDIT_PENSION_TOKENS
        )
    ):
        return "Trygg", "Konto og RF-1022-gruppe peker samme faglige vei."
    if has_amount and not has_semantic:
        return "Mistenkelig", "Belop alene er ikke nok til trygg mapping."
    if evidence <= {"manual", "historikk"} and "historikk" in evidence:
        return "Mistenkelig", "Historikk alene er ikke nok til trygg mapping."
    if current_group:
        account_family = infer_semantic_family(f"{account} {name}")
        code_family = infer_semantic_family(code)
        if account_family and code_family and account_family == code_family:
            return "Trygg", "Konto og A07-kode har samme fagfamilie."
        return "Uavklart", "Koblingen mangler tydelig faglig evidens."
    return "Uavklart", "Koblingen mangler RF-1022-gruppe."


def build_mapping_audit_df(
    gl_df: pd.DataFrame | None,
    mapping_current: Mapping[str, str] | None,
    *,
    suggestions_df: pd.DataFrame | None = None,
    mapping_previous: Mapping[str, str] | None = None,
    code_profile_state: Mapping[str, Mapping[str, object]] | None = None,
    basis_col: str = "Endring",
    include_unmapped: bool = False,
    rulebook: object | None = None,
) -> pd.DataFrame:
    if gl_df is None or gl_df.empty:
        return pd.DataFrame(columns=list(_MAPPING_AUDIT_COLUMNS))

    mapping_clean = {
        str(account).strip(): str(code).strip()
        for account, code in (mapping_current or {}).items()
        if str(account).strip()
    }
    gl_work = gl_df.copy()
    if "Konto" not in gl_work.columns:
        return pd.DataFrame(columns=list(_MAPPING_AUDIT_COLUMNS))
    gl_work["Konto"] = gl_work["Konto"].astype(str).str.strip()
    gl_work = gl_work.drop_duplicates(subset=["Konto"])
    gl_by_account = {str(row.get("Konto") or "").strip(): row for _, row in gl_work.iterrows()}
    if rulebook is None:
        try:
            from . import data as control_data

            effective_rulebook = control_data.load_rulebook(None)
        except Exception:
            effective_rulebook = {}
    else:
        effective_rulebook = rulebook

    account_order = list(gl_by_account)
    if not include_unmapped:
        account_order = [account for account in account_order if str(mapping_clean.get(account) or "").strip()]

    rows: list[dict[str, object]] = []
    for account in account_order:
        row = gl_by_account.get(account)
        if row is None:
            continue
        name = row.get("Navn")
        code = str(mapping_clean.get(account) or "").strip()
        value_column = control_gl_basis_column_for_account(account, name, requested_basis=basis_col)
        current_group = a07_code_rf1022_group(code) if code else ""
        expected_group = _audit_expected_rf1022_group(account, name)
        evidence = _audit_evidence_for_mapping(
            account=account,
            code=code,
            name=name,
            suggestions_df=suggestions_df,
            mapping_previous=mapping_previous,
            profile_state=(code_profile_state or {}).get(code, {}) if code else {},
        )
        status, reason = _audit_status_for_mapping(
            account=account,
            name=name,
            code=code,
            current_group=current_group,
            expected_group=expected_group,
            evidence=evidence,
        )
        if code:
            from . import data as control_data

            alias_status = control_data.evaluate_a07_rule_name_status(code, name, effective_rulebook)
        else:
            alias_status = ""
        if alias_status == "Ekskludert" and status == "Trygg":
            status = "Mistenkelig"
            reason = (
                f"{reason} Kontonavn er ekskludert for A07-koden."
                if reason
                else "Kontonavn er ekskludert for A07-koden."
            )
        rows.append(
            {
                "Konto": account,
                "Navn": name,
                "CurrentA07Code": code,
                "CurrentRf1022GroupId": current_group,
                "ExpectedRf1022GroupId": expected_group,
                "AliasStatus": alias_status,
                "Kol": value_column,
                "Belop": row.get(value_column),
                "Status": status,
                "Reason": reason,
                "Evidence": ", ".join(sorted(evidence)),
            }
        )

    if not rows:
        return pd.DataFrame(columns=list(_MAPPING_AUDIT_COLUMNS))
    return pd.DataFrame(rows, columns=list(_MAPPING_AUDIT_COLUMNS)).reset_index(drop=True)

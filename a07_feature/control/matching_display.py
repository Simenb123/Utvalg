from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd

from ..suggest.select import UiSuggestionRow, select_best_suggestion_for_code
from .matching_guardrails import _row_flag, _row_has_name_anchor
from .matching_shared import _format_picker_amount, _parse_konto_tokens, _safe_float


def _ui_suggestion_row_from_series(row: pd.Series) -> UiSuggestionRow:
    accounts = _parse_konto_tokens(row.get("ForslagKontoer"))
    hit_raw = row.get("HitTokens")
    if isinstance(hit_raw, (list, tuple, set)):
        hit_tokens = [str(value).strip() for value in hit_raw if str(value).strip()]
    else:
        hit_tokens = [token.strip() for token in str(hit_raw or "").replace(";", ",").split(",") if token.strip()]
    return UiSuggestionRow(
        kode=str(row.get("Kode") or "").strip(),
        kode_navn=str(row.get("KodeNavn") or row.get("Navn") or row.get("Kode") or "").strip(),
        a07_belop=_safe_float(row.get("A07_Belop")),
        gl_kontoer=accounts,
        gl_sum=_safe_float(row.get("GL_Sum")),
        diff=_safe_float(row.get("Diff")),
        score=_safe_float(row.get("Score")),
        combo_size=int(_safe_float(row.get("ComboSize") or len(accounts) or 1)),
        within_tolerance=bool(row.get("WithinTolerance", False)),
        hit_tokens=hit_tokens,
        source_index=int(row.name) if isinstance(row.name, (int, float)) else None,
    )


def ui_suggestion_row_from_series(row: pd.Series) -> UiSuggestionRow:
    return _ui_suggestion_row_from_series(row)


def _row_account_display(
    row: pd.Series | None,
    *,
    raw_key: str,
    display_key: str,
) -> str:
    if row is None:
        return ""
    display = str(row.get(display_key) or "").strip()
    if display:
        return display
    return str(row.get(raw_key) or "").strip()


def _format_present_amount(row: pd.Series | None, key: str) -> str:
    if row is None:
        return ""
    try:
        if hasattr(row, "index") and key not in row.index:
            return ""
    except Exception:
        pass
    value = row.get(key)
    if value is None or value == "":
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return _format_picker_amount(value)


def build_suggestion_status_label(row: pd.Series | None) -> str:
    if row is None:
        return ""
    guardrail = str(row.get("SuggestionGuardrail") or "").strip().lower()
    if guardrail == "accepted":
        return "God kandidat"
    if guardrail == "blocked":
        return "Blokkert"
    score = _safe_float(row.get("Score"))
    if score >= 0.8 or bool(row.get("WithinTolerance", False)):
        return "Må vurderes"
    return "Må vurderes"


def build_suggestion_reason_label(row: pd.Series | None) -> str:
    if row is None:
        return ""
    guardrail_reason = str(row.get("SuggestionGuardrailReason") or "").strip()
    if guardrail_reason:
        return guardrail_reason
    if _row_flag(row, "UsedHistory") or bool(str(row.get("HistoryAccountsVisning") or row.get("HistoryAccounts") or "").strip()):
        return "Treff på historikk"
    if _row_flag(row, "UsedRulebook"):
        return "Treff på regelbok"
    if _row_flag(row, "UsedUsage"):
        return "Treff på kontobruk"
    if _row_has_name_anchor(row):
        return "Treff på navn"
    if str(row.get("AmountEvidence") or "").strip().lower() in {"exact", "within_tolerance", "near"}:
        return "Beløp uten støtte"
    return "Må vurderes"


def best_suggestion_row_for_code(
    suggestions_df: pd.DataFrame,
    code: str | None,
    *,
    locked_codes: set[str] | None = None,
) -> pd.Series | None:
    code_s = str(code or "").strip()
    if not code_s or suggestions_df is None or suggestions_df.empty or "Kode" not in suggestions_df.columns:
        return None

    matches = suggestions_df.loc[suggestions_df["Kode"].astype(str).str.strip() == code_s].copy()
    if matches.empty:
        return None
    if "SuggestionGuardrail" in matches.columns:
        allowed = matches.loc[matches["SuggestionGuardrail"].fillna("").astype(str).str.strip().str.lower() != "blocked"].copy()
        if not allowed.empty:
            matches = allowed

    ui_rows = [_ui_suggestion_row_from_series(row) for _, row in matches.iterrows()]
    best_ui = select_best_suggestion_for_code(ui_rows, code_s, locked_codes=locked_codes)
    if best_ui is None:
        return None

    if best_ui.source_index is not None and best_ui.source_index in matches.index:
        try:
            return matches.loc[best_ui.source_index]
        except Exception:
            pass

    for _, row in matches.iterrows():
        ui_row = _ui_suggestion_row_from_series(row)
        if (
            ui_row.kode == best_ui.kode
            and ui_row.gl_kontoer == best_ui.gl_kontoer
            and abs(ui_row.diff - best_ui.diff) < 1e-9
            and abs((ui_row.score or 0.0) - (best_ui.score or 0.0)) < 1e-9
        ):
            return row
    return None


def build_control_suggestion_summary(code: str | None, suggestions_df: pd.DataFrame, selected_row: pd.Series | None) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return "Velg A07-kode til høyre for å se beste forslag."
    if suggestions_df is None or suggestions_df.empty:
        return f"Ingen forslag funnet for {code_s} akkurat nå."

    count = int(len(suggestions_df))
    row = selected_row if selected_row is not None else suggestions_df.iloc[0]
    accounts = _row_account_display(row, raw_key="ForslagKontoer", display_key="ForslagVisning") or "-"
    diff = _format_picker_amount(row.get("Diff")) or "-"
    a07_amount = _format_present_amount(row, "A07_Belop")
    gl_amount = _format_present_amount(row, "GL_Sum")
    amount_parts = []
    if a07_amount:
        amount_parts.append(f"A07 {a07_amount}")
    if gl_amount:
        amount_parts.append(f"GL forslag {gl_amount}")
    amount_parts.append(f"Diff {diff}")
    status = build_suggestion_status_label(row) or "Vurder"
    return f"Beste forslag for {code_s} | {count} kandidat(er) | Nå valgt: {accounts} | {status} | {' | '.join(amount_parts)}"


def build_control_suggestion_effect_summary(
    code: str | None,
    current_accounts: Sequence[object],
    selected_row: pd.Series | None,
) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return "Velg A07-kode til høyre for å se hva valgt forslag vil gjøre."
    if selected_row is None:
        return f"Velg et forslag for å se hva som vil bli mappet til {code_s}."

    suggested_accounts = _parse_konto_tokens(selected_row.get("ForslagKontoer"))
    if not suggested_accounts:
        return f"Valgt forslag for {code_s} mangler kontoer."

    current = [str(account).strip() for account in (current_accounts or []) if str(account).strip()]
    suggested = [str(account).strip() for account in suggested_accounts if str(account).strip()]
    suggested_text = _row_account_display(selected_row, raw_key="ForslagKontoer", display_key="ForslagVisning")
    current_text = ",".join(current) if current else "ingen mapping"
    if not suggested_text:
        suggested_text = ",".join(suggested)
    diff = _format_picker_amount(selected_row.get("Diff")) or "-"
    a07_amount = _format_present_amount(selected_row, "A07_Belop")
    gl_amount = _format_present_amount(selected_row, "GL_Sum")
    amount_parts = []
    if a07_amount:
        amount_parts.append(f"A07 {a07_amount}")
    if gl_amount:
        amount_parts.append(f"GL forslag {gl_amount}")
    amount_parts.append(f"Diff {diff}")
    amount_text = " | ".join(amount_parts)
    status_text = build_suggestion_status_label(selected_row) or "Vurder"

    if current and set(current) == set(suggested):
        return f"Matcher dagens mapping: {suggested_text} | {status_text} | {amount_text}"
    if not current:
        return f"Vil mappe {suggested_text} til {code_s} | {status_text} | {amount_text}"
    return f"Vil erstatte {current_text} med {suggested_text} | {status_text} | {amount_text}"


def preferred_support_tab_key(
    *,
    current_accounts: Sequence[object],
    history_accounts: Sequence[object],
    best_row: pd.Series | None,
) -> str:
    if any(str(account).strip() for account in current_accounts or ()):
        return "mapping"
    if best_row is not None:
        return "suggestions"
    if any(str(account).strip() for account in history_accounts or ()):
        return "history"
    return "mapping"


@dataclass(frozen=True)
class SmartmappingFallback:
    message: str
    preferred_tab: str


def build_smartmapping_fallback(
    *,
    code: str | None,
    current_accounts: Sequence[object],
    history_accounts: Sequence[object],
    best_row: pd.Series | None,
) -> SmartmappingFallback:
    code_s = str(code or "").strip() or "valgt kode"
    current = [str(account).strip() for account in current_accounts or () if str(account).strip()]
    history = [str(account).strip() for account in history_accounts or () if str(account).strip()]

    if best_row is not None:
        suggested_accounts = _parse_konto_tokens(best_row.get("ForslagKontoer"))
        accounts_text = _row_account_display(best_row, raw_key="ForslagKontoer", display_key="ForslagVisning")
        if not accounts_text:
            accounts_text = ", ".join(suggested_accounts) if suggested_accounts else "ingen kontoer"
        diff = _format_picker_amount(best_row.get("Diff")) or "-"
        score = _format_picker_amount(best_row.get("Score")) or "-"
        if history:
            return SmartmappingFallback(
                message=(
                    f"Ingen trygg automatikk for {code_s}. Beste kandidat er {accounts_text} | Diff {diff} | "
                    f"Score {score}. Historikk finnes også ({', '.join(history)})."
                ),
                preferred_tab="suggestions",
            )
        return SmartmappingFallback(
            message=(
                f"Ingen trygg automatikk for {code_s}. Beste kandidat er {accounts_text} | Diff {diff} | "
                f"Score {score}. Se Beste forslag nederst."
            ),
            preferred_tab="suggestions",
        )

    if history:
        return SmartmappingFallback(
            message=f"Ingen direkte auto brukt for {code_s}. Historikk finnes ({', '.join(history)}). Se Historikk nederst.",
            preferred_tab="history",
        )

    if current:
        return SmartmappingFallback(
            message=f"{code_s} er allerede koblet mot {', '.join(current)}. Se Mapping nederst.",
            preferred_tab="mapping",
        )

    return SmartmappingFallback(
        message=f"Ingen trygg automatikk for {code_s}. Velg kontoer til venstre eller jobb videre i Koblinger / Beste forslag.",
        preferred_tab="mapping",
    )


def compact_accounts(values: Iterable[object], *, max_items: int = 3) -> str:
    tokens = [str(value).strip() for value in values if str(value).strip()]
    if not tokens:
        return "ingen"
    if len(tokens) <= max_items:
        return ", ".join(tokens)
    return ", ".join(tokens[:max_items]) + ", ..."


__all__ = [
    "SmartmappingFallback",
    "best_suggestion_row_for_code",
    "build_control_suggestion_effect_summary",
    "build_control_suggestion_summary",
    "build_smartmapping_fallback",
    "build_suggestion_reason_label",
    "build_suggestion_status_label",
    "compact_accounts",
    "preferred_support_tab_key",
    "ui_suggestion_row_from_series",
]

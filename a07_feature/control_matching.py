from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import pandas as pd

from .suggest.select import UiSuggestionRow, select_best_suggestion_for_code


def _safe_float(value: object) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        try:
            text = str(value or "").strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
            return float(text)
        except Exception:
            return 0.0


def _format_picker_amount(value: object, *, decimals: int = 2) -> str:
    amount = _safe_float(value)
    text = f"{amount:,.{int(decimals)}f}"
    return text.replace(",", " ").replace(".", ",")


def _parse_konto_tokens(raw: object) -> list[str]:
    if isinstance(raw, (list, tuple, set)):
        values = [str(value).strip() for value in raw if str(value).strip()]
    else:
        values = [part.strip() for part in str(raw or "").replace(";", ",").split(",") if part.strip()]

    seen: set[str] = set()
    accounts: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        accounts.append(value)
    return accounts


def build_account_name_lookup(gl_df: pd.DataFrame) -> dict[str, str]:
    if gl_df is None or gl_df.empty or "Konto" not in gl_df.columns:
        return {}

    lookup: dict[str, str] = {}
    names = gl_df["Navn"] if "Navn" in gl_df.columns else pd.Series("", index=gl_df.index)
    for konto, navn in zip(gl_df["Konto"].tolist(), names.tolist()):
        konto_s = str(konto or "").strip()
        if not konto_s:
            continue
        lookup[konto_s] = str(navn or "").strip()
    return lookup


def format_accounts_with_names(
    raw: object,
    *,
    account_names: Mapping[str, str] | None = None,
    joiner: str = " + ",
    max_items: int | None = None,
) -> str:
    accounts = _parse_konto_tokens(raw)
    if not accounts:
        return ""

    visible = accounts
    hidden_count = 0
    if max_items is not None and int(max_items) > 0 and len(accounts) > int(max_items):
        visible = accounts[: int(max_items)]
        hidden_count = len(accounts) - len(visible)

    labels: list[str] = []
    for account in visible:
        name = str((account_names or {}).get(account) or "").strip()
        labels.append(f"{account} {name}".strip())
    if hidden_count > 0:
        labels.append(f"+{hidden_count} til")
    return joiner.join(labels)


def _backfill_evidence_fields(work: pd.DataFrame) -> None:
    """Ensure new evidence columns exist so UI code can trust them even for
    legacy/hand-built DataFrames produced outside the solver."""

    def _str_col(name: str) -> pd.Series:
        if name in work.columns:
            return work[name].fillna("").astype(str)
        return pd.Series([""] * len(work), index=work.index)

    def _bool_col(name: str) -> pd.Series:
        if name in work.columns:
            return work[name].fillna(False).astype(bool)
        return pd.Series([False] * len(work), index=work.index)

    explain_lower = _str_col("Explain").str.lower()
    history_nonempty = _str_col("HistoryAccounts").str.strip().ne("")
    hits_nonempty = _str_col("HitTokens").str.strip().ne("")
    within = _bool_col("WithinTolerance")

    if "UsedHistory" not in work.columns:
        work["UsedHistory"] = history_nonempty
    else:
        work["UsedHistory"] = work["UsedHistory"].fillna(False).astype(bool)

    if "UsedRulebook" not in work.columns:
        work["UsedRulebook"] = explain_lower.str.contains("regel=", regex=False)
    else:
        work["UsedRulebook"] = work["UsedRulebook"].fillna(False).astype(bool)

    if "UsedUsage" not in work.columns:
        work["UsedUsage"] = explain_lower.str.contains("bruk=", regex=False)
    else:
        work["UsedUsage"] = work["UsedUsage"].fillna(False).astype(bool)

    if "UsedSpecialAdd" not in work.columns:
        work["UsedSpecialAdd"] = explain_lower.str.contains("special_add", regex=False)
    else:
        work["UsedSpecialAdd"] = work["UsedSpecialAdd"].fillna(False).astype(bool)

    if "UsedResidual" not in work.columns:
        work["UsedResidual"] = False
    else:
        work["UsedResidual"] = work["UsedResidual"].fillna(False).astype(bool)

    if "AmountDiffAbs" not in work.columns:
        if "Diff" in work.columns:
            work["AmountDiffAbs"] = work["Diff"].apply(lambda v: abs(_safe_float(v)))
        else:
            work["AmountDiffAbs"] = 0.0
    else:
        work["AmountDiffAbs"] = work["AmountDiffAbs"].apply(_safe_float)

    if "AmountEvidence" not in work.columns:
        def _derive_evidence(row: pd.Series) -> str:
            diff_abs = _safe_float(row.get("AmountDiffAbs"))
            if diff_abs <= 0.01 and bool(row.get("WithinTolerance", False)):
                return "exact"
            if bool(row.get("WithinTolerance", False)):
                return "within_tolerance"
            if _safe_float(row.get("Score")) >= 0.70:
                return "near"
            return "weak"

        work["AmountEvidence"] = [_derive_evidence(row) for _, row in work.iterrows()]
    else:
        work["AmountEvidence"] = work["AmountEvidence"].fillna("").astype(str)

    if "AnchorSignals" not in work.columns:
        signals: list[str] = []
        for idx in work.index:
            parts: list[str] = []
            if bool(hits_nonempty.get(idx, False)):
                parts.append("navnetreff")
            if bool(work.at[idx, "UsedUsage"]):
                parts.append("kontobruk")
            if bool(history_nonempty.get(idx, False)):
                parts.append("historikk")
            if bool(work.at[idx, "UsedSpecialAdd"]):
                parts.append("special_add")
            signals.append(",".join(parts))
        work["AnchorSignals"] = signals
    else:
        work["AnchorSignals"] = work["AnchorSignals"].fillna("").astype(str)


def decorate_suggestions_for_display(suggestions_df: pd.DataFrame, gl_df: pd.DataFrame) -> pd.DataFrame:
    if suggestions_df is None:
        return pd.DataFrame()
    if suggestions_df.empty:
        work = suggestions_df.copy()
        if "ForslagVisning" not in work.columns:
            work["ForslagVisning"] = ""
        if "HistoryAccountsVisning" not in work.columns:
            work["HistoryAccountsVisning"] = ""
        return work

    account_names = build_account_name_lookup(gl_df)
    work = suggestions_df.copy()
    if "ForslagKontoer" in work.columns:
        work["ForslagVisning"] = work["ForslagKontoer"].apply(
            lambda value: format_accounts_with_names(value, account_names=account_names)
        )
    elif "ForslagVisning" not in work.columns:
        work["ForslagVisning"] = ""
    if "HistoryAccounts" in work.columns:
        work["HistoryAccountsVisning"] = work["HistoryAccounts"].apply(
            lambda value: format_accounts_with_names(value, account_names=account_names)
        )
    elif "HistoryAccountsVisning" not in work.columns:
        work["HistoryAccountsVisning"] = ""
    _backfill_evidence_fields(work)
    work["Forslagsstatus"] = [build_suggestion_status_label(row) for _, row in work.iterrows()]
    work["HvorforKort"] = [build_suggestion_reason_label(row) for _, row in work.iterrows()]
    return work


def accounts_for_code(mapping: dict[str, str], code: str | None) -> list[str]:
    code_s = str(code or "").strip()
    if not code_s:
        return []

    accounts = [
        str(account).strip()
        for account, mapped_code in (mapping or {}).items()
        if str(account).strip() and str(mapped_code).strip() == code_s
    ]
    return sorted(set(accounts), key=lambda value: (len(value), value))


def _gl_accounts(gl_df: pd.DataFrame) -> set[str]:
    if gl_df is None or gl_df.empty or "Konto" not in gl_df.columns:
        return set()
    return {
        str(account).strip()
        for account in gl_df["Konto"].astype(str).tolist()
        if str(account).strip()
    }


def safe_previous_accounts_for_code(
    code: str | None,
    *,
    mapping_current: dict[str, str],
    mapping_previous: dict[str, str],
    gl_df: pd.DataFrame,
) -> list[str]:
    code_s = str(code or "").strip()
    if not code_s:
        return []

    previous_accounts = accounts_for_code(mapping_previous, code_s)
    if not previous_accounts:
        return []

    if accounts_for_code(mapping_current, code_s):
        return []

    gl_accounts = _gl_accounts(gl_df)
    if any(account not in gl_accounts for account in previous_accounts):
        return []

    for account in previous_accounts:
        existing_code = str((mapping_current or {}).get(account) or "").strip()
        if existing_code and existing_code != code_s:
            return []

    return previous_accounts


def select_safe_history_codes(history_compare_df: pd.DataFrame) -> list[str]:
    if history_compare_df is None or history_compare_df.empty:
        return []
    if "Kode" not in history_compare_df.columns or "KanBrukes" not in history_compare_df.columns:
        return []

    selected: list[str] = []
    seen_codes: set[str] = set()
    for _, row in history_compare_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        if not code or code in seen_codes:
            continue
        if not bool(row.get("KanBrukes", False)):
            continue
        selected.append(code)
        seen_codes.add(code)
    return selected


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


def _row_flag(row: pd.Series, name: str, *, explain_token: str | None = None) -> bool:
    try:
        if name in row.index:
            raw = row.get(name)
            if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
                return bool(raw)
    except Exception:
        pass
    if explain_token:
        explain = str(row.get("Explain", "") or "").lower()
        return explain_token in explain
    return False


def _row_is_strict_auto(row: pd.Series | None) -> bool:
    if row is None:
        return False
    try:
        if not bool(row.get("WithinTolerance", False)):
            return False
        used_history = _row_flag(row, "UsedHistory") or bool(
            str(row.get("HistoryAccounts", "") or "").strip()
        )
        if used_history:
            return True
        used_rulebook = _row_flag(row, "UsedRulebook", explain_token="regel=")
        score = _safe_float(row.get("Score"))
        return used_rulebook and score >= 0.9
    except Exception:
        return False


def build_suggestion_status_label(row: pd.Series | None) -> str:
    if row is None:
        return ""
    if _row_is_strict_auto(row):
        return "Trygg auto"
    if bool(row.get("WithinTolerance", False)):
        return "God kandidat"
    score = _safe_float(row.get("Score"))
    if score >= 0.8:
        return "Maa vurderes"
    return "Svak kandidat"


def build_suggestion_reason_label(row: pd.Series | None) -> str:
    if row is None:
        return ""

    used_history = _row_flag(row, "UsedHistory") or bool(
        str(row.get("HistoryAccountsVisning") or row.get("HistoryAccounts") or "").strip()
    )
    if used_history:
        return "Samme som historikk"

    used_special_add = _row_flag(row, "UsedSpecialAdd", explain_token="special_add")
    combo_size = int(_safe_float(row.get("ComboSize") or 0))
    account_count = len(_parse_konto_tokens(row.get("ForslagKontoer")))
    if used_special_add or combo_size > 1 or account_count > 1:
        return "Kombinerer flere kontoer"

    amount_evidence = str(row.get("AmountEvidence") or "").strip().lower()
    amount_fits = amount_evidence in ("exact", "within_tolerance")
    used_rulebook = _row_flag(row, "UsedRulebook", explain_token="regel=")
    used_usage = _row_flag(row, "UsedUsage", explain_token="bruk=")

    if amount_fits and used_rulebook:
        return "Belop passer mot regelbok"
    if amount_fits and used_usage:
        return "Belop passer mot kontobruk"

    anchors = str(row.get("AnchorSignals") or "").lower()
    if "navnetreff" in anchors or str(row.get("HitTokens") or "").strip():
        return "Treff paa navn"
    if used_rulebook:
        return "Treff paa regelbok"
    if used_usage:
        return "Ligner faktisk kontobruk"
    if amount_evidence == "near":
        return "Belop er naer"
    return "Usikker match"


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
        return "Velg A07-kode til hoyre for aa se beste forslag."
    if suggestions_df is None or suggestions_df.empty:
        return f"Ingen forslag funnet for {code_s} akkurat naa."

    count = int(len(suggestions_df))
    row = selected_row if selected_row is not None else suggestions_df.iloc[0]
    accounts = _row_account_display(row, raw_key="ForslagKontoer", display_key="ForslagVisning") or "-"
    diff = _format_picker_amount(row.get("Diff")) or "-"
    status = build_suggestion_status_label(row) or "Vurder"
    return f"Beste forslag for {code_s} | {count} kandidat(er) | Naa valgt: {accounts} | {status} | Diff {diff}"


def build_control_suggestion_effect_summary(
    code: str | None,
    current_accounts: Sequence[object],
    selected_row: pd.Series | None,
) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return "Velg A07-kode til hoyre for aa se hva valgt forslag vil gjore."
    if selected_row is None:
        return f"Velg et forslag for aa se hva som vil bli mappet til {code_s}."

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
    status_text = build_suggestion_status_label(selected_row) or "Vurder"

    if current and set(current) == set(suggested):
        return f"Matcher dagens mapping: {suggested_text} | {status_text} | Diff {diff}"
    if not current:
        return f"Vil mappe {suggested_text} til {code_s} | {status_text} | Diff {diff}"
    return f"Vil erstatte {current_text} med {suggested_text} | {status_text} | Diff {diff}"


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
                    f"Score {score}. Historikk finnes ogsa ({', '.join(history)})."
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
        message=f"Ingen trygg automatikk for {code_s}. Velg kontoer til venstre eller jobb videre i Koblet naa / Beste forslag.",
        preferred_tab="mapping",
    )


def compact_accounts(values: Iterable[object], *, max_items: int = 3) -> str:
    tokens = [str(value).strip() for value in values if str(value).strip()]
    if not tokens:
        return "ingen"
    if len(tokens) <= max_items:
        return ", ".join(tokens)
    return ", ".join(tokens[:max_items]) + ", ..."

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from formatting import format_number_no

from .. import select_batch_suggestions, select_magic_wand_suggestions
from . import status as a07_control_status
from .statement_model import (
    CONTROL_STATEMENT_COLUMNS as _CANONICAL_CONTROL_STATEMENT_COLUMNS,
    CONTROL_STATEMENT_PAYROLL_ORDER as _CONTROL_MVP_GROUP_ORDER,
    CONTROL_STATEMENT_PAYROLL_SET as _CONTROL_MVP_GROUP_SET,
    CONTROL_STATEMENT_VIEW_ALL,
    CONTROL_STATEMENT_VIEW_LABELS,
    CONTROL_STATEMENT_VIEW_LEGACY,
    CONTROL_STATEMENT_VIEW_PAYROLL,
    CONTROL_STATEMENT_VIEW_UNCLASSIFIED,
    control_statement_view_requires_unclassified,
    empty_control_statement_df as _empty_control_statement_df,
    filter_control_statement_df,
    normalize_control_statement_df,
    normalize_control_statement_view,
)
from .matching import (
    accounts_for_code,
    best_suggestion_row_for_code,
    decorate_suggestions_for_display,
    evaluate_current_mapping_suspicion,
    safe_previous_accounts_for_code,
    ui_suggestion_row_from_series,
)
from .basis import (
    account_int as _shared_account_int,
    control_gl_basis_column_for_account as _shared_control_gl_basis_column_for_account,
    normalize_gl_basis_column as _shared_normalize_gl_basis_column,
)
from .statement_source import build_current_control_statement_rows
from ..suggest.models import EXCLUDED_A07_CODES


_CONTROL_HIDDEN_CODES = {
    "aga",
    "forskuddstrekk",
    "finansskattloenn",
    "finansskattlÃ¸nn",
}

_RF1022_POST_RULES = (
    (100, "LÃ¸nn o.l.", {"100_loenn_ol"}),
    (100, "Refusjon", {"100_refusjon"}),
    (111, "Naturalytelser", {"111_naturalytelser"}),
    (112, "Pensjon", {"112_pensjon"}),
    (100, "Lonn og trekk", {"Lonnskostnad", "Skyldig lonn", "Feriepenger", "Skyldig feriepenger", "Skattetrekk"}),
    (
        110,
        "Arbeidsgiveravgift",
        {
            "Kostnadsfort arbeidsgiveravgift",
            "Kostnadsfort arbeidsgiveravgift av feriepenger",
            "Skyldig arbeidsgiveravgift",
            "Skyldig arbeidsgiveravgift av feriepenger",
        },
    ),
    (120, "Pensjon og refusjon", {"Pensjonskostnad", "Skyldig pensjon", "Refusjon"}),
    (130, "Naturalytelser og styrehonorar", {"Naturalytelse", "Styrehonorar"}),
)

_RF1022_A07_BRIDGE: dict[str, tuple[str, ...]] = {
    "100_loenn_ol": (
        "fastloenn",
        "timeloenn",
        "overtidsgodtgjoerelse",
        "feriepenger",
        "trekkloennForFerie",
        "styrehonorarOgGodtgjoerelseVerv",
        "annet",
    ),
    "100_refusjon": (
        "sumAvgiftsgrunnlagRefusjon",
    ),
    "111_naturalytelser": (
        "elektroniskKommunikasjon",
        "skattepliktigDelForsikringer",
    ),
    "112_pensjon": (
        "tilskuddOgPremieTilPensjon",
    ),
}

_RF1022_GROUP_LABELS: dict[str, str] = {
    "100_loenn_ol": "Post 100 Lonn o.l.",
    "100_refusjon": "Post 100 Refusjon",
    "111_naturalytelser": "Post 111 Naturalytelser",
    "112_pensjon": "Post 112 Pensjon",
}

_WORK_FAMILY_BY_GROUP = {
    "100_loenn_ol": "payroll",
    "100_refusjon": "refund",
    "111_naturalytelser": "natural",
    "112_pensjon": "pension",
}

_CONTROL_COLUMNS = ("A07Post", "A07_Belop", "GL_Belop", "Diff")
_CONTROL_EXTRA_COLUMNS = (
    "Kode",
    "Navn",
    "Status",
    "AntallKontoer",
    "Anbefalt",
    "DagensMapping",
    "Arbeidsstatus",
    "GuidetStatus",
    "GuidetNeste",
    "MatchingReady",
    "SuggestionGuardrail",
    "SuggestionGuardrailReason",
    "CurrentMappingSuspicious",
    "CurrentMappingSuspiciousReason",
    "Rf1022GroupId",
    "WorkFamily",
    "ReconcileStatus",
    "NesteHandling",
    "Locked",
    "Hvorfor",
)
_CONTROL_GL_DATA_COLUMNS = ("Konto", "Navn", "IB", "Endring", "UB", "BelopAktiv", "Kol", "Kode", "Rf1022GroupId", "WorkFamily")
_CONTROL_SELECTED_ACCOUNT_COLUMNS = ("Konto", "Navn", "IB", "Endring", "UB")
_HISTORY_COLUMNS = ("Kode", "Navn", "AarKontoer", "HistorikkKontoer", "Status", "KanBrukes", "Merknad")
_CONTROL_STATEMENT_COLUMNS = _CANONICAL_CONTROL_STATEMENT_COLUMNS
_RF1022_OVERVIEW_COLUMNS = ("GroupId", "Post", "Omraade", "Kontrollgruppe", "GL_Belop", "A07", "Diff", "Status", "AntallKontoer")
_RF1022_ACCOUNT_COLUMNS = (
    "Post",
    "Konto",
    "Navn",
    "KostnadsfortYtelse",
    "TilleggTidligereAar",
    "FradragPaalopt",
    "SamledeYtelser",
    "AgaPliktig",
    "AgaGrunnlag",
    "Feriepengegrunnlag",
)

_RF1022_ACCRUAL_NAME_TOKENS = (
    "skyldig",
    "avsatt",
    "avsetning",
    "pÃ¥lÃ¸pt",
    "pÃ¥lop",
    "palopt",
    "feriepengegjeld",
)

_RF1022_WITHHOLDING_ACCOUNTS = {"2600", "2610", "2690"}
_RF1022_ACCRUAL_PAY_ACCOUNTS = {"2930", "2940", "2945"}
_RF1022_ACCRUAL_AGA_ACCOUNTS = {"2770", "2785", "2931"}
_RF1022_PERIODISATION_PAY_ACCOUNTS = {"5095", "5096"}


@dataclass(frozen=True)
class Rf1022TreatmentDetails:
    kind: str
    cost_amount: float | None
    addition_amount: float | None
    deduction_amount: float | None
    taxable_amount: float | None
    aga_amount: float | None


def _empty_control_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[*_CONTROL_COLUMNS, *_CONTROL_EXTRA_COLUMNS])


def _empty_suggestions_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "Kode",
            "KodeNavn",
            "Basis",
            "A07_Belop",
            "ForslagKontoer",
            "GL_Sum",
            "Diff",
            "Score",
            "ComboSize",
            "WithinTolerance",
            "Explain",
            "HitTokens",
            "HistoryAccounts",
            "ForslagVisning",
            "Forslagsstatus",
            "HvorforKort",
            "SuggestionGuardrail",
            "SuggestionGuardrailReason",
        ]
    )


def _empty_rf1022_overview_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_RF1022_OVERVIEW_COLUMNS))


def _empty_rf1022_accounts_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_RF1022_ACCOUNT_COLUMNS))


def rf1022_group_a07_codes(group_id: object) -> tuple[str, ...]:
    group_s = str(group_id or "").strip()
    if not group_s:
        return ()
    return tuple(_RF1022_A07_BRIDGE.get(group_s, ()))


def rf1022_group_label(group_id: object) -> str:
    group_s = str(group_id or "").strip()
    if not group_s:
        return ""
    return str(_RF1022_GROUP_LABELS.get(group_s) or group_s)


def a07_code_rf1022_group(code: object) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return ""
    for group_id, codes in _RF1022_A07_BRIDGE.items():
        if code_s in codes:
            return group_id
    return "100_loenn_ol"


def work_family_for_rf1022_group(group_id: object) -> str:
    group_s = str(group_id or "").strip()
    if not group_s:
        return "unknown"
    return str(_WORK_FAMILY_BY_GROUP.get(group_s) or "unknown")


def work_family_for_a07_code(code: object) -> str:
    return work_family_for_rf1022_group(a07_code_rf1022_group(code))


def _rf1022_blank_zero(value: float | None) -> float | None:
    if value is None:
        return None
    rounded = round(float(value), 2)
    return None if abs(rounded) < 1e-9 else rounded


def is_rf1022_accrual_account(account_no: object, account_name: object) -> bool:
    account_s = str(account_no or "").strip()
    name_norm = str(account_name or "").strip().casefold()
    if account_s.startswith("29"):
        return True
    return any(token in name_norm for token in _RF1022_ACCRUAL_NAME_TOKENS)


def resolve_rf1022_treatment_kind(
    *,
    account_no: object,
    account_name: object,
    group_id: object = "",
    post_text: object = "",
) -> str:
    account_s = str(account_no or "").strip()
    name_s = str(account_name or "").strip()
    text = f"{account_s} {name_s}".casefold()
    group_s = str(group_id or "").strip()
    label_s = f"{group_s} {str(post_text or '').strip()}".casefold()

    if group_s == "100_refusjon" or "refusjon" in label_s:
        return "refund"
    if group_s == "112_pensjon" or "pensjon" in label_s:
        return "pension"
    if account_s in _RF1022_WITHHOLDING_ACCOUNTS or any(
        token in text for token in ("forskuddstrekk", "pÃ¥leggstrekk", "paleggstrekk")
    ):
        return "withholding"
    if account_s in _RF1022_ACCRUAL_AGA_ACCOUNTS or (
        any(token in text for token in ("arbeidsgiveravgift", "aga"))
        and any(token in text for token in ("skyldig", "pÃ¥lÃ¸pt", "pÃ¥lop", "periodisering"))
    ):
        return "accrual_aga"
    if account_s in _RF1022_ACCRUAL_PAY_ACCOUNTS:
        return "accrual_pay"
    if account_s in _RF1022_PERIODISATION_PAY_ACCOUNTS or (
        "periodisering" in text and any(token in text for token in ("lÃ¸nn", "lonn", "ferie"))
    ):
        return "periodisation_pay"
    if is_rf1022_accrual_account(account_s, name_s) and any(
        token in text for token in ("lÃ¸nn", "lonn", "ferie", "feriepenger", "etterlÃ¸nn", "etterlonn")
    ):
        return "accrual_pay"
    return "cost"


def rf1022_treatment_details(
    *,
    account_no: object,
    account_name: object,
    ib: object,
    endring: object,
    ub: object,
    group_id: object = "",
    post_text: object = "",
    aga_pliktig: bool = False,
) -> Rf1022TreatmentDetails:
    ib_value = _safe_float(ib) or 0.0
    endring_value = _safe_float(endring) or 0.0
    ub_value = _safe_float(ub) or 0.0
    kind = resolve_rf1022_treatment_kind(
        account_no=account_no,
        account_name=account_name,
        group_id=group_id,
        post_text=post_text,
    )

    if kind == "refund":
        return Rf1022TreatmentDetails(
            kind="refund",
            cost_amount=None,
            addition_amount=None,
            deduction_amount=None,
            taxable_amount=None,
            aga_amount=_rf1022_blank_zero(endring_value),
        )
    if kind == "pension":
        return Rf1022TreatmentDetails(
            kind="pension",
            cost_amount=None,
            addition_amount=None,
            deduction_amount=None,
            taxable_amount=None,
            aga_amount=_rf1022_blank_zero(endring_value),
        )
    if kind == "withholding":
        return Rf1022TreatmentDetails(
            kind="withholding",
            cost_amount=None,
            addition_amount=None,
            deduction_amount=None,
            taxable_amount=None,
            aga_amount=None,
        )
    if kind in {"accrual_pay", "accrual_aga"}:
        addition_amount = _rf1022_blank_zero(abs(ib_value))
        deduction_amount = _rf1022_blank_zero(abs(ub_value))
        taxable_amount = None
        if kind == "accrual_pay":
            taxable_amount = _rf1022_blank_zero((addition_amount or 0.0) - (deduction_amount or 0.0))
        return Rf1022TreatmentDetails(
            kind=kind,
            cost_amount=None,
            addition_amount=addition_amount,
            deduction_amount=deduction_amount,
            taxable_amount=taxable_amount,
            aga_amount=_rf1022_blank_zero(
                (
                    (taxable_amount or 0.0)
                    if kind == "accrual_pay"
                    else (addition_amount or 0.0) - (deduction_amount or 0.0)
                )
                if (kind == "accrual_aga" or aga_pliktig)
                else 0.0
            ),
        )
    if kind == "periodisation_pay":
        taxable_amount = _rf1022_blank_zero(endring_value)
        return Rf1022TreatmentDetails(
            kind="periodisation_pay",
            cost_amount=_rf1022_blank_zero(endring_value),
            addition_amount=None,
            deduction_amount=None,
            taxable_amount=taxable_amount,
            aga_amount=_rf1022_blank_zero(taxable_amount if aga_pliktig else 0.0),
        )
    taxable_amount = _rf1022_blank_zero(endring_value)
    return Rf1022TreatmentDetails(
        kind="cost",
        cost_amount=_rf1022_blank_zero(endring_value),
        addition_amount=None,
        deduction_amount=None,
        taxable_amount=taxable_amount,
        aga_amount=_rf1022_blank_zero(taxable_amount if aga_pliktig else 0.0),
    )


def format_rf1022_treatment_text(
    *,
    account_no: object,
    account_name: object,
    ib: object,
    endring: object,
    ub: object,
    group_id: object = "",
    post_text: object = "",
) -> str:
    treatment = rf1022_treatment_details(
        account_no=account_no,
        account_name=account_name,
        ib=ib,
        endring=endring,
        ub=ub,
        group_id=group_id,
        post_text=post_text,
        aga_pliktig=False,
    )
    if treatment.kind == "refund":
        return f"RF-1022: Endring -> refusjon/grunnlag {format_number_no(float(_safe_float(endring) or 0.0), 2)}"
    if treatment.kind == "pension":
        return f"RF-1022: Endring -> pensjonsgrunnlag {format_number_no(float(_safe_float(endring) or 0.0), 2)}"
    if treatment.kind == "withholding":
        return "RF-1022: Trekk-/oppgjørskonto - ingen kostnadsført ytelse"
    if treatment.kind in {"accrual_pay", "accrual_aga"}:
        addition = float(treatment.addition_amount or 0.0)
        deduction = float(treatment.deduction_amount or 0.0)
        net = float(
            treatment.taxable_amount
            if treatment.taxable_amount is not None
            else (addition - deduction)
        )
        return (
            "RF-1022: +|IB| "
            f"{format_number_no(addition, 2)} - |UB| {format_number_no(deduction, 2)}"
            f" = {format_number_no(net, 2)}"
        )
    return f"RF-1022: Endring -> kostnadsført {format_number_no(float(_safe_float(endring) or 0.0), 2)}"


def _empty_a07_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["Kode", "Navn", "Belop", "GL_Belop", "Diff", "AntallKontoer", "Status", "Kontoer"])


def _empty_history_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_HISTORY_COLUMNS))


def _safe_float(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _account_int(value: object) -> int | None:
    return _shared_account_int(value)


def _normalize_gl_basis_column(value: object, *, default: str = "Endring") -> str:
    return _shared_normalize_gl_basis_column(value, default=default)


def control_gl_basis_column_for_account(
    account_no: object,
    account_name: object | None = None,
    *,
    requested_basis: object = "Endring",
) -> str:
    """Return the GL column A07 should use for this account row."""
    return _shared_control_gl_basis_column_for_account(
        account_no,
        account_name,
        requested_basis=requested_basis,
    )


def _format_amount(value: object, decimals: int = 2) -> str:
    amount = _safe_float(value)
    if amount is None:
        return "-"
    return format_number_no(float(amount), int(decimals))


def _parse_konto_tokens(raw: object) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def _gl_accounts(gl_df: pd.DataFrame) -> set[str]:
    if gl_df is None or gl_df.empty or "Konto" not in gl_df.columns:
        return set()
    return {
        str(account).strip()
        for account in gl_df["Konto"].astype(str).tolist()
        if str(account).strip()
    }


def build_control_statement_export_df(
    *,
    client: str | None,
    year: str | int | None,
    gl_df: pd.DataFrame | None,
    reconcile_df: pd.DataFrame | None = None,
    mapping_current: dict[str, str] | None = None,
    include_unclassified: bool = False,
) -> pd.DataFrame:
    client_s = str(client or "").strip()
    if not client_s or gl_df is None or gl_df.empty:
        return _empty_control_statement_df()

    year_i: int | None = None
    year_s = str(year or "").strip()
    if year_s:
        try:
            year_i = int(year_s)
        except Exception:
            year_i = None

    mapping_clean = {
        str(account).strip(): str(code).strip()
        for account, code in (mapping_current or {}).items()
        if str(account).strip()
    }
    reconcile_lookup: dict[str, pd.Series] = {}
    if reconcile_df is not None and not reconcile_df.empty and "Kode" in reconcile_df.columns:
        for _, row in reconcile_df.iterrows():
            code = str(row.get("Kode") or "").strip()
            if code:
                reconcile_lookup[code] = row

    try:
        rows = build_current_control_statement_rows(
            client_s,
            year_i,
            gl_df,
            include_unclassified=bool(include_unclassified),
        )
    except Exception:
        return _empty_control_statement_df()

    export_rows: list[dict[str, object]] = []
    for row in rows:
        accounts = [str(account).strip() for account in row.accounts if str(account).strip()]
        mapped_codes: list[str] = []
        has_unmapped_accounts = False
        for account in accounts:
            mapped_code = str(mapping_clean.get(account) or "").strip()
            if mapped_code:
                mapped_codes.append(mapped_code)
            else:
                has_unmapped_accounts = True

        matched_rows: list[pd.Series] = []
        seen_codes: set[str] = set()
        for raw_code in mapped_codes:
            code = str(raw_code or "").strip()
            if not code or code in seen_codes:
                continue
            match = reconcile_lookup.get(code)
            if match is None:
                continue
            matched_rows.append(match)
            seen_codes.add(code)

        a07_total: float | None = None
        diff_total: float | None = None
        if matched_rows:
            a07_values = [_safe_float(match.get("A07_Belop")) for match in matched_rows]
            diff_values = [_safe_float(match.get("Diff")) for match in matched_rows]
            a07_total = sum(value for value in a07_values if value is not None)
            diff_total = sum(value for value in diff_values if value is not None)

        if not mapped_codes:
            status = "UlÃ¸st"
        elif has_unmapped_accounts or not matched_rows:
            status = "Manuell"
        else:
            within_flags = [bool(match.get("WithinTolerance", False)) for match in matched_rows]
            status = "Ferdig" if within_flags and all(within_flags) else "Manuell"

        export_rows.append(
            {
                "Gruppe": row.group_id,
                "Navn": row.label,
                "IB": row.ib,
                "Endring": row.movement,
                "UB": row.ub,
                "A07": a07_total,
                "Diff": diff_total,
                "Status": status,
                "AntallKontoer": row.account_count,
                "Kontoer": ", ".join(accounts),
                "Kilder": ", ".join(row.source_breakdown),
            }
        )

    rows_df = pd.DataFrame(export_rows)
    if rows_df.empty:
        return _empty_control_statement_df()
    return normalize_control_statement_df(rows_df)


def filter_control_statement_mvp_df(control_statement_df: pd.DataFrame | None) -> pd.DataFrame:
    return filter_control_statement_df(control_statement_df, view=CONTROL_STATEMENT_VIEW_PAYROLL)


def rf1022_post_for_group(group_id: object, label: object | None = None) -> tuple[int, str]:
    group_text = str(group_id or "").strip()
    label_text = str(label or "").strip()
    combined = f"{group_text} {label_text}".casefold()

    for post_no, post_label, exact_groups in _RF1022_POST_RULES:
        exact_lookup = {str(value).casefold() for value in exact_groups}
        if group_text.casefold() in exact_lookup or label_text.casefold() in exact_lookup:
            return int(post_no), str(post_label)

    if "avgift" in combined:
        return 110, "Arbeidsgiveravgift"
    if "pensjon" in combined or "refusjon" in combined:
        return 120, "Pensjon og refusjon"
    if "natural" in combined or "styre" in combined:
        return 130, "Naturalytelser og styrehonorar"
    if any(token in combined for token in ("lonn", "ferie", "trekk")):
        return 100, "Lonn og trekk"
    return 999, "Andre kontrollgrupper"


def build_rf1022_statement_df(
    control_statement_df: pd.DataFrame | None,
    *,
    basis_col: str = "Endring",
) -> pd.DataFrame:
    control_statement_df = normalize_control_statement_df(control_statement_df)
    if control_statement_df.empty:
        return _empty_rf1022_overview_df()

    gl_col = basis_col if basis_col in control_statement_df.columns else "Endring"
    rows: list[dict[str, object]] = []
    for _, row in control_statement_df.iterrows():
        group_id = str(row.get("Gruppe") or "").strip()
        label = str(row.get("Navn") or "").strip() or group_id
        if not group_id and not label:
            continue
        post_no, post_label = rf1022_post_for_group(group_id, label)
        rows.append(
            {
                "GroupId": group_id or label,
                "Post": str(post_no),
                "Omraade": post_label,
                "Kontrollgruppe": label,
                "GL_Belop": row.get(gl_col),
                "A07": row.get("A07"),
                "Diff": row.get("Diff"),
                "Status": row.get("Status"),
                "AntallKontoer": row.get("AntallKontoer"),
                "WorkFamily": work_family_for_rf1022_group(group_id or label),
                "_post_sort": post_no,
            }
        )

    if not rows:
        return _empty_rf1022_overview_df()

    view_df = pd.DataFrame(rows)
    view_df = view_df.sort_values(by=["_post_sort", "Kontrollgruppe", "GroupId"], kind="stable")
    return view_df.drop(columns=["_post_sort"], errors="ignore").reset_index(drop=True)


def build_rf1022_statement_summary(
    rf1022_df: pd.DataFrame | None,
    *,
    tag_totals: dict[str, float] | None = None,
) -> str:
    if rf1022_df is None or rf1022_df.empty:
        return "Ingen poster i kontrolloppstillingen."

    def _sum_col(column_id: str) -> str:
        if column_id not in rf1022_df.columns:
            return "-"
        series = pd.to_numeric(rf1022_df[column_id], errors="coerce").fillna(0.0)
        return format_number_no(float(series.sum()), 2)

    parts = [
        f"Poster {len(rf1022_df)}",
        f"GL {_sum_col('GL_Belop')}",
        f"A07 {_sum_col('A07')}",
        f"Diff {_sum_col('Diff')}",
    ]
    totals = dict(tag_totals or {})
    if totals:
        parts.extend(
            [
                f"Opplysningspliktig {format_number_no(float(totals.get('opplysningspliktig', 0.0)), 2)}",
                f"AGA-pliktig {format_number_no(float(totals.get('aga_pliktig', 0.0)), 2)}",
                f"Finansskatt {format_number_no(float(totals.get('finansskatt_pliktig', 0.0)), 2)}",
            ]
        )
    return " | ".join(parts)


def build_control_statement_accounts_df(
    gl_df: pd.DataFrame,
    control_statement_df: pd.DataFrame,
    group_id: str | None,
) -> pd.DataFrame:
    group_s = str(group_id or "").strip()
    if not group_s:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))
    control_statement_df = normalize_control_statement_df(control_statement_df)
    if gl_df is None or gl_df.empty or control_statement_df.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    matches = control_statement_df.loc[control_statement_df["Gruppe"].astype(str).str.strip() == group_s]
    if matches.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    row = matches.iloc[0]
    accounts = _parse_konto_tokens(row.get("Kontoer"))
    if not accounts:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    selected = gl_df.loc[gl_df["Konto"].astype(str).str.strip().isin(accounts)].copy()
    if selected.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    order = {account: idx for idx, account in enumerate(accounts)}
    selected["Konto"] = selected["Konto"].astype(str).str.strip()
    selected["_order"] = selected["Konto"].map(order).fillna(len(order))
    selected = selected.sort_values(by=["_order", "Konto"], kind="stable")
    if "BelopAktiv" not in selected.columns:
        selected["BelopAktiv"] = selected.get("Endring")
    if "Kol" not in selected.columns:
        selected["Kol"] = "Endring"
    selected = selected.reindex(columns=list(_CONTROL_GL_DATA_COLUMNS), fill_value="")
    return selected.reset_index(drop=True)


def build_rf1022_accounts_df(
    control_gl_df: pd.DataFrame | None,
    control_statement_df: pd.DataFrame | None,
    group_id: str | None,
    *,
    basis_col: str = "Endring",
    profile_document: object | None = None,
) -> pd.DataFrame:
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

    def _profile_for_account(account_no: object):
        if profile_document is None:
            return None
        getter = getattr(profile_document, "get", None)
        if not callable(getter):
            return None
        try:
            return getter(str(account_no or "").strip())
        except Exception:
            return None

    def _has_tag(profile: object | None, tag: str) -> bool:
        if profile is None:
            return False
        try:
            tags = tuple(getattr(profile, "control_tags", ()) or ())
        except Exception:
            tags = ()
        return str(tag or "").strip() in tags

    def _blank_zero(value: float | None) -> float | None:
        if value is None:
            return None
        return None if abs(float(value)) < 1e-9 else float(value)

    rows: list[dict[str, object]] = []
    for _, row in work.iterrows():
        account_no = str(row.get("Konto") or "").strip()
        account_name = str(row.get("Navn") or "").strip()
        ib = _safe_float(row.get("IB")) or 0.0
        ub = _safe_float(row.get("UB")) or 0.0
        movement = _safe_float(row.get(value_col))
        profile = _profile_for_account(account_no)

        opplysningspliktig = _has_tag(profile, "opplysningspliktig")
        aga_pliktig = _has_tag(profile, "aga_pliktig")
        feriepengegrunnlag = _has_tag(profile, "feriepengergrunnlag")

        treatment = rf1022_treatment_details(
            account_no=account_no,
            account_name=account_name,
            ib=ib,
            endring=movement,
            ub=ub,
            group_id=group_text,
            post_text=post_value,
            aga_pliktig=aga_pliktig,
        )
        aga_flag: bool | None = None if treatment.kind in {"refund", "pension", "withholding", "accrual_aga"} else aga_pliktig

        rows.append(
            {
                "Post": post_value,
                "Konto": account_no,
                "Navn": account_name,
                "KostnadsfortYtelse": treatment.cost_amount,
                "TilleggTidligereAar": treatment.addition_amount,
                "FradragPaalopt": treatment.deduction_amount,
                "SamledeYtelser": treatment.taxable_amount if opplysningspliktig or treatment.taxable_amount is not None else None,
                "AgaPliktig": aga_flag,
                "AgaGrunnlag": treatment.aga_amount,
                "Feriepengegrunnlag": feriepengegrunnlag,
            }
        )

    return pd.DataFrame(rows).reindex(columns=list(_RF1022_ACCOUNT_COLUMNS), fill_value="").reset_index(drop=True)


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


def filter_suggestions_df(
    suggestions_df: pd.DataFrame,
    *,
    scope_key: str | None,
    selected_code: str | None = None,
    unresolved_code_values: Sequence[str] | None = None,
) -> pd.DataFrame:
    if suggestions_df is None or suggestions_df.empty:
        return _empty_suggestions_df()
    if "Kode" not in suggestions_df.columns:
        return suggestions_df.copy()

    scope_s = str(scope_key or "valgt_kode").strip().lower()
    work = suggestions_df.copy()
    codes = work["Kode"].astype(str).str.strip()

    if scope_s == "valgt_kode":
        code_s = str(selected_code or "").strip()
        if code_s:
            return work.loc[codes == code_s].copy()
        scope_s = "uloste"

    if scope_s == "uloste":
        unresolved_set = {str(code).strip() for code in (unresolved_code_values or []) if str(code).strip()}
        if unresolved_set:
            return work.loc[codes.isin(unresolved_set)].copy()
        return work.copy()

    return work.copy()


def filter_control_search_df(control_df: pd.DataFrame, search_text: object = "") -> pd.DataFrame:
    if control_df is None:
        return _empty_control_df()
    if control_df.empty:
        return control_df.reset_index(drop=True)

    search_s = str(search_text or "").strip().casefold()
    if not search_s:
        return control_df.reset_index(drop=True)

    haystack = pd.Series("", index=control_df.index, dtype="object")
    for column in (
        "A07Post",
        "Kode",
        "Navn",
        "Status",
        "Anbefalt",
        "NesteHandling",
        "DagensMapping",
        "Post",
        "Kontrollgruppe",
        "Omraade",
        "GroupId",
    ):
        if column in control_df.columns:
            haystack = haystack.str.cat(control_df[column].fillna("").astype(str), sep=" ")
    return control_df.loc[haystack.str.casefold().str.contains(search_s, regex=False)].reset_index(drop=True)


def filter_control_visible_codes_df(control_df: pd.DataFrame) -> pd.DataFrame:
    if control_df is None or control_df.empty:
        return _empty_control_df()
    if "Kode" not in control_df.columns:
        return control_df.reset_index(drop=True)
    hidden = {value.casefold() for value in _CONTROL_HIDDEN_CODES}
    codes = control_df["Kode"].fillna("").astype(str).str.strip().str.casefold()
    return control_df.loc[~codes.isin(hidden)].copy().reset_index(drop=True)


def build_control_queue_df(
    a07_overview_df: pd.DataFrame,
    suggestions_df: pd.DataFrame,
    *,
    mapping_current: dict[str, str],
    mapping_previous: dict[str, str],
    gl_df: pd.DataFrame,
    code_profile_state: dict[str, dict[str, object]] | None = None,
    locked_codes: set[str] | None = None,
) -> pd.DataFrame:
    if a07_overview_df is None or a07_overview_df.empty:
        return _empty_control_df()

    if suggestions_df is None:
        suggestions_df = _empty_suggestions_df()
    elif not suggestions_df.empty and "SuggestionGuardrail" not in suggestions_df.columns:
        suggestions_df = decorate_suggestions_for_display(suggestions_df, gl_df)

    locked = {str(code).strip() for code in (locked_codes or set()) if str(code).strip()}
    rows: list[dict[str, object]] = []
    for _, row in a07_overview_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        navn = str(row.get("Navn") or "").strip()
        rf1022_group_id = a07_code_rf1022_group(code)
        work_family = work_family_for_rf1022_group(rf1022_group_id)
        reconcile_status = str(row.get("Status") or "").strip()
        current_accounts = accounts_for_code(mapping_current, code)
        history_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=mapping_current,
            mapping_previous=mapping_previous,
            gl_df=gl_df,
        )
        code_suggestions = suggestions_df.loc[
            suggestions_df.get("Kode", pd.Series("", index=suggestions_df.index)).astype(str).str.strip() == code
        ].copy()
        best_row = best_suggestion_row_for_code(suggestions_df, code, locked_codes=locked)
        profile_state = dict((code_profile_state or {}).get(code) or {})
        profile_source = str(profile_state.get("source") or "").strip().lower()
        has_explicit_mapping = bool(current_accounts)
        locked_flag = bool(code in locked or profile_state.get("locked"))
        needs_control_group = bool(profile_state.get("missing_control_group"))
        needs_control_tags = bool(profile_state.get("missing_control_tags"))
        has_control_conflict = bool(profile_state.get("control_conflict"))
        matching_ready = bool(not code_suggestions.empty)
        suggestion_guardrail = str(best_row.get("SuggestionGuardrail") or "").strip() if best_row is not None else ""
        suggestion_guardrail_reason = (
            str(best_row.get("SuggestionGuardrailReason") or "").strip() if best_row is not None else ""
        )
        current_mapping_suspicious, current_mapping_suspicious_reason = evaluate_current_mapping_suspicion(
            code=code,
            code_name=navn,
            current_accounts=current_accounts,
            history_accounts=history_accounts,
            gl_df=gl_df,
            profile_state=profile_state,
        )
        next_action = a07_control_status.control_next_action_label(
            reconcile_status,
            has_history=bool(history_accounts),
            best_suggestion=best_row,
        )
        if locked_flag:
            work_status = "Ferdig"
        elif has_explicit_mapping and profile_source == "history":
            work_status = "Historikk"
        elif has_explicit_mapping:
            work_status = "Manuell"
        elif next_action in {
            "Bruk historikk.",
            "Bruk beste forslag.",
            "Sammenlign med historikk.",
            "Vurder foreslÃ¥tt mapping.",
            "Aapne historikk for valgt kode.",
            "Se forslag for valgt kode.",
        }:
            work_status = "Forslag"
        else:
            work_status = "UlÃ¸st"
        if work_status == "Ferdig":
            display_status = "Ferdig"
        elif has_control_conflict or needs_control_group:
            display_status = "Krever RF-1022"
        elif needs_control_tags:
            display_status = "Krever lÃ¸nnsflagg"
        elif work_status == "Historikk":
            display_status = "Historikk brukt"
        elif work_status == "Forslag" and bool(history_accounts) and best_row is None:
            display_status = "Historikk klar"
        elif work_status == "Forslag":
            display_status = "Trygt forslag"
        elif work_status == "Manuell":
            display_status = "Kontroller mapping"
        else:
            display_status = "MÃ¥ avklares"

        recommended = a07_control_status.control_recommendation_label(
            has_history=bool(history_accounts),
            best_suggestion=best_row,
        )
        if work_status == "Historikk":
            recommended = "Se historikk"
            next_action = "Sammenlign med historikk."
        elif has_control_conflict:
            recommended = "RF-1022"
            next_action = "Rydd RF-1022-post for mappede kontoer."
        elif needs_control_group:
            recommended = "RF-1022"
            next_action = "Tildel RF-1022-post i Saldobalanse."
        elif needs_control_tags:
            recommended = "LÃ¸nnsflagg"
            next_action = "FullfÃ¸r lÃ¸nnsflagg i Saldobalanse."
        elif work_status == "Manuell":
            recommended = "Kontroller"
            next_action = "Kontroller dagens mapping."
        elif display_status == "Ferdig":
            recommended = "Ferdig"
            next_action = "Ingen handling nÃ¸dvendig."

        if locked_flag:
            guided_status = "Ferdig"
            display_status = "Ferdig"
            recommended = "Ferdig"
            guided_next = "Ingen handling"
            next_action = "Ingen handling nodvendig."
        elif current_mapping_suspicious:
            guided_status = "Mistenkelig kobling"
            display_status = "Mistenkelig kobling"
            recommended = "Se forslag" if best_row is not None else "Kontroller kobling"
            guided_next = "Se forslag" if best_row is not None else "Kontroller kobling"
            next_action = (
                "Se forslag for valgt kode."
                if best_row is not None
                else current_mapping_suspicious_reason or "Kontroller dagens kobling."
            )
        elif best_row is not None and not has_explicit_mapping:
            guided_status = "Har forslag"
            display_status = "Har forslag"
            recommended = "Se forslag"
            guided_next = "Se forslag"
            next_action = suggestion_guardrail_reason or "Se forslag for valgt kode."
        elif bool(history_accounts) and not has_explicit_mapping:
            guided_status = "Har historikk"
            display_status = "Har historikk"
            recommended = "Se historikk"
            guided_next = "Se historikk"
            next_action = "Aapne historikk for valgt kode."
        elif has_control_conflict or needs_control_group or needs_control_tags:
            guided_status = "Lonnskontroll"
            display_status = "Lonnskontroll"
            recommended = "Apne lonnsklassifisering"
            guided_next = "Apne lonnsklassifisering"
            if has_control_conflict:
                next_action = "Rydd RF-1022-post for mappede kontoer."
            elif needs_control_group:
                next_action = "Tildel RF-1022-post i Saldobalanse."
            else:
                next_action = "Fullfor lonnsflagg i Saldobalanse."
        elif has_explicit_mapping:
            guided_status = "Kontroller kobling"
            display_status = "Kontroller kobling"
            recommended = "Kontroller kobling"
            guided_next = "Kontroller kobling"
            next_action = "Kontroller dagens kobling."
        else:
            guided_status = "Maa avklares"
            display_status = "Maa avklares"
            recommended = "Kontroller kobling"
            guided_next = "Kontroller kobling"
            next_action = "Velg koblinger eller vurder forslag."

        display_name = navn or code
        if code and navn and navn.casefold() != code.casefold():
            display_name = f"{navn} ({code})"

        rows.append(
            {
                "A07Post": display_name,
                "Kode": code,
                "Navn": navn,
                "A07_Belop": row.get("Belop"),
                "GL_Belop": row.get("GL_Belop"),
                "Diff": row.get("Diff"),
                "AntallKontoer": row.get("AntallKontoer"),
                "Status": display_status,
                "DagensMapping": ", ".join(current_accounts),
                "Anbefalt": recommended,
                "Arbeidsstatus": work_status,
                "GuidetStatus": guided_status,
                "GuidetNeste": guided_next,
                "MatchingReady": matching_ready,
                "SuggestionGuardrail": suggestion_guardrail,
                "SuggestionGuardrailReason": suggestion_guardrail_reason,
                "CurrentMappingSuspicious": current_mapping_suspicious,
                "CurrentMappingSuspiciousReason": current_mapping_suspicious_reason,
                "Rf1022GroupId": rf1022_group_id,
                "WorkFamily": work_family,
                "ReconcileStatus": reconcile_status,
                "NesteHandling": next_action,
                "Locked": locked_flag,
                "Hvorfor": str(profile_state.get("why_summary") or "").strip(),
            }
        )

    out = pd.DataFrame(rows, columns=[*_CONTROL_COLUMNS, *_CONTROL_EXTRA_COLUMNS])
    if out.empty:
        return out

    status_priority = {"UlÃ¸st": 0, "Forslag": 1, "Historikk": 2, "Manuell": 3, "Ferdig": 4}
    work_status = out.get("Arbeidsstatus", pd.Series(index=out.index, dtype="object")).fillna("").astype(str)
    status_priority = {
        "Mistenkelig kobling": 0,
        "Har forslag": 1,
        "Har historikk": 2,
        "Maa avklares": 3,
        "Lonnskontroll": 4,
        "Kontroller kobling": 5,
        "Ferdig": 6,
    }
    work_status = out.get("GuidetStatus", pd.Series(index=out.index, dtype="object")).fillna("").astype(str)
    diff_abs = pd.to_numeric(out.get("Diff"), errors="coerce").abs()
    a07_abs = pd.to_numeric(out.get("A07_Belop"), errors="coerce").abs()
    belop_abs = diff_abs.where(diff_abs.notna() & diff_abs.ne(0), a07_abs).fillna(0)
    sort_df = out.assign(_status_priority=work_status.map(status_priority).fillna(9), _belop_abs=belop_abs)
    sort_df = sort_df.sort_values(by=["_status_priority", "_belop_abs", "Kode"], ascending=[True, False, True], kind="stable")
    return sort_df.drop(columns=["_status_priority", "_belop_abs"], errors="ignore").reset_index(drop=True)


def build_control_gl_df(
    gl_df: pd.DataFrame,
    mapping: dict[str, str],
    *,
    basis_col: str = "Endring",
) -> pd.DataFrame:
    if gl_df is None or gl_df.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    mapping_clean = {str(account).strip(): str(code).strip() for account, code in (mapping or {}).items()}
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


_RF1022_CANDIDATE_DATA_COLUMNS = (
    "Konto",
    "Navn",
    "Kode",
    "BelopAktiv",
    "Rf1022GroupId",
    "Matchgrunnlag",
    "Belopsgrunnlag",
    "Forslagsstatus",
)


def _suggestion_account_tokens(raw: object) -> list[str]:
    if isinstance(raw, (list, tuple, set)):
        values = [str(value).strip() for value in raw if str(value).strip()]
    else:
        values = [part.strip() for part in str(raw or "").replace(";", ",").split(",") if part.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _suggestion_flag(row: pd.Series, column: str) -> bool:
    try:
        value = row.get(column, False)
    except Exception:
        return False
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "ja", "yes"}
    return bool(value)


def _suggestion_text(row: pd.Series, column: str) -> str:
    try:
        value = row.get(column)
    except Exception:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value or "").strip()


def _suggestion_has_rf1022_anchor(row: pd.Series) -> tuple[bool, str]:
    explain = _suggestion_text(row, "Explain").lower()
    anchor_signals = _suggestion_text(row, "AnchorSignals").lower()
    hit_tokens = _suggestion_text(row, "HitTokens")
    parts: list[str] = []
    if _suggestion_flag(row, "UsedRulebook") or "regel=" in explain:
        parts.append("Regelbok/alias")
    if hit_tokens or "navnetreff" in anchor_signals or "navn=" in explain:
        parts.append(f"Navn/alias: {hit_tokens}" if hit_tokens else "Navn/alias")
    if _suggestion_flag(row, "UsedSpecialAdd") or "special_add" in explain:
        parts.append("Tilleggsregel")
    cleaned = [part for idx, part in enumerate(parts) if part and part not in parts[:idx]]
    return bool(cleaned), ", ".join(cleaned)


def _suggestion_has_amount_support(row: pd.Series) -> tuple[bool, str]:
    evidence = _suggestion_text(row, "AmountEvidence").lower()
    within = _suggestion_flag(row, "WithinTolerance")
    diff_abs = abs(_safe_float(row.get("AmountDiffAbs", row.get("Diff"))) or 0.0)
    if within and evidence in {"", "exact", "within_tolerance"}:
        if diff_abs <= 0.01:
            return True, "Eksakt belop"
        return True, "Innen toleranse"
    if within and not evidence:
        return True, "Innen toleranse"
    return False, ""


_RF1022_SPECIAL_ADD_ACCOUNTS: dict[str, set[str]] = {
    "feriepenger": {"2940"},
}


def _candidate_target_amount(row: pd.Series) -> float:
    target = _safe_float(row.get("A07_Belop"))
    if target is None:
        target = _safe_float(row.get("GL_Sum"))
    return float(target or 0.0)


def _candidate_tolerance(row: pd.Series) -> float:
    target_abs = abs(_candidate_target_amount(row))
    return max(100.0, 0.02 * max(target_abs, 1.0))


def _candidate_account_amount(gl_row: pd.Series, value_col: str) -> float:
    amount = _safe_float(gl_row.get(value_col)) if value_col else None
    if amount is None:
        amount = _safe_float(gl_row.get("BelopAktiv"))
    return float(amount or 0.0)


def _is_special_add_account(row: pd.Series, account: str) -> bool:
    code = _suggestion_text(row, "Kode")
    return account in _RF1022_SPECIAL_ADD_ACCOUNTS.get(code, set()) and (
        _suggestion_flag(row, "UsedSpecialAdd") or "special_add" in _suggestion_text(row, "Explain").lower()
    )


def _refund_account_has_specific_support(row: pd.Series, account: str, account_name: object) -> bool:
    code = _suggestion_text(row, "Kode").casefold()
    code_name = _suggestion_text(row, "KodeNavn").casefold()
    if "sumavgiftsgrunnlagrefusjon" not in code and "refusjon" not in code_name:
        return True
    if str(account).strip() == "5800":
        return True
    text = f"{account_name or ''} {_suggestion_text(row, 'HitTokens')} {_suggestion_text(row, 'Explain')}".casefold()
    return any(token in text for token in ("nav", "sykepenger", "sykepenge", "foreldrepenger", "foreldrepenge"))


def _candidate_account_anchor(
    row: pd.Series,
    gl_row: pd.Series,
    account: str,
    *,
    account_count: int,
) -> tuple[bool, str]:
    if not _refund_account_has_specific_support(row, account, gl_row.get("Navn")):
        return False, ""
    history_accounts = set(_suggestion_account_tokens(row.get("HistoryAccounts")))
    if account in history_accounts:
        return True, "Historikk"
    if _is_special_add_account(row, account):
        return True, "Tilleggsregel"

    hit_tokens = _suggestion_account_tokens(_suggestion_text(row, "HitTokens").replace(" ", ","))
    account_text = f"{account} {gl_row.get('Navn') or ''}".casefold()
    account_hits = [token for token in hit_tokens if token.casefold() and token.casefold() in account_text]
    if account_hits:
        return True, f"Navn/alias: {', '.join(account_hits)}"

    if account_count == 1 and _suggestion_flag(row, "UsedRulebook"):
        return True, "Regelbok/alias"
    if account_count == 1 and _suggestion_flag(row, "UsedUsage"):
        return True, "Kontobruk"
    return False, ""


def _candidate_account_amount_support(
    row: pd.Series,
    gl_row: pd.Series,
    account: str,
    value_col: str,
    *,
    account_count: int,
) -> tuple[bool, str]:
    amount = _candidate_account_amount(gl_row, value_col)
    if _is_special_add_account(row, account) and abs(amount) > 0.000001:
        return True, "Tilleggsregel"

    row_has_amount, row_amount_text = _suggestion_has_amount_support(row)
    if account_count == 1 and row_has_amount:
        return True, row_amount_text

    if not _suggestion_flag(row, "WithinTolerance"):
        return False, ""
    target = _candidate_target_amount(row)
    tolerance = _candidate_tolerance(row)
    if abs(abs(amount) - abs(target)) <= tolerance:
        if abs(abs(amount) - abs(target)) <= 0.01:
            return True, "Eksakt belop"
        return True, "Egen konto innen toleranse"
    return False, ""


def build_rf1022_candidate_df(
    control_gl_df: pd.DataFrame | None,
    suggestions_df: pd.DataFrame | None,
    group_id: object | None,
    *,
    basis_col: str = "Endring",
) -> pd.DataFrame:
    """Build strict RF-1022 account candidates for the compact A07 surface.

    A candidate must be tied to the selected RF-1022 group through the A07
    code bridge and have both semantic/catalog support and amount support.
    History-only and amount-only rows are intentionally excluded.
    """

    empty = pd.DataFrame(columns=list(_RF1022_CANDIDATE_DATA_COLUMNS))
    group_s = str(group_id or "").strip()
    if (
        not group_s
        or suggestions_df is None
        or suggestions_df.empty
        or control_gl_df is None
        or control_gl_df.empty
    ):
        return empty
    if "Kode" not in suggestions_df.columns or "ForslagKontoer" not in suggestions_df.columns:
        return empty

    allowed_codes = set(rf1022_group_a07_codes(group_s))
    if not allowed_codes:
        return empty

    gl_work = control_gl_df.copy()
    if "Konto" not in gl_work.columns:
        return empty
    gl_work["Konto"] = gl_work["Konto"].fillna("").astype(str).str.strip()
    gl_by_account: dict[str, pd.Series] = {}
    for _, gl_row in gl_work.iterrows():
        account = str(gl_row.get("Konto") or "").strip()
        if account and account not in gl_by_account:
            gl_by_account[account] = gl_row

    value_col = "BelopAktiv" if "BelopAktiv" in gl_work.columns else (basis_col if basis_col in gl_work.columns else "")
    if value_col not in gl_work.columns:
        value_col = "Endring" if "Endring" in gl_work.columns else ""

    rows_by_account: dict[str, dict[str, object]] = {}
    for _, row in suggestions_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        if not code or code not in allowed_codes or a07_code_rf1022_group(code) != group_s:
            continue
        if _suggestion_text(row, "SuggestionGuardrail").lower() == "blocked":
            continue
        row_has_anchor, row_match_text = _suggestion_has_rf1022_anchor(row)
        if not row_has_anchor:
            continue
        accounts = _suggestion_account_tokens(row.get("ForslagKontoer"))
        account_count = len(accounts)
        status = (
            "Trygt forslag"
            if _suggestion_text(row, "SuggestionGuardrail").lower() == "accepted"
            else "Maa vurderes"
        )
        for account in accounts:
            gl_row = gl_by_account.get(account)
            if gl_row is None:
                continue
            has_anchor, match_text = _candidate_account_anchor(
                row,
                gl_row,
                account,
                account_count=account_count,
            )
            has_amount, amount_text = _candidate_account_amount_support(
                row,
                gl_row,
                account,
                value_col,
                account_count=account_count,
            )
            if not has_anchor or not has_amount:
                continue
            if row_match_text and row_match_text not in match_text:
                match_text = f"{match_text}, {row_match_text}" if match_text else row_match_text
            candidate = {
                "Konto": account,
                "Navn": str(gl_row.get("Navn") or "").strip(),
                "Kode": code,
                "BelopAktiv": gl_row.get(value_col) if value_col else gl_row.get("BelopAktiv"),
                "Rf1022GroupId": group_s,
                "Matchgrunnlag": match_text,
                "Belopsgrunnlag": amount_text,
                "Forslagsstatus": status,
            }
            existing = rows_by_account.get(account)
            if existing is None or existing.get("Forslagsstatus") != "Trygt forslag":
                rows_by_account[account] = candidate

    if not rows_by_account:
        return empty
    out = pd.DataFrame(rows_by_account.values())
    return out.reindex(columns=list(_RF1022_CANDIDATE_DATA_COLUMNS), fill_value="").sort_values(
        by=["Forslagsstatus", "Konto"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)


def build_rf1022_candidate_df_for_groups(
    control_gl_df: pd.DataFrame | None,
    suggestions_df: pd.DataFrame | None,
    group_ids: Sequence[object] | None = None,
    *,
    basis_col: str = "Endring",
) -> pd.DataFrame:
    """Build RF-1022 candidates across groups for global automatic matching."""

    groups = [
        str(group_id or "").strip()
        for group_id in (group_ids or tuple(_RF1022_A07_BRIDGE.keys()))
        if str(group_id or "").strip()
    ]
    groups = list(dict.fromkeys(groups))
    if not groups:
        return pd.DataFrame(columns=list(_RF1022_CANDIDATE_DATA_COLUMNS))

    frames: list[pd.DataFrame] = []
    for group_id in groups:
        frame = build_rf1022_candidate_df(
            control_gl_df,
            suggestions_df,
            group_id,
            basis_col=basis_col,
        )
        if frame is not None and not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=list(_RF1022_CANDIDATE_DATA_COLUMNS))

    out = pd.concat(frames, ignore_index=True)
    return out.reindex(columns=list(_RF1022_CANDIDATE_DATA_COLUMNS), fill_value="").sort_values(
        by=["Forslagsstatus", "Rf1022GroupId", "Konto"],
        ascending=[False, True, True],
        kind="stable",
    ).reset_index(drop=True)


def rf1022_candidate_tree_tag(row: pd.Series) -> str:
    status = str(row.get("Forslagsstatus") or "").strip()
    return "suggestion_ok" if status == "Trygt forslag" else "suggestion_review"


def filter_control_gl_df(
    control_gl_df: pd.DataFrame,
    *,
    search_text: object = "",
    only_unmapped: bool = False,
    active_only: bool = False,
) -> pd.DataFrame:
    if control_gl_df is None or control_gl_df.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    filtered = control_gl_df.copy()
    if active_only:
        numeric_cols = [column for column in ("IB", "Endring", "UB") if column in filtered.columns]
        if numeric_cols:
            numeric = filtered[numeric_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
            has_activity = numeric.ne(0).any(axis=1)
        else:
            has_activity = pd.Series(False, index=filtered.index)
        if "Kode" in filtered.columns:
            has_mapping = filtered["Kode"].fillna("").astype(str).str.strip() != ""
            filtered = filtered.loc[has_activity | has_mapping].copy()
        else:
            filtered = filtered.loc[has_activity].copy()
    if only_unmapped and "Kode" in filtered.columns:
        filtered = filtered.loc[filtered["Kode"].astype(str).str.strip() == ""].copy()

    search_s = str(search_text or "").strip().casefold()
    if search_s:
        haystack = pd.Series("", index=filtered.index, dtype="object")
        for column in ("Konto", "Navn", "Kode"):
            if column in filtered.columns:
                haystack = haystack.str.cat(filtered[column].fillna("").astype(str), sep=" ")
        filtered = filtered.loc[haystack.str.casefold().str.contains(search_s, regex=False)].copy()

    return filtered.reset_index(drop=True)


def filter_control_queue_by_rf1022_group(
    control_df: pd.DataFrame,
    group_id: object | None,
) -> pd.DataFrame:
    if control_df is None or control_df.empty:
        return _empty_control_df()
    group_s = str(group_id or "").strip()
    if not group_s:
        return control_df.reset_index(drop=True)
    if "Rf1022GroupId" not in control_df.columns:
        return control_df.reset_index(drop=True)
    mask = control_df["Rf1022GroupId"].fillna("").astype(str).str.strip() == group_s
    return control_df.loc[mask].reset_index(drop=True)


def filter_suggestions_for_rf1022_group(
    suggestions_df: pd.DataFrame,
    group_id: object | None,
) -> pd.DataFrame:
    if suggestions_df is None or suggestions_df.empty:
        return _empty_suggestions_df()
    group_s = str(group_id or "").strip()
    if not group_s or "Kode" not in suggestions_df.columns:
        return suggestions_df.reset_index(drop=True)
    allowed_codes = set(rf1022_group_a07_codes(group_s))
    if not allowed_codes:
        return suggestions_df.reset_index(drop=True)
    codes = suggestions_df["Kode"].fillna("").astype(str).str.strip()
    return suggestions_df.loc[codes.isin(allowed_codes)].reset_index(drop=True)


def _family_tag_from_name(family: object, *, suspicious: bool = False) -> str:
    if suspicious:
        return "family_warning"
    family_s = str(family or "").strip().lower()
    if family_s in {"payroll", "refund", "natural", "pension"}:
        return f"family_{family_s}"
    return "family_unknown"


def control_family_tree_tag(row: pd.Series) -> str:
    suspicious = bool(row.get("CurrentMappingSuspicious", False)) or str(row.get("GuidetStatus") or "").strip() == "Mistenkelig kobling"
    family = str(row.get("WorkFamily") or "").strip()
    if not family:
        family = work_family_for_a07_code(row.get("Kode"))
    return _family_tag_from_name(family, suspicious=suspicious)


def rf1022_overview_tree_tag(row: pd.Series) -> str:
    family = str(row.get("WorkFamily") or "").strip()
    if not family:
        family = work_family_for_rf1022_group(row.get("GroupId"))
    return _family_tag_from_name(family)


def control_gl_family_tree_tag(row: pd.Series) -> str:
    mapped_code = str(row.get("Kode") or "").strip()
    if not mapped_code:
        return "family_unknown"
    family = str(row.get("WorkFamily") or "").strip() or work_family_for_a07_code(mapped_code)
    return _family_tag_from_name(family)


def control_queue_tree_tag(row: pd.Series) -> str:
    try:
        diff_value = pd.to_numeric(row.get("Diff"), errors="coerce")
    except Exception:
        diff_value = float("nan")
    if pd.notna(diff_value):
        if abs(float(diff_value)) <= 0.005:
            return "control_done"
        return "control_manual"
    status_s = str(row.get("Arbeidsstatus") or row.get("Status") or "").strip()
    if status_s in {"Forslag", "Historikk"}:
        return "control_review"
    if status_s in {"Ulost", "UlÃ¸st", "Manuell"} or status_s:
        return "control_manual"
    return "control_default"


def control_gl_tree_tag(row: pd.Series, selected_code: str | None, suggested_accounts: Sequence[object] | None = None) -> str:
    _ = (selected_code, suggested_accounts)
    mapped_code = str(row.get("Kode") or "").strip()
    if not mapped_code:
        return "control_gl_unmapped"
    return "control_gl_mapped"


def suggestion_tree_tag(row: pd.Series) -> str:
    try:
        explain = str(row.get("Explain", "") or "").lower()
        has_history = bool(str(row.get("HistoryAccounts", "") or "").strip())
        score = float(row.get("Score") or 0.0)
        visual_strict_auto = bool(row.get("WithinTolerance", False)) and (has_history or ("regel=" in explain and score >= 0.9))
    except Exception:
        visual_strict_auto = False
    if visual_strict_auto:
        return "suggestion_ok"
    try:
        within = bool(row.get("WithinTolerance", False))
    except Exception:
        within = False
    try:
        score = float(row.get("Score") or 0.0)
    except Exception:
        score = 0.0
    if within or score >= 0.8:
        return "suggestion_review"
    return "suggestion_default"


def reconcile_tree_tag(row: pd.Series) -> str:
    try:
        within = bool(row.get("WithinTolerance", False))
    except Exception:
        within = False
    return "reconcile_ok" if within else "reconcile_diff"


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


def a07_suggestion_is_strict_auto(row: pd.Series | dict[str, object]) -> bool:
    getter = getattr(row, "get", None)
    if not callable(getter):
        return False

    def _text(value: object) -> str:
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        return str(value or "").strip()

    def _flag(value: object) -> bool:
        try:
            if pd.isna(value):
                return False
        except Exception:
            pass
        return bool(value)

    try:
        if not _flag(getter("WithinTolerance", False)):
            return False
        guardrail = _text(getter("SuggestionGuardrail", "")).lower()
        if guardrail:
            return guardrail == "accepted"
        if _text(getter("HistoryAccounts", "")):
            return True
        if _flag(getter("UsedHistory", False)):
            return True
        if _flag(getter("UsedRulebook", False)):
            return True
        explain = _text(getter("Explain", "")).lower()
        score = float(getter("Score", 0.0) or 0.0)
        return "regel=" in explain and score >= 0.9
    except Exception:
        return False


def select_batch_suggestion_rows(
    suggestions_df: pd.DataFrame,
    mapping_existing: dict[str, str],
    *,
    min_score: float = 0.85,
    locked_codes: set[str] | None = None,
) -> list[int]:
    if suggestions_df is None or suggestions_df.empty:
        return []
    selected_rows = select_batch_suggestions(
        [ui_suggestion_row_from_series(row) for _, row in suggestions_df.iterrows()],
        mapping_existing,
        min_score=min_score,
        locked_codes=locked_codes,
    )
    strict_indexes = {int(idx) for idx, row in suggestions_df.iterrows() if a07_suggestion_is_strict_auto(row)}
    return [int(row.source_index) for row in selected_rows if row.source_index is not None and int(row.source_index) in strict_indexes]


def select_magic_wand_suggestion_rows(
    suggestions_df: pd.DataFrame,
    mapping_existing: dict[str, str],
    *,
    unresolved_codes: Sequence[object] | None = None,
    locked_codes: set[str] | None = None,
) -> list[int]:
    if suggestions_df is None or suggestions_df.empty:
        return []
    selected_rows = select_magic_wand_suggestions(
        [ui_suggestion_row_from_series(row) for _, row in suggestions_df.iterrows()],
        mapping_existing,
        unresolved_codes=unresolved_codes,
        locked_codes=locked_codes,
    )
    strict_indexes = {int(idx) for idx, row in suggestions_df.iterrows() if a07_suggestion_is_strict_auto(row)}
    return [int(row.source_index) for row in selected_rows if row.source_index is not None and int(row.source_index) in strict_indexes]


def control_queue_tree_tag(row: pd.Series) -> str:
    try:
        diff_value = pd.to_numeric(row.get("Diff"), errors="coerce")
    except Exception:
        diff_value = float("nan")
    if pd.notna(diff_value) and abs(float(diff_value)) <= 0.005:
        return "control_done"
    status_s = str(row.get("GuidetStatus") or row.get("Arbeidsstatus") or row.get("Status") or "").strip()
    if status_s in {"Har forslag", "Har historikk", "Forslag", "Historikk"}:
        return "control_review"
    if status_s in {
        "Mistenkelig kobling",
        "Maa avklares",
        "Lonnskontroll",
        "Kontroller kobling",
        "Ulost",
        "UlÃ¸st",
        "UlÃ¸st",
        "Manuell",
    }:
        return "control_manual"
    if status_s == "Ferdig":
        return "control_done"
    if pd.notna(diff_value):
        return "control_manual"
    if status_s:
        return "control_manual"
    return "control_default"


def suggestion_tree_tag(row: pd.Series) -> str:
    guardrail = str(row.get("SuggestionGuardrail") or "").strip().lower()
    if guardrail == "accepted":
        return "suggestion_ok"
    if guardrail in {"review", "blocked"}:
        return "suggestion_review"
    try:
        explain = str(row.get("Explain", "") or "").lower()
        has_history = bool(str(row.get("HistoryAccounts", "") or "").strip())
        score = float(row.get("Score") or 0.0)
        visual_strict_auto = bool(row.get("WithinTolerance", False)) and (has_history or ("regel=" in explain and score >= 0.9))
    except Exception:
        visual_strict_auto = False
    if visual_strict_auto:
        return "suggestion_ok"
    try:
        if bool(row.get("WithinTolerance", False)) or float(row.get("Score") or 0.0) >= 0.85:
            return "suggestion_review"
    except Exception:
        pass
    return "suggestion_default"

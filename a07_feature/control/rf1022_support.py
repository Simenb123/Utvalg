from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from formatting import format_number_no

from .rf1022_bridge import (
    rf1022_group_label as _bridge_rf1022_group_label,
    resolve_a07_rf1022_group,
)

_RF1022_POST_RULES = (
    (100, "Lønn o.l.", {"100_loenn_ol"}),
    (100, "Refusjon", {"100_refusjon"}),
    (111, "Naturalytelser", {"111_naturalytelser"}),
    (112, "Pensjon", {"112_pensjon"}),
    (999, "Uavklart RF-1022", {"uavklart_rf1022"}),
    (100, "Lønn og trekk", {"Lønnskostnad", "Skyldig lønn", "Feriepenger", "Skyldig feriepenger", "Skattetrekk"}),
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

_WORK_FAMILY_BY_GROUP = {
    "100_loenn_ol": "payroll",
    "100_refusjon": "refund",
    "111_naturalytelser": "natural",
    "112_pensjon": "pension",
    "uavklart_rf1022": "unknown",
}

_RF1022_ACCRUAL_NAME_TOKENS = (
    "skyldig",
    "avsatt",
    "avsetning",
    "påløpt",
    "pålop",
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


def rf1022_group_label(group_id: object) -> str:
    return str(_bridge_rf1022_group_label(group_id) or "")


def a07_code_rf1022_group(code: object) -> str:
    return resolve_a07_rf1022_group(code)


def work_family_for_rf1022_group(group_id: object) -> str:
    group_s = str(group_id or "").strip()
    if not group_s:
        return "unknown"
    return str(_WORK_FAMILY_BY_GROUP.get(group_s) or "unknown")


def work_family_for_a07_code(code: object) -> str:
    return work_family_for_rf1022_group(a07_code_rf1022_group(code))


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
        token in text for token in ("forskuddstrekk", "påleggstrekk", "paleggstrekk")
    ):
        return "withholding"
    if account_s in _RF1022_ACCRUAL_AGA_ACCOUNTS or (
        any(token in text for token in ("arbeidsgiveravgift", "aga"))
        and any(token in text for token in ("skyldig", "påløpt", "pålop", "periodisering"))
    ):
        return "accrual_aga"
    if account_s in _RF1022_ACCRUAL_PAY_ACCOUNTS:
        return "accrual_pay"
    if account_s in _RF1022_PERIODISATION_PAY_ACCOUNTS or (
        "periodisering" in text and any(token in text for token in ("lønn", "lonn", "ferie"))
    ):
        return "periodisation_pay"
    if is_rf1022_accrual_account(account_s, name_s) and any(
        token in text for token in ("lønn", "lonn", "ferie", "feriepenger", "etterlønn", "etterlonn")
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
        return 100, "Lønn og trekk"
    return 999, "Andre kontrollgrupper"


__all__ = [
    "Rf1022TreatmentDetails",
    "_safe_float",
    "a07_code_rf1022_group",
    "format_rf1022_treatment_text",
    "is_rf1022_accrual_account",
    "resolve_rf1022_treatment_kind",
    "rf1022_group_label",
    "rf1022_post_for_group",
    "rf1022_treatment_details",
    "work_family_for_a07_code",
    "work_family_for_rf1022_group",
]

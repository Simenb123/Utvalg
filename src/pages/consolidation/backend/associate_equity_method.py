"""EK-metode for tilknyttede selskaper."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Iterable

import pandas as pd

from .models import (
    AssociateAdjustmentRow,
    AssociateCase,
    ConsolidationProject,
    EliminationJournal,
    EliminationLine,
)


_DEFAULT_LINE_MAPPING = {
    "investment_regnr": 575,
    "result_regnr": 100,
    "other_equity_regnr": 695,
    "retained_earnings_regnr": 705,
}


@dataclass
class AssociateFieldSuggestion:
    field_name: str
    field_label: str
    source_label: str
    raw_amount: float
    share_amount: float
    confidence: float
    source_page: int | None = None
    source_text: str = ""


def _safe_float(value: object) -> float:
    try:
        if value is None:
            return 0.0
        result = float(value)
        return 0.0 if pd.isna(result) else result
    except Exception:
        return 0.0


def _normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    replacements = {
        "æ": "ae",
        "ø": "oe",
        "å": "aa",
        "&": " og ",
        "/": " ",
        "-": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return " ".join(text.split())


def _case_line_mapping(
    case: AssociateCase,
    project_defaults: dict[str, int] | None = None,
) -> dict[str, int]:
    mapping = dict(_DEFAULT_LINE_MAPPING)
    if project_defaults:
        for key, value in project_defaults.items():
            try:
                mapping[str(key)] = int(value)
            except Exception:
                continue
    for key, value in dict(case.line_mapping or {}).items():
        try:
            mapping[str(key)] = int(value)
        except Exception:
            continue
    return mapping


def compute_associate_case_generation_hash(case: AssociateCase) -> str:
    """Stabil hash for journal-relevante inputfelt."""
    payload = {
        "name": case.name,
        "investor_company_id": case.investor_company_id,
        "ownership_pct": round(_safe_float(case.ownership_pct), 6),
        "acquisition_date": case.acquisition_date,
        "opening_carrying_amount": round(_safe_float(case.opening_carrying_amount), 6),
        "share_of_result": round(_safe_float(case.share_of_result), 6),
        "share_of_other_equity": round(_safe_float(case.share_of_other_equity), 6),
        "dividends": round(_safe_float(case.dividends), 6),
        "impairment": round(_safe_float(case.impairment), 6),
        "excess_value_amortization": round(_safe_float(case.excess_value_amortization), 6),
        "line_mapping": _case_line_mapping(case),
        "manual_adjustment_rows": [
            {
                "label": row.label,
                "amount": round(_safe_float(row.amount), 6),
                "offset_regnr": int(row.offset_regnr or 0),
                "description": row.description,
            }
            for row in case.manual_adjustment_rows
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_goodwill_amortization(case: AssociateCase) -> dict[str, float]:
    """Beregn goodwill og årlig amortisering fra kostpris og andel netto eiendeler."""
    cost = _safe_float(case.acquisition_cost)
    net_assets = _safe_float(case.share_of_net_assets_at_acquisition)
    goodwill = cost - net_assets
    useful_life = max(int(case.goodwill_useful_life_years or 5), 1)
    annual = goodwill / useful_life if goodwill != 0.0 else 0.0
    return {
        "acquisition_cost": cost,
        "share_of_net_assets_at_acquisition": net_assets,
        "goodwill": goodwill,
        "goodwill_useful_life_years": useful_life,
        "annual_amortization": annual,
    }


def build_associate_case_calculation(case: AssociateCase) -> dict[str, object]:
    """Beregn bevegelsesbro og tilhørende journalbevegelser."""
    mapping = _case_line_mapping(case)
    movements: list[dict[str, object]] = []

    def add_movement(key: str, label: str, movement: float, offset_regnr: int) -> None:
        amount = _safe_float(movement)
        if abs(amount) <= 0.005:
            return
        movements.append(
            {
                "key": key,
                "label": label,
                "movement": amount,
                "investment_regnr": int(mapping["investment_regnr"]),
                "offset_regnr": int(offset_regnr or 0),
            }
        )

    add_movement("share_of_result", "Andel resultat", _safe_float(case.share_of_result), mapping["result_regnr"])
    add_movement(
        "share_of_other_equity",
        "Andre EK-bevegelser",
        _safe_float(case.share_of_other_equity),
        mapping["other_equity_regnr"],
    )
    add_movement("dividends", "Utbytte", -abs(_safe_float(case.dividends)), mapping["retained_earnings_regnr"])
    add_movement("impairment", "Nedskrivning", -abs(_safe_float(case.impairment)), mapping["result_regnr"])
    add_movement(
        "excess_value_amortization",
        "Merverdi/amortisering",
        -abs(_safe_float(case.excess_value_amortization)),
        mapping["result_regnr"],
    )

    for row in case.manual_adjustment_rows:
        amount = _safe_float(row.amount)
        if abs(amount) <= 0.005:
            continue
        movements.append(
            {
                "key": f"manual:{row.row_id}",
                "label": row.label or "Manuell justering",
                "movement": amount,
                "investment_regnr": int(mapping["investment_regnr"]),
                "offset_regnr": int(row.offset_regnr or 0),
                "description": row.description or "",
                "row_id": row.row_id,
            }
        )

    total_movement = sum(_safe_float(item["movement"]) for item in movements)
    opening = _safe_float(case.opening_carrying_amount)
    closing = opening + total_movement

    goodwill_info = compute_goodwill_amortization(case)

    return {
        "opening_carrying_amount": opening,
        "movements": movements,
        "total_movement": total_movement,
        "closing_carrying_amount": closing,
        "generation_hash": compute_associate_case_generation_hash(case),
        "line_mapping": mapping,
        "goodwill": goodwill_info,
    }


def validate_associate_case(case: AssociateCase, project: ConsolidationProject | None = None) -> list[str]:
    """Valider at saken er klar for generering."""
    issues: list[str] = []
    if not str(case.name or "").strip():
        issues.append("Tilknyttet sak mangler navn.")
    if not str(case.investor_company_id or "").strip():
        issues.append("Tilknyttet sak mangler investor.")
    if project is not None and case.investor_company_id and project.find_company(case.investor_company_id) is None:
        issues.append("Investor finnes ikke i konsolideringsprosjektet.")
    ownership = _safe_float(case.ownership_pct)
    if ownership <= 0.0 or ownership > 100.0:
        issues.append("Eierandel må være mellom 0 og 100 prosent.")

    mapping = _case_line_mapping(case)
    for key in ("investment_regnr", "result_regnr", "other_equity_regnr", "retained_earnings_regnr"):
        if int(mapping.get(key, 0) or 0) <= 0:
            issues.append(f"Mangler gyldig regnskapslinje for {key}.")

    has_core_values = any(
        abs(_safe_float(value)) > 0.005
        for value in (
            case.opening_carrying_amount,
            case.share_of_result,
            case.share_of_other_equity,
            case.dividends,
            case.impairment,
            case.excess_value_amortization,
        )
    )
    has_manual_rows = any(abs(_safe_float(row.amount)) > 0.005 for row in case.manual_adjustment_rows)
    if not has_core_values and not has_manual_rows:
        issues.append("Arbeidspapiret mangler tallgrunnlag.")

    for row in case.manual_adjustment_rows:
        if abs(_safe_float(row.amount)) > 0.005 and int(row.offset_regnr or 0) <= 0:
            issues.append(f"Manuell justering '{row.label or row.row_id}' mangler motpost-regnr.")

    return issues


def build_associate_journal(case: AssociateCase, project: ConsolidationProject) -> EliminationJournal:
    """Bygg låst EK-journal fra tilknyttet sak."""
    issues = validate_associate_case(case, project)
    if issues:
        raise ValueError("\n".join(issues))

    calc = build_associate_case_calculation(case)
    investor_id = str(case.investor_company_id or "").strip()
    lines: list[EliminationLine] = []
    for movement in calc["movements"]:
        amount = _safe_float(movement["movement"])
        if abs(amount) <= 0.005:
            continue
        label = str(movement.get("label", "") or "EK-metode")
        description = str(movement.get("description", "") or "").strip()
        line_desc = f"EK-metode {case.name}: {label}".strip()
        if description:
            line_desc = f"{line_desc} ({description})"
        lines.append(
            EliminationLine(
                regnr=int(movement["investment_regnr"]),
                company_id=investor_id,
                amount=amount,
                description=line_desc,
            )
        )
        lines.append(
            EliminationLine(
                regnr=int(movement["offset_regnr"]),
                company_id=investor_id,
                amount=-amount,
                description=line_desc,
            )
        )

    journal = EliminationJournal(
        name=f"EK-metode: {case.name}",
        voucher_no=project.next_elimination_voucher_no(),
        lines=lines,
        kind="equity_method",
        status="active",
        locked=True,
        locked_reason="Generert fra tilknyttet sak",
        source_associate_case_id=case.case_id,
        generation_hash=str(calc["generation_hash"]),
    )
    if not journal.name:
        journal.name = journal.display_label
    return journal


def sync_associate_case_journal(case: AssociateCase, project: ConsolidationProject) -> EliminationJournal:
    """Opprett eller oppdater journal for saken og marker den som oppdatert."""
    new_journal = build_associate_journal(case, project)
    existing = None
    if case.journal_id:
        existing = project.find_journal(case.journal_id)
    if existing is None:
        for journal in project.eliminations:
            if str(journal.source_associate_case_id or "").strip() == case.case_id:
                existing = journal
                break

    if existing is None:
        project.eliminations.append(new_journal)
        journal = new_journal
    else:
        existing.name = new_journal.name
        existing.lines = new_journal.lines
        existing.kind = new_journal.kind
        existing.status = "active"
        existing.locked = True
        existing.locked_reason = new_journal.locked_reason
        existing.source_associate_case_id = case.case_id
        existing.generation_hash = new_journal.generation_hash
        journal = existing

    case.journal_id = journal.journal_id
    case.generation_hash = journal.generation_hash
    case.last_generated_at = journal.created_at if existing is None else case.last_generated_at or journal.created_at
    case.status = "generated"
    return journal


def mark_associate_case_stale(case: AssociateCase, project: ConsolidationProject | None = None) -> None:
    """Marker sak og journal som utdaterte når input endres."""
    current_hash = compute_associate_case_generation_hash(case)
    if not str(case.journal_id or "").strip():
        case.status = "draft"
        case.generation_hash = current_hash if case.status == "generated" else case.generation_hash
        return
    if case.generation_hash and case.generation_hash == current_hash:
        if case.status != "generated":
            case.status = "generated"
        if project is not None:
            journal = project.find_journal(case.journal_id)
            if journal is not None:
                journal.status = "active"
        return
    case.status = "stale"
    if project is not None:
        journal = project.find_journal(case.journal_id)
        if journal is not None:
            journal.status = "stale"


def delete_associate_case(case_id: str, project: ConsolidationProject) -> None:
    """Fjern sak og tilknyttet generert journal."""
    case = project.find_associate_case(case_id)
    if case is None:
        return
    if case.journal_id:
        project.eliminations = [
            journal
            for journal in project.eliminations
            if journal.journal_id != case.journal_id
        ]
    project.associate_cases = [
        existing
        for existing in project.associate_cases
        if existing.case_id != case_id
    ]


def _best_keyword_match(rows: Iterable[dict[str, object]], *, keywords: tuple[str, ...]) -> dict[str, object] | None:
    best: dict[str, object] | None = None
    best_score = 0.0
    for row in rows:
        search_text = " ".join(
            [
                str(row.get("regnskapslinje", "") or ""),
                str(row.get("source_regnskapslinje", "") or ""),
                str(row.get("source_text", "") or ""),
            ]
        )
        norm = _normalize_text(search_text)
        if not norm:
            continue
        score = 0.0
        for keyword in keywords:
            if keyword in norm:
                score = max(score, 0.75 + (0.05 * len(keyword.split())))
        if score <= 0:
            continue
        score = min(score, 0.95)
        source_confidence = _safe_float(row.get("confidence"))
        if source_confidence > 0:
            score = min(0.99, score + (source_confidence * 0.05))
        if best is None or score > best_score:
            best = dict(row)
            best_score = score
            best["_match_confidence"] = score
    return best


def suggest_associate_fields_from_line_basis(
    line_basis_df: pd.DataFrame,
    *,
    ownership_pct: float,
) -> list[AssociateFieldSuggestion]:
    """Bygg feltforslag til EK-arbeidspapiret fra linjegrunnlag eller PDF-forslag."""
    if line_basis_df is None or line_basis_df.empty:
        return []

    work = line_basis_df.copy()
    rows = [row._asdict() if hasattr(row, "_asdict") else dict(row) for row in work.to_dict(orient="records")]
    ownership_factor = _safe_float(ownership_pct) / 100.0

    suggestion_specs = [
        (
            "share_of_result",
            "Andel resultat",
            ("resultat etter skatt", "arets resultat", "årsresultat", "arsresultat"),
            False,
        ),
        (
            "share_of_other_equity",
            "Andre EK-bevegelser",
            ("annen egenkapital", "ovrig totalresultat", "øvrig totalresultat", "andre inntekter og kostnader"),
            False,
        ),
        (
            "dividends",
            "Utbytte",
            ("utbytte", "dividend"),
            True,
        ),
    ]

    suggestions: list[AssociateFieldSuggestion] = []
    for field_name, field_label, keywords, use_abs in suggestion_specs:
        best = _best_keyword_match(rows, keywords=keywords)
        if best is None:
            continue
        raw_amount = _safe_float(best.get("ub"))
        share_amount = raw_amount * ownership_factor
        if use_abs:
            share_amount = abs(share_amount)
        suggestions.append(
            AssociateFieldSuggestion(
                field_name=field_name,
                field_label=field_label,
                source_label=str(
                    best.get("source_regnskapslinje")
                    or best.get("regnskapslinje")
                    or best.get("source_text")
                    or ""
                ),
                raw_amount=raw_amount,
                share_amount=share_amount,
                confidence=round(_safe_float(best.get("_match_confidence")), 3),
                source_page=int(best["source_page"]) if pd.notna(best.get("source_page")) else None,
                source_text=str(best.get("source_text", "") or ""),
            )
        )

    return suggestions
